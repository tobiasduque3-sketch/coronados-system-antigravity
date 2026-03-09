from pathlib import Path
import sqlite3

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "coronados.db"

TABLE_COLUMNS: dict[str, list[str]] = {
    "cierres": [
        "fecha",
        "turno",
        "inicio_caja",
        "efectivo",
        "posnet",
        "transferencias",
        "pedidosya",
        "gastos",
        "efectivo_neto",
        "total_turno",
        "valor_z",
    ],
    "gastos": ["fecha", "proveedor", "monto", "categoria"],
    "sueldos": ["fecha", "empleado", "monto"],
    "pedidosya": ["fecha", "monto", "metodo_pago", "comentarios"],
    "transferencias": ["fecha", "alias_app", "monto", "comentario"],
}

TABLE_DEFINITIONS: dict[str, list[tuple[str, str]]] = {
    "cierres": [
        ("fecha", "TEXT"),
        ("turno", "TEXT"),
        ("inicio_caja", "REAL"),
        ("efectivo", "REAL"),
        ("posnet", "REAL"),
        ("transferencias", "REAL"),
        ("pedidosya", "REAL"),
        ("gastos", "REAL"),
        ("efectivo_neto", "REAL"),
        ("total_turno", "REAL"),
        ("valor_z", "REAL"),
    ],
    "gastos": [
        ("fecha", "TEXT"),
        ("proveedor", "TEXT"),
        ("monto", "REAL"),
        ("categoria", "TEXT"),
    ],
    "sueldos": [
        ("fecha", "TEXT"),
        ("empleado", "TEXT"),
        ("monto", "REAL"),
    ],
    "pedidosya": [
        ("fecha", "TEXT"),
        ("monto", "REAL"),
        ("metodo_pago", "TEXT"),
        ("comentarios", "TEXT"),
    ],
    "transferencias": [
        ("fecha", "TEXT"),
        ("alias_app", "TEXT"),
        ("monto", "REAL"),
        ("comentario", "TEXT"),
    ],
}


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_database() -> None:
    with get_connection() as conn:
        for table_name, columns in TABLE_DEFINITIONS.items():
            column_defs = ", ".join(f"{name} {col_type}" for name, col_type in columns)
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {column_defs}
                )
                """
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                action_type TEXT NOT NULL,
                module TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ''
            )
            """
        )


def table_is_empty(table_name: str) -> bool:
    ensure_database()
    with get_connection() as conn:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
    return count == 0


def read_table(table_name: str) -> pd.DataFrame:
    ensure_database()
    columns = TABLE_COLUMNS[table_name]
    sql = f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id"
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn)
    if df.empty:
        return pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def replace_table(table_name: str, df: pd.DataFrame) -> None:
    ensure_database()
    columns = TABLE_COLUMNS[table_name]
    df_out = df.copy()
    for col in columns:
        if col not in df_out.columns:
            df_out[col] = ""
    df_out = df_out[columns]

    placeholders = ", ".join(["?"] * len(columns))
    sql_insert = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

    rows = []
    for values in df_out.itertuples(index=False, name=None):
        rows.append(tuple(None if pd.isna(v) else v for v in values))

    with get_connection() as conn:
        conn.execute(f"DELETE FROM {table_name}")
        if rows:
            conn.executemany(sql_insert, rows)


def import_if_table_empty(table_name: str, df: pd.DataFrame) -> bool:
    if table_is_empty(table_name):
        replace_table(table_name, df)
        return True
    return False
