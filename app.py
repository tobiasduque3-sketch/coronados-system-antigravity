"""
Coronados - Sistema de gestion
UI simplificada para una pequena empresa familiar.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from services.auth import (
    ADMIN_ROLES,
    ASSIGNABLE_ROLES,
    ROLE_ADMIN,
    ROLE_ADMIN_OWNER,
    ROLE_CAJA,
    ROLE_MANAGER,
    ROLE_OWNER,
    authenticate_user,
    create_user,
    delete_user,
    ensure_default_users,
    list_users,
    reset_password,
    set_user_active,
)
from services.audit import get_audit_logs, log_event
from services.business import calcular_total_turno, generar_reporte_excel, ingresos_cierres
from services.catalogs import CATEGORIAS_GASTO, lista_empleados, lista_proveedores
from utils.backup_tools import create_db_backup, list_db_backups, restore_db_backup
from utils.database import DB_PATH, ensure_database
from utils.storage import (
    ARCHIVO_EXCEL_REFERENCIA,
    cargar_cierres,
    cargar_gastos,
    cargar_pedidosya,
    cargar_sueldos,
    cargar_transferencias,
    guardar_cierre,
    guardar_gastos,
    guardar_pedidosya,
    guardar_sueldos,
    guardar_transferencias,
)

st.set_page_config(
    page_title="Coronados",
    page_icon=":fork_and_knife_with_plate:",
    layout="wide",
    initial_sidebar_state="expanded",
)

NOMBRE_APP = "Coronados"
PAGINA_INICIO = "Inicio"
PAGINA_OPERACION = "Operacion diaria"
PAGINA_HISTORIAL = "Historial"
PAGINA_PERSONAL = "Personal"
PAGINA_ADMIN = "Administracion"
METODOS_PAGO = ["Efectivo", "Posnet", "Transferencia"]
TIPOS_OTROS_INGRESOS = ["Pedidos Ya", "Transferencia"]
PAGINAS_TODAS = [PAGINA_INICIO, PAGINA_OPERACION, PAGINA_HISTORIAL, PAGINA_PERSONAL, PAGINA_ADMIN]
ROL_PAGINAS = {
    ROLE_CAJA: [PAGINA_INICIO, PAGINA_OPERACION, PAGINA_HISTORIAL],
    ROLE_MANAGER: [PAGINA_INICIO, PAGINA_OPERACION, PAGINA_HISTORIAL, PAGINA_PERSONAL],
    ROLE_ADMIN_OWNER: PAGINAS_TODAS,
    ROLE_ADMIN: PAGINAS_TODAS,
    ROLE_OWNER: PAGINAS_TODAS,
}

st.markdown(
    """
