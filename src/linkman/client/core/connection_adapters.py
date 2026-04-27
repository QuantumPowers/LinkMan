from abc import ABC, abstractmethod
import asyncio
from typing import Optional
import ssl as ssl_module


class ConnectionAdapter(ABC):
    """
    抽象连接适配器基类，定义统一的连接接口
    """

    @abstractmethod
    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        pass

    @abstractmethod
    async def read(self, size: int) -> bytes:
        pass

    @abstractmethod
    async def write(self, data: bytes) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    def needs_drain(self) -> bool:
        pass


class TcpConnectionAdapter(ConnectionAdapter):

    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(server_host, server_port, ssl=ssl_context),
            timeout=30,
        )

    async def read(self, size: int) -> bytes:
        if self._reader is None:
            raise RuntimeError("Not connected")
        return await self._reader.read(size)

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("Not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    def needs_drain(self) -> bool:
        return True


class WebSocketConnectionAdapter(ConnectionAdapter):

    def __init__(self, path: str = "/linkman"):
        self._path = path
        self._websocket = None
        self._session = None

    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        import aiohttp

        websocket_port = server_port + 2
        scheme = "wss" if ssl_context else "ws"
        ws_url = f"{scheme}://{server_host}:{websocket_port}{self._path}"

        self._session = aiohttp.ClientSession()
        self._websocket = await asyncio.wait_for(
            self._session.ws_connect(ws_url, ssl=ssl_context, timeout=30),
            timeout=30,
        )

    async def read(self, size: int) -> bytes:
        if self._websocket is None:
            raise RuntimeError("Not connected")

        while True:
            msg = await self._websocket.receive()
            if msg.type == self._websocket.MSG_BINARY:
                return msg.data
            elif msg.type in (self._websocket.MSG_CLOSED, self._websocket.MSG_ERROR):
                raise RuntimeError("WebSocket connection closed")

    async def write(self, data: bytes) -> None:
        if self._websocket is None:
            raise RuntimeError("Not connected")
        await self._websocket.send_bytes(data)

    async def close(self) -> None:
        if self._websocket:
            await self._websocket.close()
        if self._session:
            await self._session.close()

    def needs_drain(self) -> bool:
        return False


class PooledTcpConnectionAdapter(ConnectionAdapter):
    """TCP adapter backed by a connection pool for server-side connection reuse."""

    def __init__(self, pool):
        self._pool = pool
        self._connection = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        conn = await self._pool.get_connection()
        self._connection = conn
        self._reader = conn.reader
        self._writer = conn.writer

    async def read(self, size: int) -> bytes:
        if self._reader is None:
            raise RuntimeError("Not connected")
        return await self._reader.read(size)

    async def write(self, data: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("Not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        if self._connection is not None:
            await self._pool.return_connection(self._connection)
            self._connection = None
            self._reader = None
            self._writer = None

    def needs_drain(self) -> bool:
        return True