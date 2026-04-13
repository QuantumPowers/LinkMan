"""
Key management and derivation utilities.

Implements secure key generation, derivation, and management
following Shadowsocks 2022 specification.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Final

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


class KeyDerivation(Enum):
    """Key derivation methods."""

    HKDF_SHA256 = "hkdf-sha256"
    PBKDF2_SHA256 = "pbkdf2-sha256"


@dataclass(frozen=True)
class KeyPair:
    """A pair of salts for bidirectional communication."""

    client_salt: bytes
    server_salt: bytes

    def to_base64(self) -> str:
        """Encode key pair as base64 string."""
        combined = self.client_salt + self.server_salt
        return base64.urlsafe_b64encode(combined).decode("ascii").rstrip("=")

    @classmethod
    def from_base64(cls, encoded: str) -> "KeyPair":
        """Decode key pair from base64 string."""
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding
        combined = base64.urlsafe_b64decode(encoded)
        if len(combined) != 32:
            raise ValueError(f"Invalid key pair length: {len(combined)}, expected 32")
        return cls(client_salt=combined[:16], server_salt=combined[16:])


class KeyManager:
    """
    Manages encryption keys for LinkMan.

    Features:
    - Secure key generation
    - Key derivation from passwords
    - Session key management
    - Key rotation support
    """

    MIN_KEY_LENGTH: Final[int] = 16
    MAX_KEY_LENGTH: Final[int] = 64
    DEFAULT_ITERATIONS: Final[int] = 100000

    def __init__(self, master_key: bytes | None = None):
        """
        Initialize key manager.

        Args:
            master_key: Optional master key (generated if not provided)
        """
        self._master_key = master_key or self.generate_master_key()
        self._session_keys: dict[str, bytes] = {}

    @property
    def master_key(self) -> bytes:
        """Get the master key."""
        return self._master_key

    @property
    def master_key_hex(self) -> str:
        """Get master key as hex string."""
        return self._master_key.hex()

    @property
    def master_key_base64(self) -> str:
        """Get master key as base64 string."""
        return base64.urlsafe_b64encode(self._master_key).decode("ascii").rstrip("=")

    @classmethod
    def generate_master_key(cls, length: int = 32) -> bytes:
        """
        Generate a secure random master key.

        Args:
            length: Key length in bytes (default 32 for AES-256)

        Returns:
            Random master key
        """
        if length < cls.MIN_KEY_LENGTH or length > cls.MAX_KEY_LENGTH:
            raise ValueError(f"Key length must be between {cls.MIN_KEY_LENGTH} and {cls.MAX_KEY_LENGTH}")
        return secrets.token_bytes(length)

    @classmethod
    def derive_from_password(
        cls,
        password: str,
        salt: bytes | None = None,
        length: int = 32,
        iterations: int = DEFAULT_ITERATIONS,
    ) -> "KeyManager":
        """
        Derive a key manager from a password using PBKDF2.

        Args:
            password: Password string
            salt: Optional salt (generated if not provided)
            length: Desired key length
            iterations: PBKDF2 iterations

        Returns:
            KeyManager instance with derived key
        """
        if salt is None:
            salt = secrets.token_bytes(16)

        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=length,
        )
        return cls(master_key=key)

    def derive_subkey(
        self,
        salt: bytes,
        length: int = 32,
        info: bytes = b"linkman-subkey",
    ) -> bytes:
        """
        Derive a subkey from the master key using HKDF.

        Args:
            salt: Salt for key derivation
            length: Desired subkey length
            info: Context info for key separation

        Returns:
            Derived subkey
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            info=info,
        )
        return hkdf.derive(self._master_key)

    def generate_session_key(self, session_id: str, length: int = 32) -> bytes:
        """
        Generate a session-specific key.

        Args:
            session_id: Unique session identifier
            length: Desired key length

        Returns:
            Session key
        """
        salt = hashlib.sha256(session_id.encode()).digest()[:16]
        key = self.derive_subkey(salt, length, info=f"session-{session_id}".encode())
        self._session_keys[session_id] = key
        return key

    def get_session_key(self, session_id: str) -> bytes | None:
        """Get a previously generated session key."""
        return self._session_keys.get(session_id)

    def rotate_session_key(self, session_id: str) -> bytes:
        """
        Rotate a session key.

        Args:
            session_id: Session identifier

        Returns:
            New session key
        """
        new_session_id = f"{session_id}-rotated-{secrets.token_hex(4)}"
        return self.generate_session_key(new_session_id)

    def clear_session_key(self, session_id: str) -> None:
        """Clear a session key from memory."""
        self._session_keys.pop(session_id, None)

    def clear_all_session_keys(self) -> None:
        """Clear all session keys from memory."""
        self._session_keys.clear()

    @classmethod
    def from_hex(cls, hex_key: str) -> "KeyManager":
        """Create key manager from hex-encoded key."""
        return cls(master_key=bytes.fromhex(hex_key))

    @classmethod
    def from_base64(cls, b64_key: str) -> "KeyManager":
        """Create key manager from base64-encoded key."""
        padding = 4 - (len(b64_key) % 4)
        if padding != 4:
            b64_key += "=" * padding
        return cls(master_key=base64.urlsafe_b64decode(b64_key))


def generate_identity() -> str:
    """
    Generate a unique identity string for server/client.

    Format: base64-encoded random bytes
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")


def compute_identity_hash(identity: str, timestamp: int) -> bytes:
    """
    Compute hash of identity with timestamp for replay protection.

    Args:
        identity: Client/server identity string
        timestamp: Unix timestamp

    Returns:
        SHA256 hash
    """
    data = f"{identity}:{timestamp}".encode()
    return hashlib.sha256(data).digest()
