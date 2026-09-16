import base64
import binascii
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

ENCRYPTION_VERSION = 1
NONCE_LENGTH = 12


class SecretEncryptionError(ValueError):
    """Raised when a portal secret cannot be encrypted or authenticated."""


def _key(key_version: str | None = None) -> bytes:
    encoded_key = settings.SECRET_ENCRYPTION_KEY
    if key_version and key_version != settings.SECRET_ENCRYPTION_KEY_VERSION:
        try:
            configured_keys = json.loads(settings.SECRET_ENCRYPTION_KEYS or "{}")
            encoded_key = configured_keys[key_version]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SecretEncryptionError("Secret encryption key version is unavailable") from exc
    if not encoded_key:
        raise SecretEncryptionError("Secret encryption is not configured")
    try:
        key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise SecretEncryptionError("Secret encryption key is invalid") from exc
    if len(key) != 32:
        raise SecretEncryptionError("Secret encryption key must contain 32 bytes")
    return key


def _associated_data(portal_name: str, encryption_version: int) -> bytes:
    return f"2FAuto:otp_entries:{encryption_version}:{portal_name}".encode("utf-8")


def encrypt_secret(secret: str, portal_name: str) -> dict[str, str | int]:
    """Encrypt one portal seed and return storage-safe encoded fields."""
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = AESGCM(_key()).encrypt(
        nonce,
        secret.encode("utf-8"),
        _associated_data(portal_name, ENCRYPTION_VERSION),
    )
    return {
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "encryption_version": ENCRYPTION_VERSION,
        "key_version": settings.SECRET_ENCRYPTION_KEY_VERSION,
    }


def decrypt_secret(
    ciphertext: str | None,
    nonce: str | None,
    portal_name: str,
    encryption_version: int | None,
    key_version: str | None,
) -> str:
    """Authenticate and decrypt one portal seed for the OTP service only."""
    if (
        not ciphertext
        or not nonce
        or encryption_version != ENCRYPTION_VERSION
        or not key_version
    ):
        raise SecretEncryptionError("Secret encryption metadata is invalid")
    try:
        decoded_ciphertext = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        decoded_nonce = base64.urlsafe_b64decode(nonce.encode("ascii"))
        if len(decoded_nonce) != NONCE_LENGTH:
            raise SecretEncryptionError("Secret encryption nonce is invalid")
        plaintext = AESGCM(_key(key_version)).decrypt(
            decoded_nonce,
            decoded_ciphertext,
            _associated_data(portal_name, encryption_version),
        )
        return plaintext.decode("utf-8")
    except (
        ValueError,
        UnicodeEncodeError,
        UnicodeDecodeError,
        binascii.Error,
        InvalidTag,
    ) as exc:
        raise SecretEncryptionError("Secret decryption failed") from exc
