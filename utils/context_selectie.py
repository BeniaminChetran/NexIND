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
    key_firma: str,
    optiuni_masini: list[str] | None = None,
    default_masina: str | None = None,
    key_masina: str | None = None,
    draft: dict | None = None,
    campo_firma: str = "sel_firma",
    campo_masina: str = "sel_masina",
):
    """
    Aplică o singură dată per tab (când widget-urile nu sunt încă în session_state)
    firma și mașina active din contextul global, lăsând utilizatorul să schimbe liber ulterior.
    """
    init_context_selectie()
    init_flag = f"_{tab_prefix}_ctx_aplicat"

    if st.session_state.get(init_flag):
        return

    ctx_f = st.session_state.get("ctx_firma")
    ctx_m = st.session_state.get("ctx_masina")

    if key_firma and key_firma not in st.session_state:
        aleasa_f = ctx_f if (ctx_f and ctx_f in optiuni_firme) else default_firma
        if aleasa_f in optiuni_firme:
            st.session_state[key_firma] = aleasa_f
            if isinstance(draft, dict) and campo_firma:
                draft[campo_firma] = aleasa_f

    if key_masina and optiuni_masini and key_masina not in st.session_state:
        aleasa_m = ctx_m if (ctx_m and ctx_m in optiuni_masini) else default_masina
        if aleasa_m in optiuni_masini:
            st.session_state[key_masina] = aleasa_m
            if isinstance(draft, dict) and campo_masina:
                draft[campo_masina] = aleasa_m

    st.session_state[init_flag] = True
    
 def sorteaza_firme_alfabetic(firme: list[dict] | None) -> list[dict]:
    if not firme:
        return []
    return sorted(
        firme,
        key=lambda f: str((f or {}).get("nume_firma") or "").strip().lower(),
    )


def sorteaza_masini_alfabetic(masini: list[dict] | None) -> list[dict]:
    if not masini:
        return []
    return sorted(
        masini,
        key=lambda m: str((m or {}).get("denumire") or "").strip().lower(),
    )


def sorteaza_piese_alfabetic(piese: list[dict] | None) -> list[dict]:
    if not piese:
        return []
    return sorted(
        piese,
        key=lambda p: str((p or {}).get("denumire") or "").strip().lower(),
    )