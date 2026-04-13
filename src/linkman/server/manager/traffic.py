"""
Traffic management and accounting.

Provides:
- Traffic tracking per device/client
- Quota management
- Traffic warnings
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from linkman.shared.utils.logger import get_logger

logger = get_logger("server.traffic")


@dataclass
class TrafficStats:
    """Traffic statistics for a period."""

    bytes_sent: int = 0
    bytes_received: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    @property
    def total_bytes(self) -> int:
        """Get total bytes."""
        return self.bytes_sent + self.bytes_received

    @property
    def total_mb(self) -> float:
        """Get total MB."""
        return self.total_bytes / (1024 * 1024)

    @property
    def total_gb(self) -> float:
        """Get total GB."""
        return self.total_bytes / (1024 * 1024 * 1024)

    def add(self, sent: int, received: int) -> None:
        """Add traffic."""
        self.bytes_sent += sent
        self.bytes_received += received

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "total_bytes": self.total_bytes,
            "total_mb": round(self.total_mb, 2),
            "total_gb": round(self.total_gb, 3),
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass
class TrafficWarning:
    """Traffic warning configuration."""

    threshold_mb: int
    current_mb: float
    timestamp: float = field(default_factory=time.time)
    notified: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "threshold_mb": self.threshold_mb,
            "current_mb": round(self.current_mb, 2),
            "timestamp": self.timestamp,
            "notified": self.notified,
        }


class TrafficManager:
    """
    Manages traffic accounting and quotas.

    Features:
    - Per-client traffic tracking
    - Global traffic tracking
    - Quota enforcement
    - Traffic warnings
    """

    CLEANUP_INTERVAL = 3600
    STATS_RETENTION = 86400 * 30

    def __init__(
        self,
        enabled: bool = True,
        limit_mb: int = 0,
        warning_threshold_mb: int = 1000,
        reset_day: int = 1,
    ):
        """
        Initialize traffic manager.

        Args:
            enabled: Whether traffic tracking is enabled
            limit_mb: Monthly traffic limit in MB (0 = unlimited)
            warning_threshold_mb: Warning threshold in MB
            reset_day: Day of month to reset counters
        """
        self._enabled = enabled
        self._limit_mb = limit_mb
        self._warning_threshold_mb = warning_threshold_mb
        self._reset_day = reset_day

        self._client_stats: dict[str, TrafficStats] = defaultdict(TrafficStats)
        self._global_stats = TrafficStats()
        self._warnings: dict[str, TrafficWarning] = {}
        self._warning_callbacks: list = []
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the traffic manager."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Traffic manager started (limit: {self._limit_mb}MB)")

    async def stop(self) -> None:
        """Stop the traffic manager."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Traffic manager stopped")

    @property
    def global_stats(self) -> TrafficStats:
        """Get global traffic statistics."""
        return self._global_stats

    @property
    def total_mb(self) -> float:
        """Get total traffic in MB."""
        return self._global_stats.total_mb

    @property
    def remaining_mb(self) -> float:
        """Get remaining traffic in MB."""
        if self._limit_mb == 0:
            return float("inf")
        return max(0, self._limit_mb - self._global_stats.total_mb)

    def add_warning_callback(self, callback) -> None:
        """Add a callback for traffic warnings."""
        self._warning_callbacks.append(callback)

    async def record_transfer(
        self,
        client_id: str,
        sent: int,
        received: int,
    ) -> None:
        """
        Record traffic transfer.

        Args:
            client_id: Client identifier
            sent: Bytes sent
            received: Bytes received
        """
        if not self._enabled:
            return

        self._client_stats[client_id].add(sent, received)
        self._global_stats.add(sent, received)

        await self._check_warnings(client_id)

    async def check_quota(self, client_id: str) -> bool:
        """
        Check if client has quota remaining.

        Args:
            client_id: Client identifier

        Returns:
            True if quota available
        """
        if not self._enabled or self._limit_mb == 0:
            return True

        return self._global_stats.total_mb < self._limit_mb

    def get_client_stats(self, client_id: str) -> TrafficStats:
        """Get statistics for a client."""
        return self._client_stats.get(client_id, TrafficStats())

    def get_all_client_stats(self) -> dict[str, TrafficStats]:
        """Get statistics for all clients."""
        return dict(self._client_stats)

    def get_top_clients(self, limit: int = 10) -> list[tuple[str, TrafficStats]]:
        """Get top clients by traffic."""
        sorted_clients = sorted(
            self._client_stats.items(),
            key=lambda x: x[1].total_bytes,
            reverse=True,
        )
        return sorted_clients[:limit]

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._client_stats.clear()
        self._global_stats = TrafficStats()
        self._warnings.clear()
        logger.info("Traffic statistics reset")

    def check_reset_needed(self) -> bool:
        """Check if monthly reset is needed."""
        now = datetime.now()
        if now.day == self._reset_day:
            reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if self._global_stats.start_time < reset_time.timestamp():
                return True
        return False

    def get_stats(self) -> dict:
        """Get traffic statistics."""
        return {
            "enabled": self._enabled,
            "total_mb": round(self._global_stats.total_mb, 2),
            "total_gb": round(self._global_stats.total_gb, 3),
            "limit_mb": self._limit_mb,
            "remaining_mb": round(self.remaining_mb, 2),
            "client_count": len(self._client_stats),
            "warnings": len(self._warnings),
        }

    async def _check_warnings(self, client_id: str) -> None:
        """Check and generate warnings."""
        current_mb = self._global_stats.total_mb

        if current_mb >= self._warning_threshold_mb:
            warning = TrafficWarning(
                threshold_mb=self._warning_threshold_mb,
                current_mb=current_mb,
            )

            existing = self._warnings.get(client_id)
            if existing and existing.notified:
                return

            self._warnings[client_id] = warning

            for callback in self._warning_callbacks:
                try:
                    await callback(warning)
                except Exception as e:
                    logger.error(f"Warning callback error: {e}")

            warning.notified = True
            logger.warning(f"Traffic warning: {current_mb:.2f}MB used")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)

                if self.check_reset_needed():
                    self.reset_stats()

                self._cleanup_old_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def _cleanup_old_stats(self) -> None:
        """Clean up old statistics."""
        cutoff = time.time() - self.STATS_RETENTION
        old_clients = [
            client_id
            for client_id, stats in self._client_stats.items()
            if stats.end_time and stats.end_time < cutoff
        ]

        for client_id in old_clients:
            del self._client_stats[client_id]

        if old_clients:
            logger.debug(f"Cleaned up {len(old_clients)} old client stats")

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration dictionary."""
        return cls(
            enabled=config.get("enabled", True),
            limit_mb=config.get("limit_mb", 0),
            warning_threshold_mb=config.get("warning_threshold_mb", 1000),
            reset_day=config.get("reset_day", 1),
        )
