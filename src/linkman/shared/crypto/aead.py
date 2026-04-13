"""
AEAD (Authenticated Encryption with Associated Data) cipher implementation.

Supports:
- AES-256-GCM
- ChaCha20-Poly1305
- AES-128-GCM

Based on Shadowsocks 2022 protocol specification.
"""

from __future__ import annotations

import os
import secrets
from abc import ABC, abstractmethod
from enum import Enum
from typing import ClassVar

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import (
    AESGCM,
    ChaCha20Poly1305,
)


class AEADType(Enum):
    """Supported AEAD cipher types."""

    AES_128_GCM = "aes-128-gcm"
    AES_256_GCM = "aes-256-gcm"
    CHACHA20_POLY1305 = "chacha20-poly1305"

    @property
    def key_size(self) -> int:
        """Return key size in bytes."""
        sizes = {
            AEADType.AES_128_GCM: 16,
            AEADType.AES_256_GCM: 32,
            AEADType.CHACHA20_POLY1305: 32,
        }
        return sizes[self]

    @property
    def nonce_size(self) -> int:
        """Return nonce size in bytes."""
        return 12

    @property
    def tag_size(self) -> int:
        """Return authentication tag size in bytes."""
        return 16

    @property
    def salt_size(self) -> int:
        """Return salt size in bytes for key derivation."""
        return 16


