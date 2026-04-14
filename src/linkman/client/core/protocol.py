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
from linkman.shared.errors import wrap_error, NetworkError, CryptoError
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
    BUFFER_SIZE = 131072  # Increased buffer size for better performance

    def __init__(
        self,
        key: bytes,
        cipher_type: AEADType = AEADType.AES_256_GCM,
        tls_enabled: bool = False,
        websocket_enabled: bool = False,
        websocket_path: str = "/linkman",
    ):
        """
        Initialize client protocol.

        Args:
            key: Server encryption key
            cipher_type: AEAD cipher type
            tls_enabled: Whether to use TLS
            websocket_enabled: Whether to use WebSocket
            websocket_path: WebSocket path
        """
        self._key = key
        self._cipher_type = cipher_type
        self._tls_enabled = tls_enabled
        self._websocket_enabled = websocket_enabled
        self._websocket_path = websocket_path

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
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Connect to server and establish tunnel with retry mechanism.

        Args:
            server_host: Server hostname or IP
            server_port: Server port
            target: Target address to connect to
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retry attempts in seconds

        Raises:
            ProtocolError: If connection fails after all retries
        """
        if self._is_connected:
            raise ProtocolError("Already connected")

        self._start_time = time.time()
        
        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to {server_host}:{server_port} (attempt {attempt + 1}/{max_retries})")

                # Create SSL context if TLS is enabled
                ssl_context = None
                if hasattr(self, '_tls_enabled') and self._tls_enabled:
                    import ssl
                    ssl_context = ssl.create_default_context()
                    # Don't verify certificate for now (can be configured later)
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    # Set minimum TLS version to TLS 1.2
                    ssl_context.min_version = ssl.TLSVersion.TLSv1_2
                    logger.info("TLS enabled for client connection")

                # Use WebSocket if enabled
                if hasattr(self, '_websocket_enabled') and self._websocket_enabled:
                    import aiohttp
                    
                    # Create WebSocket connection
                    # WebSocket uses port + 1
                    websocket_port = server_port + 1
                    ws_url = f"{'wss' if self._tls_enabled else 'ws'}://{server_host}:{websocket_port}{self._websocket_path}"
                    logger.info(f"Connecting to WebSocket at {ws_url}")
                    
                    session = aiohttp.ClientSession()
                    try:
                        self._websocket = await asyncio.wait_for(
                            session.ws_connect(
                                ws_url,
                                ssl=ssl_context,
                                timeout=self.HANDSHAKE_TIMEOUT,
                            ),
                            timeout=self.HANDSHAKE_TIMEOUT,
                        )
                        logger.info("WebSocket connection established")
                    except Exception as e:
                        await session.close()
                        raise e
                else:
                    # Use regular TCP connection
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(server_host, server_port, ssl=ssl_context),
                        timeout=self.HANDSHAKE_TIMEOUT,
                    )

                client_salt = secrets.token_bytes(16)
                
                # Send salt based on connection type
                if hasattr(self, '_websocket_enabled') and self._websocket_enabled:
                    await self._websocket.send_bytes(client_salt)
                else:
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
                return
                
            except Exception as e:
                wrapped_error = wrap_error(e)
                last_error = wrapped_error
                logger.warning(f"Connection attempt {attempt + 1} failed: {wrapped_error}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    # Close any partially established connection
                    if self._writer:
                        try:
                            self._writer.close()
                            await self._writer.wait_closed()
                        except Exception as close_error:
                            logger.debug(f"Error closing connection: {close_error}")
                    self._reader = None
                    self._writer = None
                    self._cipher = None
                else:
                    break

        raise ProtocolError(f"Failed to connect after {max_retries} attempts: {last_error}", cause=last_error)

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
        """Relay data from local to server with optimized performance."""
        if self._cipher is None or self._target_reader is None:
            return

        try:
            total_sent = 0
            while not self._is_closed:
                data = await self._target_reader.read(self.BUFFER_SIZE)
                if not data:
                    break

                # Optimize: write encrypted data in one go
                await self._write_encrypted(data)
                self._bytes_sent += len(data)
                total_sent += len(data)
                
                # Drain only when we have significant data to write
                if total_sent >= self.BUFFER_SIZE * 2:
                    # For WebSocket, no need to drain
                    if not (hasattr(self, '_websocket_enabled') and self._websocket_enabled):
                        if self._writer:
                            await self._writer.drain()
                    total_sent = 0

        except asyncio.CancelledError:
            pass
        except Exception as e:
            wrapped_error = wrap_error(e)
            logger.debug(f"Upstream relay error: {wrapped_error}")

    async def _relay_downstream(self) -> None:
        """Relay data from server to local with optimized performance."""
        if self._cipher is None or self._target_writer is None:
            return

        try:
            buffer = b""
            total_received = 0
            while not self._is_closed:
                # Handle WebSocket connection
                if hasattr(self, '_websocket_enabled') and self._websocket_enabled and hasattr(self, '_websocket'):
                    msg = await self._websocket.receive()
                    if msg.type == self._websocket.MSG_BINARY:
                        chunk = msg.data
                    elif msg.type in (self._websocket.MSG_CLOSED, self._websocket.MSG_ERROR):
                        if buffer:
                            logger.debug("Incomplete packet when closing connection")
                        break
                    else:
                        continue
                else:
                    # Handle regular TCP connection
                    if self._reader is None:
                        break
                    chunk = await self._reader.read(self.BUFFER_SIZE)
                    if not chunk:
                        if buffer:
                            logger.debug("Incomplete packet when closing connection")
                        break

                buffer += chunk
                
                # Process all complete packets in buffer
                while buffer:
                    try:
                        payload, buffer = self._cipher.decrypt_packet(buffer)
                        if payload:
                            self._target_writer.write(payload)
                            self._bytes_received += len(payload)
                            total_received += len(payload)
                    except ValueError:
                        # Incomplete packet, continue reading
                        break
                
                # Drain only when we have significant data to write
                if total_received >= self.BUFFER_SIZE * 2:
                    await self._target_writer.drain()
                    total_received = 0

        except asyncio.CancelledError:
            pass
        except Exception as e:
            wrapped_error = wrap_error(e)
            logger.debug(f"Downstream relay error: {wrapped_error}")

    async def _read_encrypted(self) -> bytes:
        """Read and decrypt data from server."""
        if self._cipher is None:
            raise ProtocolError("Not connected")

        # Handle WebSocket connection
        if hasattr(self, '_websocket_enabled') and self._websocket_enabled and hasattr(self, '_websocket'):
            while True:
                msg = await self._websocket.receive()
                if msg.type == self._websocket.MSG_BINARY:
                    try:
                        payload, _ = self._cipher.decrypt_packet(msg.data)
                        return payload
                    except ValueError:
                        continue
                elif msg.type in (self._websocket.MSG_CLOSED, self._websocket.MSG_ERROR):
                    raise ProtocolError("WebSocket connection closed")
        else:
            # Handle regular TCP connection
            if self._reader is None:
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
        if self._cipher is None:
            raise ProtocolError("Not connected")

        encrypted = self._cipher.encrypt_packet(data)

        # Handle WebSocket connection
        if hasattr(self, '_websocket_enabled') and self._websocket_enabled and hasattr(self, '_websocket'):
            await self._websocket.send_bytes(encrypted)
        else:
            # Handle regular TCP connection
            if self._writer is None:
                raise ProtocolError("Not connected")
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

        # Close WebSocket connection
        if hasattr(self, '_websocket_enabled') and self._websocket_enabled and hasattr(self, '_websocket'):
            await self._websocket.close()
        else:
            # Close regular TCP connection
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
