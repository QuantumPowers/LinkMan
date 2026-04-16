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
        """
        建立连接
        
        Args:
            server_host: 服务器主机名或IP
            server_port: 服务器端口
            ssl_context: SSL上下文，None表示不使用TLS
        """
        pass
    
    @abstractmethod
    async def read(self, size: int) -> bytes:
        """
        读取数据
        
        Args:
            size: 读取大小
            
        Returns:
            读取到的数据
        """
        pass
    
    @abstractmethod
    async def write(self, data: bytes) -> None:
        """
        写入数据
        
        Args:
            data: 要写入的数据
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        关闭连接
        """
        pass
    
    @abstractmethod
    def needs_drain(self) -> bool:
        """
        是否需要调用drain()
        
        Returns:
            bool: 是否需要drain
        """
        pass


class TcpConnectionAdapter(ConnectionAdapter):
    """
    TCP连接适配器
    """
    
    def __init__(self):
        """
        初始化TCP连接适配器
        """
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
    
    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        """
        建立TCP连接
        
        Args:
            server_host: 服务器主机名或IP
            server_port: 服务器端口
            ssl_context: SSL上下文，None表示不使用TLS
        """
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(server_host, server_port, ssl=ssl_context),
            timeout=30,
        )
    
    async def read(self, size: int) -> bytes:
        """
        从TCP连接读取数据
        
        Args:
            size: 读取大小
            
        Returns:
            读取到的数据
        """
        if self._reader is None:
            raise RuntimeError("Not connected")
        return await self._reader.read(size)
    
    async def write(self, data: bytes) -> None:
        """
        向TCP连接写入数据
        
        Args:
            data: 要写入的数据
        """
        if self._writer is None:
            raise RuntimeError("Not connected")
        self._writer.write(data)
        await self._writer.drain()
    
    async def close(self) -> None:
        """
        关闭TCP连接
        """
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
    
    def needs_drain(self) -> bool:
        """
        TCP连接需要drain
        
        Returns:
            bool: True
        """
        return True


class WebSocketConnectionAdapter(ConnectionAdapter):
    """
    WebSocket连接适配器
    """
    
    def __init__(self, path: str = "/linkman"):
        """
        初始化WebSocket连接适配器
        
        Args:
            path: WebSocket路径
        """
        self._path = path
        self._websocket = None
        self._session = None
    
    async def connect(self, server_host: str, server_port: int, ssl_context: Optional[ssl_module.SSLContext]) -> None:
        """
        建立WebSocket连接
        
        Args:
            server_host: 服务器主机名或IP
            server_port: 服务器端口
            ssl_context: SSL上下文，None表示不使用TLS
        """
        import aiohttp
        
        # WebSocket使用端口+1
        websocket_port = server_port + 1
        scheme = "wss" if ssl_context else "ws"
        ws_url = f"{scheme}://{server_host}:{websocket_port}{self._path}"
        
        self._session = aiohttp.ClientSession()
        self._websocket = await asyncio.wait_for(
            self._session.ws_connect(ws_url, ssl=ssl_context, timeout=30),
            timeout=30,
        )
    
    async def read(self, size: int) -> bytes:
        """
        从WebSocket连接读取数据
        
        Args:
            size: 读取大小（WebSocket忽略此参数）
            
        Returns:
            读取到的数据
        """
        if self._websocket is None:
            raise RuntimeError("Not connected")
        
        while True:
            msg = await self._websocket.receive()
            if msg.type == self._websocket.MSG_BINARY:
                return msg.data
            elif msg.type in (self._websocket.MSG_CLOSED, self._websocket.MSG_ERROR):
                raise RuntimeError("WebSocket connection closed")
    
    async def write(self, data: bytes) -> None:
        """
        向WebSocket连接写入数据
        
        Args:
            data: 要写入的数据
        """
        if self._websocket is None:
            raise RuntimeError("Not connected")
        await self._websocket.send_bytes(data)
    
    async def close(self) -> None:
        """
        关闭WebSocket连接
        """
        if self._websocket:
            await self._websocket.close()
        if self._session:
            await self._session.close()
    
    def needs_drain(self) -> bool:
        """
        WebSocket连接不需要drain
        
        Returns:
            bool: False
        """
        return False