"""
System monitoring and status reporting.

Provides:
- Server status
- Connection monitoring
- Performance metrics
"""

from __future__ import annotations

import asyncio
import platform
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from linkman.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from linkman.server.core.handler import ConnectionHandler
    from linkman.server.core.session import SessionManager
    from linkman.server.manager.device import DeviceManager
    from linkman.server.manager.traffic import TrafficManager

logger = get_logger("server.monitor")


@dataclass
class ServerStatus:
    """Server status information."""

    uptime: float = 0.0
    start_time: float = field(default_factory=time.time)
    connections: int = 0
    total_connections: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0

    @property
    def uptime_str(self) -> str:
        """Get human-readable uptime."""
        uptime = self.uptime
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        return f"{days}d {hours}h {minutes}m"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "uptime": self.uptime,
            "uptime_str": self.uptime_str,
            "start_time": self.start_time,
            "connections": self.connections,
            "total_connections": self.total_connections,
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_percent": round(self.memory_percent, 1),
            "disk_percent": round(self.disk_percent, 1),
        }


def _get_platform() -> str:
    return platform.platform()


def _get_python_version() -> str:
    return platform.python_version()


def _get_hostname() -> str:
    return platform.node()


def _get_architecture() -> str:
    return platform.machine()


@dataclass
class SystemInfo:
    """System information."""

    platform: str = field(default_factory=_get_platform)
    python_version: str = field(default_factory=_get_python_version)
    hostname: str = field(default_factory=_get_hostname)
    architecture: str = field(default_factory=_get_architecture)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "platform": self.platform,
            "python_version": self.python_version,
            "hostname": self.hostname,
            "architecture": self.architecture,
        }


class Monitor:
    """
    System monitor for LinkMan server.

    Features:
    - Server status tracking
    - Resource monitoring
    - Integration with other managers
    """

    UPDATE_INTERVAL = 5

    def __init__(
        self,
        connection_handler: "ConnectionHandler | None" = None,
        session_manager: "SessionManager | None" = None,
        device_manager: "DeviceManager | None" = None,
        traffic_manager: "TrafficManager | None" = None,
    ):
        """
        Initialize monitor.

        Args:
            connection_handler: Connection handler instance
            session_manager: Session manager instance
            device_manager: Device manager instance
            traffic_manager: Traffic manager instance
        """
        self._connection_handler = connection_handler
        self._session_manager = session_manager
        self._device_manager = device_manager
        self._traffic_manager = traffic_manager

        self._status = ServerStatus()
        self._system_info = SystemInfo()
        self._monitor_task: asyncio.Task | None = None
        self._running = False

    @property
    def status(self) -> ServerStatus:
        """Get current status."""
        return self._status

    @property
    def system_info(self) -> SystemInfo:
        """Get system info."""
        return self._system_info

    async def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Monitor started")

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Monitor stopped")

    def get_full_status(self) -> dict:
        """Get complete status report."""
        status = self._status.to_dict()
        status["system"] = self._system_info.to_dict()

        if self._connection_handler:
            status["connections"] = self._connection_handler.get_stats()

        if self._session_manager:
            status["sessions"] = self._session_manager.get_stats()

        if self._device_manager:
            status["devices"] = self._device_manager.get_stats()

        if self._traffic_manager:
            status["traffic"] = self._traffic_manager.get_stats()

        return status

    def get_devices_status(self) -> list[dict]:
        """Get all devices status."""
        if not self._device_manager:
            return []

        devices = self._device_manager.get_all_devices()
        return [d.to_dict() for d in devices]

    def get_traffic_report(self) -> dict:
        """Get traffic report."""
        if not self._traffic_manager:
            return {}

        report = self._traffic_manager.get_stats()
        report["top_clients"] = [
            {"client_id": cid, "stats": stats.to_dict()}
            for cid, stats in self._traffic_manager.get_top_clients(10)
        ]
        return report

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.UPDATE_INTERVAL)
                await self._update_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")

    async def _update_status(self) -> None:
        """Update server status."""
        self._status.uptime = time.time() - self._status.start_time

        if self._connection_handler:
            self._status.connections = self._connection_handler.active_connections
            self._status.total_connections = self._connection_handler.total_connections

        try:
            import psutil

            self._status.cpu_percent = psutil.cpu_percent()
            self._status.memory_percent = psutil.virtual_memory().percent
            self._status.disk_percent = psutil.disk_usage("/").percent
        except ImportError:
            pass

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration."""
        return cls()
