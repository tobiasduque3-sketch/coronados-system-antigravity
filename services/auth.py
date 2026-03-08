from __future__ import annotations

import hashlib
import secrets
from typing import Any

from utils.database import get_connection

ROLE_ADMIN_OWNER = "admin/owner"
ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_CAJA = "caja"
VALID_ROLES = {ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER, ROLE_MANAGER, ROLE_CAJA}


def _hash_password(password: str, salt: str | None = None) -> str:
    salt_hex = salt or secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations_s, salt_hex, digest = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_s),
        ).hex()
        return secrets.compare_digest(check, digest)
    except Exception:
        return False


def ensure_default_users() -> bool:
    """Create initial users on first run. Returns True if users were created."""
    defaults = [
        ("owner", "owner123", ROLE_ADMIN_OWNER),
        ("manager", "manager123", ROLE_MANAGER),
        ("caja", "caja123", ROLE_CAJA),
    ]

    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            return False

        for username, password, role in defaults:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, _hash_password(password), role),
            )
    return True


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    username = (username or "").strip()
    if not username or not password:
        return None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not row:
        return None
    user = {
        "username": row[0],
        "password_hash": row[1],
        "role": row[2],
        "is_active": row[3],
    }
    if not user["is_active"] or user["role"] not in VALID_ROLES:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return {"username": user["username"], "role": user["role"]}
