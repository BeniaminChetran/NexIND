#------------------------------
#-------setari.py--------------
#------------------------------

import streamlit as st
from repositories.setari_repository import SetariRepository

def render_setari():
    st.subheader("⚙️ Setări Aplicație & Conectare")
    setari = SetariRepository.get_setari()
    with st.form("form_set"):
        nume = st.text_input("Nume Firma Ta", value=setari.get('nume_firma_mea', ''))
        srv = st.text_input("SMTP Server", value=setari.get('smtp_server', ''))
        usr = st.text_input("User Gmail", value=setari.get('smtp_user', ''))
        pwd = st.text_input("App Password", type="password", value=setari.get('smtp_pass', ''))
        sheet = st.text_input("Google Sheet URL", value=setari.get('google_sheet_url', ''))
        if st.form_submit_button("💾 Salvează Setările"):
            SetariRepository.save_setari({"nume_firma_mea": nume, "smtp_server": srv, "smtp_user": usr, "smtp_pass": pwd, "google_sheet_url": sheet})
            st.success("Setări salvate!")
            st.rerun()