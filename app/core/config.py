import os
import sys
import base64
import binascii
import json
import platform
from pathlib import Path
import pyotp
from dotenv import load_dotenv

if os.getenv("APP_ENV", "").lower() != "packaged":
    load_dotenv()


def default_packaged_data_dir(role: str) -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("PROGRAMDATA" if role == "server" else "LOCALAPPDATA")
        if not base:
            raise ValueError("Application data directory is unavailable")
        return Path(base) / "2FAuto"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "2FAuto"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "2fauto"


class Settings:
    APP_ENV: str
    API_KEY: str
    OTP_SECRET: str
    HOST: str
    PORT: int
    ENABLE_DOCS: bool
    COOKIE_SECURE: bool
    SECRET_ENCRYPTION_KEY: str
    SECRET_ENCRYPTION_KEY_VERSION: str
    SECRET_ENCRYPTION_KEYS: str
    SESSION_IDLE_TIMEOUT_SECONDS: int
    SESSION_ABSOLUTE_TIMEOUT_SECONDS: int
    LEGACY_API_ENABLED: bool
    CLIENT_RATE_LIMIT_PER_MINUTE: int
    DATABASE_PATH: str
    SESSION_SECRET: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
    PACKAGED_DATA_DIR: str
    PACKAGED_ROLE: str

    def __init__(self) -> None:
        self.APP_ENV = os.getenv("APP_ENV", "development").lower()
        self.API_KEY = os.getenv("API_KEY", "")
        self.OTP_SECRET = os.getenv("OTP_SECRET", "")
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "8000"))
        self.ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"
        self.COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
        self.SECRET_ENCRYPTION_KEY = os.getenv("SECRET_ENCRYPTION_KEY", "")
        self.SECRET_ENCRYPTION_KEY_VERSION = os.getenv(
            "SECRET_ENCRYPTION_KEY_VERSION", "v1"
        )
        self.SECRET_ENCRYPTION_KEYS = os.getenv("SECRET_ENCRYPTION_KEYS", "")
        self.SESSION_IDLE_TIMEOUT_SECONDS = int(
            os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "900")
        )
        self.SESSION_ABSOLUTE_TIMEOUT_SECONDS = int(
            os.getenv("SESSION_ABSOLUTE_TIMEOUT_SECONDS", "28800")
        )
        self.LEGACY_API_ENABLED = os.getenv("LEGACY_API_ENABLED", "false").lower() == "true"
        self.CLIENT_RATE_LIMIT_PER_MINUTE = int(
            os.getenv("CLIENT_RATE_LIMIT_PER_MINUTE", "60")
        )
        self.PACKAGED_ROLE = os.getenv("TWOFAUTO_ROLE", "desktop-web")
        self.PACKAGED_DATA_DIR = os.getenv("TWOFAUTO_PACKAGED_DATA_DIR", "")
        if self.APP_ENV == "packaged" and not self.PACKAGED_DATA_DIR:
            self.PACKAGED_DATA_DIR = str(default_packaged_data_dir(self.PACKAGED_ROLE))
        default_database = (
            str(Path(self.PACKAGED_DATA_DIR) / "otp_service.db")
            if self.APP_ENV == "packaged" else "otp_service.db"
        )
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", default_database)
        self.SESSION_SECRET = os.getenv("SESSION_SECRET", "")
        self.ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

        self._validate()

    def _validate(self) -> None:
        missing = []
        if self.APP_ENV not in {"development", "test", "production", "packaged"}:
            missing.append("APP_ENV must be development, test, production, or packaged")
        if self.LEGACY_API_ENABLED and not self.API_KEY:
            missing.append("API_KEY")
        if not self.SESSION_SECRET and self.APP_ENV != "packaged":
            missing.append("SESSION_SECRET")
        if not self.ADMIN_PASSWORD and self.APP_ENV != "packaged":
            missing.append("ADMIN_PASSWORD")
        if not self.SECRET_ENCRYPTION_KEY and self.APP_ENV != "packaged":
            missing.append("SECRET_ENCRYPTION_KEY")

        if self.SECRET_ENCRYPTION_KEY:
            try:
                encryption_key = base64.urlsafe_b64decode(
                    self.SECRET_ENCRYPTION_KEY.encode("ascii")
                )
                if len(encryption_key) != 32:
                    missing.append("SECRET_ENCRYPTION_KEY must contain 32 bytes")
            except (ValueError, UnicodeEncodeError, binascii.Error):
                missing.append("SECRET_ENCRYPTION_KEY must be URL-safe base64")
        if not self.SECRET_ENCRYPTION_KEY_VERSION:
            missing.append("SECRET_ENCRYPTION_KEY_VERSION")
        if self.SECRET_ENCRYPTION_KEYS:
            try:
                configured_keys = json.loads(self.SECRET_ENCRYPTION_KEYS)
                if not isinstance(configured_keys, dict):
                    raise ValueError
                for encoded_key in configured_keys.values():
                    decoded_key = base64.urlsafe_b64decode(str(encoded_key).encode("ascii"))
                    if len(decoded_key) != 32:
                        raise ValueError
            except (ValueError, TypeError, UnicodeEncodeError, binascii.Error, json.JSONDecodeError):
                missing.append("SECRET_ENCRYPTION_KEYS must map versions to 32-byte URL-safe base64 keys")
        if self.SESSION_IDLE_TIMEOUT_SECONDS <= 0:
            missing.append("SESSION_IDLE_TIMEOUT_SECONDS must be positive")
        if self.SESSION_ABSOLUTE_TIMEOUT_SECONDS <= 0:
            missing.append("SESSION_ABSOLUTE_TIMEOUT_SECONDS must be positive")
        if (
            self.SESSION_IDLE_TIMEOUT_SECONDS
            >= self.SESSION_ABSOLUTE_TIMEOUT_SECONDS
        ):
            missing.append("SESSION_IDLE_TIMEOUT_SECONDS must be below absolute timeout")
        if self.CLIENT_RATE_LIMIT_PER_MINUTE <= 0:
            missing.append("CLIENT_RATE_LIMIT_PER_MINUTE must be positive")

        if self.APP_ENV == "production":
            sample_values = {
                "SESSION_SECRET": {"change-this-session-secret"},
                "ADMIN_PASSWORD": {"change-this-admin-password"},
                "SECRET_ENCRYPTION_KEY": {"change-this-encryption-key"},
            }
            if self.LEGACY_API_ENABLED and self.API_KEY == "your-strong-random-api-key":
                missing.append("API_KEY must not use the sample value")
            for name, values in sample_values.items():
                if getattr(self, name) in values:
                    missing.append(f"{name} must not use the sample value")
            if not self.COOKIE_SECURE:
                missing.append("COOKIE_SECURE must be true in production")
            if self.ENABLE_DOCS:
                missing.append("ENABLE_DOCS must be false in production")

        if missing:
            print(
                f"[FATAL] Missing required environment variables: {', '.join(missing)}. "
                "Set them in your .env file and restart."
            )
            sys.exit(1)

        if self.OTP_SECRET:
            try:
                totp = pyotp.TOTP(self.OTP_SECRET)
                totp.now()  # will raise if secret is not valid base32
            except Exception:
                print(
                    "[FATAL] OTP_SECRET is not a valid base32-encoded TOTP secret. "
                    "Generate one with: python -c \"import pyotp; print(pyotp.random_base32())\""
                )
                sys.exit(1)


settings = Settings()
