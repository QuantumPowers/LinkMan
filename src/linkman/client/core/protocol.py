"""
Client protocol implementation for Shadowsocks 2022.

Handles:
- Connection to server
- Protocol handshake
- Data relay
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import TYPE_CHECKING

from linkman.shared.crypto.aead import AEADCipher, AEADType
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
    from linkman.client.proxy.local import LocalProxy

logger = get_logger("client.protocol")


class ClientProtocol:
    """
    Client-side protocol handler for Shadowsocks 2022.

    Protocol flow:
    1. Connect to server
    2. Send salt to server
    3. Initialize cipher
    4. Send encrypted request
    5. Receive response
    6. Relay data bidirectionally
    """

    HANDSHAKE_TIMEOUT = 30
    BUFFER_SIZE = 65536

    def __init__(
        self,
        key: bytes,
        cipher_type: AEADType = AEADType.AES_256_GCM,
    ):
        """
        Initialize client protocol.

        Args:
            key: Server encryption key
            cipher_type: AEAD cipher type
        """
        self._key = key
        self._cipher_type = cipher_type

        self._cipher: AEADCipher | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._target_reader: asyncio.StreamReader | None = None
        self._target_writer: asyncio.StreamWriter | None = None
        self._is_connected = False
        self._is_closed = False
        self._start_time = 0.0
        self._bytes_sent = 0
        self._bytes_received = 0

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._is_connected and not self._is_closed

    @property
    def bytes_sent(self) -> int:
        """Get bytes sent."""
        return self._bytes_sent

    @property
    def bytes_received(self) -> int:
        """Get bytes received."""
        return self._bytes_received

    async def connect(
        self,
        server_host: str,
        server_port: int,
        target: Address,
    ) -> None:
        """
        Connect to server and establish tunnel.

        Args:
            server_host: Server hostname or IP
            server_port: Server port
            target: Target address to connect to
        """
        if self._is_connected:
            raise ProtocolError("Already connected")

        self._start_time = time.time()
        logger.info(f"Connecting to {server_host}:{server_port}")

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(server_host, server_port),
            timeout=self.HANDSHAKE_TIMEOUT,
        )

        client_salt = secrets.token_bytes(16)
        self._writer.write(client_salt)
        await self._writer.drain()

        self._cipher = AEADCipher(self._cipher_type, self._key, client_salt)

        request = Request(command=Command.CONNECT, address=target)
        await self._write_encrypted(request.to_bytes())

        response_data = await self._read_encrypted()
        response = Response.__new__(Response)
        response.reply_code = ReplyCode(response_data[0])

        if response.reply_code != ReplyCode.SUCCEEDED:
            raise ProtocolError(
                f"Connection failed: {response.reply_code.name}",
                response.reply_code,
            )

        self._is_connected = True
        logger.info(f"Connected to server, tunnel established to {target}")

    async def relay(
        self,
        local_reader: asyncio.StreamReader,
        local_writer: asyncio.StreamWriter,
    ) -> None:
        """
        Relay data between local and server.

        Args:
            local_reader: Local stream reader
            local_writer: Local stream writer
        """
        if not self._is_connected:
            raise ProtocolError("Not connected")

        self._target_reader = local_reader
        self._target_writer = local_writer

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
        """Relay data from local to server."""
        if self._cipher is None or self._target_reader is None:
            return

        try:
            while not self._is_closed:
                data = await self._target_reader.read(self.BUFFER_SIZE)
                if not data:
                    break

                await self._write_encrypted(data)
                self._bytes_sent += len(data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Upstream relay error: {e}")

    async def _relay_downstream(self) -> None:
        """Relay data from server to local."""
        if self._cipher is None or self._target_writer is None:
            return

        try:
            while not self._is_closed:
                data = await self._read_encrypted()
                if not data:
                    break

                self._target_writer.write(data)
                await self._target_writer.drain()
                self._bytes_received += len(data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Downstream relay error: {e}")

    async def _read_encrypted(self) -> bytes:
        """Read and decrypt data from server."""
        if self._cipher is None or self._reader is None:
            raise ProtocolError("Not connected")

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
        """Encrypt and write data to server."""
        if self._cipher is None or self._writer is None:
            raise ProtocolError("Not connected")

        encrypted = self._cipher.encrypt_packet(data)
        self._writer.write(encrypted)
        await self._writer.drain()

    async def close(self) -> None:
        """Close the connection."""
        if self._is_closed:
            return

        self._is_closed = True
        self._is_connected = False

        duration = time.time() - self._start_time
        logger.info(
            f"Connection closed (sent: {self._bytes_sent}, "
            f"recv: {self._bytes_received}, duration: {duration:.1f}s)"
        )

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        if self._target_writer:
            self._target_writer.close()
            try:
                await self._target_writer.wait_closed()
            except Exception:
                pass
