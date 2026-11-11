#------------------------------
#----app.py--------------------
#------------------------------

#-----------------------------------------------------------------------------------
# APLICATIE NexInd CMMS Enterprise Dashboard & Predictive v10.4.7 (Modularizat)
#-----------------------------------------------------------------------------------

import streamlit as st
from dotenv import load_dotenv

# Import pagini modulare
from pages.dashboard import render_dashboard
from pages.predictii import render_predictii
from pages.activitati import render_activitati
from pages.istoric import render_istoric
from pages.documentatii import render_documentatii
from pages.masini import render_masini
from pages.piese import render_piese
from pages.firme import render_firme
from pages.setari import render_setari

load_dotenv()

# Configurare Pagină & Stil UI
st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("CMMS Enterprise v10.4.7")
st.sidebar.markdown("---")
st.sidebar.info("Arhitectură Enterprise modularizată.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

# Taburile aplicației în ordinea dorită
tab_dashboard, tab_predictii, tab_activitati, tab_rapoarte, tab_optimizare, tab_masini, tab_piese, tab_firme, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "🔮 1. Predicții",
    "📝 2. Activități", 
    "📋 3. Istoric",
    "📊 4. Documentații / Proceduri", 
    "🏭 5. Mașini", 
    "🔧 6. Piese", 
    "📇 7. Firme",
    "⚙️ 8. Setări"
])

with tab_dashboard:
    render_dashboard()

with tab_predictii:
    render_predictii()

with tab_activitati:
    render_activitati()

with tab_rapoarte:
    render_istoric()

with tab_optimizare:
    render_documentatii()

with tab_masini:
    render_masini()

with tab_piese:
    render_piese()

with tab_firme:
    render_firme()

with tab_setari:
    render_setari()