from pathlib import Path
import pandas as pd
from utils.database import TABLE_COLUMNS, ensure_database, read_table, replace_table

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "coronados.db"

ARCHIVO_CIERRES = BASE_DIR / "cierres.csv"
ARCHIVO_GASTOS = BASE_DIR / "gastos.csv"
ARCHIVO_SUELDOS = BASE_DIR / "sueldos.csv"
ARCHIVO_PEDIDOSYA = BASE_DIR / "pedidosya.csv"
ARCHIVO_TRANSFERENCIAS = BASE_DIR / "transferencias.csv"
ARCHIVO_EXCEL_REFERENCIA = BASE_DIR / "Administracion Coronados.xlsx"


def cargar_csv(ruta: Path, columnas: list[str] | None = None) -> pd.DataFrame:
    ruta = Path(ruta)
    if ruta.exists():
        try:
            return pd.read_csv(ruta, encoding="utf-8")
        except Exception:
            pass
    return pd.DataFrame(columns=columnas if columnas else [])


def guardar_csv(df: pd.DataFrame, ruta: Path) -> None:
    ruta = Path(ruta)
    df.to_csv(ruta, index=False, encoding="utf-8")


def _cargar_tabla(table_name: str) -> pd.DataFrame:
    ensure_database()
    return read_table(table_name)


def _guardar_tabla(table_name: str, df: pd.DataFrame) -> None:
    ensure_database()
    replace_table(table_name, df)


def cargar_cierres() -> pd.DataFrame:
    df = _cargar_tabla("cierres")
    if "valor_z" not in df.columns:
        df["valor_z"] = ""
    return df[TABLE_COLUMNS["cierres"]]


def guardar_cierre(df: pd.DataFrame) -> None:
    _guardar_tabla("cierres", df)


def cargar_gastos() -> pd.DataFrame:
    return _cargar_tabla("gastos")


def guardar_gastos(df: pd.DataFrame) -> None:
    _guardar_tabla("gastos", df)


def cargar_pedidosya() -> pd.DataFrame:
    return _cargar_tabla("pedidosya")


def guardar_pedidosya(df: pd.DataFrame) -> None:
    _guardar_tabla("pedidosya", df)


def cargar_transferencias() -> pd.DataFrame:
    return _cargar_tabla("transferencias")


def guardar_transferencias(df: pd.DataFrame) -> None:
    _guardar_tabla("transferencias", df)


def cargar_sueldos() -> pd.DataFrame:
    return _cargar_tabla("sueldos")


def guardar_sueldos(df: pd.DataFrame) -> None:
    _guardar_tabla("sueldos", df)
