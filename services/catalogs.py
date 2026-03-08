import pandas as pd

from utils.storage import ARCHIVO_EXCEL_REFERENCIA, cargar_gastos, cargar_sueldos

PROVEEDORES_DEFAULT = [
    "Proveedor de carne",
    "Verdulería",
    "Bebidas",
    "Limpieza e higiene",
    "Gas",
    "Supermercado",
    "Fiambrería",
    "Panadería",
    "Otro",
]
CATEGORIAS_GASTO = ["Insumos", "Servicios", "Mantenimiento", "Limpieza", "Otros"]
EMPLEADOS_DEFAULT = ["Cocina", "Mozo/a", "Cajero/a", "Limpieza", "Encargado/a", "Otro"]


def _columna_por_nombre(df: pd.DataFrame, nombre: str) -> str | None:
    nombre_limpio = nombre.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == nombre_limpio:
            return c
    return None


def _valores_unicos_texto(serie: pd.Series) -> list[str]:
    out = set()
    for v in serie.dropna():
        s = str(v).strip()
        if s:
            out.add(s)
    return sorted(out)


def cargar_proveedores_desde_excel() -> list[str]:
    if not ARCHIVO_EXCEL_REFERENCIA.exists():
        return PROVEEDORES_DEFAULT.copy()
    try:
        todos = set()
        for hoja in ("Egresos", "Proveedores"):
            try:
                df = pd.read_excel(ARCHIVO_EXCEL_REFERENCIA, sheet_name=hoja)
                if df.empty:
                    continue
                col = _columna_por_nombre(df, "Proveedor")
                if col is not None:
                    todos.update(_valores_unicos_texto(df[col]))
            except Exception:
                continue
        if todos:
            return sorted(todos) + ["Otro"]
    except Exception:
        pass
    return PROVEEDORES_DEFAULT.copy()


def cargar_empleados_desde_excel() -> list[str]:
    if not ARCHIVO_EXCEL_REFERENCIA.exists():
        return []
    try:
        df = pd.read_excel(ARCHIVO_EXCEL_REFERENCIA, sheet_name="Sueldos")
        if df.empty:
            return []
        col = _columna_por_nombre(df, "Empleado")
        if col is None:
            return []
        valores = _valores_unicos_texto(df[col])
        return valores if valores else []
    except Exception:
        return []


def lista_proveedores() -> list[str]:
    desde_excel = cargar_proveedores_desde_excel()
    df_g = cargar_gastos()
    if not df_g.empty and "proveedor" in df_g.columns:
        usados = _valores_unicos_texto(df_g["proveedor"])
        desde_excel = sorted(set(desde_excel) | set(usados))
    if "Otro" not in desde_excel:
        desde_excel.append("Otro")
    return desde_excel


def lista_empleados() -> list[str]:
    desde_excel = cargar_empleados_desde_excel()
    df_s = cargar_sueldos()
    usados = _valores_unicos_texto(df_s["empleado"]) if not df_s.empty and "empleado" in df_s.columns else []
    combinado = sorted(set(EMPLEADOS_DEFAULT) | set(desde_excel) | set(usados))
    if "Otro" not in combinado:
        combinado.append("Otro")
    return combinado
