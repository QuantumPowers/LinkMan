"""
Configuration management for LinkMan.

Provides centralized configuration with:
- File-based configuration (TOML)
- Environment variable support
- Validation and defaults
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import tomli_w


from linkman.shared.errors import ConfigError


@dataclass
class ServerConfig:
    """Server-specific configuration."""

    host: str = "0.0.0.0"
    port: int = 8388
    management_port: int = 8389
    max_connections: int = 1024
    connection_timeout: int = 300
    buffer_size: int = 65536


@dataclass
class ClientConfig:
    """Client-specific configuration."""

    local_host: str = "127.0.0.1"
    local_port: int = 1080
    server_host: str = ""
    server_port: int = 8388
    connection_timeout: int = 30
    buffer_size: int = 65536


@dataclass
class CryptoConfig:
    """Cryptographic configuration."""

    cipher: str = "aes-256-gcm"
    key: str = ""
    identity: str = ""


@dataclass
class TrafficConfig:
    """Traffic management configuration."""

    enabled: bool = True
    limit_mb: int = 0
    warning_threshold_mb: int = 1000
    reset_day: int = 1


@dataclass
class DeviceConfig:
    """Device management configuration."""

    max_devices: int = 5
    session_timeout: int = 3600
    allowed_devices: list[str] = field(default_factory=list)


@dataclass
class LogConfig:
    """Logging configuration."""

    level: str = "INFO"
    file: str = "logs/linkman.log"
    max_size_mb: int = 10
    backup_count: int = 5
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"


@dataclass
class TLSConfig:
    """TLS configuration for traffic obfuscation."""

    enabled: bool = False
    cert_file: str = ""
    key_file: str = ""
    domain: str = ""
    websocket_path: str = "/linkman"
    websocket_enabled: bool = False


@dataclass
class Config:
    """
    Main configuration class.

    Supports:
    - Loading from TOML file
    - Environment variable overrides
    - Validation
    - Saving to file
    """

    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    traffic: TrafficConfig = field(default_factory=TrafficConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    log: LogConfig = field(default_factory=LogConfig)
    tls: TLSConfig = field(default_factory=TLSConfig)
    protocol: str = "shadowsocks2022"

    _config_path: Path | None = field(default=None, repr=False)

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """
        Load configuration from TOML file.

        Args:
            path: Path to configuration file

        Returns:
            Config instance

        Raises:
            ConfigError: If file cannot be read or parsed
        """
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Configuration file not found: {path}")

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            raise ConfigError(f"Failed to parse configuration: {e}") from e

        config = cls._from_dict(data)
        config._config_path = path
        return config

    @classmethod
    def from_env(cls) -> Self:
        """
        Create configuration from environment variables.

        Environment variables:
        - LINKMAN_SERVER_HOST
        - LINKMAN_SERVER_PORT
        - LINKMAN_CRYPTO_KEY
        - etc.

        Returns:
            Config instance
        """
        config = cls()

        if host := os.getenv("LINKMAN_SERVER_HOST"):
            config.server.host = host
        if port := os.getenv("LINKMAN_SERVER_PORT"):
            config.server.port = int(port)
        if key := os.getenv("LINKMAN_CRYPTO_KEY"):
            config.crypto.key = key
        if identity := os.getenv("LINKMAN_CRYPTO_IDENTITY"):
            config.crypto.identity = identity
        if local_port := os.getenv("LINKMAN_CLIENT_LOCAL_PORT"):
            config.client.local_port = int(local_port)
        if server_host := os.getenv("LINKMAN_CLIENT_SERVER_HOST"):
            config.client.server_host = server_host
        if server_port := os.getenv("LINKMAN_CLIENT_SERVER_PORT"):
            config.client.server_port = int(server_port)

        return config

    @classmethod
    def load(cls, path: str | Path | None = None) -> Self:
        """
        Load configuration with fallback chain.

        Priority:
        1. Specified path
        2. ./linkman.toml
        3. ~/.linkman/config.toml
        4. Environment variables
        5. Defaults

        Args:
            path: Optional configuration file path

        Returns:
            Config instance
        """
        search_paths = [
            Path("linkman.toml"),
            Path.home() / ".linkman" / "config.toml",
        ]

        if path:
            search_paths.insert(0, Path(path))

        for search_path in search_paths:
            if search_path.exists():
                return cls.from_file(search_path)

        return cls.from_env()

    def save(self, path: str | Path | None = None) -> None:
        """
        Save configuration to TOML file.

        Args:
            path: Optional path (uses original path if not specified)

        Raises:
            ConfigError: If cannot save
        """
        save_path = Path(path) if path else self._config_path
        if save_path is None:
            raise ConfigError("No configuration path specified")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._to_dict()
        try:
            with open(save_path, "wb") as f:
                tomli_w.dump(data, f)
        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}") from e

    def _to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "management_port": self.server.management_port,
                "max_connections": self.server.max_connections,
                "connection_timeout": self.server.connection_timeout,
                "buffer_size": self.server.buffer_size,
            },
            "client": {
                "local_host": self.client.local_host,
                "local_port": self.client.local_port,
                "server_host": self.client.server_host,
                "server_port": self.client.server_port,
                "connection_timeout": self.client.connection_timeout,
                "buffer_size": self.client.buffer_size,
            },
            "crypto": {
                "cipher": self.crypto.cipher,
                "key": self.crypto.key,
                "identity": self.crypto.identity,
            },
            "traffic": {
                "enabled": self.traffic.enabled,
                "limit_mb": self.traffic.limit_mb,
                "warning_threshold_mb": self.traffic.warning_threshold_mb,
                "reset_day": self.traffic.reset_day,
            },
            "device": {
                "max_devices": self.device.max_devices,
                "session_timeout": self.device.session_timeout,
                "allowed_devices": self.device.allowed_devices,
            },
            "log": {
                "level": self.log.level,
                "file": self.log.file,
                "max_size_mb": self.log.max_size_mb,
                "backup_count": self.log.backup_count,
                "format": self.log.format,
            },
            "tls": {
                "enabled": self.tls.enabled,
                "cert_file": self.tls.cert_file,
                "key_file": self.tls.key_file,
                "domain": self.tls.domain,
                "websocket_path": self.tls.websocket_path,
                "websocket_enabled": self.tls.websocket_enabled,
            },
            "protocol": self.protocol,
        }

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """Create config from dictionary."""
        config = cls()

        if "server" in data:
            s = data["server"]
            config.server = ServerConfig(
                host=s.get("host", config.server.host),
                port=s.get("port", config.server.port),
                management_port=s.get("management_port", config.server.management_port),
                max_connections=s.get("max_connections", config.server.max_connections),
                connection_timeout=s.get("connection_timeout", config.server.connection_timeout),
                buffer_size=s.get("buffer_size", config.server.buffer_size),
            )

        if "client" in data:
            c = data["client"]
            config.client = ClientConfig(
                local_host=c.get("local_host", config.client.local_host),
                local_port=c.get("local_port", config.client.local_port),
                server_host=c.get("server_host", config.client.server_host),
                server_port=c.get("server_port", config.client.server_port),
                connection_timeout=c.get("connection_timeout", config.client.connection_timeout),
                buffer_size=c.get("buffer_size", config.client.buffer_size),
            )

        if "crypto" in data:
            cr = data["crypto"]
            config.crypto = CryptoConfig(
                cipher=cr.get("cipher", config.crypto.cipher),
                key=cr.get("key", config.crypto.key),
                identity=cr.get("identity", config.crypto.identity),
            )

        if "traffic" in data:
            t = data["traffic"]
            config.traffic = TrafficConfig(
                enabled=t.get("enabled", config.traffic.enabled),
                limit_mb=t.get("limit_mb", config.traffic.limit_mb),
                warning_threshold_mb=t.get("warning_threshold_mb", config.traffic.warning_threshold_mb),
                reset_day=t.get("reset_day", config.traffic.reset_day),
            )

        if "device" in data:
            d = data["device"]
            config.device = DeviceConfig(
                max_devices=d.get("max_devices", config.device.max_devices),
                session_timeout=d.get("session_timeout", config.device.session_timeout),
                allowed_devices=d.get("allowed_devices", config.device.allowed_devices),
            )

        if "log" in data:
            l = data["log"]
            config.log = LogConfig(
                level=l.get("level", config.log.level),
                file=l.get("file", config.log.file),
                max_size_mb=l.get("max_size_mb", config.log.max_size_mb),
                backup_count=l.get("backup_count", config.log.backup_count),
                format=l.get("format", config.log.format),
            )

        if "tls" in data:
            tl = data["tls"]
            config.tls = TLSConfig(
                enabled=tl.get("enabled", config.tls.enabled),
                cert_file=tl.get("cert_file", config.tls.cert_file),
                key_file=tl.get("key_file", config.tls.key_file),
                domain=tl.get("domain", config.tls.domain),
                websocket_path=tl.get("websocket_path", config.tls.websocket_path),
                websocket_enabled=tl.get("websocket_enabled", config.tls.websocket_enabled),
            )

        if "protocol" in data:
            config.protocol = data["protocol"]

        return config

    def validate(self) -> list[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.crypto.key:
            errors.append("crypto.key is required")
        else:
            # Validate key format
            try:
                from linkman.shared.crypto.keys import KeyManager
                KeyManager.from_base64(self.crypto.key)
            except Exception as e:
                errors.append(f"Invalid crypto.key format: {e}")
            
            # Validate key strength
            if len(self.crypto.key) < 32:
                errors.append("crypto.key should be at least 32 characters long")

        if self.server.port < 1 or self.server.port > 65535:
            errors.append(f"Invalid server port: {self.server.port}")

        if self.client.local_port < 1 or self.client.local_port > 65535:
            errors.append(f"Invalid local port: {self.client.local_port}")

        if self.tls.enabled:
            # cert_file and key_file are not required - will be generated if missing
            pass

        return errors
