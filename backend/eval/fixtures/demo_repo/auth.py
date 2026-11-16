"""Token based authentication helpers."""

import hashlib
import hmac
import time

SECRET = "demo-secret"
TOKEN_TTL_SECONDS = 900


def create_token(user_id: str, now: int | None = None) -> str:
    """Build a signed token that expires after TOKEN_TTL_SECONDS."""
    issued = now or int(time.time())
    payload = f"{user_id}:{issued + TOKEN_TTL_SECONDS}"
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def validate_token(token: str, now: int | None = None) -> str | None:
    """Return the user id when the signature and expiry are valid."""
    try:
        user_id, expires, signature = token.split(":")
    except ValueError:
        return None

    payload = f"{user_id}:{expires}"
    expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    if int(expires) < (now or int(time.time())):
        return None
    return user_id


def hash_password(password: str, salt: str) -> str:
    """Derive a password hash with PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
