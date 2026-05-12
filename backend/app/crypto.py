import base64
import hashlib
from itertools import cycle

from app.config import get_settings


def _key_stream() -> bytes:
    settings = get_settings()
    material = settings.session_secret or settings.app_pin_hash or settings.app_pin or "codex-fast-trade-local"
    return hashlib.sha256(material.encode("utf-8")).digest()


def protect_secret(value: str) -> str:
    raw = value.encode("utf-8")
    encrypted = bytes(byte ^ key for byte, key in zip(raw, cycle(_key_stream())))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def reveal_secret(value: str) -> str:
    encrypted = base64.urlsafe_b64decode(value.encode("ascii"))
    raw = bytes(byte ^ key for byte, key in zip(encrypted, cycle(_key_stream())))
    return raw.decode("utf-8")


def mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
