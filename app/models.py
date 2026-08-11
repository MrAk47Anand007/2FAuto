from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    role: str
    is_active: bool


@dataclass(frozen=True)
class OtpEntry:
    id: int
    portal_name: str
    display_name: str
    secret: str
    period: int
    is_active: bool
