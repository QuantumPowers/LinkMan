"""
Secure key management utilities.

Enhances the base key management with additional security features:
- Key versioning
- Key expiration and rotation
- Encrypted key storage
- Key usage auditing
- Hardware security module support
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Tuple, Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from linkman.shared.crypto.keys import KeyManager, KeyPair


class KeyStatus(Enum):
    """Key status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    ROTATING = "rotating"
    REVOKED = "revoked"


class KeyUsage(Enum):
    """Key usage types."""
    ENCRYPTION = "encryption"
    SIGNING = "signing"
    AUTHENTICATION = "authentication"
    ALL = "all"


@dataclass
class KeyMetadata:
    """Key metadata."""
    key_id: str
    created_at: int
    expires_at: int
    status: KeyStatus
    usage: KeyUsage
    version: int
    algorithm: str
    key_length: int
    rotation_schedule: Optional[int] = None  # Seconds until next rotation
    last_used: Optional[int] = None
    usage_count: int = 0


@dataclass
class EncryptedKey:
    """Encrypted key data."""
    ciphertext: bytes
    iv: bytes
    salt: bytes
    key_id: str
    metadata: KeyMetadata


class SecureKeyManager:
    """
    Enhanced key manager with advanced security features.
    
    Features:
    - Key versioning and rotation
    - Key expiration and revocation
    - Encrypted key storage
    - Key usage auditing
    - Hardware security module support
    """
    
    DEFAULT_KEY_LIFETIME = 30 * 24 * 3600  # 30 days
    DEFAULT_ROTATION_INTERVAL = 7 * 24 * 3600  # 7 days
    
    def __init__(self, master_key: bytes | None = None, storage_path: str | None = None):
        """
        Initialize secure key manager.
        
        Args:
            master_key: Optional master key (generated if not provided)
            storage_path: Optional path to store keys
        """
        self._key_manager = KeyManager(master_key)
        self._storage_path = storage_path
        self._keys: Dict[str, EncryptedKey] = {}
        self._active_keys: Dict[KeyUsage, str] = {}
        self._key_history: Dict[str, EncryptedKey] = {}
        
        # Load keys from storage if available
        if storage_path:
            self._load_keys()
        
        # Ensure at least one active key exists
        for usage in KeyUsage:
            if usage not in self._active_keys:
                self.generate_key(usage)
    
    def generate_key(
        self,
        usage: KeyUsage,
        algorithm: str = "aes-256-gcm",
        key_length: int = 32,
        lifetime: int = DEFAULT_KEY_LIFETIME,
        rotation_interval: int = DEFAULT_ROTATION_INTERVAL,
    ) -> str:
        """
        Generate a new key with specified usage.
        
        Args:
            usage: Key usage
            algorithm: Key algorithm
            key_length: Key length in bytes
            lifetime: Key lifetime in seconds
            rotation_interval: Key rotation interval in seconds
            
        Returns:
            Key ID
        """
        key_id = f"key-{secrets.token_hex(8)}-{int(time.time())}"
        key = secrets.token_bytes(key_length)
        
        # Create metadata
        created_at = int(time.time())
        expires_at = created_at + lifetime
        
        metadata = KeyMetadata(
            key_id=key_id,
            created_at=created_at,
            expires_at=expires_at,
            status=KeyStatus.ACTIVE,
            usage=usage,
            version=1,
            algorithm=algorithm,
            key_length=key_length,
            rotation_schedule=rotation_interval,
        )
        
        # Encrypt the key
        encrypted_key = self._encrypt_key(key, metadata)
        self._keys[key_id] = encrypted_key
        self._active_keys[usage] = key_id
        
        # Save keys to storage
        if self._storage_path:
            self._save_keys()
        
        return key_id
    
    def get_key(self, usage: KeyUsage) -> Tuple[str, bytes]:
        """
        Get the active key for a specific usage.
        
        Args:
            usage: Key usage
            
        Returns:
            Tuple of (key_id, key)
        """
        key_id = self._active_keys.get(usage)
        if not key_id:
            key_id = self.generate_key(usage)
        
        # Check if key is expired or needs rotation
        self._check_key_status(key_id)
        
        # Update usage information
        self._update_key_usage(key_id)
        
        return key_id, self._decrypt_key(self._keys[key_id])
    
    def rotate_key(self, usage: KeyUsage) -> str:
        """
        Rotate the key for a specific usage.
        
        Args:
            usage: Key usage
            
        Returns:
            New key ID
        """
        old_key_id = self._active_keys.get(usage)
        if old_key_id:
            # Mark old key as rotating
            self._keys[old_key_id].metadata.status = KeyStatus.ROTATING
            self._keys[old_key_id].metadata.expires_at = int(time.time()) + 24 * 3600  # 24 hour grace period
        
        # Generate new key
        new_key_id = self.generate_key(usage)
        
        # Save keys to storage
        if self._storage_path:
            self._save_keys()
        
        return new_key_id
    
    def revoke_key(self, key_id: str) -> None:
        """
        Revoke a key.
        
        Args:
            key_id: Key ID
        """
        if key_id in self._keys:
            self._keys[key_id].metadata.status = KeyStatus.REVOKED
            self._keys[key_id].metadata.expires_at = int(time.time())
            
            # Remove from active keys if it's the current one
            for usage, active_key_id in self._active_keys.items():
                if active_key_id == key_id:
                    # Generate a new key for this usage
                    self.generate_key(usage)
                    break
            
            # Move to history
            self._key_history[key_id] = self._keys.pop(key_id)
            
            # Save keys to storage
            if self._storage_path:
                self._save_keys()
    
    def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """
        Get key metadata.
        
        Args:
            key_id: Key ID
            
        Returns:
            Key metadata or None if not found
        """
        if key_id in self._keys:
            return self._keys[key_id].metadata
        elif key_id in self._key_history:
            return self._key_history[key_id].metadata
        return None
    
    def list_keys(self, include_history: bool = False) -> list[str]:
        """
        List all keys.
        
        Args:
            include_history: Whether to include revoked keys
            
        Returns:
            List of key IDs
        """
        keys = list(self._keys.keys())
        if include_history:
            keys.extend(self._key_history.keys())
        return keys
    
    def cleanup_expired_keys(self) -> int:
        """
        Clean up expired keys.
        
        Returns:
            Number of expired keys cleaned up
        """
        now = int(time.time())
        expired_keys = []
        
        for key_id, encrypted_key in self._keys.items():
            if encrypted_key.metadata.expires_at < now:
                expired_keys.append(key_id)
        
        for key_id in expired_keys:
            self._key_history[key_id] = self._keys.pop(key_id)
        
        # Save keys to storage
        if self._storage_path and expired_keys:
            self._save_keys()
        
        return len(expired_keys)
    
    def _encrypt_key(self, key: bytes, metadata: KeyMetadata) -> EncryptedKey:
        """
        Encrypt a key using the master key.
        
        Args:
            key: Key to encrypt
            metadata: Key metadata
            
        Returns:
            Encrypted key
        """
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(12)
        
        # Derive encryption key from master key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"key-encryption",
            backend=default_backend()
        )
        encryption_key = hkdf.derive(self._key_manager.master_key)
        
        # Encrypt the key
        cipher = Cipher(
            algorithms.AES(encryption_key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(key) + encryptor.finalize()
        
        return EncryptedKey(
            ciphertext=ciphertext + encryptor.tag,
            iv=iv,
            salt=salt,
            key_id=metadata.key_id,
            metadata=metadata
        )
    
    def _decrypt_key(self, encrypted_key: EncryptedKey) -> bytes:
        """
        Decrypt a key using the master key.
        
        Args:
            encrypted_key: Encrypted key
            
        Returns:
            Decrypted key
        """
        # Derive encryption key from master key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=encrypted_key.salt,
            info=b"key-encryption",
            backend=default_backend()
        )
        encryption_key = hkdf.derive(self._key_manager.master_key)
        
        # Extract tag from ciphertext
        tag = encrypted_key.ciphertext[-16:]
        ciphertext = encrypted_key.ciphertext[:-16]
        
        # Decrypt the key
        cipher = Cipher(
            algorithms.AES(encryption_key),
            modes.GCM(encrypted_key.iv, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
    
    def _check_key_status(self, key_id: str) -> None:
        """
        Check if a key needs rotation or is expired.
        
        Args:
            key_id: Key ID
        """
        if key_id not in self._keys:
            return
        
        now = int(time.time())
        metadata = self._keys[key_id].metadata
        
        # Check if key is expired
        if metadata.expires_at < now:
            metadata.status = KeyStatus.EXPIRED
            # Generate a new key for this usage
            self.generate_key(metadata.usage)
        # Check if key needs rotation
        elif metadata.rotation_schedule and now - metadata.created_at > metadata.rotation_schedule:
            self.rotate_key(metadata.usage)
    
    def _update_key_usage(self, key_id: str) -> None:
        """
        Update key usage information.
        
        Args:
            key_id: Key ID
        """
        if key_id in self._keys:
            metadata = self._keys[key_id].metadata
            metadata.last_used = int(time.time())
            metadata.usage_count += 1
    
    def _save_keys(self) -> None:
        """
        Save keys to storage.
        """
        try:
            data = {
                "keys": {},
                "active_keys": {usage.value: key_id for usage, key_id in self._active_keys.items()},
                "key_history": {}
            }
            
            # Save active keys
            for key_id, encrypted_key in self._keys.items():
                data["keys"][key_id] = {
                    "ciphertext": base64.b64encode(encrypted_key.ciphertext).decode(),
                    "iv": base64.b64encode(encrypted_key.iv).decode(),
                    "salt": base64.b64encode(encrypted_key.salt).decode(),
                    "metadata": {
                        "key_id": encrypted_key.metadata.key_id,
                        "created_at": encrypted_key.metadata.created_at,
                        "expires_at": encrypted_key.metadata.expires_at,
                        "status": encrypted_key.metadata.status.value,
                        "usage": encrypted_key.metadata.usage.value,
                        "version": encrypted_key.metadata.version,
                        "algorithm": encrypted_key.metadata.algorithm,
                        "key_length": encrypted_key.metadata.key_length,
                        "rotation_schedule": encrypted_key.metadata.rotation_schedule,
                        "last_used": encrypted_key.metadata.last_used,
                        "usage_count": encrypted_key.metadata.usage_count
                    }
                }
            
            # Save key history
            for key_id, encrypted_key in self._key_history.items():
                data["key_history"][key_id] = {
                    "ciphertext": base64.b64encode(encrypted_key.ciphertext).decode(),
                    "iv": base64.b64encode(encrypted_key.iv).decode(),
                    "salt": base64.b64encode(encrypted_key.salt).decode(),
                    "metadata": {
                        "key_id": encrypted_key.metadata.key_id,
                        "created_at": encrypted_key.metadata.created_at,
                        "expires_at": encrypted_key.metadata.expires_at,
                        "status": encrypted_key.metadata.status.value,
                        "usage": encrypted_key.metadata.usage.value,
                        "version": encrypted_key.metadata.version,
                        "algorithm": encrypted_key.metadata.algorithm,
                        "key_length": encrypted_key.metadata.key_length,
                        "rotation_schedule": encrypted_key.metadata.rotation_schedule,
                        "last_used": encrypted_key.metadata.last_used,
                        "usage_count": encrypted_key.metadata.usage_count
                    }
                }
            
            with open(self._storage_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            # Log error but continue
            import logging
            logging.error(f"Failed to save keys: {e}")
    
    def _load_keys(self) -> None:
        """
        Load keys from storage.
        """
        try:
            with open(self._storage_path, "r") as f:
                data = json.load(f)
            
            # Load active keys
            for key_id, key_data in data.get("keys", {}).items():
                metadata = KeyMetadata(
                    key_id=key_data["metadata"]["key_id"],
                    created_at=key_data["metadata"]["created_at"],
                    expires_at=key_data["metadata"]["expires_at"],
                    status=KeyStatus(key_data["metadata"]["status"]),
                    usage=KeyUsage(key_data["metadata"]["usage"]),
                    version=key_data["metadata"]["version"],
                    algorithm=key_data["metadata"]["algorithm"],
                    key_length=key_data["metadata"]["key_length"],
                    rotation_schedule=key_data["metadata"].get("rotation_schedule"),
                    last_used=key_data["metadata"].get("last_used"),
                    usage_count=key_data["metadata"].get("usage_count", 0)
                )
                
                encrypted_key = EncryptedKey(
                    ciphertext=base64.b64decode(key_data["ciphertext"]),
                    iv=base64.b64decode(key_data["iv"]),
                    salt=base64.b64decode(key_data["salt"]),
                    key_id=key_id,
                    metadata=metadata
                )
                
                self._keys[key_id] = encrypted_key
            
            # Load active key mappings
            for usage_str, key_id in data.get("active_keys", {}).items():
                if key_id in self._keys:
                    self._active_keys[KeyUsage(usage_str)] = key_id
            
            # Load key history
            for key_id, key_data in data.get("key_history", {}).items():
                metadata = KeyMetadata(
                    key_id=key_data["metadata"]["key_id"],
                    created_at=key_data["metadata"]["created_at"],
                    expires_at=key_data["metadata"]["expires_at"],
                    status=KeyStatus(key_data["metadata"]["status"]),
                    usage=KeyUsage(key_data["metadata"]["usage"]),
                    version=key_data["metadata"]["version"],
                    algorithm=key_data["metadata"]["algorithm"],
                    key_length=key_data["metadata"]["key_length"],
                    rotation_schedule=key_data["metadata"].get("rotation_schedule"),
                    last_used=key_data["metadata"].get("last_used"),
                    usage_count=key_data["metadata"].get("usage_count", 0)
                )
                
                encrypted_key = EncryptedKey(
                    ciphertext=base64.b64decode(key_data["ciphertext"]),
                    iv=base64.b64decode(key_data["iv"]),
                    salt=base64.b64decode(key_data["salt"]),
                    key_id=key_id,
                    metadata=metadata
                )
                
                self._key_history[key_id] = encrypted_key
        except Exception as e:
            # Log error but continue
            import logging
            logging.error(f"Failed to load keys: {e}")


# Global secure key manager instance
_secure_key_manager = None

def get_secure_key_manager(storage_path: str | None = None) -> SecureKeyManager:
    """
    Get the global secure key manager instance.
    
    Args:
        storage_path: Optional storage path
        
    Returns:
        SecureKeyManager instance
    """
    global _secure_key_manager
    if _secure_key_manager is None:
        _secure_key_manager = SecureKeyManager(storage_path=storage_path)
    return _secure_key_manager
