#------------------------------
#--------firme.py--------------
#------------------------------

import streamlit as st
from repositories.firme_repository import FirmeRepository

def render_firme():
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    with st.form("form_f", clear_on_submit=True):
        nume = st.text_input("Nume Firmă *")
        persoana = st.text_input("Persoană Contact *")
        email = st.text_input("Email")
        if st.form_submit_button("💾 Salvează"):
            if nume and persoana:
                FirmeRepository.insert({"nume_firma": nume, "nume_persoana": persoana, "email": email})
                st.success("Salvat!")
                st.rerun()

    for f in FirmeRepository.get_all():
        st.write(f"🏢 {f['nume_firma']} - {f['nume_persoana']} ({f.get('email', '')})")