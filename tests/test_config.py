"""Tests for config module."""

import pytest
import tempfile
from pathlib import Path

from linkman.shared.utils.config import (
    Config,
    ServerConfig,
    ClientConfig,
    CryptoConfig,
    TrafficConfig,
    DeviceConfig,
    LogConfig,
    TLSConfig,
    ConfigError,
)


class TestConfig:
    """Test Config class."""

    def test_default_config(self):
        config = Config()
        
        assert config.server.port == 8388
        assert config.client.local_port == 1080
        assert config.crypto.cipher == "aes-256-gcm"

    def test_to_dict(self):
        config = Config()
        data = config._to_dict()
        
        assert "server" in data
        assert "client" in data
        assert "crypto" in data

    def test_save_and_load(self):
        config = Config()
        config.server.port = 9999
        config.crypto.key = "test_key_base64"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.toml"
            config.save(path)
            
            loaded = Config.from_file(path)
            
            assert loaded.server.port == 9999
            assert loaded.crypto.key == "test_key_base64"

    def test_validate_missing_key(self):
        config = Config()
        
        errors = config.validate()
        
        assert "crypto.key is required" in errors

    def test_validate_invalid_port(self):
        config = Config()
        config.crypto.key = "test_key"
        config.server.port = 70000
        
        errors = config.validate()
        
        assert any("Invalid server port" in e for e in errors)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LINKMAN_SERVER_PORT", "9999")
        monkeypatch.setenv("LINKMAN_CRYPTO_KEY", "env_key")
        
        config = Config.from_env()
        
        assert config.server.port == 9999
        assert config.crypto.key == "env_key"


class TestServerConfig:
    """Test ServerConfig."""

    def test_defaults(self):
        config = ServerConfig()
        
        assert config.host == "0.0.0.0"
        assert config.port == 8388
        assert config.max_connections == 1024


class TestClientConfig:
    """Test ClientConfig."""

    def test_defaults(self):
        config = ClientConfig()
        
        assert config.local_host == "127.0.0.1"
        assert config.local_port == 1080


class TestCryptoConfig:
    """Test CryptoConfig."""

    def test_defaults(self):
        config = CryptoConfig()
        
        assert config.cipher == "aes-256-gcm"
        assert config.key == ""


class TestTrafficConfig:
    """Test TrafficConfig."""

    def test_defaults(self):
        config = TrafficConfig()
        
        assert config.enabled is True
        assert config.limit_mb == 0
        assert config.warning_threshold_mb == 1000


class TestDeviceConfig:
    """Test DeviceConfig."""

    def test_defaults(self):
        config = DeviceConfig()
        
        assert config.max_devices == 5
        assert config.session_timeout == 3600


class TestTLSConfig:
    """Test TLSConfig."""

    def test_defaults(self):
        config = TLSConfig()
        
        assert config.enabled is False
        assert config.websocket_path == "/linkman"
