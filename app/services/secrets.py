from app.core.config import settings
from app.core.database import get_db
from app.core.secrets import decrypt_secret, encrypt_secret


def rotate_portal_secrets(batch_size: int = 100, after_id: int = 0) -> dict[str, int]:
    """Rotate a bounded batch and return a cursor for the next invocation."""
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    processed = 0
    last_id = after_id
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, portal_name, secret_ciphertext, secret_nonce,
                   encryption_version, key_version
            FROM otp_entries
            WHERE id > ?
              AND secret_ciphertext IS NOT NULL
              AND key_version != ?
            ORDER BY id
            LIMIT ?
            """,
            (after_id, settings.SECRET_ENCRYPTION_KEY_VERSION, batch_size),
        ).fetchall()
        for row in rows:
            plaintext = decrypt_secret(
                row["secret_ciphertext"],
                row["secret_nonce"],
                row["portal_name"],
                row["encryption_version"],
                row["key_version"],
            )
            encrypted = encrypt_secret(plaintext, row["portal_name"])
            db.execute(
                """
                UPDATE otp_entries
                SET secret_ciphertext = ?, secret_nonce = ?,
                    encryption_version = ?, key_version = ?
                WHERE id = ?
                """,
                (
                    encrypted["ciphertext"],
                    encrypted["nonce"],
                    encrypted["encryption_version"],
                    encrypted["key_version"],
                    row["id"],
                ),
            )
            processed += 1
            last_id = row["id"]
    return {"processed": processed, "last_id": last_id}
