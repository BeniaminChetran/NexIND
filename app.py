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
from pages.reparatii_electronice import render_reparatii_electronice
from pages.oferte import render_oferte
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
tab_dashboard, tab_activitati,tab_oferte, tab_firme, tab_masini, tab_piese, tab_electronice, tab_istoric, tab_documentatii, tab_predictii, tab_masuratori, tab_setari = st.tabs([
    "📈 0. Dashboard",
    "📝 1. Activități", 
    "💼 2. Oferte Preț"
    "📇 3. Firme",
    "🏭 4. Mașini", 
    "🔧 5. Piese",
    "⚡ 6. Reparații Electronice",
    "📋 7. Istoric",
    "📊 8. Documentații / Proceduri",
    "🔮 9. Predicții",
    "📏 10. Măsurători",
    "⚙️ 11. Setări"
])

# 2. Conținutul fiecărui tab legat de funcția corespunzătoare din module
with tab_dashboard:
    render_dashboard()

with tab_activitati:
    render_activitati()
    
with tab_oferte:
    render_oferte()

with tab_firme:
    render_firme()

with tab_masini:
    render_masini()

with tab_piese:
    render_piese()
    
with tab_electronice:
    render_reparatii_electronice()

with tab_istoric:
    render_istoric()

with tab_documentatii:
    render_documentatii()

with tab_predictii:
    render_predictii()

with tab_masuratori:
    render_masuratori()

with tab_setari:
    render_setari()