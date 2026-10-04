import asyncio
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

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
    return AuthenticatedUser(
        id=str(user["id"]),
        issuer=str(user["issuer"]),
        subject=str(user["subject"]),
        email=user["email"],
        display_name=str(user["display_name"]),
    )


def allowed_frontend_origins() -> tuple[str, ...]:
    value = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000",
    )
    return tuple(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
