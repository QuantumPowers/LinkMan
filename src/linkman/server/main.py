"""
Server main entry point.

Usage:
    python -m linkman.server.main
    or
    linkman-server
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Self

import uvicorn

from linkman.shared.crypto.aead import AEADType
from linkman.shared.crypto.keys import KeyManager
from linkman.shared.utils.config import Config
from linkman.shared.utils.logger import get_logger, setup_logger
from linkman.server.core.handler import ConnectionHandler
from linkman.server.core.session import SessionManager
from linkman.server.manager.auth import AuthManager
from linkman.server.manager.device import DeviceManager
from linkman.server.manager.traffic import TrafficManager
from linkman.server.manager.monitor import Monitor
from linkman.server.api.routes import create_app

logger = get_logger("server")


class Server:
    """
    LinkMan VPN Server.

    Manages all server components:
    - Connection handling
    - Session management
    - Device management
    - Traffic accounting
    - Monitoring
    - API server
    """

    def __init__(self, config: Config):
        """
        Initialize server.

        Args:
            config: Server configuration
        """
        self._config = config

        key_manager = KeyManager.from_base64(config.crypto.key) if config.crypto.key else KeyManager()

        self._session_manager = SessionManager(
            session_timeout=config.device.session_timeout,
        )

        self._device_manager = DeviceManager(
            max_devices=config.device.max_devices,
            allowed_devices=config.device.allowed_devices,
        )

        self._traffic_manager = TrafficManager(
            enabled=config.traffic.enabled,
            limit_mb=config.traffic.limit_mb,
            warning_threshold_mb=config.traffic.warning_threshold_mb,
            reset_day=config.traffic.reset_day,
        )

        self._auth_manager = AuthManager(
            default_allow=True,
        )

        cipher_type = AEADType(config.crypto.cipher)
        self._connection_handler = ConnectionHandler(
            key=key_manager.master_key,
            cipher_type=cipher_type,
            auth_manager=self._auth_manager,
            device_manager=self._device_manager,
            traffic_manager=self._traffic_manager,
            session_manager=self._session_manager,
            max_connections=config.server.max_connections,
        )

        self._monitor = Monitor(
            connection_handler=self._connection_handler,
            session_manager=self._session_manager,
            device_manager=self._device_manager,
            traffic_manager=self._traffic_manager,
        )

        self._app = create_app(
            connection_handler=self._connection_handler,
            session_manager=self._session_manager,
            device_manager=self._device_manager,
            traffic_manager=self._traffic_manager,
            monitor=self._monitor,
        )

        self._tcp_server = None
        self._running = False

    @property
    def config(self) -> Config:
        """Get configuration."""
        return self._config

    async def start(self) -> None:
        """Start the server."""
        if self._running:
            return

        logger.info("Starting LinkMan server...")

        await self._session_manager.start()
        await self._device_manager.start()
        await self._traffic_manager.start()
        await self._monitor.start()

        self._tcp_server = await asyncio.start_server(
            self._connection_handler.handle_connection,
            self._config.server.host,
            self._config.server.port,
        )

        self._running = True

        addr = self._tcp_server.sockets[0].getsockname()
        logger.info(f"Server listening on {addr[0]}:{addr[1]}")
        logger.info(f"Management API on port {self._config.server.management_port}")

    async def stop(self) -> None:
        """Stop the server."""
        if not self._running:
            return

        logger.info("Stopping LinkMan server...")

        self._running = False

        if self._tcp_server:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()

        await self._monitor.stop()
        await self._traffic_manager.stop()
        await self._device_manager.stop()
        await self._session_manager.stop()

        logger.info("Server stopped")

    async def run(self) -> None:
        """Run the server."""
        await self.start()

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def signal_handler():
            logger.info("Received shutdown signal")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            async with self._tcp_server:
                await stop_event.wait()
        finally:
            await self.stop()

    @classmethod
    def from_config_file(cls, path: str) -> Self:
        """Create server from config file."""
        config = Config.load(path)
        return cls(config)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="LinkMan VPN Server")
    parser.add_argument(
        "-c", "--config",
        default="linkman.toml",
        help="Configuration file path",
    )
    parser.add_argument(
        "--host",
        help="Server host (overrides config)",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        help="Server port (overrides config)",
    )
    parser.add_argument(
        "--management-port",
        type=int,
        help="Management API port (overrides config)",
    )
    parser.add_argument(
        "--key",
        help="Encryption key (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new key and exit",
    )

    args = parser.parse_args()

    if args.generate_key:
        key = KeyManager.generate_master_key()
        print(f"Generated key: {KeyManager(key).master_key_base64}")
        sys.exit(0)

    setup_logger(level=args.log_level)

    config = Config.load(args.config)

    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    if args.management_port:
        config.server.management_port = args.management_port
    if args.key:
        config.crypto.key = args.key

    errors = config.validate()
    if errors:
        logger.error(f"Configuration errors: {errors}")
        sys.exit(1)

    server = Server(config)

    api_config = uvicorn.Config(
        server._app,
        host=config.server.host,
        port=config.server.management_port,
        log_level=args.log_level.lower(),
    )
    api_server = uvicorn.Server(api_config)

    async def run_all():
        await asyncio.gather(
            server.run(),
            api_server.serve(),
        )

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