class CipherBase(ABC):
    """Abstract base class for AEAD ciphers."""

    @abstractmethod
    def encrypt(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Encrypt plaintext with optional associated data.

        Args:
            plaintext: Data to encrypt
            associated_data: Optional data to authenticate but not encrypt

        Returns:
            Encrypted data with authentication tag appended
        """
        pass

    @abstractmethod
    def decrypt(self, ciphertext: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Decrypt ciphertext and verify authentication tag.

        Args:
            ciphertext: Encrypted data with authentication tag
            associated_data: Optional associated data used during encryption

        Returns:
            Decrypted plaintext

        Raises:
            InvalidTag: If authentication fails
        """
        pass


class AESGCMCipher(CipherBase):
    """AES-GCM cipher implementation."""

    def __init__(self, key: bytes, nonce: bytes):
        """
        Initialize AES-GCM cipher.

        Args:
            key: Encryption key (16 or 32 bytes)
            nonce: Nonce for this encryption (12 bytes)
        """
        if len(key) not in (16, 32):
            raise ValueError(f"Invalid key size: {len(key)}, expected 16 or 32")
        if len(nonce) != 12:
            raise ValueError(f"Invalid nonce size: {len(nonce)}, expected 12")

        self._cipher = AESGCM(key)
        self._nonce = nonce

    def encrypt(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """Encrypt using AES-GCM."""
        return self._cipher.encrypt(self._nonce, plaintext, associated_data)

    def decrypt(self, ciphertext: bytes, associated_data: bytes | None = None) -> bytes:
        """Decrypt using AES-GCM."""
        return self._cipher.decrypt(self._nonce, ciphertext, associated_data)


class ChaCha20Poly1305Cipher(CipherBase):
    """ChaCha20-Poly1305 cipher implementation."""

    def __init__(self, key: bytes, nonce: bytes):
        """
        Initialize ChaCha20-Poly1305 cipher.

        Args:
            key: Encryption key (32 bytes)
            nonce: Nonce for this encryption (12 bytes)
        """
        if len(key) != 32:
            raise ValueError(f"Invalid key size: {len(key)}, expected 32")
        if len(nonce) != 12:
            raise ValueError(f"Invalid nonce size: {len(nonce)}, expected 12")

        self._cipher = ChaCha20Poly1305(key)
        self._nonce = nonce

    def encrypt(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """Encrypt using ChaCha20-Poly1305."""
        return self._cipher.encrypt(self._nonce, plaintext, associated_data)

    def decrypt(self, ciphertext: bytes, associated_data: bytes | None = None) -> bytes:
        """Decrypt using ChaCha20-Poly1305."""
        return self._cipher.decrypt(self._nonce, ciphertext, associated_data)


class AEADCipher:
    """
    AEAD cipher wrapper with nonce management for Shadowsocks 2022.

    This class handles:
    - Nonce incrementing for each packet
    - Packet format: [length (2 bytes)][length tag (16 bytes)][payload][payload tag]
    """

    MAX_PACKET_SIZE: ClassVar[int] = 0x3FFF
    CHUNK_SIZE: ClassVar[int] = 0x3FFF

    def __init__(self, cipher_type: AEADType, key: bytes, salt: bytes):
        """
        Initialize AEAD cipher.

        Args:
            cipher_type: Type of AEAD cipher to use
            key: Master key
            salt: Salt for subkey derivation

        Raises:
            ValueError: If key size is invalid
        """
        if len(key) != cipher_type.key_size:
            raise ValueError(f"Invalid key size: {len(key)}, expected {cipher_type.key_size}")
        if len(salt) != cipher_type.salt_size:
            raise ValueError(f"Invalid salt size: {len(salt)}, expected {cipher_type.salt_size}")

        self._cipher_type = cipher_type
        self._key = key
        self._salt = salt

        self._subkey = self._derive_subkey(key, salt)
        self._client_nonce = bytearray(12)
        self._server_nonce = bytearray(12)

    def _derive_subkey(self, key: bytes, salt: bytes) -> bytes:
        """Derive subkey from master key and salt using HKDF-SHA256."""
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=self._cipher_type.key_size,
            salt=salt,
            info=b"ss-subkey",
        )
        return hkdf.derive(key)

    def _create_cipher(self, key: bytes, nonce: bytes) -> CipherBase:
        """Create cipher instance based on type."""
        if self._cipher_type == AEADType.CHACHA20_POLY1305:
            return ChaCha20Poly1305Cipher(key, nonce)
        else:
            return AESGCMCipher(key, nonce)

    def _increment_nonce(self, nonce: bytearray) -> None:
        """Increment nonce by 1 (big-endian counter in first 8 bytes)."""
        for i in range(11, -1, -1):
            nonce[i] = (nonce[i] + 1) & 0xFF
            if nonce[i] != 0:
                break

    def encrypt_packet(self, plaintext: bytes) -> bytes:
        """
        Encrypt a single packet.

        Format: [encrypted_length][length_tag][encrypted_payload][payload_tag]

        Args:
            plaintext: Data to encrypt

        Returns:
            Encrypted packet
        """
        if len(plaintext) > self.MAX_PACKET_SIZE:
            raise ValueError(f"Payload too large: {len(plaintext)} > {self.MAX_PACKET_SIZE}")

        length = len(plaintext)
        length_bytes = length.to_bytes(2, "big")

        cipher = self._create_cipher(self._subkey, bytes(self._client_nonce))
        encrypted_length = cipher.encrypt(length_bytes)
        self._increment_nonce(self._client_nonce)

        cipher = self._create_cipher(self._subkey, bytes(self._client_nonce))
        encrypted_payload = cipher.encrypt(plaintext)
        self._increment_nonce(self._client_nonce)

        return encrypted_length + encrypted_payload

    def decrypt_packet(self, data: bytes) -> tuple[bytes, bytes]:
        """
        Decrypt a single packet.

        Args:
            data: Encrypted data starting with length

        Returns:
            Tuple of (decrypted payload, remaining data)

        Raises:
            InvalidTag: If authentication fails
        """
        length_size = 2 + self._cipher_type.tag_size

        if len(data) < length_size:
            raise ValueError("Insufficient data for length")

        encrypted_length = data[:length_size]
        remaining = data[length_size:]

        cipher = self._create_cipher(self._subkey, bytes(self._server_nonce))
        length_bytes = cipher.decrypt(encrypted_length)
        self._increment_nonce(self._server_nonce)

        payload_length = int.from_bytes(length_bytes, "big")
        if payload_length > self.MAX_PACKET_SIZE:
            raise ValueError(f"Invalid payload length: {payload_length}")

        payload_size = payload_length + self._cipher_type.tag_size
        if len(remaining) < payload_size:
            raise ValueError(f"Insufficient data for payload: need {payload_size}, have {len(remaining)}")

        encrypted_payload = remaining[:payload_size]
        rest = remaining[payload_size:]

        cipher = self._create_cipher(self._subkey, bytes(self._server_nonce))
        payload = cipher.decrypt(encrypted_payload)
        self._increment_nonce(self._server_nonce)

        return payload, rest

    @classmethod
    def generate_key(cls, cipher_type: AEADType) -> bytes:
        """Generate a random key for the specified cipher type."""
        return secrets.token_bytes(cipher_type.key_size)

    @classmethod
    def generate_salt(cls, cipher_type: AEADType) -> bytes:
        """Generate a random salt for the specified cipher type."""
        return secrets.token_bytes(cipher_type.salt_size)


def create_cipher_pair(
    cipher_type: AEADType,
    key: bytes,
    client_salt: bytes,
    server_salt: bytes,
) -> tuple[AEADCipher, AEADCipher]:
    """
    Create a pair of ciphers for bidirectional communication.

    Args:
        cipher_type: Type of AEAD cipher
        key: Shared master key
        client_salt: Salt for client-to-server direction
        server_salt: Salt for server-to-client direction

    Returns:
        Tuple of (client_cipher, server_cipher)
    """
    client_cipher = AEADCipher(cipher_type, key, client_salt)
    server_cipher = AEADCipher(cipher_type, key, server_salt)
    return client_cipher, server_cipher
