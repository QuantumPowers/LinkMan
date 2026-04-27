"""
Client main entry point.

Usage:
    python -m linkman.client.main
    or
    linkman-client
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Self

from linkman.shared.crypto.aead import AEADType
from linkman.shared.crypto.keys import KeyManager
from linkman.shared.utils.config import Config
from linkman.shared.utils.logger import get_logger, setup_logger
from linkman.shared.utils.connection_pool import ConnectionPool, ConnectionPoolManager
from linkman.client.proxy.local import LocalProxy
from linkman.client.proxy.modes import ModeManager, ProxyMode
from linkman.client.rules.matcher import RuleMatcher
from linkman.client.utils.proxy_manager import ProxyManager

logger = get_logger("client")


class Client:
    """
    LinkMan VPN Client.

    Manages:
    - Local proxy server
    - Mode switching
    - Rule management
    """

    def __init__(self, config: Config):
        """
        Initialize client.

        Args:
            config: Client configuration
        """
        self._config = config

        key_manager = KeyManager.from_base64(config.crypto.key) if config.crypto.key else KeyManager()

        cipher_type = AEADType(config.crypto.cipher)

        self._mode_manager = ModeManager(
            mode=ProxyMode.RULES,
            rule_matcher=RuleMatcher(),
        )

        self._proxy = LocalProxy(
            key=key_manager.master_key,
            cipher_type=cipher_type,
            server_host=config.client.server_host,
            server_port=config.client.server_port,
            mode_manager=self._mode_manager,
            tls_enabled=config.tls.enabled,
            websocket_enabled=config.tls.websocket_enabled,
            websocket_path=config.tls.websocket_path,
            protocol="shadowsocks2022",
            connection_pool=self._create_connection_pool(config),
        )

        self._proxy_manager = ProxyManager(
            host=config.client.local_host,
            port=config.client.local_port
        )

        self._running = False

    def _create_connection_pool(self, config: Config):
        if config.tls.websocket_enabled and config.tls.enabled:
            return None

        async def create_conn():
            import ssl as ssl_module
            ssl_context = None
            if config.tls.enabled:
                ssl_context = ssl_module.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl_module.CERT_NONE
                ssl_context.min_version = ssl_module.TLSVersion.TLSv1_2
            return await asyncio.wait_for(
                asyncio.open_connection(
                    config.client.server_host, config.client.server_port, ssl=ssl_context
                ),
                timeout=30,
            )

        pool = ConnectionPool(
            create_connection=create_conn,
            max_connections=config.server.max_connections // 2 if config.server.max_connections else 50,
        )
        return pool

    @property
    def config(self) -> Config:
        """Get configuration."""
        return self._config

    @property
    def mode_manager(self) -> ModeManager:
        """Get mode manager."""
        return self._mode_manager

    @property
    def proxy(self) -> LocalProxy:
        """Get local proxy."""
        return self._proxy

    async def start(self) -> None:
        """Start the client."""
        if self._running:
            return

        logger.info("Starting LinkMan client...")

        pool = self._proxy._connection_pool
        if pool is not None:
            await pool.start()

        await self._proxy.start(
            self._config.client.local_host,
            self._config.client.local_port,
        )

        # Set system proxy
        self._proxy_manager.set_proxy()

        self._running = True

        logger.info(
            f"Client started, proxy listening on "
            f"{self._config.client.local_host}:{self._config.client.local_port}"
        )

    async def stop(self) -> None:
        """Stop the client."""
        if not self._running:
            return

        logger.info("Stopping LinkMan client...")

        await self._proxy.stop()

        # Restore system proxy
        self._proxy_manager.restore_proxy()

        pool = self._proxy._connection_pool
        if pool is not None:
            await pool.stop()

        self._running = False

        logger.info("Client stopped")

    async def run(self) -> None:
        """Run the client."""
        await self.start()

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        # Only set up signal handlers in the main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            def signal_handler():
                logger.info("Received shutdown signal")
                stop_event.set()

            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, signal_handler)
            except ValueError:
                # Signal handlers can only be set in the main thread
                logger.debug("Signal handlers not available in this thread")

        try:
            await stop_event.wait()
        finally:
            await self.stop()

    def set_mode(self, mode: ProxyMode) -> None:
        """Set proxy mode."""
        self._mode_manager.set_mode(mode)

    def get_stats(self) -> dict:
        """Get client statistics."""
        return {
            "proxy": self._proxy.get_stats(),
            "mode": self._mode_manager.get_stats_dict(),
        }

    @classmethod
    def from_config_file(cls, path: str) -> Self:
        """Create client from config file."""
        config = Config.load(path)
        return cls(config)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="LinkMan VPN Client")
    parser.add_argument(
        "-c", "--config",
        default="linkman.toml",
        help="Configuration file path",
    )
    parser.add_argument(
        "--local-host",
        default="127.0.0.1",
        help="Local proxy host",
    )
    parser.add_argument(
        "-p", "--local-port",
        type=int,
        default=1080,
        help="Local proxy port",
    )
    parser.add_argument(
        "--server-host",
        help="Server host",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        help="Server port",
    )
    parser.add_argument(
        "--key",
        help="Encryption key (base64)",
    )
    parser.add_argument(
        "--mode",
        choices=["global", "rules", "direct"],
        default="rules",
        help="Proxy mode",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Start GUI interface",
    )

    args = parser.parse_args()

    # If GUI flag is set or no command line arguments provided, start GUI
    if args.gui or len(sys.argv) == 1:
        import subprocess
        
        # Start GUI in a separate process to avoid terminal blocking
        # This ensures that starting the client only opens the GUI and doesn't perform any other operations
        subprocess.Popen([sys.executable, "-m", "linkman.client.gui.app"])
        return

    setup_logger(level=args.log_level)

    config = Config.load(args.config)

    # Override with command line arguments if provided
    if args.local_host:
        config.client.local_host = args.local_host
    if args.local_port:
        config.client.local_port = args.local_port
    if args.server_host:
        config.client.server_host = args.server_host
    if args.server_port:
        config.client.server_port = args.server_port
    if args.key:
        config.crypto.key = args.key

    client = Client(config)
    client.set_mode(ProxyMode(args.mode))

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
