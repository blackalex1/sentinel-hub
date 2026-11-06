import pytest
from core.security import SecurityManager

def test_generate_key():
    key = SecurityManager.generate_key()
    assert isinstance(key, str)
    assert len(key) == 64  # Hex representation of 32 bytes

def test_encrypt_decrypt_string():
    key = SecurityManager.generate_key()
    original_text = "Hello, MonitHome Secure World!"
    
    encrypted = SecurityManager.encrypt(original_text, key)
    assert isinstance(encrypted, str)
    assert encrypted != original_text
    
    decrypted = SecurityManager.decrypt(encrypted, key)
    assert decrypted == original_text

def test_encrypt_decrypt_bytes():
    key = SecurityManager.generate_key()
    original_bytes = b"Some raw binary data \x00\x01\x02"
    
    encrypted = SecurityManager.encrypt_bytes(original_bytes, key)
    assert isinstance(encrypted, str)
    
    decrypted = SecurityManager.decrypt_bytes(encrypted, key)
    assert decrypted == original_bytes

def test_decrypt_invalid_key_or_data():
    key1 = SecurityManager.generate_key()
    key2 = SecurityManager.generate_key()
    original_text = "Sensitive data"
    
    encrypted = SecurityManager.encrypt(original_text, key1)
    
    # Decrypt with wrong key should return None
    decrypted = SecurityManager.decrypt(encrypted, key2)
    assert decrypted is None
    
    # Decrypt garbled data should return None
    decrypted_garbled = SecurityManager.decrypt("invalid_base64_data!!!", key1)
    assert decrypted_garbled is None
