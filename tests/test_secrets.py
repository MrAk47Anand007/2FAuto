import json

import pytest


def test_secret_authentication_binds_ciphertext_to_portal(client):
    from app.core.secrets import (
        SecretEncryptionError,
        decrypt_secret,
        encrypt_secret,
    )

    encrypted = encrypt_secret("JBSWY3DPEHPK3PXP", "portal-a")

    assert (
        decrypt_secret(
            encrypted["ciphertext"],
            encrypted["nonce"],
            "portal-a",
            encrypted["encryption_version"],
            encrypted["key_version"],
        )
        == "JBSWY3DPEHPK3PXP"
    )

    with pytest.raises(SecretEncryptionError):
        decrypt_secret(
            encrypted["ciphertext"],
            encrypted["nonce"],
            "portal-b",
            encrypted["encryption_version"],
            encrypted["key_version"],
        )

    tampered = encrypted["ciphertext"][:-2] + "AA"
    with pytest.raises(SecretEncryptionError):
        decrypt_secret(
            tampered,
            encrypted["nonce"],
            "portal-a",
            encrypted["encryption_version"],
            encrypted["key_version"],
        )


def test_secret_rotation_is_bounded_and_resumable(client):
    from app.core import config
    from app.core.database import create_otp_entry, get_db
    from app.core.secrets import decrypt_secret
    from app.services.secrets import rotate_portal_secrets

    old_key = config.settings.SECRET_ENCRYPTION_KEY
    create_otp_entry(
        "rotating-portal",
        "Rotating Portal",
        "JBSWY3DPEHPK3PXP",
        30,
        1,
    )
    config.settings.SECRET_ENCRYPTION_KEY = (
        "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    )
    config.settings.SECRET_ENCRYPTION_KEY_VERSION = "v2"
    config.settings.SECRET_ENCRYPTION_KEYS = json.dumps({"v1": old_key})

    result = rotate_portal_secrets(batch_size=1, after_id=0)
    assert result["processed"] == 1
    assert result["last_id"] > 0

    with get_db() as db:
        row = db.execute(
            """
            SELECT secret_ciphertext, secret_nonce, encryption_version, key_version
            FROM otp_entries WHERE portal_name = ?
            """,
            ("rotating-portal",),
        ).fetchone()
    assert row["key_version"] == "v2"
    assert (
        decrypt_secret(
            row["secret_ciphertext"],
            row["secret_nonce"],
            "rotating-portal",
            row["encryption_version"],
            row["key_version"],
        )
        == "JBSWY3DPEHPK3PXP"
    )
