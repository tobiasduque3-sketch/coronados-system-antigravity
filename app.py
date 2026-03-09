"""
Coronados - Sistema de Gestion
Cierre de caja, gastos detallados, personal y panel de control.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from services.auth import (
    ROLE_ADMIN_OWNER,
    ROLE_ADMIN,
    ROLE_OWNER,
    ROLE_CAJA,
    ROLE_MANAGER,
    ASSIGNABLE_ROLES,
    authenticate_user,
    create_user,
    delete_user,
    ensure_default_users,
    list_users,
    reset_password,
    set_user_active,
)
from services.audit import get_audit_logs, log_event
from services.business import (
    _fecha_str_a_date,
    calcular_total_turno,
    generar_reporte_excel,
    ingresos_cierres,
)
from services.catalogs import CATEGORIAS_GASTO, lista_empleados, lista_proveedores
from utils.backup_tools import create_db_backup, list_db_backups, restore_db_backup
from utils.database import ensure_database
from utils.storage import (
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

# Configuracion de pagina
st.set_page_config(
    page_title="Coronados - Gestion",
    page_icon=":fork_and_knife_with_plate:",
    layout="wide",
    initial_sidebar_state="expanded",
)

NOMBRE_RESTAURANTE = "Coronados"
METODOS_PAGO = ["Efectivo", "Posnet", "Transferencia"]

ALL_PAGES = [
    "Cierre de Caja",
    "Administrar Cierres",
    "Gastos Detallados",
    "Gestión de Personal",
    "Pedidos Ya",
    "Transferencias Alias",
    "Administración Global",
    "Gestion de Usuarios",
    "Backups y Restore",
    "Audit Logs",
    "Panel de Control (Dueño)",
]
ROLE_PAGES = {
    ROLE_ADMIN_OWNER: ALL_PAGES,
    ROLE_ADMIN: ALL_PAGES,
    ROLE_OWNER: ALL_PAGES,
    ROLE_CAJA: ["Cierre de Caja", "Pedidos Ya", "Transferencias Alias"],
    ROLE_MANAGER: ["Gastos Detallados", "Gestión de Personal", "Panel de Control (Dueño)"],
}
ADMIN_ROLES = {ROLE_ADMIN_OWNER, ROLE_ADMIN, ROLE_OWNER}
# Estilos
st.markdown(
    """
