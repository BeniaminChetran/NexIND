# ------------------------------
# ---- app.py (Meniu 2 Niveluri)
# ------------------------------

import base64
import importlib
import os
import traceback

from dotenv import load_dotenv
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components

from utils.acces_conturi import (
    activeaza_mod_operator,
    get_cont_activ,
    get_conturi_birou,
    seteaza_cont_birou,
)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_WIN_PATH = os.path.join(BASE_DIR, "Nexind.ico")
ICON_ANDROID_PATH = os.path.join(BASE_DIR, "Nexind_android.png")


@st.cache_resource
def _incarca_iconita_pagina(android_path: str, win_path: str):
    if os.path.isfile(android_path):
        return Image.open(android_path)
    if os.path.isfile(win_path):
        return Image.open(win_path)
    return "⚙️"


@st.cache_resource
def _incarca_android_logo_b64(android_path: str) -> str | None:
    if not os.path.isfile(android_path):
        return None
    with open(android_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


PAGE_ICON = _incarca_iconita_pagina(ICON_ANDROID_PATH, ICON_WIN_PATH)
ANDROID_LOGO_B64 = _incarca_android_logo_b64(ICON_ANDROID_PATH)

st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

if ANDROID_LOGO_B64 is not None:
    st.logo(ICON_ANDROID_PATH)

cont_curent = get_cont_activ()
if cont_curent.are_acces_total:
    st.session_state["is_unlocked"] = True
    st.session_state["preturi_deblocate"] = True
else:
    st.session_state["is_unlocked"] = False
    st.session_state["preturi_deblocate"] = False

st.markdown(
    """
    <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def _injecteaza_script_ui_unic(b64_png: str | None) -> None:
    icon_script = ""
    if b64_png:
        data_uri = f"data:image/png;base64,{b64_png}"
        icon_script = f"""
            const head = doc.head;
            if (!doc.querySelector('link[data-nexind-icon="1"]')) {{
                doc.querySelectorAll('link[rel*="icon"], link[rel="apple-touch-icon"]').forEach(el => el.remove());
                ['icon', 'shortcut icon', 'apple-touch-icon'].forEach(relType => {{
                    const link = doc.createElement('link');
                    link.rel = relType;
                    link.type = 'image/png';
                    link.href = '{data_uri}';
                    link.setAttribute('data-nexind-icon', '1');
                    head.appendChild(link);
                }});
            }}
        """

    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const doc = window.parent.document;
                {icon_script}
                let rafId = null;

                function applyAttr() {{
                    rafId = null;
                    doc.querySelectorAll('[data-testid="stSelectbox"] input:not([data-nexind-autofill-blocked="1"])').forEach(inp => {{
                        inp.dataset.nexindAutofillBlocked = "1";
                        inp.setAttribute('autocomplete', 'off');
                        inp.setAttribute('data-lpignore', 'true');
                        inp.setAttribute('data-1p-ignore', 'true');
                        inp.setAttribute('data-form-type', 'other');
                    }});
                }}

                function scheduleApplyAttr() {{
                    if (rafId === null) {{
                        rafId = window.parent.requestAnimationFrame(applyAttr);
                    }}
                }}

                applyAttr();
                if (!window.parent.__nexindSelectboxObserver && doc.body) {{
                    window.parent.__nexindSelectboxObserver = new MutationObserver(scheduleApplyAttr);
                    window.parent.__nexindSelectboxObserver.observe(doc.body, {{ childList: true, subtree: true }});
                }}
            }} catch (e) {{
                console.warn("NexInd UI init:", e);
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


if not st.session_state.get("_nexind_ui_init_done", False):
    _injecteaza_script_ui_unic(ANDROID_LOGO_B64)
    st.session_state["_nexind_ui_init_done"] = True


@st.cache_resource
def _incarca_handler_pagina(module_path: str, func_name: str):
    mod = importlib.import_module(module_path)
    if not hasattr(mod, func_name):
        raise AttributeError(f"Modulul '{module_path}' nu definește funcția '{func_name}'.")
    return getattr(mod, func_name)


def _blocheaza_sesiune():
    st.session_state["is_unlocked"] = False
    st.session_state["preturi_deblocate"] = False
    st.toast("🔒 Elementele protejate au fost blocate.")


def render_deblocare():
    from repositories.setari_repository import SetariRepository

    st.subheader("🔐 SistemAdmin — Conturi Birou & Stare Deblocare")
    st.caption(
        "Conturile de birou au acces total implicit și păstrează identitatea utilizatorului activ pentru trasabilitate."
    )

    setari = SetariRepository.get_setari()
    parola_salvata = str(setari.get("pass") or "").strip()

    if not parola_salvata:
        st.warning(
            "⚠️ Nu există nicio parolă configurată în baza de date (`setari.pass`). "
            "Setează mai întâi o parolă în **SistemAdmin → Setări**."
        )

    if st.session_state.get("is_unlocked", False):
        st.success(
            "🔓 **Status curent: DEBLOCAT** — Ai permisiuni complete de adăugare și ștergere "
            "la verificările tehnice pe sisteme și la componența sistemelor."
        )
        st.button(
            "🔒 Blochează la loc elementele protejate",
            type="primary",
            on_click=_blocheaza_sesiune,
        )
    else:
        st.info(
            "🔒 **Status curent: BLOCAT (Doar vizualizare)** — Introdu parola administratorului "
            "din Setări pentru a debloca editarea."
        )
        with st.form("form_deblocare_admin", clear_on_submit=True):
            parola_introdusa = st.text_input("Parolă administrator", type="password")
            submit_unlock = st.form_submit_button("🔓 Deblochează", type="primary")
            if submit_unlock:
                if not parola_salvata:
                    st.error("Nu este definită o parolă în Setări.")
                elif parola_introdusa == parola_salvata:
                    st.session_state["is_unlocked"] = True
                    st.session_state["preturi_deblocate"] = True
                    st.toast("🔓 Sesiune deblocată cu succes!")
                    st.rerun()
                else:
                    st.error("❌ Parolă incorectă!")


MENIU_STRUCTURA = {
    "📈 0. DashBoard": {
        "📊 Indicatori & Analiză": ("pages.dashboard", "render_dashboard"),
        "✅ De făcut & Teren": ("pages.de_facut", "render_de_facut"),
    },
    "🚨 1. Diagnostic & Documentație": {
        "🛠️ Asistent Defecte": ("pages.asistent_defecte", "render_page"),
        "📚 Index & Căutare Docs (GDrive)": ("pages.documentatie_gdrive", "render_documentatie_gdrive"),
        "📄 Documentații": ("pages.documentatii", "render_documentatii"),
    },
    "🛠️ 2. Execuție & Rapoarte": {
        "📝 Intervenții": ("pages.activitati", "render_activitati"),
        "⚡ Reparații electronice": ("pages.reparatii_electronice", "render_reparatii_electronice"),
        "🛡️ Mentenanță preventivă": ("pages.mentenanta", "render_mentenanta"),
        "📊 Măsurători": ("pages.masuratori", "render_masuratori"),
        "📋 Istoric": ("pages.istoric", "render_istoric"),
        "🔮 Predicții": ("pages.predictii", "render_predictii"),
    },
    "💼 3. Oferte & Comercial": {
        "💼 Oferte de preț": ("pages.oferte", "render_oferte"),
        "🧮 Calculator Prețuri Vânzare": ("pages.simulator_preturi", "render_simulator_preturi"),
        "📦 Comenzi (Furnizori & Clienți)": ("pages.comenzi", "render_comenzi"),
    },
    "📦 4. Nomenclatoare & Stocuri": {
        "📦 Piese": ("pages.piese", "render_piese"),
        "🦾 Mașini": ("pages.masini", "render_masini"),
        "🏢 Firme": ("pages.firme", "render_firme"),
        "📋 Catalog & Fișe Tip Mentenanță": ("pages.fise_mentenanta", "render_fise_mentenanta"),
    },
    "🔐 SistemAdmin": {
        "🔑 Deblocare": ("__local__", "render_deblocare"),
        "⚙️ Setări": ("pages.setari", "render_setari"),
    },
}

CATEGORII_LISTA = list(MENIU_STRUCTURA.keys())
conturi_birou = get_conturi_birou()
nume_conturi_birou = [c["nume"] for c in conturi_birou]
mapa_conturi_birou = {c["nume"]: c for c in conturi_birou}

c_title, c_acc, c_status = st.columns([3.2, 1.8, 1.2], vertical_alignment="center")
with c_title:
    st.title("🛠️ NexInd CMMS Dashboard & Predictive")

with c_acc:
    if cont_curent.este_operator:
        st.caption(f"👷 Mod restrâns: **{cont_curent.nume}**")
        if st.button("🏢 Cont Birou (Acces total)", use_container_width=True, key="hdr_btn_cont_birou"):
            seteaza_cont_birou(conturi_birou[0])
            st.rerun()
    else:
        idx_birou = nume_conturi_birou.index(cont_curent.nume) if cont_curent.nume in nume_conturi_birou else 0
        sel_cont_birou = st.selectbox(
            "Cont activ (Birou)",
            options=nume_conturi_birou,
            index=idx_birou,
            key="hdr_sel_cont_birou",
        )
        if sel_cont_birou != cont_curent.nume:
            seteaza_cont_birou(mapa_conturi_birou[sel_cont_birou])
            st.rerun()

        if st.button("👷 Mod Operator Mașină", use_container_width=True, key="hdr_btn_mod_operator"):
            activeaza_mod_operator()
            st.rerun()

with c_status:
    if cont_curent.este_operator:
        st.warning("👷 Operator: RESTRÂNS")
    elif st.session_state.get("is_unlocked", False):
        st.success(f"🔓 {cont_curent.nume}")
    else:
        st.warning(f"🔒 {cont_curent.nume}")

st.markdown("---")

if cont_curent.este_operator:
    try:
        handler_op = _incarca_handler_pagina("pages.operator_masina", "render_operator_masina")
        handler_op()
    except Exception as exc:
        st.error(f"❌ Eroare la încărcarea modulului **Operator Mașină**: `{exc}`")
        with st.expander("Detalii tehnice (Traceback)"):
            st.code(traceback.format_exc(), language="python")
else:
    if st.session_state.get("nav_categorie_principala") not in CATEGORII_LISTA:
        st.session_state["nav_categorie_principala"] = CATEGORII_LISTA[0]

    col_cat, col_sub = st.columns([1.3, 1.7])
    with col_cat:
        categorie_sel = st.selectbox(
            "Meniu Principal",
            options=CATEGORII_LISTA,
            key="nav_categorie_principala",
        )

    submeniuri = MENIU_STRUCTURA[categorie_sel]
    submeniuri_lista = list(submeniuri.keys())
    if st.session_state.get("nav_submeniu_activ") not in submeniuri_lista:
        st.session_state["nav_submeniu_activ"] = submeniuri_lista[0]

    with col_sub:
        submeniu_sel = st.selectbox(
            "Sub-modul",
            options=submeniuri_lista,
            key="nav_submeniu_activ",
        )

    st.markdown("---")

    mod_path, func_name = submeniuri[submeniu_sel]
    try:
        if mod_path == "__local__":
            render_deblocare()
        else:
            handler = _incarca_handler_pagina(mod_path, func_name)
            handler()
    except Exception as exc:
        st.error(f"❌ Eroare la încărcarea modulului **{submeniu_sel}**: `{exc}`")
        with st.expander("Detalii tehnice (Traceback)"):
            st.code(traceback.format_exc(), language="python")