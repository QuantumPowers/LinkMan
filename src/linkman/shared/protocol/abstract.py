"""
Protocol abstraction layer for LinkMan VPN.

Defines abstract base classes for protocol implementations.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any

from linkman.shared.protocol.types import Address, Request, Response


class ProtocolBase(ABC):
    """
    Abstract base class for VPN protocols.
    
    All protocol implementations must inherit from this class.
    """
    
    @abstractmethod
    async def connect(
        self,
        server_host: str,
        server_port: int,
        target: Address,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Connect to the server.
        
        Args:
            server_host: Server hostname or IP
            server_port: Server port
            target: Target address to connect to
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retry attempts in seconds
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the connection.
        """
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to server.
        """
        pass
    
    @property
    @abstractmethod
    def bytes_sent(self) -> int:
        """
        Get bytes sent.
        """
        pass
    
    @property
    @abstractmethod
    def bytes_received(self) -> int:
        """
        Get bytes received.
        """
        pass


class ServerProtocolBase(ABC):
    """
    Abstract base class for server-side protocol implementations.
    """
    
    @abstractmethod
    async def handle(self) -> None:
        """
        Handle the complete connection lifecycle.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close all connections.
        """
        pass
    
    @property
    @abstractmethod
    def client_address(self) -> str:
        """
        Get client address string.
        """
        pass
    
    @property
    @abstractmethod
    def target_address(self) -> str:
        """
        Get target address string.
        """
        pass
    
    @property
    @abstractmethod
    def bytes_sent(self) -> int:
        """
        Get bytes sent to target.
        """
        pass
    
    @property
    @abstractmethod
    def bytes_received(self) -> int:
        """
        Get bytes received from target.
        """
        pass


class ProtocolFactory(ABC):
    """
    Abstract factory for creating protocol instances.
    """
    
    @abstractmethod
    def create_client_protocol(self, **kwargs) -> ProtocolBase:
        """
        Create a client protocol instance.
        
        Args:
            **kwargs: Protocol-specific arguments
            
        Returns:
            ProtocolBase: Client protocol instance
        """
        pass
    
    @abstractmethod
    def create_server_protocol(self, reader, writer, handler, **kwargs) -> ServerProtocolBase:
        """
        Create a server protocol instance.
        
        Args:
            reader: Stream reader
            writer: Stream writer
            handler: Connection handler
            **kwargs: Protocol-specific arguments
            
        Returns:
            ServerProtocolBase: Server protocol instance
        """
        pass