<style>
    .main-header { font-size: 2.5rem !important; font-weight: 700; color: #1a472a; text-align: center; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1.1rem; color: #2d5a3d; text-align: center; margin-bottom: 2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700; }
    .stButton > button { width: 100%; padding: 0.75rem 1.5rem; font-size: 1.1rem; font-weight: 600; border-radius: 8px; }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
</style>
""",
    unsafe_allow_html=True,
)


def _allowed_pages_for_role(role: str) -> list[str]:
    return ROLE_PAGES.get(role, [])


def _render_login_screen() -> None:
    st.markdown(f'<p class="main-header">🍽️ {NOMBRE_RESTAURANTE}</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Iniciar sesion</p>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contrasena", type="password")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        auth = authenticate_user(username, password)
        if auth:
            log_event(auth["username"], "login", "auth", "Inicio de sesion exitoso")
            st.session_state["auth_user"] = auth["username"]
            st.session_state["auth_role"] = auth["role"]
            st.rerun()
        log_event(username, "login_failed", "auth", "Credenciales invalidas")
        st.error("Usuario o contrasena incorrectos")


def main():
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

    current_user = st.session_state.get("auth_user")
    current_role = st.session_state.get("auth_role")
    allowed_pages = _allowed_pages_for_role(current_role)

    if not allowed_pages:
        st.error("Rol sin permisos configurados.")
        return

    st.markdown(f'<p class="main-header">🍽️ {NOMBRE_RESTAURANTE}</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.caption(f"Usuario: {current_user}")
        st.caption(f"Rol: {current_role}")
        if st.button("Cerrar sesion"):
            st.session_state["auth_user"] = None
            st.session_state["auth_role"] = None
            st.rerun()

        st.header("Navegación")
        pagina = st.radio(
            "Sección",
            allowed_pages,
            label_visibility="collapsed",
        )
        st.divider()
        # Resumen rapido en sidebar
        df_c = cargar_cierres()
        df_g = cargar_gastos()
        df_s = cargar_sueldos()
        if not df_c.empty:
            st.metric("Cierres", len(df_c))
        if not df_g.empty:
            st.metric("Gastos registrados", len(df_g))
        if not df_s.empty:
            st.metric("Pagos de sueldos", len(df_s))

    if pagina not in allowed_pages:
        st.error("No tiene permisos para acceder a esta sección.")
        return
    # ---------- PÃ¡gina: Cierre de Caja ----------
    if pagina == "Cierre de Caja":
        st.markdown('<p class="sub-header">Cierre de Caja</p>', unsafe_allow_html=True)
        with st.sidebar:
            if not df_c.empty:
                with st.expander("Ãšltimos cierres"):
                    st.dataframe(df_c.tail(10)[["fecha", "turno", "total_turno"]], use_container_width=True, hide_index=True)

        st.subheader("ðŸ“ Nuevo cierre de caja")
        with st.form("form_cierre", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                turno = st.selectbox("Turno", ["MaÃ±ana", "Tarde", "Noche", "DÃ­a completo"], index=0)
                inicio_caja = st.number_input("Inicio de Caja ($)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
                efectivo = st.number_input("Efectivo ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f", help="Efectivo en caja (antes de descontar gastos)")
                gastos = st.number_input("Gastos ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f", help="Gastos pagados de la caja")
            with c2:
                posnet = st.number_input("Posnet ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f")
                transferencias = st.number_input("Transferencias ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f")
                pedidosya = st.number_input("PedidosYa ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f")
                valor_z = st.number_input("Valor Z (Fiscal) *", min_value=0.0, value=0.0, step=1.0, format="%.0f", help="Obligatorio. NÃºmero del reporte Z de la mÃ¡quina fiscal.")
            if st.form_submit_button("Calcular y guardar cierre"):
                efectivo_neto = efectivo - gastos
                total_turno = calcular_total_turno(efectivo, posnet, transferencias, pedidosya, gastos, inicio_caja)
                st.session_state["pendiente_guardar"] = {
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "turno": turno, "inicio_caja": inicio_caja, "efectivo": efectivo,
                    "posnet": posnet, "transferencias": transferencias, "pedidosya": pedidosya,
                    "gastos": gastos, "efectivo_neto": efectivo_neto, "total_turno": total_turno,
                    "valor_z": valor_z,
                }

        if "pendiente_guardar" in st.session_state:
            p = st.session_state["pendiente_guardar"]
            st.success("Cierre calculado. Revisa y confirma para guardar.")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Efectivo neto (caja)", f"$ {p['efectivo_neto']:,.2f}")
            with m2:
                st.metric("Total ingresos", f"$ {p['efectivo'] + p['posnet'] + p['transferencias'] + p['pedidosya']:,.2f}")
            with m3:
                st.metric("Gastos", f"$ {p['gastos']:,.2f}")
            with m4:
                st.metric("Total de Turno", f"$ {p['total_turno']:,.2f}")
            if "valor_z" not in p:
                p["valor_z"] = 0.0
            if st.button("âœ… Guardar este cierre en el historial", type="primary"):
                df_c = cargar_cierres()
                df_c = pd.concat([df_c, pd.DataFrame([p])], ignore_index=True)
                guardar_cierre(df_c)
                del st.session_state["pendiente_guardar"]
                st.balloons()
                log_event(current_user, "create", "cierres", "Cierre guardado")
                st.success("Cierre guardado en cierres.csv")
                st.rerun()

        with st.expander("â„¹ï¸ CÃ³mo se calcula el Total de Turno"):
            st.markdown("""**Total de Turno** = (Efectivo + Posnet + Transferencias + PedidosYa) âˆ’ Gastos âˆ’ Inicio de Caja. Los gastos se restan del efectivo (se pagan de la caja).""")

    # ---------- PÃ¡gina: Administrar Cierres ----------
    elif pagina == "Administrar Cierres":
        st.markdown('<p class="sub-header">Administrar Cierres</p>', unsafe_allow_html=True)
        df_cierres = cargar_cierres()

        # ConfirmaciÃ³n de eliminaciÃ³n
        if st.session_state.get("delete_confirm_idx") is not None:
            idx_del = st.session_state["delete_confirm_idx"]
            if idx_del in df_cierres.index:
                fila_del = df_cierres.loc[idx_del]
                detalle = f"{fila_del.get('fecha', '')} â€” Turno {fila_del.get('turno', '')} â€” $ {float(fila_del.get('total_turno', 0)):,.2f}"
            else:
                detalle = ""
            st.warning(f"**Â¿EstÃ¡s seguro de que quieres eliminar este cierre de Coronados?** ({detalle}) Esta acciÃ³n no se puede deshacer.")
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                if st.button("SÃ­, eliminar", type="primary", key="confirm_del"):
                    df_cierres = df_cierres.drop(idx_del).reset_index(drop=True)
                    guardar_cierre(df_cierres)
                    del st.session_state["delete_confirm_idx"]
                    if st.session_state.get("editing_cierre_idx") == idx_del:
                        del st.session_state["editing_cierre_idx"]
                    log_event(current_user, "delete", "cierres", "Cierre eliminado")
                    st.success("Cierre eliminado.")
                    st.rerun()
            with c2:
                if st.button("Cancelar", key="cancel_del"):
                    del st.session_state["delete_confirm_idx"]
                    st.rerun()

        # Formulario de ediciÃ³n
        editing_idx = st.session_state.get("editing_cierre_idx")
        if editing_idx is not None and not df_cierres.empty and editing_idx in df_cierres.index:
            fila = df_cierres.loc[editing_idx]
            st.subheader("âœï¸ Editar cierre")
            with st.form("form_editar_cierre"):
                e1, e2 = st.columns(2)
                with e1:
                    opciones_turno = ["MaÃ±ana", "Tarde", "Noche", "DÃ­a completo"]
                    turno_actual = str(fila["turno"]).strip() if pd.notna(fila["turno"]) else "MaÃ±ana"
                    idx_turno = opciones_turno.index(turno_actual) if turno_actual in opciones_turno else 0
                    turno_e = st.selectbox("Turno", opciones_turno, index=idx_turno)
                    def _v(key: str) -> float:
                        x = fila.get(key)
                        if pd.isna(x):
                            return 0.0
                        try:
                            return max(0.0, float(x))
                        except (TypeError, ValueError):
                            return 0.0
                    inicio_e = st.number_input("Inicio de Caja ($)", min_value=0.0, value=_v("inicio_caja"), step=100.0, format="%.2f")
                    efectivo_e = st.number_input("Efectivo ($)", min_value=0.0, value=_v("efectivo"), step=50.0, format="%.2f")
                    gastos_e = st.number_input("Gastos ($)", min_value=0.0, value=_v("gastos"), step=50.0, format="%.2f")
                with e2:
                    posnet_e = st.number_input("Posnet ($)", min_value=0.0, value=_v("posnet"), step=50.0, format="%.2f")
                    transf_e = st.number_input("Transferencias ($)", min_value=0.0, value=_v("transferencias"), step=50.0, format="%.2f")
                    pedidosya_e = st.number_input("PedidosYa ($)", min_value=0.0, value=_v("pedidosya"), step=50.0, format="%.2f")
                    valor_z_e = st.number_input("Valor Z (Fiscal)", min_value=0.0, value=_v("valor_z") if "valor_z" in fila else 0.0, step=1.0, format="%.0f")
                if st.form_submit_button("Guardar cambios"):
                    efectivo_neto_e = efectivo_e - gastos_e
                    total_turno_e = calcular_total_turno(efectivo_e, posnet_e, transf_e, pedidosya_e, gastos_e, inicio_e)
                    row_out = {
                        "fecha": fila["fecha"],
                        "turno": turno_e,
                        "inicio_caja": inicio_e,
                        "efectivo": efectivo_e,
                        "posnet": posnet_e,
                        "transferencias": transf_e,
                        "pedidosya": pedidosya_e,
                        "gastos": gastos_e,
                        "efectivo_neto": efectivo_neto_e,
                        "total_turno": total_turno_e,
                    }
                    if "valor_z" in df_cierres.columns:
                        row_out["valor_z"] = valor_z_e
                    df_cierres.loc[editing_idx] = row_out
                    guardar_cierre(df_cierres)
                    del st.session_state["editing_cierre_idx"]
                    log_event(current_user, "edit", "cierres", "Cierre actualizado")
                    st.success("Cierre actualizado correctamente.")
                    st.rerun()
            if st.button("Cancelar ediciÃ³n"):
                del st.session_state["editing_cierre_idx"]
                st.rerun()
            st.divider()

        # Tabla de cierres (mÃ¡s recientes arriba)
        st.subheader("Cierres guardados")
        if df_cierres.empty:
            st.info("No hay cierres guardados.")
        else:
            df_ver = df_cierres.sort_values("fecha", ascending=False)
            tiene_z = "valor_z" in df_ver.columns
            n_cols = [2, 1.5, 1, 1, 1, 1, 1, 1, 0.8 if tiene_z else 0, 1.5, 0.8, 0.8]
            hdrs = ["**Fecha**", "**Turno**", "**Inicio**", "**Efectivo**", "**Posnet**", "**Transf.**", "**PedidosYa**", "**Gastos**"]
            if tiene_z:
                hdrs.append("**Z**")
            hdrs.extend(["**Total**", "**Editar**", "**Eliminar**"])
            cols_h = st.columns(n_cols)
            for i, h in enumerate(hdrs):
                with cols_h[i]: st.markdown(h)
            st.markdown("---")
            for idx in df_ver.index:
                r = df_ver.loc[idx]
                with st.container():
                    cols = st.columns(n_cols)
                    ii = 0
                    cols[ii].text(str(r["fecha"])); ii += 1
                    cols[ii].text(str(r["turno"])); ii += 1
                    for k in ["inicio_caja", "efectivo", "posnet", "transferencias", "pedidosya", "gastos"]:
                        cols[ii].text(f"$ {float(r[k]):,.0f}"); ii += 1
                    if tiene_z:
                        cols[ii].text(str(r.get("valor_z", ""))); ii += 1
                    cols[ii].text(f"$ {float(r['total_turno']):,.0f}"); ii += 1
                    with cols[ii]:
                        if st.button("âœï¸ Editar", key=f"edit_{idx}"):
                            st.session_state["editing_cierre_idx"] = idx
                            st.rerun()
                    ii += 1
                    with cols[ii]:
                        if st.button("ðŸ—‘ï¸ Eliminar", key=f"del_{idx}"):
                            st.session_state["delete_confirm_idx"] = idx
                            st.rerun()

    # ---------- PÃ¡gina: Gastos Detallados ----------
    elif pagina == "Gastos Detallados":
        st.markdown('<p class="sub-header">Gastos Detallados</p>', unsafe_allow_html=True)
        st.subheader("Nuevo gasto")

        proveedor_otro = None
        col_prov, col_monto, col_cat = st.columns(3)
        with col_prov:
            proveedor_sel = st.selectbox("Nombre del proveedor", options=lista_proveedores(), key="proveedor")
            if proveedor_sel == "Otro":
                proveedor_otro = st.text_input("Indique el nombre del proveedor", key="proveedor_otro")
        with col_monto:
            monto_gasto = st.number_input("Monto ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f", key="monto_g")
        with col_cat:
            categoria = st.selectbox("CategorÃ­a", options=CATEGORIAS_GASTO, key="categoria_g")

        if st.button("Guardar gasto", type="primary"):
            nombre_proveedor = (proveedor_otro or "").strip() if proveedor_sel == "Otro" else proveedor_sel
            if not nombre_proveedor and proveedor_sel == "Otro":
                st.warning("Escriba el nombre del proveedor.")
            elif monto_gasto <= 0:
                st.warning("El monto debe ser mayor a 0.")
            else:
                df_g = cargar_gastos()
                nueva_fila = {
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "proveedor": nombre_proveedor or "Sin nombre",
                    "monto": monto_gasto,
                    "categoria": categoria,
                }
                df_g = pd.concat([df_g, pd.DataFrame([nueva_fila])], ignore_index=True)
                guardar_gastos(df_g)
                log_event(current_user, "create", "gastos", "Gasto guardado")
                st.success("Gasto guardado en gastos.csv")
                st.rerun()

        st.subheader("Gastos registrados")
        df_g = cargar_gastos()

        # ConfirmaciÃ³n de eliminaciÃ³n de gasto
        if st.session_state.get("delete_confirm_gasto_idx") is not None:
            idx_del = st.session_state["delete_confirm_gasto_idx"]
            if idx_del in df_g.index:
                fila_del = df_g.loc[idx_del]
                detalle = f"{fila_del.get('fecha', '')} â€” {fila_del.get('proveedor', '')} â€” $ {float(fila_del.get('monto', 0)):,.2f}"
            else:
                detalle = ""
            st.warning(f"**Â¿EstÃ¡s seguro de que quieres eliminar este gasto?** ({detalle}) Esta acciÃ³n no se puede deshacer.")
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                if st.button("SÃ­, eliminar", type="primary", key="confirm_del_gasto"):
                    df_g = df_g.drop(idx_del).reset_index(drop=True)
                    guardar_gastos(df_g)
                    del st.session_state["delete_confirm_gasto_idx"]
                    if st.session_state.get("editing_gasto_idx") == idx_del:
                        del st.session_state["editing_gasto_idx"]
                    log_event(current_user, "delete", "gastos", "Gasto eliminado")
                    st.success("Gasto eliminado.")
                    st.rerun()
            with c2:
                if st.button("Cancelar", key="cancel_del_gasto"):
                    del st.session_state["delete_confirm_gasto_idx"]
                    st.rerun()

        # Formulario de ediciÃ³n de gasto
        editing_gasto_idx = st.session_state.get("editing_gasto_idx")
        if editing_gasto_idx is not None and not df_g.empty and editing_gasto_idx in df_g.index:
            fila_g = df_g.loc[editing_gasto_idx]
            st.subheader("âœï¸ Editar gasto")
            proveedores_lista = lista_proveedores()
            proveedor_actual = str(fila_g["proveedor"]).strip() if pd.notna(fila_g["proveedor"]) else ""
            proveedor_en_lista = proveedor_actual in proveedores_lista
            fecha_gasto_default = _fecha_str_a_date(fila_g["fecha"]) or date.today()
            with st.form("form_editar_gasto"):
                eg0 = st.date_input("Fecha", value=fecha_gasto_default, key="edit_fecha_gasto")
                eg1, eg2, eg3 = st.columns(3)
                with eg1:
                    idx_prov = proveedores_lista.index(proveedor_actual) if proveedor_en_lista else (proveedores_lista.index("Otro") if "Otro" in proveedores_lista else 0)
                    prov_edit = st.selectbox(
                        "Proveedor",
                        options=proveedores_lista,
                        index=idx_prov,
                        key="edit_proveedor",
                    )
                    prov_otro_edit = st.text_input("Si eligiÃ³ 'Otro', nombre del proveedor", value=proveedor_actual if not proveedor_en_lista else "", key="edit_proveedor_otro")
                with eg2:
                    _m = fila_g.get("monto")
                    try:
                        monto_edit_val = max(0.0, float(_m)) if pd.notna(_m) else 0.0
                    except (TypeError, ValueError):
                        monto_edit_val = 0.0
                    monto_edit = st.number_input("Monto ($)", min_value=0.0, value=monto_edit_val, step=50.0, format="%.2f", key="edit_monto_gasto")
                with eg3:
                    cat_actual = str(fila_g["categoria"]).strip() if pd.notna(fila_g["categoria"]) else CATEGORIAS_GASTO[0]
                    cat_edit = st.selectbox(
                        "CategorÃ­a",
                        options=CATEGORIAS_GASTO,
                        index=CATEGORIAS_GASTO.index(cat_actual) if cat_actual in CATEGORIAS_GASTO else 0,
                        key="edit_categoria",
                    )
                if st.form_submit_button("Guardar cambios"):
                    nombre_final = (prov_otro_edit or "").strip() if prov_edit == "Otro" else prov_edit
                    df_g.loc[editing_gasto_idx] = {
                        "fecha": eg0.strftime("%Y-%m-%d"),
                        "proveedor": nombre_final or "Sin nombre",
                        "monto": monto_edit,
                        "categoria": cat_edit,
                    }
                    guardar_gastos(df_g)
                    del st.session_state["editing_gasto_idx"]
                    log_event(current_user, "edit", "gastos", "Gasto actualizado")
                    st.success("Gasto actualizado correctamente.")
                    st.rerun()
            if st.button("Cancelar ediciÃ³n", key="cancel_edit_gasto"):
                del st.session_state["editing_gasto_idx"]
                st.rerun()
            st.divider()

        if df_g.empty:
            st.info("AÃºn no hay gastos registrados.")
        else:
            df_g_ver = df_g.sort_values("fecha", ascending=False)
            # Encabezados
            gh1, gh2, gh3, gh4, gh5, gh6 = st.columns([2, 2, 1.2, 1.2, 0.7, 0.7])
            with gh1: st.markdown("**Fecha**")
            with gh2: st.markdown("**Proveedor**")
            with gh3: st.markdown("**Monto**")
            with gh4: st.markdown("**CategorÃ­a**")
            with gh5: st.markdown("**Editar**")
            with gh6: st.markdown("**Eliminar**")
            st.markdown("---")
            for idx in df_g_ver.index:
                r = df_g_ver.loc[idx]
                g1, g2, g3, g4, g5, g6 = st.columns([2, 2, 1.2, 1.2, 0.7, 0.7])
                with g1: st.text(str(r["fecha"]))
                with g2: st.text(str(r["proveedor"]))
                with g3: st.text(f"$ {float(r['monto']):,.2f}")
                with g4: st.text(str(r["categoria"]))
                with g5:
                    if st.button("âœï¸ Editar", key=f"edit_gasto_{idx}"):
                        st.session_state["editing_gasto_idx"] = idx
                        st.rerun()
                with g6:
                    if st.button("ðŸ—‘ï¸ Eliminar", key=f"del_gasto_{idx}"):
                        st.session_state["delete_confirm_gasto_idx"] = idx
                        st.rerun()
            st.metric("Total gastos", f"$ {df_g['monto'].sum():,.2f}")

    # ---------- PÃ¡gina: GestiÃ³n de Personal ----------
    elif pagina == "GestiÃ³n de Personal":
        st.markdown('<p class="sub-header">GestiÃ³n de Personal</p>', unsafe_allow_html=True)
        st.subheader("Pagar sueldo")

        empleados = lista_empleados()
        col_emp, col_monto = st.columns(2)
        with col_emp:
            empleado_sel = st.selectbox("Empleado", options=empleados, key="empleado")
            otro_empleado = st.text_input("Si eligiÃ³ 'Otro', escriba el nombre del empleado", key="empleado_otro", placeholder="Ej: Repartidor")
        with col_monto:
            monto_sueldo = st.number_input("Monto pagado ($)", min_value=0.0, value=0.0, step=100.0, format="%.2f", key="monto_s")

        empleado_final = (otro_empleado or "").strip() if empleado_sel == "Otro" else empleado_sel
        if empleado_final == "" and empleado_sel == "Otro":
            empleado_final = "Otro"
        if st.button("Registrar pago de sueldo", type="primary"):
            if empleado_sel == "Otro" and not (otro_empleado or "").strip():
                st.warning("Si eligiÃ³ 'Otro', escriba el nombre del empleado.")
            elif monto_sueldo <= 0:
                st.warning("El monto debe ser mayor a 0.")
            else:
                df_s = cargar_sueldos()
                df_s = pd.concat([df_s, pd.DataFrame([{
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "empleado": empleado_final,
                    "monto": monto_sueldo,
                }])], ignore_index=True)
                guardar_sueldos(df_s)
                log_event(current_user, "create", "sueldos", "Pago de sueldo guardado")
                st.success("Pago guardado en sueldos.csv")
                st.rerun()

        st.subheader("Pagos registrados")
        df_s = cargar_sueldos()

        # ConfirmaciÃ³n eliminar sueldo
        if st.session_state.get("delete_confirm_sueldo_idx") is not None:
            idx_sdel = st.session_state["delete_confirm_sueldo_idx"]
            if idx_sdel in df_s.index:
                fila_sdel = df_s.loc[idx_sdel]
                detalle_s = f"{fila_sdel.get('fecha', '')} â€” {fila_sdel.get('empleado', '')} â€” $ {float(fila_sdel.get('monto', 0)):,.2f}"
            else:
                detalle_s = ""
            st.warning(f"**Â¿EstÃ¡s seguro de que quieres eliminar este pago de sueldo?** ({detalle_s}) Esta acciÃ³n no se puede deshacer.")
            sc1, sc2, sc3 = st.columns([1, 1, 2])
            with sc1:
                if st.button("SÃ­, eliminar", type="primary", key="confirm_del_sueldo"):
                    df_s = df_s.drop(idx_sdel).reset_index(drop=True)
                    guardar_sueldos(df_s)
                    del st.session_state["delete_confirm_sueldo_idx"]
                    if st.session_state.get("editing_sueldo_idx") == idx_sdel:
                        del st.session_state["editing_sueldo_idx"]
                    log_event(current_user, "delete", "sueldos", "Pago de sueldo eliminado")
                    st.success("Pago eliminado.")
                    st.rerun()
            with sc2:
                if st.button("Cancelar", key="cancel_del_sueldo"):
                    del st.session_state["delete_confirm_sueldo_idx"]
                    st.rerun()

        # Formulario ediciÃ³n sueldo
        editing_sueldo_idx = st.session_state.get("editing_sueldo_idx")
        if editing_sueldo_idx is not None and not df_s.empty and editing_sueldo_idx in df_s.index:
            fila_s = df_s.loc[editing_sueldo_idx]
            st.subheader("âœï¸ Editar pago de sueldo")
            fecha_s_default = _fecha_str_a_date(fila_s["fecha"]) or date.today()
            with st.form("form_editar_sueldo"):
                fecha_s_edit = st.date_input("Fecha", value=fecha_s_default, key="edit_fecha_sueldo")
                emp_list = lista_empleados()
                emp_actual = str(fila_s["empleado"]).strip() if pd.notna(fila_s["empleado"]) else ""
                idx_emp = emp_list.index(emp_actual) if emp_actual in emp_list else 0
                empleado_s_edit = st.selectbox("Empleado", options=emp_list, index=idx_emp, key="edit_empleado_sueldo")
                _ms = fila_s.get("monto")
                try:
                    monto_s_val = max(0.0, float(_ms)) if pd.notna(_ms) else 0.0
                except (TypeError, ValueError):
                    monto_s_val = 0.0
                monto_s_edit = st.number_input("Monto ($)", min_value=0.0, value=monto_s_val, step=100.0, format="%.2f", key="edit_monto_sueldo")
                if st.form_submit_button("Guardar cambios"):
                    df_s.loc[editing_sueldo_idx] = {
                        "fecha": fecha_s_edit.strftime("%Y-%m-%d"),
                        "empleado": empleado_s_edit,
                        "monto": monto_s_edit,
                    }
                    guardar_sueldos(df_s)
                    del st.session_state["editing_sueldo_idx"]
                    log_event(current_user, "edit", "sueldos", "Pago de sueldo actualizado")
                    st.success("Pago actualizado correctamente.")
                    st.rerun()
            if st.button("Cancelar ediciÃ³n", key="cancel_edit_sueldo"):
                del st.session_state["editing_sueldo_idx"]
                st.rerun()
            st.divider()

        if df_s.empty:
            st.info("AÃºn no hay pagos de sueldos registrados.")
        else:
            df_s_ver = df_s.sort_values("fecha", ascending=False)
            sh1, sh2, sh3, sh4, sh5 = st.columns([2, 2, 1.2, 0.7, 0.7])
            with sh1: st.markdown("**Fecha**")
            with sh2: st.markdown("**Empleado**")
            with sh3: st.markdown("**Monto**")
            with sh4: st.markdown("**Editar**")
            with sh5: st.markdown("**Eliminar**")
            st.markdown("---")
            for idx in df_s_ver.index:
                rs = df_s_ver.loc[idx]
                s1, s2, s3, s4, s5 = st.columns([2, 2, 1.2, 0.7, 0.7])
                with s1: st.text(str(rs["fecha"]))
                with s2: st.text(str(rs["empleado"]))
                with s3: st.text(f"$ {float(rs['monto']):,.2f}")
                with s4:
                    if st.button("âœï¸ Editar", key=f"edit_sueldo_{idx}"):
                        st.session_state["editing_sueldo_idx"] = idx
                        st.rerun()
                with s5:
                    if st.button("ðŸ—‘ï¸ Eliminar", key=f"del_sueldo_{idx}"):
                        st.session_state["delete_confirm_sueldo_idx"] = idx
                        st.rerun()
            st.metric("Total sueldos pagados", f"$ {df_s['monto'].sum():,.2f}")

    # ---------- PÃ¡gina: Pedidos Ya ----------
    elif pagina == "Pedidos Ya":
        st.markdown('<p class="sub-header">Pedidos Ya</p>', unsafe_allow_html=True)
        st.subheader("Nuevo registro")
        with st.form("form_pedidosya"):
            fp1, fp2 = st.columns(2)
            with fp1:
                fecha_py = st.date_input("Fecha", value=date.today(), key="py_fecha")
                monto_py = st.number_input("Monto ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f", key="py_monto")
            with fp2:
                metodo_py = st.selectbox("MÃ©todo de pago", options=METODOS_PAGO, key="py_metodo")
                comentarios_py = st.text_area("Comentarios", key="py_comentarios", height=80)
            if st.form_submit_button("Guardar"):
                df_py = cargar_pedidosya()
                df_py = pd.concat([df_py, pd.DataFrame([{
                    "fecha": fecha_py.strftime("%Y-%m-%d"),
                    "monto": monto_py,
                    "metodo_pago": metodo_py,
                    "comentarios": (comentarios_py or "").strip(),
                }])], ignore_index=True)
                guardar_pedidosya(df_py)
                log_event(current_user, "create", "pedidosya", "Registro creado")
                st.success("Registro guardado en pedidosya.csv")
                st.rerun()
        st.subheader("Registros Pedidos Ya")
        df_py = cargar_pedidosya()
        if df_py.empty:
            st.info("No hay registros de Pedidos Ya.")
        else:
            st.dataframe(df_py.sort_values("fecha", ascending=False), use_container_width=True, hide_index=True)
            st.metric("Total Pedidos Ya", f"$ {df_py['monto'].sum():,.2f}")

    # ---------- PÃ¡gina: Transferencias Alias ----------
    elif pagina == "Transferencias Alias":
        st.markdown('<p class="sub-header">Transferencias Alias</p>', unsafe_allow_html=True)
        st.subheader("Nueva transferencia")
        with st.form("form_transf"):
            ft1, ft2 = st.columns(2)
            with ft1:
                fecha_tr = st.date_input("Fecha", value=date.today(), key="tr_fecha")
                alias_tr = st.text_input("Alias / App", placeholder="Ej: Mercado Pago, UalÃ¡...", key="tr_alias")
            with ft2:
                monto_tr = st.number_input("Monto ($)", min_value=0.0, value=0.0, step=50.0, format="%.2f", key="tr_monto")
                comentario_tr = st.text_area("Comentario", key="tr_comentario", height=80)
            if st.form_submit_button("Guardar"):
                df_tr = cargar_transferencias()
                df_tr = pd.concat([df_tr, pd.DataFrame([{
                    "fecha": fecha_tr.strftime("%Y-%m-%d"),
                    "alias_app": (alias_tr or "").strip(),
                    "monto": monto_tr,
                    "comentario": (comentario_tr or "").strip(),
                }])], ignore_index=True)
                guardar_transferencias(df_tr)
                log_event(current_user, "create", "transferencias", "Registro creado")
                st.success("Registro guardado en transferencias.csv")
                st.rerun()
        st.subheader("Transferencias registradas")
        df_tr = cargar_transferencias()
        if df_tr.empty:
            st.info("No hay transferencias registradas.")
        else:
            st.dataframe(df_tr.sort_values("fecha", ascending=False), use_container_width=True, hide_index=True)
            st.metric("Total transferencias", f"$ {df_tr['monto'].sum():,.2f}")

    # ---------- PÃ¡gina: AdministraciÃ³n Global ----------
    elif pagina == "AdministraciÃ³n Global":
        st.markdown('<p class="sub-header">AdministraciÃ³n Global</p>', unsafe_allow_html=True)
        tabla_admin = st.selectbox("Seleccione la tabla", ["Sueldos", "Gastos", "Pedidos Ya", "Transferencias"], key="admin_tabla")
        st.session_state["admin_tabla_sel"] = tabla_admin

        if tabla_admin == "Sueldos":
            _df = cargar_sueldos().sort_values("fecha", ascending=False)
            _cols = ["fecha", "empleado", "monto"]
        elif tabla_admin == "Gastos":
            _df = cargar_gastos().sort_values("fecha", ascending=False)
            _cols = ["fecha", "proveedor", "monto", "categoria"]
        elif tabla_admin == "Pedidos Ya":
            _df = cargar_pedidosya().sort_values("fecha", ascending=False)
            _cols = ["fecha", "monto", "metodo_pago", "comentarios"]
        else:
            _df = cargar_transferencias().sort_values("fecha", ascending=False)
            _cols = ["fecha", "alias_app", "monto", "comentario"]

        # ConfirmaciÃ³n eliminar (admin)
        _del_key = st.session_state.get("admin_del_key")
        if _del_key is not None:
            _t, _idx = _del_key
            if _t == tabla_admin and _idx in _df.index:
                _r = _df.loc[_idx]
                _det = " â€” ".join(str(_r.get(c, "")) for c in _cols[:3])
                st.warning(f"**Â¿Eliminar este registro?** ({_det}) Esta acciÃ³n no se puede deshacer.")
                if st.button("SÃ­, eliminar", type="primary", key="admin_confirm_del"):
                    if _t == "Sueldos":
                        d = cargar_sueldos(); d = d.drop(_idx).reset_index(drop=True); guardar_sueldos(d)
                    elif _t == "Gastos":
                        d = cargar_gastos(); d = d.drop(_idx).reset_index(drop=True); guardar_gastos(d)
                    elif _t == "Pedidos Ya":
                        d = cargar_pedidosya(); d = d.drop(_idx).reset_index(drop=True); guardar_pedidosya(d)
                    else:
                        d = cargar_transferencias(); d = d.drop(_idx).reset_index(drop=True); guardar_transferencias(d)
                    del st.session_state["admin_del_key"]
                    if st.session_state.get("admin_edit_key") == _del_key:
                        del st.session_state["admin_edit_key"]
                    mod = {"Sueldos": "sueldos", "Gastos": "gastos", "Pedidos Ya": "pedidosya", "Transferencias": "transferencias"}.get(_t, "admin")
                    log_event(current_user, "delete", mod, "Registro eliminado desde Administracion Global")
                    st.success("Registro eliminado.")
                    st.rerun()
                if st.button("Cancelar", key="admin_cancel_del"):
                    del st.session_state["admin_del_key"]
                    st.rerun()

        # EdiciÃ³n (admin)
        _edit_key = st.session_state.get("admin_edit_key")
        if _edit_key is not None:
            _t, _idx = _edit_key
            if _t != tabla_admin or _idx not in _df.index:
                if _t == tabla_admin:
                    del st.session_state["admin_edit_key"]
            elif _idx in _df.index:
                _fila = _df.loc[_idx]
                st.subheader(f"âœï¸ Editar registro de {tabla_admin}")
                with st.form("form_admin_edit"):
                    if tabla_admin == "Sueldos":
                        _fecha_val = _fecha_str_a_date(_fila["fecha"]) or date.today()
                        fe = st.date_input("Fecha", value=_fecha_val, key="ae_fecha_s")
                        _le = lista_empleados()
                        _emp_str = str(_fila["empleado"]).strip() if pd.notna(_fila["empleado"]) else ""
                        _idx_emp = _le.index(_emp_str) if _emp_str in _le else 0
                        em = st.selectbox("Empleado", options=_le, index=_idx_emp, key="ae_emp")
                        mo = st.number_input("Monto ($)", min_value=0.0, value=max(0.0, float(_fila["monto"])) if pd.notna(_fila["monto"]) else 0.0, step=100.0, format="%.2f", key="ae_monto_s")
                    elif tabla_admin == "Gastos":
                        _fecha_val = _fecha_str_a_date(_fila["fecha"]) or date.today()
                        fe = st.date_input("Fecha", value=_fecha_val, key="ae_fecha_g")
                        pr = st.text_input("Proveedor", value=str(_fila.get("proveedor", "")), key="ae_prov")
                        mo = st.number_input("Monto ($)", min_value=0.0, value=max(0.0, float(_fila["monto"])) if pd.notna(_fila["monto"]) else 0.0, step=50.0, format="%.2f", key="ae_monto_g")
                        ca = st.selectbox("CategorÃ­a", options=CATEGORIAS_GASTO, index=CATEGORIAS_GASTO.index(str(_fila["categoria"])) if str(_fila.get("categoria", "")).strip() in CATEGORIAS_GASTO else 0, key="ae_cat")
                    elif tabla_admin == "Pedidos Ya":
                        _fecha_val = _fecha_str_a_date(_fila["fecha"]) or date.today()
                        fe = st.date_input("Fecha", value=_fecha_val, key="ae_fecha_py")
                        mo = st.number_input("Monto ($)", min_value=0.0, value=max(0.0, float(_fila["monto"])) if pd.notna(_fila["monto"]) else 0.0, step=50.0, format="%.2f", key="ae_monto_py")
                        me = st.selectbox("MÃ©todo de pago", options=METODOS_PAGO, index=METODOS_PAGO.index(str(_fila.get("metodo_pago", "Efectivo"))) if str(_fila.get("metodo_pago", "")).strip() in METODOS_PAGO else 0, key="ae_metodo")
                        co = st.text_area("Comentarios", value=str(_fila.get("comentarios", "")), key="ae_com_py")
                    else:
                        _fecha_val = _fecha_str_a_date(_fila["fecha"]) or date.today()
                        fe = st.date_input("Fecha", value=_fecha_val, key="ae_fecha_tr")
                        al = st.text_input("Alias/App", value=str(_fila.get("alias_app", "")), key="ae_alias")
                        mo = st.number_input("Monto ($)", min_value=0.0, value=max(0.0, float(_fila["monto"])) if pd.notna(_fila["monto"]) else 0.0, step=50.0, format="%.2f", key="ae_monto_tr")
                        co = st.text_area("Comentario", value=str(_fila.get("comentario", "")), key="ae_com_tr")
                    if st.form_submit_button("Guardar cambios"):
                        if tabla_admin == "Sueldos":
                            d = cargar_sueldos(); d.loc[_idx] = {"fecha": fe.strftime("%Y-%m-%d"), "empleado": em, "monto": mo}; guardar_sueldos(d)
                        elif tabla_admin == "Gastos":
                            d = cargar_gastos(); d.loc[_idx] = {"fecha": fe.strftime("%Y-%m-%d"), "proveedor": pr, "monto": mo, "categoria": ca}; guardar_gastos(d)
                        elif tabla_admin == "Pedidos Ya":
                            d = cargar_pedidosya(); d.loc[_idx] = {"fecha": fe.strftime("%Y-%m-%d"), "monto": mo, "metodo_pago": me, "comentarios": co or ""}; guardar_pedidosya(d)
                        else:
                            d = cargar_transferencias(); d.loc[_idx] = {"fecha": fe.strftime("%Y-%m-%d"), "alias_app": al or "", "monto": mo, "comentario": co or ""}; guardar_transferencias(d)
                        del st.session_state["admin_edit_key"]
                        mod = {"Sueldos": "sueldos", "Gastos": "gastos", "Pedidos Ya": "pedidosya", "Transferencias": "transferencias"}.get(tabla_admin, "admin")
                        log_event(current_user, "edit", mod, "Registro actualizado desde Administracion Global")
                        st.success("Registro actualizado.")
                        st.rerun()
                if st.button("Cancelar ediciÃ³n", key="admin_cancel_edit"):
                    del st.session_state["admin_edit_key"]
                    st.rerun()
                st.divider()

        if _df.empty:
            st.info(f"No hay registros en {tabla_admin}.")
        else:
            for idx in _df.index:
                r = _df.loc[idx]
                cols_a = st.columns(len(_cols) + 2)
                for i, c in enumerate(_cols):
                    with cols_a[i]: st.text(str(r.get(c, "")))
                with cols_a[-2]:
                    if st.button("âœï¸ Editar", key=f"admin_edit_{tabla_admin}_{idx}"):
                        st.session_state["admin_edit_key"] = (tabla_admin, idx)
                        st.rerun()
                with cols_a[-1]:
                    if st.button("ðŸ—‘ï¸ Eliminar", key=f"admin_del_{tabla_admin}_{idx}"):
                        st.session_state["admin_del_key"] = (tabla_admin, idx)
                        st.rerun()

    # ---------- Pagina: Gestion de Usuarios ----------
    elif pagina == "Gestion de Usuarios":
        if current_role not in ADMIN_ROLES:
            st.error("No tiene permisos para administrar usuarios.")
            st.stop()

        st.markdown('<p class="sub-header">Gestion de Usuarios</p>', unsafe_allow_html=True)

        df_users = list_users()
        if df_users.empty:
            st.info("No hay usuarios cargados.")
        else:
            df_show = df_users.copy()
            df_show["activo"] = df_show["is_active"].apply(lambda x: "Si" if int(x) == 1 else "No")
            st.dataframe(df_show[["username", "role", "activo", "created_at"]], use_container_width=True, hide_index=True)

        st.subheader("Crear usuario")
        with st.form("form_create_user"):
            new_username = st.text_input("Usuario")
            new_password = st.text_input("Contrasena", type="password")
            new_role = st.selectbox("Rol", options=sorted(ASSIGNABLE_ROLES), index=0)
            if st.form_submit_button("Crear usuario"):
                ok, msg = create_user(new_username, new_password, new_role, actor_username=current_user)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

        if not df_users.empty:
            usernames = df_users["username"].tolist()

            st.subheader("Resetear contrasena")
            with st.form("form_reset_pass"):
                user_reset = st.selectbox("Usuario", options=usernames, key="user_reset_select")
                new_pass = st.text_input("Nueva contrasena", type="password")
                if st.form_submit_button("Resetear"):
                    ok, msg = reset_password(user_reset, new_pass, actor_username=current_user)
                    st.success(msg) if ok else st.warning(msg)

            st.subheader("Estado y eliminacion")
            with st.form("form_user_status"):
                target_user = st.selectbox("Usuario objetivo", options=usernames, key="target_user_select")
                accion = st.selectbox("Accion", options=["Desactivar", "Activar", "Eliminar"], index=0)
                if st.form_submit_button("Aplicar accion"):
                    if target_user == current_user:
                        st.warning("No puede aplicar esta accion sobre su usuario actual.")
                    else:
                        if accion == "Desactivar":
                            ok, msg = set_user_active(target_user, False, actor_username=current_user)
                        elif accion == "Activar":
                            ok, msg = set_user_active(target_user, True, actor_username=current_user)
                        else:
                            ok, msg = delete_user(target_user, actor_username=current_user)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)
    # ---------- PÃ¡gina: Panel de Control (DueÃ±o) ----------
    # ---------- Pagina: Audit Logs ----------
    elif pagina == "Audit Logs":
        if current_role not in ADMIN_ROLES:
            st.error("No tiene permisos para esta seccion.")
            st.stop()

        st.markdown('<p class="sub-header">Audit Logs</p>', unsafe_allow_html=True)

        all_logs = get_audit_logs()
        if all_logs.empty:
            st.info("No hay eventos registrados.")
        else:
            usuarios = ["Todos"] + sorted(all_logs["username"].dropna().astype(str).unique().tolist())
            modulos = ["Todos"] + sorted(all_logs["module"].dropna().astype(str).unique().tolist())
            acciones = ["Todos"] + sorted(all_logs["action_type"].dropna().astype(str).unique().tolist())

            f1, f2, f3 = st.columns(3)
            with f1:
                f_user = st.selectbox("Usuario", options=usuarios)
            with f2:
                f_module = st.selectbox("Modulo", options=modulos)
            with f3:
                f_action = st.selectbox("Accion", options=acciones)

            d1, d2 = st.columns(2)
            with d1:
                f_from = st.date_input("Desde", value=date.today() - timedelta(days=30), key="audit_from")
            with d2:
                f_to = st.date_input("Hasta", value=date.today(), key="audit_to")

            logs = get_audit_logs(
                username=None if f_user == "Todos" else f_user,
                module=None if f_module == "Todos" else f_module,
                action_type=None if f_action == "Todos" else f_action,
                date_from=f_from,
                date_to=f_to,
            )

            if logs.empty:
                st.info("No hay eventos para el filtro seleccionado.")
            else:
                st.dataframe(logs, use_container_width=True, hide_index=True)
    # ---------- Pagina: Backups y Restore ----------
    elif pagina == "Backups y Restore":
        if current_role not in ADMIN_ROLES:
            st.error("No tiene permisos para esta seccion.")
            st.stop()

        st.markdown('<p class="sub-header">Backups y Restore</p>', unsafe_allow_html=True)

        if st.button("Crear backup de base de datos", type="primary"):
            try:
                backup_path = create_db_backup(username=current_user)
                st.success(f"Backup creado: {backup_path.name}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear backup: {exc}")

        backups = list_db_backups()
        if not backups:
            st.info("No hay backups disponibles.")
        else:
            backup_names = [p.name for p in backups]
            selected_backup = st.selectbox("Backup disponible", options=backup_names)
            st.caption("La restauracion reemplaza la base actual (coronados.db).")

            confirm_restore = st.checkbox(
                "Confirmo que quiero restaurar este backup y reemplazar los datos actuales",
                key="confirm_restore_backup",
            )
            if st.button("Restaurar backup seleccionado"):
                if not confirm_restore:
                    st.warning("Debe confirmar la restauracion antes de continuar.")
                else:
                    ok, msg = restore_db_backup(selected_backup, username=current_user)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    elif pagina == "Panel de Control (DueÃ±o)":
        st.markdown('<p class="sub-header">Panel de Control (DueÃ±o)</p>', unsafe_allow_html=True)

        periodo = st.radio("PerÃ­odo", ["Esta semana", "Este mes", "Todo"], horizontal=True)

        df_c = cargar_cierres()
        df_g = cargar_gastos()
        df_s = cargar_sueldos()

        if not df_c.empty:
            df_c["fecha_dt"] = pd.to_datetime(df_c["fecha"], errors="coerce")
        if not df_g.empty:
            df_g["fecha_dt"] = pd.to_datetime(df_g["fecha"], errors="coerce")
        if not df_s.empty:
            df_s["fecha_dt"] = pd.to_datetime(df_s["fecha"], errors="coerce")

        hoy = pd.Timestamp.now().normalize()
        inicio_semana = hoy - timedelta(days=hoy.weekday())

        def filtro_semana(d):
            if d is pd.NaT or pd.isna(d):
                return False
            return inicio_semana.date() <= d.date() <= hoy.date()

        def filtro_mes(d):
            if d is pd.NaT or pd.isna(d):
                return False
            return d.month == hoy.month and d.year == hoy.year

        if periodo == "Esta semana":
            if not df_c.empty:
                df_c = df_c[df_c["fecha_dt"].apply(filtro_semana)]
            if not df_g.empty:
                df_g = df_g[df_g["fecha_dt"].apply(filtro_semana)]
            if not df_s.empty:
                df_s = df_s[df_s["fecha_dt"].apply(filtro_semana)]
        elif periodo == "Este mes":
            if not df_c.empty:
                df_c = df_c[df_c["fecha_dt"].apply(filtro_mes)]
            if not df_g.empty:
                df_g = df_g[df_g["fecha_dt"].apply(filtro_mes)]
            if not df_s.empty:
                df_s = df_s[df_s["fecha_dt"].apply(filtro_mes)]

        ingresos = ingresos_cierres(df_c)
        total_gastos = df_g["monto"].sum() if not df_g.empty else 0.0
        total_sueldos = df_s["monto"].sum() if not df_s.empty else 0.0
        ganancia_neta = ingresos - total_gastos - total_sueldos

        st.subheader("Ganancia real neta")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Ingresos (cierres)", f"$ {ingresos:,.2f}")
        with k2:
            st.metric("Gastos", f"$ {total_gastos:,.2f}")
        with k3:
            st.metric("Sueldos", f"$ {total_sueldos:,.2f}")
        with k4:
            st.metric("Ganancia real neta", f"$ {ganancia_neta:,.2f}", delta=f"{periodo}")

        st.divider()
        st.subheader("Descargar reporte para contador")
        excel_bytes = generar_reporte_excel()
        st.download_button(
            "Descargar Reporte para Contador",
            data=excel_bytes,
            file_name=f"reporte_coronados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    # BotÃ³n de export en sidebar para todas las pÃ¡ginas
    with st.sidebar:
        st.divider()
        excel_bytes = generar_reporte_excel()
        st.download_button(
            "Descargar Reporte para Contador",
            data=excel_bytes,
            file_name=f"reporte_coronados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sidebar_export",
        )


if __name__ == "__main__":
    main()














