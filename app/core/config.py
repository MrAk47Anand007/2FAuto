import os
import sys
import pyotp
from dotenv import load_dotenv

load_dotenv()


class Settings:
    API_KEY: str
    OTP_SECRET: str
    HOST: str
    PORT: int
    ENABLE_DOCS: bool

    def __init__(self) -> None:
        self.API_KEY = os.getenv("API_KEY", "")
        self.OTP_SECRET = os.getenv("OTP_SECRET", "")
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "8000"))
        self.ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"

        self._validate()

    def _validate(self) -> None:
        missing = []
        if not self.API_KEY:
            missing.append("API_KEY")
        if not self.OTP_SECRET:
            missing.append("OTP_SECRET")

        if missing:
            print(
                f"[FATAL] Missing required environment variables: {', '.join(missing)}. "
                "Set them in your .env file and restart."
            )
            sys.exit(1)

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
