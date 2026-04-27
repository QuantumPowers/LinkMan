"""
Local proxy server for handling client connections.

Provides:
- SOCKS5 proxy
- HTTP proxy (optional)
- Connection management
"""

from __future__ import annotations

import asyncio
import socket
import struct
import time
from typing import TYPE_CHECKING, Callable

from linkman.shared.crypto.aead import AEADType
from linkman.shared.crypto.keys import KeyManager
from linkman.shared.protocol.types import Address, AddressType, ReplyCode
from linkman.shared.protocol.manager import protocol_manager
from linkman.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from linkman.client.proxy.modes import ModeManager

logger = get_logger("client.proxy")


class LocalProxy:
    """
    Local SOCKS5 proxy server.

    Accepts connections from local applications and
    forwards them through the LinkMan tunnel.
    """

    BUFFER_SIZE = 65536  # 缓冲区大小（字节）
    HANDSHAKE_TIMEOUT = 30  # 握手超时时间（秒）

    def __init__(
        self,
        key: bytes,
        cipher_type: AEADType = AEADType.AES_256_GCM,
        server_host: str = "",
        server_port: int = 8388,
        mode_manager: "ModeManager | None" = None,
        tls_enabled: bool = False,
        websocket_enabled: bool = False,
        websocket_path: str = "/linkman",
        protocol: str = "shadowsocks2022",
        connection_pool=None,
    ):
        self._key = key
        self._cipher_type = cipher_type
        self._server_host = server_host
        self._server_port = server_port
        self._mode_manager = mode_manager
        self._tls_enabled = tls_enabled
        self._websocket_enabled = websocket_enabled
        self._websocket_path = websocket_path
        self._protocol = protocol
        self._connection_pool = connection_pool

        self._server = None  # 服务器实例
        self._running = False  # 是否正在运行
        self._active_connections: set[asyncio.Task] = set()  # 活跃连接
        self._connection_count = 0  # 总连接数
        self._bytes_sent = 0  # 发送的字节数
        self._bytes_received = 0  # 接收的字节数
        self._start_time = 0.0  # 启动时间
        self._on_stats_update: Callable | None = None  # 统计更新回调

    @property
    def active_connections(self) -> int:
        """Get active connection count."""
        return len(self._active_connections)

    @property
    def total_connections(self) -> int:
        """Get total connection count."""
        return self._connection_count

    @property
    def total_bytes(self) -> tuple[int, int]:
        """Get total bytes (sent, received)."""
        return self._bytes_sent, self._bytes_received

    def set_stats_callback(self, callback: Callable) -> None:
        """Set callback for stats updates."""
        self._on_stats_update = callback

    async def start(self, host: str = "127.0.0.1", port: int = 1080) -> None:
        """
        Start the local proxy server.

        Args:
            host: Local bind address
            port: Local port
        """
        if self._running:
            return

        # Try to kill any process using the port
        import socket
        import subprocess
        import sys
        
        def is_port_in_use(port: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('127.0.0.1', port)) == 0
        
        if is_port_in_use(port):
            logger.warning(f"Port {port} is already in use, attempting to free it...")
            try:
                # Try to kill process using the port (macOS/Linux)
                if sys.platform == 'darwin':  # macOS
                    result = subprocess.run(
                        ['lsof', '-ti', f'tcp:{port}'],
                        capture_output=True,
                        text=True
                    )
                    if result.stdout:
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid:
                                subprocess.run(['kill', '-9', pid], capture_output=True)
                                logger.info(f"Killed process {pid} using port {port}")
                else:  # Linux
                    result = subprocess.run(
                        ['fuser', '-k', f'{port}/tcp'],
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Freed port {port}")
                
                # Wait a bit for the port to be released
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not free port {port}: {e}")

        self._start_time = time.time()
        self._server = await asyncio.start_server(
            self._handle_connection,
            host,
            port,
        )

        self._running = True

        addr = self._server.sockets[0].getsockname()
        logger.info(f"Local proxy listening on {addr[0]}:{addr[1]}")

    async def stop(self) -> None:
        """Stop the local proxy server."""
        if not self._running:
            return

        self._running = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        for task in list(self._active_connections):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info("Local proxy stopped")

    async def run(self) -> None:
        """Run the proxy server."""
        if not self._server:
            raise RuntimeError("Proxy not started")

        async with self._server:
            await self._server.serve_forever()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a new client connection."""
        task = asyncio.current_task()
        self._active_connections.add(task)
        self._connection_count += 1

        client_addr = writer.get_extra_info("peername")
        # Only log new connections at info level to avoid excessive logging
        # logger.info(f"New connection from {client_addr}")

        protocol = None

        try:
            target = await self._socks5_handshake(reader, writer)

            if target is None:
                return

            should_proxy = True
            if self._mode_manager:
                should_proxy = await self._mode_manager.should_proxy(target)

            if should_proxy:
                protocol = protocol_manager.create_client_protocol(
                    self._protocol,
                    key=self._key,
                    cipher_type=self._cipher_type,
                    tls_enabled=self._tls_enabled,
                    websocket_enabled=self._websocket_enabled,
                    websocket_path=self._websocket_path,
                    connection_pool=self._connection_pool,
                )
                await protocol.connect(
                    self._server_host,
                    self._server_port,
                    target,
                    max_retries=3,
                    retry_delay=2.0,
                )
                await protocol.relay(reader, writer)
            else:
                await self._direct_connect(reader, writer, target)

        except asyncio.TimeoutError:
            logger.debug(f"Connection timeout from {client_addr}")
        except Exception as e:
            logger.debug(f"Connection error from {client_addr}: {e}")
        finally:
            self._active_connections.discard(task)

            if protocol:
                self._bytes_sent += protocol.bytes_sent
                self._bytes_received += protocol.bytes_received
                await protocol.close()

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            if self._on_stats_update:
                self._on_stats_update(self.get_stats())

    async def _socks5_handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Address | None:
        """
        Perform SOCKS5 handshake.

        Args:
            reader: Client stream reader
            writer: Client stream writer

        Returns:
            Target address or None if failed
        """
        header = await asyncio.wait_for(
            reader.read(2),
            timeout=self.HANDSHAKE_TIMEOUT,
        )

        if len(header) != 2 or header[0] != 5:
            return None

        nmethods = header[1]
        methods = await asyncio.wait_for(
            reader.read(nmethods),
            timeout=self.HANDSHAKE_TIMEOUT,
        )

        if 0 not in methods:
            writer.write(b"\x05\xff")
            await writer.drain()
            return None

        writer.write(b"\x05\x00")
        await writer.drain()

        request = await asyncio.wait_for(
            reader.read(4),
            timeout=self.HANDSHAKE_TIMEOUT,
        )

        if len(request) != 4 or request[0] != 5 or request[1] != 1:
            return None

        addr_type = request[3]

        if addr_type == AddressType.IPV4:
            addr_bytes = await asyncio.wait_for(
                reader.read(4),
                timeout=self.HANDSHAKE_TIMEOUT,
            )
            host = socket.inet_ntoa(addr_bytes)
        elif addr_type == AddressType.DOMAIN:
            len_byte = await asyncio.wait_for(
                reader.read(1),
                timeout=self.HANDSHAKE_TIMEOUT,
            )
            domain_len = len_byte[0]
            host = (
                await asyncio.wait_for(
                    reader.read(domain_len),
                    timeout=self.HANDSHAKE_TIMEOUT,
                )
            ).decode("idna")
        elif addr_type == AddressType.IPV6:
            addr_bytes = await asyncio.wait_for(
                reader.read(16),
                timeout=self.HANDSHAKE_TIMEOUT,
            )
            host = socket.inet_ntop(socket.AF_INET6, addr_bytes)
        else:
            return None

        port_bytes = await asyncio.wait_for(
            reader.read(2),
            timeout=self.HANDSHAKE_TIMEOUT,
        )
        port = struct.unpack("!H", port_bytes)[0]

        target = Address.from_host_port(host, port)

        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()

        return target

    async def _direct_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        target: Address,
    ) -> None:
        """Direct connection without proxy."""
        target_reader, target_writer = await asyncio.open_connection(
            target.host,
            target.port,
        )

        async def relay(src, dst):
            try:
                while True:
                    data = await src.read(self.BUFFER_SIZE)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass

        await asyncio.gather(
            relay(reader, target_writer),
            relay(target_reader, writer),
        )

        target_writer.close()
        await target_writer.wait_closed()

    def get_stats(self) -> dict:
        """Get proxy statistics."""
        return {
            "active_connections": len(self._active_connections),
            "total_connections": self._connection_count,
            "bytes_sent": self._bytes_sent,
            "bytes_received": self._bytes_received,
            "uptime": time.time() - self._start_time if self._start_time else 0,
        }
