from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from utils.database import ensure_database, get_connection


def log_event(username: str | None, action_type: str, module: str, details: str = "") -> None:
    ensure_database()
    user = (username or "system").strip() or "system"
    action = (action_type or "").strip()
    mod = (module or "").strip()
    det = (details or "").strip()[:500]

    if not action or not mod:
        return

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (timestamp, username, action_type, module, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user,
                action,
                mod,
                det,
            ),
        )


def get_audit_logs(
    username: str | None = None,
    module: str | None = None,
    action_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    ensure_database()

    where = []
    params: list[object] = []

    if username:
        where.append("username = ?")
        params.append(username)
    if module:
        where.append("module = ?")
        params.append(module)
    if action_type:
        where.append("action_type = ?")
        params.append(action_type)
    if date_from:
        where.append("date(timestamp) >= date(?)")
        params.append(date_from.strftime("%Y-%m-%d"))
    if date_to:
        where.append("date(timestamp) <= date(?)")
        params.append(date_to.strftime("%Y-%m-%d"))

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT timestamp, username, action_type, module, details
        FROM audit_logs
        {where_sql}
        ORDER BY timestamp DESC, id DESC
    """

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return pd.DataFrame(columns=["timestamp", "username", "action_type", "module", "details"])
    return df
