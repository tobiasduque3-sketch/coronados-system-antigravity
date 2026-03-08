from pathlib import Path

import pandas as pd

from utils.database import TABLE_COLUMNS, ensure_database, import_if_table_empty, replace_table, table_is_empty
from utils.storage import (
    ARCHIVO_CIERRES,
    ARCHIVO_GASTOS,
    ARCHIVO_PEDIDOSYA,
    ARCHIVO_SUELDOS,
    ARCHIVO_TRANSFERENCIAS,
)

CSV_TO_TABLE = {
    "cierres": ARCHIVO_CIERRES,
    "gastos": ARCHIVO_GASTOS,
    "sueldos": ARCHIVO_SUELDOS,
    "pedidosya": ARCHIVO_PEDIDOSYA,
    "transferencias": ARCHIVO_TRANSFERENCIAS,
}


def _leer_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)

    try:
        df = pd.read_csv(path, encoding="utf-8")
    except Exception:
        df = pd.read_csv(path)

    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def migrate_csv_to_sqlite(force: bool = False) -> None:
    ensure_database()

    for table_name, csv_path in CSV_TO_TABLE.items():
        columns = TABLE_COLUMNS[table_name]
        df_csv = _leer_csv(csv_path, columns)

        if df_csv.empty:
            print(f"[skip] {table_name}: no CSV data at {csv_path.name}")
            continue

        if force:
            replace_table(table_name, df_csv)
            print(f"[ok] {table_name}: imported {len(df_csv)} rows (force)")
            continue

        if table_is_empty(table_name):
            import_if_table_empty(table_name, df_csv)
            print(f"[ok] {table_name}: imported {len(df_csv)} rows")
        else:
            print(f"[skip] {table_name}: table already has data")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Migrate CSV files to coronados.db")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing DB table contents with CSV data.",
    )
    args = parser.parse_args()

    migrate_csv_to_sqlite(force=args.force)


if __name__ == "__main__":
    main()
