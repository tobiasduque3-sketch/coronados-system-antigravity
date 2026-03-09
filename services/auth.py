from __future__ import annotations

import hashlib
import secrets
from typing import Any

import pandas as pd

from services.audit import log_event
from utils.database import ensure_database, get_connection

ROLE_ADMIN_OWNER = "admin/owner"
ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_CAJA = "caja"

VALID_ROLES = {ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER, ROLE_MANAGER, ROLE_CAJA}
ASSIGNABLE_ROLES = {ROLE_ADMIN_OWNER, ROLE_MANAGER, ROLE_CAJA}
ADMIN_ROLES = {ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER}


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


def _count_active_admin_users(conn) -> int:
    placeholders = ",".join(["?"] * len(ADMIN_ROLES))
    sql = f"SELECT COUNT(*) FROM users WHERE is_active = 1 AND role IN ({placeholders})"
    return int(conn.execute(sql, tuple(ADMIN_ROLES)).fetchone()[0])


def ensure_default_users() -> bool:
    """Create initial users on first run. Returns True if users were created."""
    defaults = [
        ("owner", "owner123", ROLE_ADMIN_OWNER),
        ("manager", "manager123", ROLE_MANAGER),
        ("caja", "caja123", ROLE_CAJA),
    ]

    ensure_database()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            return False

        for username, password, role in defaults:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, _hash_password(password), role),
            )
    log_event("system", "create_default_users", "usuarios", "Usuarios iniciales creados")
    return True


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    username = (username or "").strip()
    if not username or not password:
        return None

    ensure_database()
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


def list_users() -> pd.DataFrame:
    ensure_database()
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT username, role, is_active, created_at FROM users ORDER BY username",
            conn,
        )
    if df.empty:
        return pd.DataFrame(columns=["username", "role", "is_active", "created_at"])
    return df


def create_user(username: str, password: str, role: str, actor_username: str | None = None) -> tuple[bool, str]:
    username = (username or "").strip()
    if not username:
        return False, "Usuario requerido."
    if len(password or "") < 4:
        return False, "Contrasena minima: 4 caracteres."
    if role not in ASSIGNABLE_ROLES:
        return False, "Rol invalido."

    ensure_database()
    try:
        with get_connection() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                return False, "El usuario ya existe."
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
                (username, _hash_password(password), role),
            )
    except Exception as exc:
        return False, f"No se pudo crear el usuario: {exc}"

    log_event(actor_username, "create", "usuarios", f"Usuario creado: {username} ({role})")
    return True, "Usuario creado."


def reset_password(username: str, new_password: str, actor_username: str | None = None) -> tuple[bool, str]:
    username = (username or "").strip()
    if not username:
        return False, "Usuario requerido."
    if len(new_password or "") < 4:
        return False, "Contrasena minima: 4 caracteres."

    ensure_database()
    try:
        with get_connection() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if not exists:
                return False, "Usuario no encontrado."
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (_hash_password(new_password), username),
            )
    except Exception as exc:
        return False, f"No se pudo actualizar la contrasena: {exc}"

    log_event(actor_username, "password_reset", "usuarios", f"Password reseteada: {username}")
    return True, "Contrasena actualizada."


def set_user_active(username: str, is_active: bool, actor_username: str | None = None) -> tuple[bool, str]:
    username = (username or "").strip()
    if not username:
        return False, "Usuario requerido."

    ensure_database()
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT role, is_active FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                return False, "Usuario no encontrado."

            target_role = str(row[0])
            target_active = int(row[1]) == 1
            if not is_active and target_active and target_role in ADMIN_ROLES:
                if _count_active_admin_users(conn) <= 1:
                    return False, "No puede desactivar el ultimo usuario admin/owner activo."

            conn.execute(
                "UPDATE users SET is_active = ? WHERE username = ?",
                (1 if is_active else 0, username),
            )
    except Exception as exc:
        return False, f"No se pudo actualizar el estado del usuario: {exc}"

    action = "reactivate" if is_active else "deactivate"
    log_event(actor_username, action, "usuarios", f"Usuario: {username}")
    return True, "Estado de usuario actualizado."


def delete_user(username: str, actor_username: str | None = None) -> tuple[bool, str]:
    username = (username or "").strip()
    if not username:
        return False, "Usuario requerido."

    ensure_database()
    try:
        with get_connection() as conn:
            row = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return False, "Usuario no encontrado."

            target_role = str(row[0])
            if target_role in ADMIN_ROLES and _count_active_admin_users(conn) <= 1:
                return False, "No puede eliminar el ultimo usuario admin/owner activo."

            conn.execute("DELETE FROM users WHERE username = ?", (username,))
    except Exception as exc:
        return False, f"No se pudo eliminar el usuario: {exc}"

    log_event(actor_username, "delete", "usuarios", f"Usuario eliminado: {username}")
    return True, "Usuario eliminado."
