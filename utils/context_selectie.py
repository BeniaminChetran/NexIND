# ------------------------------------------
# -------utils/context_selectie.py----------
# ------------------------------------------

import streamlit as st


def init_context_selectie():
    if "ctx_firma" not in st.session_state:
        st.session_state["ctx_firma"] = None
    if "ctx_masina" not in st.session_state:
        st.session_state["ctx_masina"] = None


def seteaza_context_selectie(firma: str | None = None, masina: str | None = None):
    init_context_selectie()
    if firma is not None:
        f_clean = str(firma).strip()
        st.session_state["ctx_firma"] = None if f_clean in ("", "-- Alege firma --", "Toate firmele") else f_clean
    if masina is not None:
        m_clean = str(masina).strip()
        st.session_state["ctx_masina"] = (
            None
            if m_clean in ("", "Nicio mașină", "General / Fără mașină", "Toate mașinile / General", "-- Fără utilaj / Introducere manuală --")
            else m_clean
        )


def aplica_context_la_tab(
    tab_prefix: str,
    optiuni_firme: list[str],
    default_firma: str,
    optiuni_masini: list[str],
    default_masina: str,
    key_firma: str,
    key_masina: str,
    draft: dict | None = None,
    campo_firma: str = "sel_firma",
    campo_masina: str = "sel_masina",
):
    """
    Aplică o singură dată per tab (când widget-urile nu au fost încă inițializate)
    firma și mașina active din contextul global, permițând schimbarea liberă ulterior.
    """
    init_context_selectie()
    init_flag = f"_{tab_prefix}_ctx_aplicat"

    ctx_f = st.session_state.get("ctx_firma")
    ctx_m = st.session_state.get("ctx_masina")

    if not st.session_state.get(init_flag):
        if key_firma not in st.session_state:
            aleasa_f = ctx_f if (ctx_f and ctx_f in optiuni_firme) else default_firma
            st.session_state[key_firma] = aleasa_f
            if isinstance(draft, dict) and campo_firma:
                draft[campo_firma] = aleasa_f

        if key_masina not in st.session_state:
            aleasa_m = ctx_m if (ctx_m and ctx_m in optiuni_masini) else default_masina
            st.session_state[key_masina] = aleasa_m
            if isinstance(draft, dict) and campo_masina:
                draft[campo_masina] = aleasa_m

        st.session_state[init_flag] = True