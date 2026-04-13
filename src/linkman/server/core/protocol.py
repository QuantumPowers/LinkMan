"""
Server protocol implementation for Shadowsocks 2022.

Handles:
- TCP connections
- Protocol handshake
- Data relay
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from linkman.shared.crypto.aead import AEADCipher, AEADType
from linkman.shared.crypto.keys import KeyManager
from linkman.shared.protocol.types import (
    Address,
    Command,
    ProtocolError,
    ReplyCode,
    Request,
    Response,
)
from linkman.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from linkman.server.core.handler import ConnectionHandler

logger = get_logger("server.protocol")


class ServerProtocol:
    """
    Server-side protocol handler for Shadowsocks 2022.

    Protocol flow:
    1. Receive salt from client
    2. Initialize cipher with client salt
    3. Decrypt and parse request
    4. Establish connection to target
    5. Relay data bidirectionally
    """

    HANDSHAKE_TIMEOUT = 30
    BUFFER_SIZE = 65536

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handler: "ConnectionHandler",
    ):
        """
        Initialize server protocol.

        Args:
            reader: Stream reader from client connection
            writer: Stream writer for client connection
            handler: Connection handler for callbacks
        """
        self._reader = reader
        self._writer = writer
        self._handler = handler

        self._cipher: AEADCipher | None = None
        self._target_reader: asyncio.StreamReader | None = None
        self._target_writer: asyncio.StreamWriter | None = None
        self._client_addr: str = ""
        self._target_addr: str = ""
        self._start_time = time.time()
        self._bytes_sent = 0
        self._bytes_received = 0
        self._is_closed = False

    @property
    def client_address(self) -> str:
        """Get client address string."""
        return self._client_addr

    @property
    def target_address(self) -> str:
        """Get target address string."""
        return self._target_addr

    @property
    def duration(self) -> float:
        """Get connection duration in seconds."""
        return time.time() - self._start_time

    @property
    def bytes_sent(self) -> int:
        """Get bytes sent to target."""
        return self._bytes_sent

    @property
    def bytes_received(self) -> int:
        """Get bytes received from target."""
        return self._bytes_received

    async def handle(self) -> None:
        """Handle the complete connection lifecycle."""
        try:
            peername = self._writer.get_extra_info("peername")
            self._client_addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"
            logger.info(f"New connection from {self._client_addr}")

            await self._handshake()

            await self._handle_request()

            await self._relay()

        except asyncio.TimeoutError:
            logger.warning(f"Connection timeout from {self._client_addr}")
        except ProtocolError as e:
            logger.error(f"Protocol error from {self._client_addr}: {e}")
            await self._send_error_response(e.reply_code or ReplyCode.GENERAL_FAILURE)
        except Exception as e:
            logger.exception(f"Error handling connection from {self._client_addr}: {e}")
        finally:
            await self.close()

    async def _handshake(self) -> None:
        """Perform protocol handshake."""
        salt = await asyncio.wait_for(
            self._reader.read(16),
            timeout=self.HANDSHAKE_TIMEOUT,
        )

        if len(salt) != 16:
            raise ProtocolError("Invalid salt length")

        cipher_type = self._handler.cipher_type
        self._cipher = AEADCipher(cipher_type, self._handler.key, salt)

        logger.debug(f"Handshake completed with {self._client_addr}")

    async def _handle_request(self) -> None:
        """Handle client request."""
        if self._cipher is None:
            raise ProtocolError("Cipher not initialized")

        request_data = await self._read_encrypted()

        request = Request.from_bytes(request_data)

        if request.command == Command.CONNECT:
            await self._handle_connect(request.address)
        elif request.command == Command.UDP_ASSOCIATE:
            raise ProtocolError("UDP not supported yet", ReplyCode.COMMAND_NOT_SUPPORTED)
        else:
            raise ProtocolError(f"Unknown command: {request.command}", ReplyCode.COMMAND_NOT_SUPPORTED)

    async def _handle_connect(self, address: Address) -> None:
        """Handle CONNECT command."""
        self._target_addr = str(address)
        logger.info(f"Connect request: {self._client_addr} -> {self._target_addr}")

        if not await self._handler.check_access(self._client_addr, address):
            raise ProtocolError("Access denied", ReplyCode.CONNECTION_NOT_ALLOWED)

        try:
            self._target_reader, self._target_writer = await asyncio.wait_for(
                asyncio.open_connection(address.host, address.port),
                timeout=10,
            )

            response = Response.success()
            await self._write_encrypted(response.to_bytes())

            logger.info(f"Connected: {self._client_addr} -> {self._target_addr}")

        except asyncio.TimeoutError:
            raise ProtocolError("Connection timeout", ReplyCode.TTL_EXPIRED)
        except OSError as e:
            logger.error(f"Failed to connect to {self._target_addr}: {e}")
            raise ProtocolError(str(e), ReplyCode.HOST_UNREACHABLE)

    async def _relay(self) -> None:
        """Relay data between client and target."""
        if self._target_reader is None or self._target_writer is None:
            return

        tasks = [
            asyncio.create_task(self._relay_upstream()),
            asyncio.create_task(self._relay_downstream()),
        ]

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _relay_upstream(self) -> None:
        """Relay data from client to target."""
        if self._cipher is None or self._target_writer is None:
            return

        try:
            while not self._is_closed:
                data = await self._read_encrypted()
                if not data:
                    break

                self._target_writer.write(data)
                await self._target_writer.drain()
                self._bytes_sent += len(data)

                await self._handler.on_data_transfer(self, len(data), 0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Upstream relay error: {e}")

    async def _relay_downstream(self) -> None:
        """Relay data from target to client."""
        if self._cipher is None or self._target_reader is None:
            return

        try:
            while not self._is_closed:
                data = await self._target_reader.read(self.BUFFER_SIZE)
                if not data:
                    break

                await self._write_encrypted(data)
                self._bytes_received += len(data)

                await self._handler.on_data_transfer(self, 0, len(data))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Downstream relay error: {e}")

    async def _read_encrypted(self) -> bytes:
        """Read and decrypt data from client."""
        if self._cipher is None:
            raise ProtocolError("Cipher not initialized")

        buffer = b""

        while True:
            chunk = await self._reader.read(self.BUFFER_SIZE)
            if not chunk:
                if buffer:
                    raise ProtocolError("Incomplete packet")
                return b""

            buffer += chunk

            try:
                payload, buffer = self._cipher.decrypt_packet(buffer)
                return payload
            except ValueError:
                continue

    async def _write_encrypted(self, data: bytes) -> None:
        """Encrypt and write data to client."""
        if self._cipher is None:
            raise ProtocolError("Cipher not initialized")

        encrypted = self._cipher.encrypt_packet(data)
        self._writer.write(encrypted)
        await self._writer.drain()

    async def _send_error_response(self, code: ReplyCode) -> None:
        """Send error response to client."""
        if self._cipher is None:
            return

        try:
            response = Response.failure(code)
            await self._write_encrypted(response.to_bytes())
        except Exception:
            pass

    async def close(self) -> None:
        """Close all connections."""
        if self._is_closed:
            return

        self._is_closed = True

        logger.info(
            f"Connection closed: {self._client_addr} -> {self._target_addr} "
            f"(sent: {self._bytes_sent}, recv: {self._bytes_received}, "
            f"duration: {self.duration:.1f}s)"
        )

        if self._target_writer:
            self._target_writer.close()
            try:
                await self._target_writer.wait_closed()
            except Exception:
                pass

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        await self._handler.on_disconnect(self)
