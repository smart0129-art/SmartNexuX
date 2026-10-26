import asyncio
import hashlib
import hmac
import ipaddress
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from app.services.conversation_store import ConversationStore


PASSWORD_HASH_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, encoded_hash: str | None) -> bool:
    if encoded_hash is None:
        hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes(16),
            PASSWORD_HASH_ITERATIONS,
        )
        return False

    try:
        algorithm, iterations_text, salt_hex, expected_hash_hex = encoded_hash.split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(expected_hash_hex)
    except ValueError:
        return False
    if (
        algorithm != "pbkdf2_sha256"
        or not 1 <= iterations <= 2_000_000
        or len(salt) != 16
        or len(expected_hash) != 32
    ):
        return False
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_hash, expected_hash)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    issuer: str
    subject: str
    email: str | None
    display_name: str
    role: str = "user"
    must_change_password: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def get_current_user(request: Request) -> AuthenticatedUser:
    session_user_id = request.session.get("user_id")
    if not isinstance(session_user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required",
        )

    store: ConversationStore = request.app.state.conversation_store
    user = await asyncio.to_thread(store.get_user, session_user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The signed-in account is no longer available",
        )
    role = str(user.get("role") or "user")
    must_change_password = bool(user.get("must_change_password"))
    await asyncio.to_thread(store.touch_user_last_seen, session_user_id)
    return AuthenticatedUser(
        id=str(user["id"]),
        issuer=str(user["issuer"]),
        subject=str(user["subject"]),
        email=user["email"],
        display_name=str(user["display_name"]),
        role=role,
        must_change_password=must_change_password,
    )


def allowed_frontend_origins() -> tuple[str, ...]:
    value = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000",
    )
    return tuple(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())


def is_allowed_frontend_origin(origin: str | None, configured_origins: tuple[str, ...]) -> bool:
    if origin is None:
        return False
    normalized_origin = origin.strip().rstrip("/")
    if normalized_origin in configured_origins:
        return True

    try:
        parsed = urlparse(normalized_origin)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
