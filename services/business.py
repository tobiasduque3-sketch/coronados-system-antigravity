from datetime import date, timedelta
import io

import pandas as pd

from utils.storage import (
    cargar_cierres,
    cargar_gastos,
    cargar_pedidosya,
    cargar_sueldos,
    cargar_transferencias,
)


def calcular_total_turno(
    efectivo: float,
    posnet: float,
    transf: float,
    pedidosya: float,
    gastos: float,
    inicio_caja: float,
) -> float:
    ingresos = efectivo + posnet + transf + pedidosya
    return ingresos - gastos - inicio_caja


def ingresos_cierres(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return (df["efectivo"] + df["posnet"] + df["transferencias"] + df["pedidosya"]).sum()


def filtrar_por_semana(df: pd.DataFrame, col_fecha: str) -> pd.DataFrame:
    if df.empty or col_fecha not in df.columns:
        return df
    df = df.copy()
    df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    return df[(df[col_fecha].dt.date >= inicio_semana.date()) & (df[col_fecha].dt.date <= hoy.date())]


def filtrar_por_mes(df: pd.DataFrame, col_fecha: str) -> pd.DataFrame:
    if df.empty or col_fecha not in df.columns:
        return df
    df = df.copy()
    df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
    hoy = pd.Timestamp.now()
    return df[(df[col_fecha].dt.month == hoy.month) & (df[col_fecha].dt.year == hoy.year)]


def _fecha_str_a_date(s) -> date | None:
    if pd.isna(s):
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date() if hasattr(dt, "date") else dt
    except Exception:
        return None


def generar_reporte_excel() -> bytes:
    df_cierres = cargar_cierres()
    df_gastos = cargar_gastos()
    df_sueldos = cargar_sueldos()
    df_pedidosya = cargar_pedidosya()
    df_transf = cargar_transferencias()

    ingresos = ingresos_cierres(df_cierres)
    total_gastos = df_gastos["monto"].sum() if not df_gastos.empty else 0.0
    total_sueldos = df_sueldos["monto"].sum() if not df_sueldos.empty else 0.0
    ganancia_neta = ingresos - total_gastos - total_sueldos

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resumen = pd.DataFrame(
            {
                "Concepto": [
                    "Total ingresos (cierres)",
                    "Total gastos",
                    "Total sueldos",
                    "Ganancia real neta",
                ],
                "Monto": [ingresos, total_gastos, total_sueldos, ganancia_neta],
            }
        )
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        if not df_cierres.empty:
            df_cierres.to_excel(writer, sheet_name="Cierres de caja", index=False)
        if not df_gastos.empty:
            df_gastos.to_excel(writer, sheet_name="Gastos", index=False)
        if not df_sueldos.empty:
            df_sueldos.to_excel(writer, sheet_name="Sueldos", index=False)
        if not df_pedidosya.empty:
            df_pedidosya.to_excel(writer, sheet_name="Pedidos Ya", index=False)
        if not df_transf.empty:
            df_transf.to_excel(writer, sheet_name="Transferencias Alias", index=False)
    buffer.seek(0)
    return buffer.getvalue()
