#------------------------------
#----app.py (Fără numerotare)
#------------------------------

import os
import base64
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# Configurare iconițe NexInd (Windows + Android)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
icon_win_path = os.path.join(BASE_DIR, "Nexind.ico")
icon_android_path = os.path.join(BASE_DIR, "Nexind_android.png")

if os.path.exists(icon_android_path):
    page_icon = Image.open(icon_android_path)
elif os.path.exists(icon_win_path):
    page_icon = Image.open(icon_win_path)
else:
    page_icon = "⚙️"

# UN SINGUR apel st.set_page_config în toată aplicația
st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

if os.path.exists(icon_android_path):
    st.logo(icon_android_path)

# Import pagini modulare
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
from pages.setari import render_setari

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
                const head = doc.head;
                doc.querySelectorAll('link[rel*="icon"], link[rel="apple-touch-icon"]').forEach(el => el.remove());
                ['icon', 'shortcut icon', 'apple-touch-icon'].forEach(relType => {{
                    const link = doc.createElement('link');
                    link.rel = relType;
                    link.type = 'image/png';
                    link.href = '{data_uri}';
                    head.appendChild(link);
                }});
            }})();
            </script>
            """,
            height=0,
            width=0,
        )

seteaza_iconita_android(icon_android_path)

st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("CMMS Enterprise v10.4.7")
st.sidebar.markdown("---")
st.sidebar.info("Arhitectură Enterprise optimizată.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

# Listă opțiuni meniu fără numerotare
optiuni_pagini = [
    "📈 Dashboard",
    "📝 Activități",
    "🛡️ Mentenanță Preventivă",
    "💼 Oferte Preț",
    "🏢 Firme",
    "⚙️ Mașini",
    "📦 Piese",
    "⚡ Reparații Electronice",
    "📋 Istoric",
    "📄 Documentații",
    "🔮 Predicții",
    "📊 Măsurători",
    "⚙️ Setări"
]

# Selector navigare sus în pagină
pagina_selectata = st.selectbox("🧭 Navigare rapidă module:", options=optiuni_pagini, label_visibility="collapsed")

st.markdown("---")

# Randarea paginii corespunzătoare selecției
if pagina_selectata == "📈 Dashboard":
    render_dashboard()
elif pagina_selectata == "📝 Activități":
    render_activitati()
elif pagina_selectata == "🛡️ Mentenanță Preventivă":
    render_mentenanta()
elif pagina_selectata == "💼 Oferte Preț":
    render_oferte()
elif pagina_selectata == "🏢 Firme":
    render_firme()
elif pagina_selectata == "⚙️ Mașini":
    render_masini()
elif pagina_selectata == "📦 Piese":
    render_piese()
elif pagina_selectata == "⚡ Reparații Electronice":
    render_reparatii_electronice()
elif pagina_selectata == "📋 Istoric":
    render_istoric()
elif pagina_selectata == "📄 Documentații":
    render_documentatii()
elif pagina_selectata == "🔮 Predicții":
    render_predictii()
elif pagina_selectata == "📊 Măsurători":
    render_masuratori()
elif pagina_selectata == "⚙️ Setări":
    render_setari()