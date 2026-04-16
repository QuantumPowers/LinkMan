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
from linkman.shared.protocol.abstract import ProtocolBase
from linkman.shared.errors import wrap_error, NetworkError, CryptoError
from linkman.shared.utils.logger import get_logger
from linkman.client.core.connection_adapters import ConnectionAdapter, TcpConnectionAdapter, WebSocketConnectionAdapter

if TYPE_CHECKING:
    from linkman.client.proxy.local import LocalProxy

logger = get_logger("client.protocol")


class ClientProtocol(ProtocolBase):
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
    
    # ProtocolBase abstract methods are implemented below

    HANDSHAKE_TIMEOUT = 30
    MIN_BUFFER_SIZE = 8192  # Minimum buffer size (8KB)
    MAX_BUFFER_SIZE = 262144  # Maximum buffer size (256KB)
    DEFAULT_BUFFER_SIZE = 131072  # Default buffer size (128KB)
    BUFFER_ADJUSTMENT_FACTOR = 1.5  # Buffer size adjustment factor
    
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

        # 创建连接适配器
        if websocket_enabled and tls_enabled:
            self._connection_adapter: ConnectionAdapter = WebSocketConnectionAdapter(websocket_path)
        else:
            self._connection_adapter = TcpConnectionAdapter()

        self._cipher: AEADCipher | None = None
        self._target_reader: asyncio.StreamReader | None = None
        self._target_writer: asyncio.StreamWriter | None = None
        self._is_connected = False
        self._is_closed = False
        self._start_time = 0.0
        self._bytes_sent = 0
        self._bytes_received = 0
        self._buffer_size = self.DEFAULT_BUFFER_SIZE  # Current buffer size
        self._last_buffer_adjustment = 0.0  # Time of last buffer adjustment
        self._packet_count = 0  # Number of packets processed

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
                if self._tls_enabled:
                    import ssl
                    ssl_context = ssl.create_default_context()
                    # Don't verify certificate for now (can be configured later)
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    # Set minimum TLS version to TLS 1.2
                    ssl_context.min_version = ssl.TLSVersion.TLSv1_2
                    logger.info("TLS enabled for client connection")

                # 使用连接适配器建立连接
                await self._connection_adapter.connect(server_host, server_port, ssl_context)

                client_salt = secrets.token_bytes(16)
                
                # 发送salt
                await self._connection_adapter.write(client_salt)

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
                    # 关闭连接
                    try:
                        await self._connection_adapter.close()
                    except Exception as close_error:
                        logger.debug(f"Error closing connection: {close_error}")
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

    def _adjust_buffer_size(self, packet_size: int) -> None:
        """
        Adjust buffer size based on packet size and network conditions.
        
        Args:
            packet_size: Size of the current packet
        """
        current_time = time.time()
        
        # Adjust buffer size every 100 packets or 10 seconds
        if self._packet_count % 100 == 0 or current_time - self._last_buffer_adjustment > 10:
            # Only adjust if packet size is significantly different from current buffer size
            if packet_size > self._buffer_size * 0.8:
                # Increase buffer size if packet is close to buffer size
                # Gradual increase to avoid memory spikes
                new_size = min(int(self._buffer_size * 1.2), self.MAX_BUFFER_SIZE)
                if new_size != self._buffer_size:
                    logger.debug(f"Increasing buffer size from {self._buffer_size} to {new_size}")
                    self._buffer_size = new_size
            elif packet_size < self._buffer_size * 0.2 and self._buffer_size > self.MIN_BUFFER_SIZE:
                # Decrease buffer size if packet is much smaller than buffer size
                # Gradual decrease to avoid frequent adjustments
                new_size = max(int(self._buffer_size * 0.8), self.MIN_BUFFER_SIZE)
                if new_size != self._buffer_size:
                    logger.debug(f"Decreasing buffer size from {self._buffer_size} to {new_size}")
                    self._buffer_size = new_size
            
            self._last_buffer_adjustment = current_time

    async def _relay_upstream(self) -> None:
        """Relay data from local to server with optimized performance."""
        if self._cipher is None or self._target_reader is None:
            return

        try:
            total_sent = 0
            while not self._is_closed:
                data = await self._target_reader.read(self._buffer_size)
                if not data:
                    break

                # Adjust buffer size based on packet size
                self._adjust_buffer_size(len(data))
                self._packet_count += 1

                # Optimize: write encrypted data in one go
                await self._write_encrypted(data)
                self._bytes_sent += len(data)
                total_sent += len(data)
                
                # Drain only when we have significant data to write
                if total_sent >= self._buffer_size * 2:
                    # 只有需要drain的连接才调用drain
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
                # 使用连接适配器读取数据
                try:
                    chunk = await self._connection_adapter.read(self._buffer_size)
                    if not chunk:
                        if buffer:
                            logger.debug("Incomplete packet when closing connection")
                        break
                except RuntimeError as e:
                    if "closed" in str(e):
                        if buffer:
                            logger.debug("Incomplete packet when closing connection")
                        break
                    raise

                buffer += chunk
                
                # Process all complete packets in buffer
                while buffer:
                    try:
                        payload, buffer = self._cipher.decrypt_packet(buffer)
                        if payload:
                            # Adjust buffer size based on packet size
                            self._adjust_buffer_size(len(payload))
                            self._packet_count += 1
                            
                            self._target_writer.write(payload)
                            self._bytes_received += len(payload)
                            total_received += len(payload)
                    except ValueError:
                        # Incomplete packet, continue reading
                        break
                
                # Drain only when we have significant data to write
                if total_received >= self._buffer_size * 2:
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

        buffer = b""

        while True:
            try:
                chunk = await self._connection_adapter.read(self._buffer_size)
                if not chunk:
                    if buffer:
                        raise ProtocolError("Incomplete packet")
                    return b""
            except RuntimeError as e:
                if "closed" in str(e):
                    raise ProtocolError("Connection closed")
                raise

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

        # 使用连接适配器写入数据
        await self._connection_adapter.write(encrypted)

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

        # 使用连接适配器关闭连接
        try:
            await self._connection_adapter.close()
        except Exception:
            pass

        if self._target_writer:
            self._target_writer.close()
            try:
                await self._target_writer.wait_closed()
            except Exception:
                pass
