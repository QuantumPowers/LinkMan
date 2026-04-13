"""
Connection handler for managing client connections.

Provides:
- Connection lifecycle management
- Access control
- Traffic tracking
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from linkman.shared.crypto.aead import AEADType
from linkman.shared.protocol.types import Address, ReplyCode
from linkman.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from linkman.server.core.protocol import ServerProtocol
    from linkman.server.core.session import SessionManager
    from linkman.server.manager.auth import AuthManager
    from linkman.server.manager.device import DeviceManager
    from linkman.server.manager.traffic import TrafficManager

logger = get_logger("server.handler")


class ConnectionHandler:
    """
    Handles client connections with access control and traffic tracking.

    Integrates with:
    - AuthManager: User authentication
    - DeviceManager: Device registration and limits
    - TrafficManager: Traffic accounting
    - SessionManager: Session tracking
    """

    def __init__(
        self,
        key: bytes,
        cipher_type: AEADType = AEADType.AES_256_GCM,
        auth_manager: "AuthManager | None" = None,
        device_manager: "DeviceManager | None" = None,
        traffic_manager: "TrafficManager | None" = None,
        session_manager: "SessionManager | None" = None,
        max_connections: int = 1024,
    ):
        """
        Initialize connection handler.

        Args:
            key: Server encryption key
            cipher_type: AEAD cipher type
            auth_manager: Optional authentication manager
            device_manager: Optional device manager
            traffic_manager: Optional traffic manager
            session_manager: Optional session manager
            max_connections: Maximum concurrent connections
        """
        self._key = key
        self._cipher_type = cipher_type
        self._auth_manager = auth_manager
        self._device_manager = device_manager
        self._traffic_manager = traffic_manager
        self._session_manager = session_manager
        self._max_connections = max_connections

        self._active_connections: set[ServerProtocol] = set()
        self._connection_count = 0
        self._on_connection_change: Callable[[int], None] | None = None

    @property
    def key(self) -> bytes:
        """Get server key."""
        return self._key

    @property
    def cipher_type(self) -> AEADType:
        """Get cipher type."""
        return self._cipher_type

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return len(self._active_connections)

    @property
    def total_connections(self) -> int:
        """Get total connection count."""
        return self._connection_count

    def set_connection_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for connection count changes."""
        self._on_connection_change = callback

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle a new connection.

        Args:
            reader: Stream reader
            writer: Stream writer
        """
        if len(self._active_connections) >= self._max_connections:
            logger.warning(f"Max connections reached: {self._max_connections}")
            writer.close()
            await writer.wait_closed()
            return

        from linkman.server.core.protocol import ServerProtocol

        protocol = ServerProtocol(reader, writer, self)
        self._active_connections.add(protocol)
        self._connection_count += 1

        if self._on_connection_change:
            self._on_connection_change(len(self._active_connections))

        try:
            await protocol.handle()
        finally:
            self._active_connections.discard(protocol)
            if self._on_connection_change:
                self._on_connection_change(len(self._active_connections))

    async def check_access(self, client_addr: str, target: Address) -> bool:
        """
        Check if client can access target.

        Args:
            client_addr: Client address string
            target: Target address

        Returns:
            True if access allowed
        """
        if self._auth_manager:
            if not await self._auth_manager.check_access(client_addr, target):
                return False

        if self._traffic_manager:
            if not await self._traffic_manager.check_quota(client_addr):
                logger.warning(f"Traffic quota exceeded for {client_addr}")
                return False

        return True

    async def on_data_transfer(
        self,
        protocol: "ServerProtocol",
        sent: int,
        received: int,
    ) -> None:
        """
        Called when data is transferred.

        Args:
            protocol: Protocol instance
            sent: Bytes sent to target
            received: Bytes received from target
        """
        if self._traffic_manager:
            await self._traffic_manager.record_transfer(
                protocol.client_address,
                sent,
                received,
            )

    async def on_disconnect(self, protocol: "ServerProtocol") -> None:
        """
        Called when a connection disconnects.

        Args:
            protocol: Protocol instance
        """
        if self._session_manager:
            await self._session_manager.end_session(protocol.client_address)

    def get_stats(self) -> dict:
        """Get handler statistics."""
        return {
            "active_connections": len(self._active_connections),
            "total_connections": self._connection_count,
            "max_connections": self._max_connections,
        }
