"""
Protocol manager for LinkMan VPN.

Manages protocol registration and creation.
"""

from __future__ import annotations

from typing import Dict, Type, Optional

from linkman.shared.protocol.abstract import ProtocolBase, ServerProtocolBase, ProtocolFactory


class ProtocolManager:
    """
    Protocol manager for managing protocol implementations.
    
    This class handles the registration and creation of protocol instances.
    """
    
    def __init__(self):
        """
        Initialize protocol manager.
        """
        self._factories: Dict[str, ProtocolFactory] = {}
    
    def register_protocol(self, name: str, factory: ProtocolFactory) -> None:
        """
        Register a protocol factory.
        
        Args:
            name: Protocol name
            factory: Protocol factory instance
        """
        self._factories[name] = factory
    
    def unregister_protocol(self, name: str) -> None:
        """
        Unregister a protocol factory.
        
        Args:
            name: Protocol name
        """
        if name in self._factories:
            del self._factories[name]
    
    def create_client_protocol(self, protocol_name: str, **kwargs) -> ProtocolBase:
        """
        Create a client protocol instance.
        
        Args:
            protocol_name: Protocol name
            **kwargs: Protocol-specific arguments
            
        Returns:
            ProtocolBase: Client protocol instance
            
        Raises:
            ValueError: If protocol is not registered
        """
        if protocol_name not in self._factories:
            raise ValueError(f"Protocol {protocol_name} not registered")
        
        return self._factories[protocol_name].create_client_protocol(**kwargs)
    
    def create_server_protocol(self, protocol_name: str, reader, writer, handler, **kwargs) -> ServerProtocolBase:
        """
        Create a server protocol instance.
        
        Args:
            protocol_name: Protocol name
            reader: Stream reader
            writer: Stream writer
            handler: Connection handler
            **kwargs: Protocol-specific arguments
            
        Returns:
            ServerProtocolBase: Server protocol instance
            
        Raises:
            ValueError: If protocol is not registered
        """
        if protocol_name not in self._factories:
            raise ValueError(f"Protocol {protocol_name} not registered")
        
        return self._factories[protocol_name].create_server_protocol(
            reader, writer, handler, **kwargs
        )
    
    def get_available_protocols(self) -> list[str]:
        """
        Get list of available protocols.
        
        Returns:
            list[str]: List of available protocol names
        """
        return list(self._factories.keys())
    
    def is_protocol_available(self, name: str) -> bool:
        """
        Check if a protocol is available.
        
        Args:
            name: Protocol name
            
        Returns:
            bool: True if protocol is available
        """
        return name in self._factories


# Global protocol manager instance
protocol_manager = ProtocolManager()
