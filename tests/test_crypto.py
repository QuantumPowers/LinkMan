"""Tests for crypto module."""

import pytest

from linkman.shared.crypto.aead import AEADCipher, AEADType
from linkman.shared.crypto.keys import KeyManager, KeyPair, generate_identity


class TestAEADType:
    """Test AEADType enum."""

    def test_key_sizes(self):
        assert AEADType.AES_128_GCM.key_size == 16
        assert AEADType.AES_256_GCM.key_size == 32
        assert AEADType.CHACHA20_POLY1305.key_size == 32

    def test_nonce_size(self):
        for cipher_type in AEADType:
            assert cipher_type.nonce_size == 12

    def test_tag_size(self):
        for cipher_type in AEADType:
            assert cipher_type.tag_size == 16


class TestAEADCipher:
    """Test AEADCipher."""

    @pytest.mark.parametrize("cipher_type", list(AEADType))
    def test_encrypt_decrypt(self, cipher_type: AEADType):
        key = AEADCipher.generate_key(cipher_type)
        salt = AEADCipher.generate_salt(cipher_type)
        
        cipher = AEADCipher(cipher_type, key, salt)
        
        plaintext = b"Hello, World!"
        encrypted = cipher.encrypt_packet(plaintext)
        
        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)

    @pytest.mark.parametrize("cipher_type", list(AEADType))
    def test_roundtrip(self, cipher_type: AEADType):
        key = AEADCipher.generate_key(cipher_type)
        salt = AEADCipher.generate_salt(cipher_type)
        
        cipher = AEADCipher(cipher_type, key, salt)
        
        plaintext = b"Test message for roundtrip"
        encrypted = cipher.encrypt_packet(plaintext)
        
        cipher2 = AEADCipher(cipher_type, key, salt)
        decrypted, remaining = cipher2.decrypt_packet(encrypted)
        
        assert decrypted == plaintext
        assert remaining == b""

    def test_invalid_key_size(self):
        with pytest.raises(ValueError):
            AEADCipher(AEADType.AES_256_GCM, b"short", b"salt12345678901")

    def test_large_payload(self):
        key = AEADCipher.generate_key(AEADType.AES_256_GCM)
        salt = AEADCipher.generate_salt(AEADType.AES_256_GCM)
        
        cipher = AEADCipher(AEADType.AES_256_GCM, key, salt)
        
        large_payload = b"x" * 16384
        
        with pytest.raises(ValueError):
            cipher.encrypt_packet(large_payload)


class TestKeyManager:
    """Test KeyManager."""

    def test_generate_master_key(self):
        key = KeyManager.generate_master_key()
        assert len(key) == 32
        
        key_16 = KeyManager.generate_master_key(16)
        assert len(key_16) == 16

    def test_master_key_properties(self):
        km = KeyManager()
        
        assert len(km.master_key) == 32
        assert len(km.master_key_hex) == 64
        assert len(km.master_key_base64) > 0

    def test_from_hex(self):
        original = KeyManager()
        restored = KeyManager.from_hex(original.master_key_hex)
        
        assert restored.master_key == original.master_key

    def test_from_base64(self):
        original = KeyManager()
        restored = KeyManager.from_base64(original.master_key_base64)
        
        assert restored.master_key == original.master_key

    def test_derive_subkey(self):
        km = KeyManager()
        salt = b"salt123456789012"
        
        subkey1 = km.derive_subkey(salt)
        subkey2 = km.derive_subkey(salt)
        
        assert subkey1 == subkey2
        assert subkey1 != km.master_key

    def test_session_key(self):
        km = KeyManager()
        
        key1 = km.generate_session_key("session1")
        key2 = km.generate_session_key("session2")
        
        assert key1 != key2
        assert km.get_session_key("session1") == key1
        assert km.get_session_key("nonexistent") is None

    def test_derive_from_password(self):
        km = KeyManager.derive_from_password("password123")
        
        assert len(km.master_key) == 32
        
        km2 = KeyManager.derive_from_password("password123", salt=b"fixed_salt_here")
        km3 = KeyManager.derive_from_password("password123", salt=b"fixed_salt_here")
        
        assert km2.master_key == km3.master_key


class TestKeyPair:
    """Test KeyPair."""

    def test_to_from_base64(self):
        pair = KeyPair(
            client_salt=b"client_salt_1234",
            server_salt=b"server_salt_4567",
        )
        
        encoded = pair.to_base64()
        restored = KeyPair.from_base64(encoded)
        
        assert restored.client_salt == pair.client_salt
        assert restored.server_salt == pair.server_salt


class TestIdentity:
    """Test identity functions."""

    def test_generate_identity(self):
        identity1 = generate_identity()
        identity2 = generate_identity()
        
        assert identity1 != identity2
        assert len(identity1) > 0
