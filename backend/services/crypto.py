"""AES-256-GCM encryption for API keys.

Key source: ``API_KEY_ENCRYPTION_KEY`` environment variable (32-byte hex).
If the env var is empty a dev-only warning is printed; a fixed dev key is used
so the application can start without configuration.
"""
import base64
import os
import warnings

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_DEV_KEY: bytes | None = None


def _get_key() -> bytes:
    global _DEV_KEY
    key_hex = os.getenv("API_KEY_ENCRYPTION_KEY", "")
    if not key_hex:
        if os.getenv("ENV", "development").lower() == "production":
            raise RuntimeError(
                "API_KEY_ENCRYPTION_KEY must be set when ENV=production"
            )
        if _DEV_KEY is None:
            warnings.warn(
                "API_KEY_ENCRYPTION_KEY is not set — using a DEV-only key. "
                "Set this env var to a 32-byte hex string in production.",
                RuntimeWarning,
                stacklevel=2,
            )
            _DEV_KEY = b"\x00" * 32
        return _DEV_KEY
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be hexadecimal") from exc
    if len(key) != 32:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must contain exactly 32 bytes")
    return key


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM, return base64( nonce ‖ ciphertext )."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt(encrypted: str) -> str:
    """Decrypt a string produced by :func:`encrypt`."""
    key = _get_key()
    data = base64.b64decode(encrypted)
    nonce, ct = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
