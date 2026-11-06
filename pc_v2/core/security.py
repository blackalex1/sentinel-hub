import os
import binascii
from Crypto.Cipher import AES
import logging

logger = logging.getLogger("Security")

class SecurityManager:
    @staticmethod
    def generate_key() -> str:
        """Генерация 256-битного AES ключа (HEX строка)"""
        return binascii.hexlify(os.urandom(32)).decode()

    @staticmethod
    def encrypt_bytes(data: bytes, key_hex: str) -> str:
        """Шифрование байтовых данных AES-GCM"""
        try:
            key_bytes = binascii.unhexlify(key_hex)
            cipher = AES.new(key_bytes, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(data)
            nonce = cipher.nonce
            # Формат: nonce (16 байт) + tag (16 байт) + ciphertext
            full_data = nonce + tag + ciphertext
            import base64
            return base64.b64encode(full_data).decode('ascii')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None

    @staticmethod
    def decrypt_bytes(encrypted_b64: str, key_hex: str) -> bytes:
        """Расшифровка бинарных данных AES-GCM"""
        try:
            import base64
            key_bytes = binascii.unhexlify(key_hex)
            full_data = base64.b64decode(encrypted_b64)
            nonce = full_data[:16]
            tag = full_data[16:32]
            ciphertext = full_data[32:]
            
            cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

    @staticmethod
    def encrypt(data: str, key_hex: str) -> str:
        return SecurityManager.encrypt_bytes(data.encode('utf-8'), key_hex)

    @staticmethod
    def decrypt(encrypted_b64: str, key_hex: str) -> str:
        decrypted = SecurityManager.decrypt_bytes(encrypted_b64, key_hex)
        return decrypted.decode('utf-8') if decrypted else None
