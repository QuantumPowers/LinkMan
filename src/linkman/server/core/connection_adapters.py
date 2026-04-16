from abc import ABC, abstractmethod
import asyncio
from typing import Optional
import ssl as ssl_module


class ServerConnectionAdapter(ABC):
    """
    服务器端连接适配器抽象基类，定义统一的连接接口
    """
    
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
    def get_client_address(self) -> str:
        """
        获取客户端地址
        
        Returns:
            客户端地址字符串
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


class TcpServerConnectionAdapter(ServerConnectionAdapter):
    """
    TCP服务器连接适配器
    """
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        初始化TCP服务器连接适配器
        
        Args:
            reader: 流读取器
            writer: 流写入器
        """
        self._reader = reader
        self._writer = writer
        self._client_addr = ""
        
        # 获取客户端地址
        peername = writer.get_extra_info("peername")
        if peername:
            self._client_addr = f"{peername[0]}:{peername[1]}"
        else:
            self._client_addr = "unknown"
    
    async def read(self, size: int) -> bytes:
        """
        从TCP连接读取数据
        
        Args:
            size: 读取大小
            
        Returns:
            读取到的数据
        """
        return await self._reader.read(size)
    
    async def write(self, data: bytes) -> None:
        """
        向TCP连接写入数据
        
        Args:
            data: 要写入的数据
        """
        self._writer.write(data)
        await self._writer.drain()
    
    async def close(self) -> None:
        """
        关闭TCP连接
        """
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:
            pass
    
    def get_client_address(self) -> str:
        """
        获取客户端地址
        
        Returns:
            客户端地址字符串
        """
        return self._client_addr
    
    def needs_drain(self) -> bool:
        """
        TCP连接需要drain
        
        Returns:
            bool: True
        """
        return True


class WebSocketServerConnectionAdapter(ServerConnectionAdapter):
    """
    WebSocket服务器连接适配器
    """
    
    def __init__(self, ws, client_addr: str):
        """
        初始化WebSocket服务器连接适配器
        
        Args:
            ws: WebSocket连接
            client_addr: 客户端地址
        """
        self._ws = ws
        self._client_addr = client_addr
    
    async def read(self, size: int) -> bytes:
        """
        从WebSocket连接读取数据
        
        Args:
            size: 读取大小（WebSocket忽略此参数）
            
        Returns:
            读取到的数据
        """
        import aiohttp
        
        while True:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                return msg.data
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                raise RuntimeError("WebSocket connection closed")
            else:
                continue
    
    async def write(self, data: bytes) -> None:
        """
        向WebSocket连接写入数据
        
        Args:
            data: 要写入的数据
        """
        await self._ws.send_bytes(data)
    
    async def close(self) -> None:
        """
        关闭WebSocket连接
        """
        try:
            await self._ws.close()
        except Exception:
            pass
    
    def get_client_address(self) -> str:
        """
        获取客户端地址
        
        Returns:
            客户端地址字符串
        """
        return self._client_addr
    
    def needs_drain(self) -> bool:
        """
        WebSocket连接不需要drain
        
        Returns:
            bool: False
        """
        return False