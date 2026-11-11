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
from pages.masuratori import render_masuratori
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

# 1. Definitia taburilor în ordinea exactă dorită (10 taburi în total)
tab_dashboard, tab_activitati, tab_firme, tab_masini, tab_piese, tab_istoric, tab_documentatii, tab_predictii, tab_masuratori, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "📝 1. Activități", 
    "📇 2. Firme",
    "🏭 3. Mașini", 
    "🔧 4. Piese", 
    "📋 5. Istoric",
    "📊 6. Documentații / Proceduri",
    "🔮 7. Predicții",
    "📏 8. Măsurători",
    "⚙️ 9. Setări"
])

# 2. Conținutul fiecărui tab legat de funcția corespunzătoare din module
with tab_dashboard:
    # Aici afișezi dashboard-ul sau funcția corespunzătoare
    pass

with tab_activitati:
    render_activitati()

with tab_firme:
    render_firme()

with tab_masini:
    render_masini()

with tab_piese:
    render_piese()

with tab_istoric:
    render_istoric()

with tab_documentatii:
    render_documentatii()

with tab_predictii:
    # Aici afișezi modulul de predicții
    pass

with tab_masuratori:
    render_masuratori()

with tab_setari:
    render_setari()