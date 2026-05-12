import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from hmac import compare_digest

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request

from app.config import get_settings


ph = PasswordHasher()
SESSION_TTL = timedelta(days=30)


def _signing_key() -> bytes:
    settings = get_settings()
    material = settings.session_secret or settings.app_pin_hash or settings.app_pin or "codex-fast-trade-local"
    return hashlib.sha256(material.encode("utf-8")).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def verify_pin(pin: str) -> bool:
    settings = get_settings()
    if settings.app_pin_hash:
        try:
            return ph.verify(settings.app_pin_hash, pin)
        except VerifyMismatchError:
            return False
    if settings.app_pin:
        return compare_digest(settings.app_pin, pin)
    return False


def create_session() -> str:
    payload = {
        "exp": int((datetime.now(timezone.utc) + SESSION_TTL).timestamp()),
        "nonce": secrets.token_urlsafe(16),
    }
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_signing_key(), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"v1.{payload_part}.{_b64encode(signature)}"


def destroy_session(token: str | None) -> None:
    return None


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return False
    _, payload_part, signature_part = parts
    expected_signature = _b64encode(hmac.new(_signing_key(), payload_part.encode("ascii"), hashlib.sha256).digest())
    if not compare_digest(signature_part, expected_signature):
        return False
    try:
        payload = json.loads(_b64decode(payload_part))
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return expires_at > int(datetime.now(timezone.utc).timestamp())


def require_session(request: Request) -> None:
    if not is_valid_session(request.cookies.get("cft_session")):
        raise HTTPException(status_code=401, detail="authentication required")
