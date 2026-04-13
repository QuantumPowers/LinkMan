"""
Error definitions for LinkMan VPN.

Provides comprehensive error types for different error scenarios:
- Protocol errors
- Network errors
- Cryptographic errors
- Configuration errors
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


class ErrorCode(IntEnum):
    """Error codes for LinkMan."""

    # Protocol errors (100-199)
    PROTOCOL_ERROR = 100
    INVALID_PACKET = 101
    HANDSHAKE_FAILED = 102
    AUTHENTICATION_FAILED = 103
    COMMAND_NOT_SUPPORTED = 104
    ADDRESS_TYPE_NOT_SUPPORTED = 105

    # Network errors (200-299)
    NETWORK_ERROR = 200
    CONNECTION_TIMEOUT = 201
    CONNECTION_REFUSED = 202
    HOST_UNREACHABLE = 203
    NETWORK_UNREACHABLE = 204
    DNS_ERROR = 205
    TTL_EXPIRED = 206

    # Cryptographic errors (300-399)
    CRYPTO_ERROR = 300
    INVALID_KEY = 301
    DECRYPTION_FAILED = 302
    ENCRYPTION_FAILED = 303
    INVALID_NONCE = 304
    INVALID_TAG = 305

    # Configuration errors (400-499)
    CONFIG_ERROR = 400
    MISSING_CONFIG = 401
    INVALID_CONFIG = 402
    PORT_IN_USE = 403

    # Resource errors (500-599)
    RESOURCE_ERROR = 500
    MAX_CONNECTIONS_REACHED = 501
    OUT_OF_MEMORY = 502
    FILE_ERROR = 503


class LinkManError(Exception):
    """Base exception class for LinkMan errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROTOCOL_ERROR,
        cause: Optional[Exception] = None,
    ):
        """
        Initialize LinkMan error.

        Args:
            message: Error message
            error_code: Error code
            cause: Optional cause exception
        """
        super().__init__(message)
        self.error_code = error_code
        self.cause = cause

    @property
    def error_type(self) -> str:
        """Get error type name."""
        return self.error_code.name

    def __str__(self) -> str:
        """Get string representation."""
        base_msg = f"[{self.error_type}] {super().__str__()}"
        if self.cause:
            base_msg += f" (caused by: {self.cause})"
        return base_msg


class ProtocolError(LinkManError):
    """Protocol-related errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCode.PROTOCOL_ERROR, cause)


class NetworkError(LinkManError):
    """Network-related errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCode.NETWORK_ERROR, cause)


class CryptoError(LinkManError):
    """Cryptographic errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCode.CRYPTO_ERROR, cause)


class ConfigError(LinkManError):
    """Configuration errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCode.CONFIG_ERROR, cause)


class ResourceError(LinkManError):
    """Resource-related errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCode.RESOURCE_ERROR, cause)


def wrap_error(exc: Exception) -> LinkManError:
    """
    Wrap a generic exception into a LinkManError.

    Args:
        exc: Exception to wrap

    Returns:
        LinkManError instance
    """
    from cryptography.exceptions import InvalidTag
    import asyncio
    import socket

    if isinstance(exc, LinkManError):
        return exc
    elif isinstance(exc, InvalidTag):
        return CryptoError("Decryption failed: invalid authentication tag", exc)
    elif isinstance(exc, asyncio.TimeoutError):
        return NetworkError("Connection timeout", exc)
    elif isinstance(exc, socket.gaierror):
        return NetworkError("DNS resolution failed", exc)
    elif isinstance(exc, socket.error):
        if "Connection refused" in str(exc):
            return NetworkError("Connection refused", exc)
        elif "No route to host" in str(exc):
            return NetworkError("Host unreachable", exc)
        else:
            return NetworkError(f"Network error: {exc}", exc)
    elif isinstance(exc, ValueError):
        return ProtocolError(f"Invalid value: {exc}", exc)
    else:
        return LinkManError(f"Unexpected error: {exc}", cause=exc)
