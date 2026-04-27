"""
Unified async event loop manager for LinkMan VPN client.

Provides:
- Single event loop management in a dedicated thread
- Thread-safe coroutine scheduling
- Client lifecycle management
- Resource cleanup coordination
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from linkman.shared.utils.logger import get_logger

logger = get_logger("client.asyncio_manager")


class AsyncioManager:
    """
    Unified async event loop manager for the client.

    Ensures:
    - Only one event loop runs at a time
    - Proper async lifecycle management
    - Thread-safe async task scheduling from GUI thread
    """

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._client: Any | None = None
        self._on_state_change: Callable[[str, Any], None] | None = None
        self._on_error: Callable[[str], None] | None = None

    def set_state_callback(self, callback: Callable[[str, Any], None]) -> None:
        self._on_state_change = callback

    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        self._on_error = callback

    def start(self, client: Any | None = None) -> None:
        if self._running:
            logger.warning("AsyncioManager already running")
            return

        if client is not None:
            self._client = client

        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
        logger.info("AsyncioManager started")

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        if self._client is not None:
            self._loop.call_soon(self._schedule_client_start)

        try:
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Event loop error: {e}")
        finally:
            self._loop.close()
            logger.info("Event loop closed")

    def _schedule_client_start(self) -> None:
        if self._loop is not None:
            asyncio.ensure_future(self._run_client(), loop=self._loop)

    async def _run_client(self) -> None:
        if self._client is not None:
            try:
                self._notify_state("status", "connecting")
                await self._client.start()
                self._notify_state("status", "connected")
                self._notify_state("is_connected", True)
            except Exception as e:
                logger.error(f"Client start error: {e}")
                self._notify_state("status", "error")
                self._notify_state("is_connected", False)
                self._notify_error(str(e))

    async def _stop_client(self) -> None:
        if self._client is not None:
            try:
                self._notify_state("status", "disconnecting")
                await self._client.stop()
            except Exception as e:
                logger.error(f"Client stop error: {e}")
            finally:
                self._notify_state("status", "disconnected")
                self._notify_state("is_connected", False)

    def stop(self) -> None:
        if not self._running:
            logger.warning("AsyncioManager not running")
            return

        self._running = False

        if self._loop is not None and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._stop_client(), self._loop)
            try:
                future.result(timeout=5.0)
            except Exception as e:
                logger.error(f"Error during client stop: {e}")

            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._loop = None
        logger.info("AsyncioManager stopped")

    def start_client(self, client: Any) -> None:
        self._client = client
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")
        asyncio.run_coroutine_threadsafe(self._run_client(), self._loop)

    def run_coroutine(self, coro) -> asyncio.Future:
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Event loop is not running")

        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run_coroutine_with_callback(
        self, coro, callback: Callable[[Any], None]
    ) -> None:
        def _run_and_callback():
            try:
                result = self._loop.run_until_complete(coro)
                callback(result)
            except Exception as e:
                logger.error(f"Coroutine error: {e}")

        self._loop.call_soon_threadsafe(_run_and_callback)

    def _notify_state(self, key: str, value: Any) -> None:
        if self._on_state_change is not None:
            self._on_state_change(key, value)

    def _notify_error(self, message: str) -> None:
        if self._on_error is not None:
            self._on_error(message)

    @property
    def is_running(self) -> bool:
        return self._running and self._loop is not None and self._loop.is_running()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop
