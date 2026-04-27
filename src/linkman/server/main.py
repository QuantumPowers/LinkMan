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
import os
import signal
import sys
from typing import Self

import uvicorn

from linkman.shared.crypto.aead import AEADType
from linkman.shared.crypto.keys import KeyManager
from linkman.shared.utils.config import Config
from linkman.shared.utils.logger import get_logger, setup_logger
from linkman.shared.utils.cert import generate_cert_if_missing
from linkman.shared.utils.db import get_db, close_db
from linkman.server.core.handler import ConnectionHandler
from linkman.server.core.session import SessionManager
from linkman.server.core.udp import UDPServer
from linkman.server.core.websocket import WebSocketHandler
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
            default_allow=False,
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

        # Initialize UDP server
        self._udp_server = UDPServer(
            key=key_manager.master_key,
            cipher_type=cipher_type,
        )
        self._udp_server_port = 0

        # Initialize WebSocket handler
        self._websocket_handler = WebSocketHandler(
            key=key_manager.master_key,
            cipher_type=cipher_type,
            connection_handler=self._connection_handler,
            auth_manager=self._auth_manager,
        )
        self._websocket_app = None
        self._websocket_server = None

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

        await get_db()

        await self._session_manager.start()
        await self._device_manager.start()
        await self._traffic_manager.start()
        await self._monitor.start()

        # Start UDP server
        _, self._udp_server_port = await self._udp_server.start(
            self._config.server.host,
            0  # Use random port
        )

        # Update connection handler with UDP server port
        self._connection_handler.set_udp_server_port(self._udp_server_port)

        # Create SSL context if TLS is enabled
        ssl_context = None
        if self._config.tls.enabled:
            # Generate certificate if missing
            domain = self._config.tls.domain or "localhost"
            cert_dir = os.path.dirname(self._config.tls.cert_file) if self._config.tls.cert_file else "."
            
            # Use certificate files from config or generate new ones
            if self._config.tls.cert_file and self._config.tls.key_file:
                cert_file = self._config.tls.cert_file
                key_file = self._config.tls.key_file
                was_generated = False
            else:
                # Generate self-signed certificate
                cert_file, key_file, was_generated = generate_cert_if_missing(
                    domain=domain,
                    cert_dir=cert_dir,
                    validity_days=365,
                )
                # Update config with generated files
                self._config.tls.cert_file = cert_file
                self._config.tls.key_file = key_file

            # Create SSL context
            import ssl
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(
                certfile=cert_file,
                keyfile=key_file
            )
            logger.info(f"TLS enabled{' (certificate generated)' if was_generated else ''}")

        # Use port from config
        self._tcp_server = await asyncio.start_server(
            self._connection_handler.handle_connection,
            self._config.server.host,
            self._config.server.port,  # Use port from config
            ssl=ssl_context,
        )

        # Start WebSocket server if TLS is enabled
        if self._config.tls.enabled:
            try:
                from aiohttp import web
                
                app = web.Application()
                websocket_path = self._config.tls.websocket_path or "/api/ws"
                app.add_routes([web.get(websocket_path, self._websocket_handler.handle_websocket)])
                
                # Start WebSocket server on a different port
                websocket_port = self._config.server.port + 2
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, self._config.server.host, websocket_port, ssl_context=ssl_context)
                await site.start()
                
                self._websocket_server = runner
                logger.info(f"WebSocket support enabled at ws://{self._config.server.host}:{websocket_port}{websocket_path}")
            except Exception as e:
                logger.warning(f"Failed to start WebSocket server: {e}")
                logger.info("WebSocket support disabled")

        self._running = True

        addr = self._tcp_server.sockets[0].getsockname()
        logger.info(f"Server listening on {addr[0]}:{addr[1]}")
        logger.info(f"UDP server on port {self._udp_server_port}")
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

        # Stop UDP server
        await self._udp_server.stop()

        # Stop WebSocket server
        if self._websocket_server:
            await self._websocket_server.cleanup()
            logger.info("WebSocket server stopped")

        await self._monitor.stop()
        await self._traffic_manager.stop()
        await self._device_manager.stop()
        await self._session_manager.stop()

        await close_db()

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
