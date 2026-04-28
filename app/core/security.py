"""AES-256 encryption utilities for sensitive data."""
import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


class AESCipher:
    """AES-256 encryption/decryption utility."""

    def __init__(self, key: str):
        """Initialize with a 32-byte key."""
        if len(key) != 32:
            # Derive 32 bytes from key using SHA256
            import hashlib
            key = hashlib.sha256(key.encode()).digest()
        self.key = key.encode() if isinstance(key, str) else key

    def _pad(self, data: bytes) -> bytes:
        """Pad data to 16-byte block size."""
        padder = padding.PKCS7(128).padder()
        return padder.update(data) + padder.finalize()

    def _unpad(self, data: bytes) -> bytes:
        """Remove padding."""
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(data) + unpadder.finalize()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return base64-encoded ciphertext."""
        iv = os.urandom(16)
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        padded = self._pad(plaintext.encode('utf-8'))
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        # Prepend IV to ciphertext
        combined = iv + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted: str) -> str:
        """Decrypt base64-encoded ciphertext and return plaintext."""
        try:
            combined = base64.b64decode(encrypted.encode('utf-8'))
            iv = combined[:16]
            ciphertext = combined[16:]
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            return self._unpad(padded).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    @staticmethod
    def generate_key() -> str:
        """Generate a random 32-byte key."""
        return base64.b64encode(os.urandom(32)).decode('utf-8')


def get_cipher():
    """Get AESCipher instance using ENCRYPTION_KEY from settings."""
    from app.config import settings
    return AESCipher(settings.ENCRYPTION_KEY)


def encrypt_data(data: str) -> str:
    """Encrypt data using AES-256."""
    return get_cipher().encrypt(data)


def decrypt_data(encrypted: str) -> str:
    """Decrypt data using AES-256."""
    return get_cipher().decrypt(encrypted)