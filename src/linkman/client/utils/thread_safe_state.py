"""
Thread-safe state management for LinkMan VPN client.

Provides:
- Lock-protected state dictionary
- Callback notifications for state changes
- Safe cross-thread state access between GUI and async threads
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from linkman.shared.utils.logger import get_logger

logger = get_logger("client.thread_safe_state")


class ThreadSafeState:
    """
    Thread-safe state container with change notification.

    Designed to bridge state between the GUI main thread and the
    async event loop thread, ensuring safe concurrent access.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "is_connected": False,
            "status": "idle",
            "bytes_sent": 0,
            "bytes_received": 0,
            "error": None,
            "server_host": "",
            "server_port": 0,
        }
        self._callbacks: list[Callable[[str, Any], None]] = []

    def update(self, key: str, value: Any) -> None:
        with self._lock:
            old_value = self._state.get(key)
            if old_value == value:
                return
            self._state[key] = value

        for callback in self._callbacks:
            try:
                callback(key, value)
            except Exception as e:
                logger.error(f"State callback error for key '{key}': {e}")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def register_callback(self, callback: Callable[[str, Any], None]) -> None:
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[str, Any], None]) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    @property
    def is_connected(self) -> bool:
        return self.get("is_connected", False)

    @property
    def status(self) -> str:
        return self.get("status", "idle")

    @property
    def error(self) -> str | None:
        return self.get("error")

    def reset(self) -> None:
        with self._lock:
            self._state["is_connected"] = False
            self._state["status"] = "idle"
            self._state["bytes_sent"] = 0
            self._state["bytes_received"] = 0
            self._state["error"] = None