<style>
.main-header { font-size: 2.2rem !important; font-weight: 700; color: #1a472a; margin-bottom: 0.2rem; }
.sub-header { font-size: 1rem; color: #47624d; margin-bottom: 1.2rem; }
div[data-testid="stMetricValue"] { font-size: 1.7rem !important; font-weight: 700; }
</style>
""",
    unsafe_allow_html=True,
)


def _allowed_pages_for_role(role: str) -> list[str]:
    return ROL_PAGINAS.get(role, [PAGINA_INICIO])


def _is_admin(role: str | None) -> bool:
    return role in ADMIN_ROLES


def _can_manage_personal(role: str | None) -> bool:
    return role in {ROLE_MANAGER, ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER}


def _can_manage_gastos(role: str | None) -> bool:
    return role in {ROLE_MANAGER, ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER}


def _can_edit_history(role: str | None) -> bool:
    return role in {ROLE_MANAGER, ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER}


def _currency(value: float) -> str:
    return f"$ {float(value):,.2f}"


def _go_to(page: str) -> None:
    st.session_state["nav_page"] = page
    st.rerun()


def _sum_column(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _today_df(df: pd.DataFrame, column: str = "fecha") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df.iloc[0:0].copy() if not df.empty else df
    fechas = pd.to_datetime(df[column], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    return df.loc[fechas.dt.normalize() == hoy].copy()


def _render_title(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="main-header">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{subtitle}</div>', unsafe_allow_html=True)


def _render_login_screen() -> None:
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        _render_title(NOMBRE_APP, "Acceso al sistema")
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contrasena", type="password")
            submitted = st.form_submit_button("Ingresar", use_container_width=True)
        if submitted:
            auth = authenticate_user(username, password)
            if auth:
                log_event(auth["username"], "login", "auth", "Inicio de sesion exitoso")
                st.session_state["auth_user"] = auth["username"]
                st.session_state["auth_role"] = auth["role"]
                st.session_state["nav_page"] = PAGINA_INICIO
                st.rerun()
            log_event(username, "login_failed", "auth", "Credenciales invalidas")
            st.error("Usuario o contrasena incorrectos")


def _render_inicio(role: str, user: str) -> None:
    _render_title("Inicio", "Resumen del dia y accesos rapidos")
    
    # Date Filtering
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        date_filter = st.selectbox(
            "Filtrar por",
            ["Hoy", "Esta Semana", "Este Mes", "Todo el historial"],
            index=0,
        )
    
    df_cierres = cargar_cierres()
    df_gastos = cargar_gastos()
    df_sueldos = cargar_sueldos()

    from services.business import filtrar_por_semana, filtrar_por_mes
    import pandas as pd
    
    if date_filter == "Hoy":
        cierres_filtered = _today_df(df_cierres)
        gastos_filtered = _today_df(df_gastos)
        sueldos_filtered = _today_df(df_sueldos)
    elif date_filter == "Esta Semana":
        cierres_filtered = filtrar_por_semana(df_cierres, "fecha")
        gastos_filtered = filtrar_por_semana(df_gastos, "fecha")
        sueldos_filtered = filtrar_por_semana(df_sueldos, "fecha")
    elif date_filter == "Este Mes":
        cierres_filtered = filtrar_por_mes(df_cierres, "fecha")
        gastos_filtered = filtrar_por_mes(df_gastos, "fecha")
        sueldos_filtered = filtrar_por_mes(df_sueldos, "fecha")
    else:
        cierres_filtered = df_cierres
        gastos_filtered = df_gastos
        sueldos_filtered = df_sueldos

    ventas = ingresos_cierres(cierres_filtered)
    gastos = _sum_column(gastos_filtered, "monto")
    sueldos = _sum_column(sueldos_filtered, "monto")
    neto = ventas - gastos - sueldos
    caja_esperada = _sum_column(cierres_filtered, "efectivo_neto")

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Ventas ({date_filter})", _currency(ventas))
    m2.metric(f"Gastos ({date_filter})", _currency(gastos))
    m3.metric(f"Neto ({date_filter})", _currency(neto))
    m4.metric(f"Caja esperada ({date_filter})", _currency(caja_esperada))

    st.markdown("---")
    
    # Charts and Alerts
    c1, c2 = st.columns([1.5, 1])
    with c1:
        st.subheader("Visualizacion")
        chart_data = pd.DataFrame(
            {
                "Categoria": ["Ventas", "Gastos", "Sueldos", "Neto"],
                "Monto": [ventas, gastos, sueldos, neto],
            }
        )
        st.bar_chart(chart_data, x="Categoria", y="Monto", use_container_width=True)

    with c2:
        st.subheader("Alertas")
        alertas = []
        cierres_hoy = _today_df(df_cierres)
        if cierres_hoy.empty:
            alertas.append("Todavia no hay cierres cargados hoy.")
        if _can_manage_gastos(role) and _today_df(df_gastos).empty:
            alertas.append("No hay gastos registrados hoy.")
        if not cierres_hoy.empty and "valor_z" in cierres_hoy.columns:
            invalido = pd.to_numeric(cierres_hoy["valor_z"], errors="coerce").fillna(0) <= 0
            if bool(invalido.any()):
                alertas.append("Hay cierres de hoy sin valor Z valido.")
        if alertas:
            for alerta in alertas:
                st.warning(alerta)
        else:
            st.success("Sin alertas importantes.")
            
        st.subheader("Acciones rapidas")
        if st.button("Abrir operacion diaria", use_container_width=True):
            _go_to(PAGINA_OPERACION)
        if st.button("Ver historial", use_container_width=True):
            _go_to(PAGINA_HISTORIAL)
        if _can_manage_personal(role):
            if st.button("Abrir personal", use_container_width=True):
                _go_to(PAGINA_PERSONAL)
        if _is_admin(role):
            if st.button("Abrir administracion", use_container_width=True):
                _go_to(PAGINA_ADMIN)
        st.info(f"Usuario: {user} | Rol: {role}")


def _render_form_cierre(current_user: str) -> None:
    st.subheader("Cierre de caja")
    df_c = cargar_cierres()
    if not df_c.empty:
        with st.expander("Ultimos cierres"):
            st.dataframe(df_c.tail(10)[["fecha", "turno", "total_turno"]], use_container_width=True)
    with st.form("form_cierre", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            turno = st.selectbox("Turno", ["Manana", "Tarde", "Noche", "Dia completo"], index=0)
            inicio_caja = st.number_input("Inicio de caja", min_value=0.0, value=0.0, step=100.0, format="%.2f")
            efectivo = st.number_input("Efectivo", min_value=0.0, value=0.0, step=50.0, format="%.2f")
            gastos = st.number_input("Gastos desde caja", min_value=0.0, value=0.0, step=50.0, format="%.2f")
        with c2:
            posnet = st.number_input("Posnet", min_value=0.0, value=0.0, step=50.0, format="%.2f")
            transferencias = st.number_input("Transferencias", min_value=0.0, value=0.0, step=50.0, format="%.2f")
            pedidosya = st.number_input("Pedidos Ya", min_value=0.0, value=0.0, step=50.0, format="%.2f")
            valor_z = st.number_input("Valor Z", min_value=0.0, value=0.0, step=1.0, format="%.0f")
        submitted = st.form_submit_button("Guardar cierre", use_container_width=True)
    if submitted:
        if valor_z <= 0:
            st.warning("El valor Z debe ser mayor a 0.")
            return
        efectivo_neto = efectivo - gastos
        total_turno = calcular_total_turno(efectivo, posnet, transferencias, pedidosya, gastos, inicio_caja)
        row = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "turno": turno,
            "inicio_caja": inicio_caja,
            "efectivo": efectivo,
            "posnet": posnet,
            "transferencias": transferencias,
            "pedidosya": pedidosya,
            "gastos": gastos,
            "efectivo_neto": efectivo_neto,
            "total_turno": total_turno,
            "valor_z": valor_z,
        }
        df_c = pd.concat([df_c, pd.DataFrame([row])], ignore_index=True)
        guardar_cierre(df_c)
        log_event(current_user, "create", "cierres", "Cierre guardado")
        st.success("Cierre guardado correctamente.")
        st.rerun()


def _render_form_gasto(current_user: str) -> None:
    st.subheader("Gasto del dia")
    proveedor_otro = ""
    c1, c2, c3 = st.columns(3)
    with c1:
        proveedor = st.selectbox("Proveedor", options=lista_proveedores(), key="op_proveedor")
        if proveedor == "Otro":
            proveedor_otro = st.text_input("Nombre del proveedor", key="op_proveedor_otro")
    with c2:
        monto = st.number_input("Monto", min_value=0.0, value=0.0, step=50.0, format="%.2f", key="op_monto_gasto")
    with c3:
        categoria = st.selectbox("Categoria", options=CATEGORIAS_GASTO, key="op_categoria_gasto")
    if st.button("Guardar gasto", type="primary", use_container_width=True):
        nombre = (proveedor_otro or "").strip() if proveedor == "Otro" else proveedor
        if proveedor == "Otro" and not nombre:
            st.warning("Escriba el nombre del proveedor.")
            return
        if monto <= 0:
            st.warning("El monto debe ser mayor a 0.")
            return
        df_g = cargar_gastos()
        row = {"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "proveedor": nombre or "Sin nombre", "monto": monto, "categoria": categoria}
        df_g = pd.concat([df_g, pd.DataFrame([row])], ignore_index=True)
        guardar_gastos(df_g)
        log_event(current_user, "create", "gastos", "Gasto guardado")
        st.success("Gasto guardado correctamente.")
        st.rerun()


def _render_form_otros_ingresos(current_user: str) -> None:
    st.subheader("Otros ingresos")
    tipo = st.selectbox("Tipo", options=TIPOS_OTROS_INGRESOS, key="op_tipo_otro")
    c1, c2 = st.columns(2)
    with c1:
        fecha_mov = st.date_input("Fecha", value=date.today(), key="op_fecha_otro")
        monto = st.number_input("Monto", min_value=0.0, value=0.0, step=50.0, format="%.2f", key="op_monto_otro")
    with c2:
        if tipo == "Pedidos Ya":
            metodo = st.selectbox("Metodo de pago", options=METODOS_PAGO, key="op_metodo_otro")
            comentario = st.text_area("Comentario", key="op_comentario_py", height=90)
        else:
            alias_app = st.text_input("Alias o app", key="op_alias_otro")
            comentario = st.text_area("Comentario", key="op_comentario_tr", height=90)
    if st.button("Guardar otro ingreso", type="primary", use_container_width=True):
        if monto <= 0:
            st.warning("El monto debe ser mayor a 0.")
            return
        if tipo == "Pedidos Ya":
            df_py = cargar_pedidosya()
            row = {"fecha": fecha_mov.strftime("%Y-%m-%d"), "monto": monto, "metodo_pago": metodo, "comentarios": (comentario or "").strip()}
            df_py = pd.concat([df_py, pd.DataFrame([row])], ignore_index=True)
            guardar_pedidosya(df_py)
            log_event(current_user, "create", "pedidosya", "Registro creado")
        else:
            df_tr = cargar_transferencias()
            row = {"fecha": fecha_mov.strftime("%Y-%m-%d"), "alias_app": (alias_app or "").strip(), "monto": monto, "comentario": (comentario or "").strip()}
            df_tr = pd.concat([df_tr, pd.DataFrame([row])], ignore_index=True)
            guardar_transferencias(df_tr)
            log_event(current_user, "create", "transferencias", "Registro creado")
        st.success("Ingreso guardado correctamente.")
        st.rerun()


def _render_operacion_diaria(role: str, current_user: str) -> None:
    _render_title("Operacion diaria", "Las tareas mas usadas del dia")
    
    tab_names = ["Cierre de caja", "Otros ingresos"]
    if _can_manage_gastos(role):
        tab_names.insert(1, "Gastos")
        
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        _render_form_cierre(current_user)
        
    if _can_manage_gastos(role):
        with tabs[1]:
            _render_form_gasto(current_user)
        with tabs[2]:
            _render_form_otros_ingresos(current_user)
    else:
        with tabs[1]:
            _render_form_otros_ingresos(current_user)

def _render_historial_cierres(editable: bool, current_user: str) -> None:
    df_c = cargar_cierres()
    st.subheader("Cierres")
    if df_c.empty:
        st.info("No hay cierres guardados.")
        return
    st.dataframe(df_c.sort_values("fecha", ascending=False), use_container_width=True)
    if not editable:
        return
    ids = df_c.sort_values("fecha", ascending=False).index.tolist()
    idx = st.selectbox("Seleccionar cierre", options=ids, format_func=lambda i: f"{df_c.loc[i, 'fecha']} - {df_c.loc[i, 'turno']}")
    fila = df_c.loc[idx]
    with st.form("edit_cierre_hist"):
        c1, c2 = st.columns(2)
        with c1:
            turnos = ["Manana", "Tarde", "Noche", "Dia completo"]
            turno = st.selectbox("Turno", options=turnos, index=turnos.index(str(fila.get("turno", turnos[0]))) if str(fila.get("turno", turnos[0])) in turnos else 0)
            inicio = st.number_input("Inicio de caja", min_value=0.0, value=float(fila.get("inicio_caja", 0) or 0), step=100.0, format="%.2f")
            efectivo = st.number_input("Efectivo", min_value=0.0, value=float(fila.get("efectivo", 0) or 0), step=50.0, format="%.2f")
            gastos = st.number_input("Gastos", min_value=0.0, value=float(fila.get("gastos", 0) or 0), step=50.0, format="%.2f")
        with c2:
            posnet = st.number_input("Posnet", min_value=0.0, value=float(fila.get("posnet", 0) or 0), step=50.0, format="%.2f")
            transf = st.number_input("Transferencias", min_value=0.0, value=float(fila.get("transferencias", 0) or 0), step=50.0, format="%.2f")
            pedidos = st.number_input("Pedidos Ya", min_value=0.0, value=float(fila.get("pedidosya", 0) or 0), step=50.0, format="%.2f")
            valor_z = st.number_input("Valor Z", min_value=0.0, value=float(fila.get("valor_z", 0) or 0), step=1.0, format="%.0f")
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button("Guardar cambios", use_container_width=True)
        borrar = b2.form_submit_button("Eliminar cierre", use_container_width=True)
    if guardar:
        if valor_z <= 0:
            st.warning("El valor Z debe ser mayor a 0.")
        else:
            df_c.loc[idx] = {
                "fecha": fila["fecha"],
                "turno": turno,
                "inicio_caja": inicio,
                "efectivo": efectivo,
                "posnet": posnet,
                "transferencias": transf,
                "pedidosya": pedidos,
                "gastos": gastos,
                "efectivo_neto": efectivo - gastos,
                "total_turno": calcular_total_turno(efectivo, posnet, transf, pedidos, gastos, inicio),
                "valor_z": valor_z,
            }
            guardar_cierre(df_c)
            log_event(current_user, "edit", "cierres", "Cierre actualizado")
            st.success("Cierre actualizado.")
            st.rerun()
    if borrar:
        df_c = df_c.drop(idx).reset_index(drop=True)
        guardar_cierre(df_c)
        log_event(current_user, "delete", "cierres", "Cierre eliminado")
        st.success("Cierre eliminado.")
        st.rerun()


def _render_historial_gastos(editable: bool, current_user: str) -> None:
    df_g = cargar_gastos()
    st.subheader("Gastos")
    if df_g.empty:
        st.info("No hay gastos cargados.")
        return
    st.dataframe(df_g.sort_values("fecha", ascending=False), use_container_width=True)
    if not editable:
        return
    ids = df_g.sort_values("fecha", ascending=False).index.tolist()
    idx = st.selectbox("Seleccionar gasto", options=ids, format_func=lambda i: f"{df_g.loc[i, 'fecha']} - {df_g.loc[i, 'proveedor']}")
    fila = df_g.loc[idx]
    with st.form("edit_gasto_hist"):
        fecha_val = pd.to_datetime(fila.get("fecha"), errors="coerce")
        fecha_edit = st.date_input("Fecha", value=fecha_val.date() if pd.notna(fecha_val) else date.today())
        proveedor = st.text_input("Proveedor", value=str(fila.get("proveedor", "")))
        monto = st.number_input("Monto", min_value=0.0, value=float(fila.get("monto", 0) or 0), step=50.0, format="%.2f")
        categoria = st.selectbox("Categoria", options=CATEGORIAS_GASTO, index=CATEGORIAS_GASTO.index(str(fila.get("categoria", CATEGORIAS_GASTO[0]))) if str(fila.get("categoria", CATEGORIAS_GASTO[0])) in CATEGORIAS_GASTO else 0)
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button("Guardar cambios", use_container_width=True)
        borrar = b2.form_submit_button("Eliminar gasto", use_container_width=True)
    if guardar:
        if monto <= 0:
            st.warning("El monto debe ser mayor a 0.")
        else:
            df_g.loc[idx] = {"fecha": fecha_edit.strftime("%Y-%m-%d"), "proveedor": (proveedor or "Sin nombre").strip(), "monto": monto, "categoria": categoria}
            guardar_gastos(df_g)
            log_event(current_user, "edit", "gastos", "Gasto actualizado")
            st.success("Gasto actualizado.")
            st.rerun()
    if borrar:
        df_g = df_g.drop(idx).reset_index(drop=True)
        guardar_gastos(df_g)
        log_event(current_user, "delete", "gastos", "Gasto eliminado")
        st.success("Gasto eliminado.")
        st.rerun()


def _render_historial_otros(editable: bool, current_user: str) -> None:
    subtipo = st.radio("Tipo de ingreso", options=TIPOS_OTROS_INGRESOS, horizontal=True)
    if subtipo == "Pedidos Ya":
        df = cargar_pedidosya()
        st.subheader("Pedidos Ya")
        if df.empty:
            st.info("No hay registros cargados.")
            return
        st.dataframe(df.sort_values("fecha", ascending=False), use_container_width=True)
        if not editable:
            return
        ids = df.sort_values("fecha", ascending=False).index.tolist()
        idx = st.selectbox("Seleccionar registro", options=ids, format_func=lambda i: f"{df.loc[i, 'fecha']} - {_currency(df.loc[i, 'monto'])}", key="hist_py")
        fila = df.loc[idx]
        with st.form("edit_py_hist"):
            fecha_val = pd.to_datetime(fila.get("fecha"), errors="coerce")
            fecha_edit = st.date_input("Fecha", value=fecha_val.date() if pd.notna(fecha_val) else date.today(), key="py_fecha_hist")
            monto = st.number_input("Monto", min_value=0.0, value=float(fila.get("monto", 0) or 0), step=50.0, format="%.2f", key="py_monto_hist")
            metodo = st.selectbox("Metodo de pago", options=METODOS_PAGO, index=METODOS_PAGO.index(str(fila.get("metodo_pago", METODOS_PAGO[0]))) if str(fila.get("metodo_pago", METODOS_PAGO[0])) in METODOS_PAGO else 0, key="py_metodo_hist")
            comentario = st.text_area("Comentario", value=str(fila.get("comentarios", "")), key="py_com_hist")
            b1, b2 = st.columns(2)
            guardar = b1.form_submit_button("Guardar cambios", use_container_width=True)
            borrar = b2.form_submit_button("Eliminar registro", use_container_width=True)
        if guardar:
            if monto <= 0:
                st.warning("El monto debe ser mayor a 0.")
            else:
                df.loc[idx] = {"fecha": fecha_edit.strftime("%Y-%m-%d"), "monto": monto, "metodo_pago": metodo, "comentarios": (comentario or "").strip()}
                guardar_pedidosya(df)
                log_event(current_user, "edit", "pedidosya", "Registro actualizado")
                st.success("Registro actualizado.")
                st.rerun()
        if borrar:
            df = df.drop(idx).reset_index(drop=True)
            guardar_pedidosya(df)
            log_event(current_user, "delete", "pedidosya", "Registro eliminado")
            st.success("Registro eliminado.")
            st.rerun()
    else:
        df = cargar_transferencias()
        st.subheader("Transferencias")
        if df.empty:
            st.info("No hay registros cargados.")
            return
        st.dataframe(df.sort_values("fecha", ascending=False), use_container_width=True)
        if not editable:
            return
        ids = df.sort_values("fecha", ascending=False).index.tolist()
        idx = st.selectbox("Seleccionar registro", options=ids, format_func=lambda i: f"{df.loc[i, 'fecha']} - {_currency(df.loc[i, 'monto'])}", key="hist_tr")
        fila = df.loc[idx]
        with st.form("edit_tr_hist"):
            fecha_val = pd.to_datetime(fila.get("fecha"), errors="coerce")
            fecha_edit = st.date_input("Fecha", value=fecha_val.date() if pd.notna(fecha_val) else date.today(), key="tr_fecha_hist")
            alias_app = st.text_input("Alias o app", value=str(fila.get("alias_app", "")), key="tr_alias_hist")
            monto = st.number_input("Monto", min_value=0.0, value=float(fila.get("monto", 0) or 0), step=50.0, format="%.2f", key="tr_monto_hist")
            comentario = st.text_area("Comentario", value=str(fila.get("comentario", "")), key="tr_com_hist")
            b1, b2 = st.columns(2)
            guardar = b1.form_submit_button("Guardar cambios", use_container_width=True)
            borrar = b2.form_submit_button("Eliminar registro", use_container_width=True)
        if guardar:
            if monto <= 0:
                st.warning("El monto debe ser mayor a 0.")
            else:
                df.loc[idx] = {"fecha": fecha_edit.strftime("%Y-%m-%d"), "alias_app": (alias_app or "").strip(), "monto": monto, "comentario": (comentario or "").strip()}
                guardar_transferencias(df)
                log_event(current_user, "edit", "transferencias", "Registro actualizado")
                st.success("Registro actualizado.")
                st.rerun()
        if borrar:
            df = df.drop(idx).reset_index(drop=True)
            guardar_transferencias(df)
            log_event(current_user, "delete", "transferencias", "Registro eliminado")
            st.success("Registro eliminado.")
            st.rerun()


def _render_historial(role: str, current_user: str) -> None:
    _render_title("Historial", "Revision de registros y correcciones")
    editable = _can_edit_history(role)
    
    tab_names = ["Cierres", "Otros ingresos"]
    if _can_manage_gastos(role):
        tab_names.insert(1, "Gastos")
        
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        _render_historial_cierres(editable, current_user)
        
    if _can_manage_gastos(role):
        with tabs[1]:
            _render_historial_gastos(editable, current_user)
        with tabs[2]:
            _render_historial_otros(editable, current_user)
    else:
        with tabs[1]:
            _render_historial_otros(editable, current_user)


def _render_personal(current_user: str) -> None:
    _render_title("Personal", "Empleados y sueldos")
    empleados = lista_empleados()
    c1, c2 = st.columns(2)
    with c1:
        empleado = st.selectbox("Empleado", options=empleados, key="personal_empleado")
        otro = st.text_input("Nombre del empleado", key="personal_otro") if empleado == "Otro" else ""
    with c2:
        monto = st.number_input("Monto pagado", min_value=0.0, value=0.0, step=100.0, format="%.2f", key="personal_monto")
    if st.button("Registrar pago", type="primary", use_container_width=True):
        nombre = (otro or "").strip() if empleado == "Otro" else empleado
        if empleado == "Otro" and not nombre:
            st.warning("Escriba el nombre del empleado.")
            return
        if monto <= 0:
            st.warning("El monto debe ser mayor a 0.")
            return
        df_s = cargar_sueldos()
        row = {"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "empleado": nombre, "monto": monto}
        df_s = pd.concat([df_s, pd.DataFrame([row])], ignore_index=True)
        guardar_sueldos(df_s)
        log_event(current_user, "create", "sueldos", "Pago de sueldo guardado")
        st.success("Pago registrado.")
        st.rerun()
    st.markdown("---")
    df_s = cargar_sueldos()
    if df_s.empty:
        st.info("No hay pagos registrados.")
        return
    st.dataframe(df_s.sort_values("fecha", ascending=False), use_container_width=True)
    ids = df_s.sort_values("fecha", ascending=False).index.tolist()
    idx = st.selectbox("Seleccionar pago", options=ids, format_func=lambda i: f"{df_s.loc[i, 'fecha']} - {df_s.loc[i, 'empleado']}")
    fila = df_s.loc[idx]
    with st.form("edit_sueldo_hist"):
        fecha_val = pd.to_datetime(fila.get("fecha"), errors="coerce")
        fecha_edit = st.date_input("Fecha", value=fecha_val.date() if pd.notna(fecha_val) else date.today())
        empleado_edit = st.selectbox("Empleado", options=empleados, index=empleados.index(str(fila.get("empleado", empleados[0]))) if str(fila.get("empleado", empleados[0])) in empleados else 0)
        monto_edit = st.number_input("Monto", min_value=0.0, value=float(fila.get("monto", 0) or 0), step=100.0, format="%.2f")
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button("Guardar cambios", use_container_width=True)
        borrar = b2.form_submit_button("Eliminar pago", use_container_width=True)
    if guardar:
        if monto_edit <= 0:
            st.warning("El monto debe ser mayor a 0.")
        else:
            df_s.loc[idx] = {"fecha": fecha_edit.strftime("%Y-%m-%d"), "empleado": empleado_edit, "monto": monto_edit}
            guardar_sueldos(df_s)
            log_event(current_user, "edit", "sueldos", "Pago de sueldo actualizado")
            st.success("Pago actualizado.")
            st.rerun()
    if borrar:
        df_s = df_s.drop(idx).reset_index(drop=True)
        guardar_sueldos(df_s)
        log_event(current_user, "delete", "sueldos", "Pago eliminado")
        st.success("Pago eliminado.")
        st.rerun()

def _render_admin_users(current_user: str) -> None:
    st.subheader("Gestion de usuarios")
    df_users = list_users()
    if df_users.empty:
        st.info("No hay usuarios cargados.")
    else:
        df_show = df_users.copy()
        df_show["activo"] = df_show["is_active"].apply(lambda x: "Si" if int(x) == 1 else "No")
        st.dataframe(df_show[["username", "role", "activo", "created_at"]], use_container_width=True)
    with st.form("create_user_form"):
        st.markdown("**Crear usuario**")
        username = st.text_input("Usuario")
        password = st.text_input("Contrasena", type="password")
        role = st.selectbox("Rol", options=sorted(ASSIGNABLE_ROLES))
        if st.form_submit_button("Crear usuario"):
            ok, msg = create_user(username, password, role, actor_username=current_user)
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
            if ok:
                st.rerun()
    if not df_users.empty:
        usuarios = df_users["username"].tolist()
        with st.form("reset_user_pass"):
            st.markdown("**Resetear contrasena**")
            objetivo = st.selectbox("Usuario", options=usuarios, key="reset_user")
            nueva = st.text_input("Nueva contrasena", type="password")
            if st.form_submit_button("Resetear contrasena"):
                ok, msg = reset_password(objetivo, nueva, actor_username=current_user)
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)
        with st.form("user_state_form"):
            st.markdown("**Estado y eliminacion**")
            objetivo = st.selectbox("Usuario objetivo", options=usuarios, key="state_user")
            accion = st.selectbox("Accion", options=["Desactivar", "Activar", "Eliminar"])
            confirmar = st.checkbox("Confirmar eliminacion permanente", value=False)
            if st.form_submit_button("Aplicar accion"):
                if objetivo == current_user:
                    st.warning("No puede aplicar esta accion sobre su usuario actual.")
                elif accion == "Eliminar" and not confirmar:
                    st.warning("Debe confirmar la eliminacion permanente para continuar.")
                else:
                    if accion == "Desactivar":
                        ok, msg = set_user_active(objetivo, False, actor_username=current_user)
                    elif accion == "Activar":
                        ok, msg = set_user_active(objetivo, True, actor_username=current_user)
                    else:
                        ok, msg = delete_user(objetivo, actor_username=current_user)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)
                    if ok:
                        st.rerun()


def _render_admin_backups(current_user: str) -> None:
    st.subheader("Respaldo y restauracion")
    if st.button("Crear respaldo", type="primary", use_container_width=True):
        try:
            backup_path = create_db_backup(username=current_user)
            st.success(f"Respaldo creado: {backup_path.name}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo crear el respaldo: {exc}")
    backups = list_db_backups()
    if not backups:
        st.info("No hay respaldos disponibles.")
        return
    selected = st.selectbox("Respaldo disponible", options=[p.name for p in backups])
    confirmar = st.checkbox("Confirmo que quiero restaurar este respaldo")
    if st.button("Restaurar respaldo", use_container_width=True):
        if not confirmar:
            st.warning("Debe confirmar la restauracion.")
        else:
            ok, msg = restore_db_backup(selected, username=current_user)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
            if ok:
                st.rerun()


def _render_admin_logs() -> None:
    st.subheader("Registro de actividad")
    logs_all = get_audit_logs()
    if logs_all.empty:
        st.info("No hay eventos registrados.")
        return
    usuarios = ["Todos"] + sorted(logs_all["username"].dropna().astype(str).unique().tolist())
    modulos = ["Todos"] + sorted(logs_all["module"].dropna().astype(str).unique().tolist())
    acciones = ["Todos"] + sorted(logs_all["action_type"].dropna().astype(str).unique().tolist())
    f1, f2, f3 = st.columns(3)
    with f1:
        usuario = st.selectbox("Usuario", options=usuarios)
    with f2:
        modulo = st.selectbox("Modulo", options=modulos)
    with f3:
        accion = st.selectbox("Accion", options=acciones)
    d1, d2 = st.columns(2)
    with d1:
        desde = st.date_input("Desde", value=date.today() - timedelta(days=30))
    with d2:
        hasta = st.date_input("Hasta", value=date.today())
    if desde > hasta:
        st.warning("La fecha Desde no puede ser mayor que Hasta.")
        return
    logs = get_audit_logs(
        username=None if usuario == "Todos" else usuario,
        module=None if modulo == "Todos" else modulo,
        action_type=None if accion == "Todos" else accion,
        date_from=desde,
        date_to=hasta,
    )
    if logs.empty:
        st.info("No hay eventos para el filtro seleccionado.")
    else:
        st.dataframe(logs, use_container_width=True)


def _render_admin_config() -> None:
    st.subheader("Configuracion")
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"Base de datos: {DB_PATH.name}")
        st.info(f"Excel de referencia: {ARCHIVO_EXCEL_REFERENCIA.name}")
        st.info(f"Excel disponible: {'Si' if ARCHIVO_EXCEL_REFERENCIA.exists() else 'No'}")
    with c2:
        st.write("Permisos vigentes")
        st.write("- Caja: operacion diaria e historial basico")
        st.write("- Manager: operacion, historial y personal")
        st.write("- Owner/Admin: acceso completo")


def _render_administracion(current_user: str, current_role: str) -> None:
    if not _is_admin(current_role):
        st.error("No tiene permisos para esta seccion.")
        st.stop()
    _render_title("Administracion", "Herramientas avanzadas")
    herramienta = st.selectbox("Herramienta", options=["Gestion de usuarios", "Respaldo y restauracion", "Registro de actividad", "Configuracion"])
    st.markdown("---")
    if herramienta == "Gestion de usuarios":
        _render_admin_users(current_user)
    elif herramienta == "Respaldo y restauracion":
        _render_admin_backups(current_user)
    elif herramienta == "Registro de actividad":
        _render_admin_logs()
    else:
        _render_admin_config()


def main() -> None:
    ensure_database()
    created_defaults = ensure_default_users()
    if "auth_user" not in st.session_state:
        st.session_state["auth_user"] = None
    if "auth_role" not in st.session_state:
        st.session_state["auth_role"] = None
    if not st.session_state.get("auth_user"):
        if created_defaults:
            st.info("Usuarios iniciales creados: owner/owner123, manager/manager123, caja/caja123")
        _render_login_screen()
        return

    current_user = st.session_state["auth_user"]
    current_role = st.session_state["auth_role"]
    allowed_pages = _allowed_pages_for_role(current_role)
    if "nav_page" not in st.session_state or st.session_state["nav_page"] not in allowed_pages:
        st.session_state["nav_page"] = allowed_pages[0]

    with st.sidebar:
        st.title(NOMBRE_APP)
        st.caption(f"Usuario: {current_user}")
        st.caption(f"Rol: {current_role}")
        if st.button("Cerrar sesion", use_container_width=True):
            st.session_state["auth_user"] = None
            st.session_state["auth_role"] = None
            st.session_state["nav_page"] = PAGINA_INICIO
            st.rerun()
        st.markdown("---")
        
        # Use a separate key to avoid Streamlit session state bound variable exceptions
        selected_page_index = allowed_pages.index(st.session_state["nav_page"]) if st.session_state["nav_page"] in allowed_pages else 0
        pagina = st.radio("Ir a", options=allowed_pages, index=selected_page_index, key="nav_radio")
        if pagina != st.session_state["nav_page"]:
            st.session_state["nav_page"] = pagina
            st.rerun()

    if st.session_state["nav_page"] == PAGINA_INICIO:
        _render_inicio(current_role, current_user)
    elif st.session_state["nav_page"] == PAGINA_OPERACION:
        _render_operacion_diaria(current_role, current_user)
    elif st.session_state["nav_page"] == PAGINA_HISTORIAL:
        _render_historial(current_role, current_user)
    elif st.session_state["nav_page"] == PAGINA_PERSONAL:
        if not _can_manage_personal(current_role):
            st.error("No tiene permisos para esta seccion.")
            st.stop()
        _render_personal(current_user)
    elif st.session_state["nav_page"] == PAGINA_ADMIN:
        _render_administracion(current_user, current_role)

    with st.sidebar:
        st.markdown("---")
        excel_bytes = generar_reporte_excel()
        st.download_button(
            "Descargar reporte",
            data=excel_bytes,
            file_name=f"reporte_coronados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
