# ------------------------------------------
# --------utils/draft_state.py--------------
# ------------------------------------------

import streamlit as st


def init_draft(draft_key: str, defaults: dict, counter_key: str | None = None) -> dict:
    """Inițializează o dată în session_state dicționarul de draft și contorul de resetare."""
    if draft_key not in st.session_state or not isinstance(st.session_state[draft_key], dict):
        st.session_state[draft_key] = dict(defaults)
    else:
        for k, v in defaults.items():
            if k not in st.session_state[draft_key]:
                st.session_state[draft_key][k] = v

    if counter_key and counter_key not in st.session_state:
        st.session_state[counter_key] = 0

    return st.session_state[draft_key]


def reset_draft(draft_key: str, defaults: dict, counter_key: str | None = None) -> dict:
    """Resetează draft-ul la valorile implicite și incrementează contorul pentru chei noi de widget."""
    st.session_state[draft_key] = dict(defaults)
    if counter_key:
        st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
    return st.session_state[draft_key]


def widget_key(prefix: str, camp: str, counter_key: str | None = None, scope_id=None) -> str:
    """Generează o cheie unică per modul, câmp, sesiune/record și contor de resetare."""
    cnt = st.session_state.get(counter_key, 0) if counter_key else 0
    scope = f"_{scope_id}" if scope_id is not None else ""
    return f"{prefix}{scope}_{cnt}_{camp}"


def sync_camp(draft_key: str, w_key: str, camp: str, transform=None):
    """Callback on_change: copiază imediat valoarea widget-ului în dicționarul de draft."""
    draft = st.session_state.get(draft_key)
    if isinstance(draft, dict) and w_key in st.session_state:
        val = st.session_state[w_key]
        draft[camp] = transform(val) if callable(transform) else val


def lega_camp(
    draft_key: str,
    camp: str,
    val_implicit,
    prefix: str,
    counter_key: str | None = None,
    scope_id=None,
    transform=None,
):
    """Leagă un câmp din draft la o cheie de widget în session_state fără a suprascrie editările."""
    draft = st.session_state[draft_key]
    if camp not in draft:
        draft[camp] = transform(val_implicit) if callable(transform) else val_implicit

    val_curent = transform(draft[camp]) if callable(transform) else draft[camp]
    draft[camp] = val_curent

    w_key = widget_key(prefix, camp, counter_key, scope_id)
    if w_key not in st.session_state:
        st.session_state[w_key] = val_curent

    return w_key, val_curent
