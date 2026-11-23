#------------------------------
#----app.py (Meniu 2 Niveluri)
#------------------------------

import os
import base64
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image



load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
icon_win_path = os.path.join(BASE_DIR, "Nexind.ico")
icon_android_path = os.path.join(BASE_DIR, "Nexind_android.png")

if os.path.exists(icon_android_path):
    page_icon = Image.open(icon_android_path)
elif os.path.exists(icon_win_path):
    page_icon = Image.open(icon_win_path)
else:
    page_icon = "⚙️"

st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

if os.path.exists(icon_android_path):
    st.logo(icon_android_path)

# Inițializare stare globală de deblocare
if "is_unlocked" not in st.session_state:
    st.session_state["is_unlocked"] = False

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


# Import pagini modulare
from repositories.setari_repository import SetariRepository
from pages.dashboard import render_dashboard
from pages.predictii import render_predictii
from pages.activitati import render_activitati
from pages.mentenanta import render_mentenanta
from pages.istoric import render_istoric
from pages.documentatii import render_documentatii
from pages.masini import render_masini
from pages.piese import render_piese
from pages.firme import render_firme
from pages.masuratori import render_masuratori
from pages.reparatii_electronice import render_reparatii_electronice
from pages.oferte import render_oferte
from pages.simulator_preturi import render_simulator_preturi
from pages.setari import render_setari
from pages.documentatie_gdrive import render_documentatie_gdrive
from pages.asistent_defecte import render_page as render_asistent_defecte
from pages.fise_mentenanta import render_fise_mentenanta


def seteaza_iconita_android(cale_png: str):
    if os.path.exists(cale_png):
        with open(cale_png, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"
        components.html(
            f"""
            <script>
            (function() {{
                const doc = window.parent.document;
                if (doc.querySelector('link[data-nexind-icon="1"]')) {{
                    return;
                }}
                const head = doc.head;
                doc.querySelectorAll('link[rel*="icon"], link[rel="apple-touch-icon"]').forEach(el => el.remove());
                ['icon', 'shortcut icon', 'apple-touch-icon'].forEach(relType => {{
                    const link = doc.createElement('link');
                    link.rel = relType;
                    link.type = 'image/png';
                    link.href = '{data_uri}';
                    link.setAttribute('data-nexind-icon', '1');
                    head.appendChild(link);
                }});
            }})();
            </script>
            """,
            height=0,
            width=0,
        )


def blocheaza_autofill_selectbox():
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            function applyAttr() {
                doc.querySelectorAll('[data-testid="stSelectbox"] input').forEach(inp => {
                    if (!inp.dataset.nexindAutofillBlocked) {
                        inp.dataset.nexindAutofillBlocked = "1";
                        inp.setAttribute('autocomplete', 'off');
                        inp.setAttribute('data-lpignore', 'true');
                        inp.setAttribute('data-1p-ignore', 'true');
                        inp.setAttribute('data-form-type', 'other');
                    }
                });
            }
            applyAttr();
            if (!window.parent.__nexindSelectboxObserver) {
                window.parent.__nexindSelectboxObserver = new MutationObserver(applyAttr);
                window.parent.document.addEventListener('DOMContentLoaded', () => {
                    window.parent.__nexindSelectboxObserver.observe(doc.body, { childList: true, subtree: true });
                });
                if (doc.body) {
                    window.parent.__nexindSelectboxObserver.observe(doc.body, { childList: true, subtree: true });
                }
            }
        })();
        </script>
        """,
        height=0,
        width=0,
    )


seteaza_iconita_android(icon_android_path)
blocheaza_autofill_selectbox()


def render_deblocare():
    st.subheader("🔐 SistemAdmin — Deblocare Editare Configurații Sisteme")
    st.caption("Deblochează global toate zonele protejate cu parolă din aplicație: prețuri achiziție piese, furnizori, tarife standard (Nivel A & B), adaos comercial implicit, praguri și componența sistemelor.")

    setari = SetariRepository.get_setari()
    parola_salvata = str(setari.get("pass") or "").strip()

    if not parola_salvata:
        st.warning("⚠️ Nu există nicio parolă configurată în baza de date (`setari.pass`). Setează mai întâi o parolă în **SistemAdmin → Setări**.")

    if st.session_state.get("is_unlocked", False):
        st.success("🔓 **Status curent: DEBLOCAT** — Ai permisiuni complete de adăugare și ștergere la verificările tehnice pe sisteme și la componența sistemelor.")
        if st.button("🔒 Blochează la loc elementele protejate", type="primary"):
            st.session_state["is_unlocked"] = False
            st.session_state["preturi_deblocate"] = False
            st.toast("🔒 Elementele protejate au fost blocate.")
            st.rerun()
    else:
        st.info("🔒 **Status curent: BLOCAT (Doar vizualizare)** — Introdu parola administratorului din Setări pentru a debloca editarea.")
        with st.form("form_deblocare_admin"):
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


c_title, c_status = st.columns([4.2, 1.3], vertical_alignment="center")
with c_title:
    st.title("🛠️ NexInd CMMS Dashboard & Predictive")
with c_status:
    if st.session_state.get("is_unlocked", False):
        st.success("🔓 Sistem: DEBLOCAT")
    else:
        st.warning("🔒 Sistem: BLOCAT")

# Structură bară de meniu (Categorie -> Sub-meniuri)
MENIU_STRUCTURA = {
    "📈 0. DashBoard": {
        "📈 DashBoard": render_dashboard,
        },
    "🚨 1. Diagnostic & Documentație": {
        "🛠️ Asistent Defecte": render_asistent_defecte,
        "📚 Index & Căutare Docs (GDrive)": render_documentatie_gdrive,
        "📄 Documentații": render_documentatii,
    },
    "🛠️ 2. Execuție & Rapoarte": {
        "📝 Intervenții": render_activitati,
        "⚡ Reparații electronice": render_reparatii_electronice,
        "🛡️ Mentenanță preventivă": render_mentenanta,
        "📊 Măsurători": render_masuratori,
        "📋 Istoric": render_istoric,
        "🔮 Predicții": render_predictii,
    },
    "💼 3. Oferte & Comercial": {
        "💼 Oferte de preț": render_oferte,
        "🧮 Calculator Prețuri Vânzare": render_simulator_preturi,
    },
    "📦 4. Nomenclatoare & Stocuri": {
        "📦 Piese": render_piese,
        "🦾 Mașini": render_masini,
        "🏢 Firme": render_firme,
        "📋 Catalog & Fișe Tip Mentenanță": render_fise_mentenanta,
    },
    "🔐 SistemAdmin": {
        "🔑 Deblocare": render_deblocare,
        "⚙️ Setări": render_setari,
    },
}

categorii_lista = list(MENIU_STRUCTURA.keys())
if st.session_state.get("nav_categorie_principala") not in categorii_lista:
    st.session_state["nav_categorie_principala"] = categorii_lista[0]

col_cat, col_sub = st.columns([1.3, 1.7])
with col_cat:
    categorie_sel = st.selectbox(
        "Meniu Principal",
        options=categorii_lista,
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

# Randarea paginii selectate
submeniuri[submeniu_sel]()
