"""
Device management for multi-device support.

Provides:
- Device registration
- Device limits
- Device status tracking
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Self
from enum import Enum

from linkman.shared.utils.logger import get_logger

logger = get_logger("server.device")


class DeviceStatus(Enum):
    """Device connection status."""

    ONLINE = "online"
    OFFLINE = "offline"
    IDLE = "idle"


@dataclass
class Device:
    """Represents a registered device."""

    device_id: str
    name: str
    user_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    status: DeviceStatus = DeviceStatus.OFFLINE
    connection_count: int = 0
    total_bytes: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.status == DeviceStatus.ONLINE

    def update_activity(self, bytes_transferred: int = 0) -> None:
        """Update device activity."""
        self.last_seen = time.time()
        self.total_bytes += bytes_transferred

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "status": self.status.value,
            "connection_count": self.connection_count,
            "total_bytes": self.total_bytes,
            "metadata": self.metadata,
        }


class DeviceManager:
    """
    Manages registered devices.

    Features:
    - Device registration and removal
    - Device limit enforcement
    - Online status tracking
    """

    IDLE_TIMEOUT = 300
    CLEANUP_INTERVAL = 60

    def __init__(
        self,
        max_devices: int = 5,
        allowed_devices: list[str] | None = None,
    ):
        """
        Initialize device manager.

        Args:
            max_devices: Maximum number of devices
            allowed_devices: Optional list of pre-allowed device IDs
        """
        self._max_devices = max_devices
        self._devices: dict[str, Device] = {}
        self._connections: dict[str, int] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

        if allowed_devices:
            for device_id in allowed_devices:
                self._devices[device_id] = Device(
                    device_id=device_id,
                    name=f"Device-{device_id[:8]}",
                )

    async def start(self) -> None:
        """Start the device manager."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Device manager started (max: {self._max_devices})")

    async def stop(self) -> None:
        """Stop the device manager."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Device manager stopped")

    @property
    def device_count(self) -> int:
        """Get total device count."""
        return len(self._devices)

    @property
    def online_count(self) -> int:
        """Get online device count."""
        return sum(1 for d in self._devices.values() if d.is_online)

    def register_device(
        self,
        device_id: str,
        name: str | None = None,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> Device | None:
        """
        Register a new device.

        Args:
            device_id: Unique device identifier
            name: Optional device name
            user_id: Optional user ID
            metadata: Optional metadata

        Returns:
            Created device or None if limit reached
        """
        if device_id in self._devices:
            device = self._devices[device_id]
            device.status = DeviceStatus.ONLINE
            device.update_activity()
            return device

        if len(self._devices) >= self._max_devices:
            logger.warning(f"Device limit reached: {self._max_devices}")
            return None

        device = Device(
            device_id=device_id,
            name=name or f"Device-{device_id[:8]}",
            user_id=user_id,
            metadata=metadata or {},
            status=DeviceStatus.ONLINE,
        )

        self._devices[device_id] = device
        logger.info(f"Device registered: {device_id} ({name})")
        return device

    def unregister_device(self, device_id: str) -> bool:
        """
        Unregister a device.

        Args:
            device_id: Device identifier

        Returns:
            True if device was removed
        """
        if device_id in self._devices:
            del self._devices[device_id]
            logger.info(f"Device unregistered: {device_id}")
            return True
        return False

    def get_device(self, device_id: str) -> Device | None:
        """Get device by ID."""
        return self._devices.get(device_id)

    def get_all_devices(self) -> list[Device]:
        """Get all devices."""
        return list(self._devices.values())

    def get_online_devices(self) -> list[Device]:
        """Get online devices."""
        return [d for d in self._devices.values() if d.is_online]

    def device_connect(self, device_id: str) -> None:
        """Record device connection."""
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ONLINE
            self._devices[device_id].connection_count += 1
            self._connections[device_id] = self._connections.get(device_id, 0) + 1

    def device_disconnect(self, device_id: str) -> None:
        """Record device disconnection."""
        if device_id in self._devices:
            if device_id in self._connections:
                self._connections[device_id] -= 1
                if self._connections[device_id] <= 0:
                    del self._connections[device_id]
                    self._devices[device_id].status = DeviceStatus.IDLE

    def is_device_allowed(self, device_id: str) -> bool:
        """Check if device is allowed to connect."""
        if device_id in self._devices:
            return True
        return len(self._devices) < self._max_devices

    def update_device_activity(
        self,
        device_id: str,
        bytes_transferred: int = 0,
    ) -> None:
        """Update device activity."""
        if device_id in self._devices:
            self._devices[device_id].update_activity(bytes_transferred)

    def get_stats(self) -> dict:
        """Get device statistics."""
        return {
            "total_devices": len(self._devices),
            "online_devices": self.online_count,
            "max_devices": self._max_devices,
            "active_connections": sum(self._connections.values()),
        }

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of idle devices."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                self._update_idle_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def _update_idle_status(self) -> None:
        """Update idle device status."""
        now = time.time()
        for device in self._devices.values():
            if device.status == DeviceStatus.ONLINE:
                if device.device_id not in self._connections:
                    if now - device.last_seen > self.IDLE_TIMEOUT:
                        device.status = DeviceStatus.IDLE

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration dictionary."""
        return cls(
            max_devices=config.get("max_devices", 5),
            allowed_devices=config.get("allowed_devices"),
        )

    @staticmethod
    def generate_device_id(identifier: str) -> str:
        """Generate device ID from identifier."""
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]
