"""
Session management for tracking client connections.

Provides:
- Session creation and tracking
- Session timeout handling
- Session statistics
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Self

from linkman.shared.utils.logger import get_logger

logger = get_logger("server.session")


@dataclass
class Session:
    """Represents a client session."""

    session_id: str
    client_address: str
    device_id: str | None = None
    user_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    bytes_sent: int = 0
    bytes_received: int = 0
    connection_count: int = 0
    last_activity: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Get session duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_bytes(self) -> int:
        """Get total bytes transferred."""
        return self.bytes_sent + self.bytes_received

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.end_time is None

    def update_activity(self, sent: int = 0, received: int = 0) -> None:
        """Update session activity."""
        self.last_activity = time.time()
        self.bytes_sent += sent
        self.bytes_received += received

    def end(self) -> None:
        """End the session."""
        self.end_time = time.time()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "client_address": self.client_address,
            "device_id": self.device_id,
            "user_id": self.user_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "total_bytes": self.total_bytes,
            "connection_count": self.connection_count,
            "last_activity": self.last_activity,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


class SessionManager:
    """
    Manages client sessions.

    Features:
    - Session creation and tracking
    - Automatic cleanup of expired sessions
    - Session statistics
    """

    DEFAULT_TIMEOUT = 3600
    CLEANUP_INTERVAL = 60

    def __init__(
        self,
        session_timeout: int = DEFAULT_TIMEOUT,
        max_sessions: int = 10000,
    ):
        """
        Initialize session manager.

        Args:
            session_timeout: Session timeout in seconds
            max_sessions: Maximum sessions to track
        """
        self._session_timeout = session_timeout
        self._max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self._client_sessions: dict[str, set[str]] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the session manager."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop the session manager."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Session manager stopped")

    def create_session(
        self,
        client_address: str,
        device_id: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        """
        Create a new session.

        Args:
            client_address: Client address string
            device_id: Optional device identifier
            user_id: Optional user identifier
            metadata: Optional session metadata

        Returns:
            Created session
        """
        session_id = str(uuid.uuid4())

        session = Session(
            session_id=session_id,
            client_address=client_address,
            device_id=device_id,
            user_id=user_id,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session

        if client_address not in self._client_sessions:
            self._client_sessions[client_address] = set()
        self._client_sessions[client_address].add(session_id)

        logger.debug(f"Session created: {session_id} for {client_address}")
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def get_client_sessions(self, client_address: str) -> list[Session]:
        """Get all sessions for a client."""
        session_ids = self._client_sessions.get(client_address, set())
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_active_sessions(self) -> list[Session]:
        """Get all active sessions."""
        return [s for s in self._sessions.values() if s.is_active]

    def update_session(
        self,
        session_id: str,
        sent: int = 0,
        received: int = 0,
    ) -> None:
        """Update session activity."""
        session = self._sessions.get(session_id)
        if session:
            session.update_activity(sent, received)

    async def end_session(self, client_address: str) -> None:
        """End all sessions for a client."""
        session_ids = self._client_sessions.get(client_address, set())

        for session_id in session_ids:
            session = self._sessions.get(session_id)
            if session and session.is_active:
                session.end()
                logger.debug(f"Session ended: {session_id}")

    def get_stats(self) -> dict:
        """Get session statistics."""
        active = [s for s in self._sessions.values() if s.is_active]
        total_bytes = sum(s.total_bytes for s in self._sessions.values())

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(active),
            "unique_clients": len(self._client_sessions),
            "total_bytes": total_bytes,
            "max_sessions": self._max_sessions,
        }

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = []

        for session_id, session in self._sessions.items():
            if not session.is_active:
                if session.end_time and (now - session.end_time) > self._session_timeout:
                    expired.append(session_id)
            elif (now - session.last_activity) > self._session_timeout:
                session.end()
                expired.append(session_id)

        for session_id in expired:
            session = self._sessions.pop(session_id, None)
            if session:
                client_sessions = self._client_sessions.get(session.client_address)
                if client_sessions:
                    client_sessions.discard(session_id)
                    if not client_sessions:
                        del self._client_sessions[session.client_address]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired sessions")

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration dictionary."""
        return cls(
            session_timeout=config.get("session_timeout", cls.DEFAULT_TIMEOUT),
            max_sessions=config.get("max_sessions", 10000),
        )
