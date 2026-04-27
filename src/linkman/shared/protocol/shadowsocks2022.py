"""
Shadowsocks 2022 protocol implementation.

Provides factory for creating Shadowsocks 2022 protocol instances.
"""

from __future__ import annotations

from linkman.shared.crypto.aead import AEADType
from linkman.shared.protocol.abstract import ProtocolFactory, ProtocolBase, ServerProtocolBase

from linkman.client.core.protocol import ClientProtocol
from linkman.server.core.protocol import ServerProtocol


class Shadowsocks2022Factory(ProtocolFactory):
    """
    Factory for creating Shadowsocks 2022 protocol instances.
    """
    
    def create_client_protocol(self, **kwargs) -> ProtocolBase:
        key = kwargs.get('key')
        cipher_type = kwargs.get('cipher_type', AEADType.AES_256_GCM)
        tls_enabled = kwargs.get('tls_enabled', False)
        websocket_enabled = kwargs.get('websocket_enabled', False)
        websocket_path = kwargs.get('websocket_path', '/linkman')
        connection_pool = kwargs.get('connection_pool', None)

        return ClientProtocol(
            key=key,
            cipher_type=cipher_type,
            tls_enabled=tls_enabled,
            websocket_enabled=websocket_enabled,
            websocket_path=websocket_path,
            connection_pool=connection_pool,
        )
    
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
        return ServerProtocol(reader, writer, handler)


# Register the protocol
from linkman.shared.protocol.manager import protocol_manager
protocol_manager.register_protocol('shadowsocks2022', Shadowsocks2022Factory())
