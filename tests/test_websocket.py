"""Tests for WebSocket module."""

import pytest
from unittest.mock import Mock, AsyncMock

from linkman.server.core.websocket import WebSocketHandler
from linkman.server.manager.auth import AuthManager
from linkman.shared.crypto.aead import AEADType


class TestWebSocketHandler:
    """Test WebSocketHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.key = b"test_key_123456789012345678901234"  # 32 bytes
        self.cipher_type = AEADType.AES_256_GCM
        self.connection_handler = Mock()
        self.connection_handler.check_access = AsyncMock(return_value=True)
        self.auth_manager = AuthManager(allowed_identities=["valid_token"])
        
        self.websocket_handler = WebSocketHandler(
            key=self.key,
            cipher_type=self.cipher_type,
            connection_handler=self.connection_handler,
            auth_manager=self.auth_manager,
        )

    def test_validate_auth_with_valid_token(self):
        """Test validate_auth with valid token."""
        auth_header = "Bearer valid_token"
        assert self.websocket_handler._validate_auth(auth_header) is True

    def test_validate_auth_with_invalid_token(self):
        """Test validate_auth with invalid token."""
        auth_header = "Bearer invalid_token"
        assert self.websocket_handler._validate_auth(auth_header) is False

    def test_validate_auth_without_bearer_scheme(self):
        """Test validate_auth without Bearer scheme."""
        auth_header = "Token valid_token"
        assert self.websocket_handler._validate_auth(auth_header) is False

    def test_validate_auth_with_empty_token(self):
        """Test validate_auth with empty token."""
        auth_header = "Bearer "
        assert self.websocket_handler._validate_auth(auth_header) is False

    def test_validate_auth_without_header(self):
        """Test validate_auth without header."""
        assert self.websocket_handler._validate_auth(None) is False

    def test_validate_auth_with_invalid_format(self):
        """Test validate_auth with invalid format."""
        auth_header = "Bearer"
        assert self.websocket_handler._validate_auth(auth_header) is False

    def test_validate_auth_without_auth_manager(self):
        """Test validate_auth without auth manager."""
        # Create WebSocketHandler without auth_manager
        websocket_handler = WebSocketHandler(
            key=self.key,
            cipher_type=self.cipher_type,
            connection_handler=self.connection_handler,
        )
        
        # Should fallback to checking if token is not empty
        auth_header = "Bearer any_token"
        assert websocket_handler._validate_auth(auth_header) is True
        
        # Empty token should still fail
        auth_header = "Bearer "
        assert websocket_handler._validate_auth(auth_header) is False

    def test_validate_auth_with_empty_allowed_identities(self):
        """Test validate_auth with empty allowed identities."""
        # Create AuthManager with empty allowed_identities
        auth_manager = AuthManager(allowed_identities=[])
        websocket_handler = WebSocketHandler(
            key=self.key,
            cipher_type=self.cipher_type,
            connection_handler=self.connection_handler,
            auth_manager=auth_manager,
        )
        
        # Should allow any token when allowed_identities is empty
        auth_header = "Bearer any_token"
        assert websocket_handler._validate_auth(auth_header) is True
