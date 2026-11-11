#------------------------------
#--------firme.py--------------
#------------------------------

import streamlit as st
from repositories.firme_repository import FirmeRepository

def render_firme():
    st.subheader("📇 Gestiune Firme și Persoane de Contact")
    
    with st.form("form_firme_nou", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nume_firma = st.text_input("Nume Firmă / Client *")
            cui = st.text_input("CUI")
            reg_com = st.text_input("Nr. Reg. Com.")
            adresa = st.text_input("Adresă Sediu")
        with col2:
            banca = st.text_input("Bancă")
            cont = st.text_input("Cont (IBAN)")
            persoana = st.text_input("Persoană de Contact *")
            email = st.text_input("Adresă E-mail Contact")
            telefon = st.text_input("Telefon")

        submitted = st.form_submit_button("💾 Salvează Firmă Nouă")
        if submitted:
            if nume_firma and persoana:
                FirmeRepository.insert({
                    "nume_firma": nume_firma,
                    "cui": cui,
                    "reg_com": reg_com,
                    "adresa": adresa,
                    "banca": banca,
                    "cont": cont,
                    "nume_persoana": persoana,
                    "email": email,
                    "telefon": telefon
                })
                st.success(f"Firma '{nume_firma}' a fost salvată cu succes!")
                st.rerun()
            else:
                st.error("Te rugăm să completezi cel puțin 'Nume Firmă' și 'Persoană de Contact'.")

    st.markdown("---")
    st.subheader("📋 Firme Înregistrate")
    
    firme_list = FirmeRepository.get_all()
    if firme_list:
        for f in firme_list:
            cui_txt = f" (CUI: {f['cui']})" if f.get('cui') else ""
            pers_txt = f" - Contact: {f['nume_persoana']}" if f.get('nume_persoana') else ""
            with st.expander(f"🏢 {f['nume_firma']}{cui_txt}{pers_txt}"):
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.write(f"**CUI:** {f.get('cui', 'N/A')}")
                    st.write(f"**Reg. Com.:** {f.get('reg_com', 'N/A')}")
                    st.write(f"**Adresă:** {f.get('adresa', 'N/A')}")
                    st.write(f"**Bancă:** {f.get('banca', 'N/A')}")
                    st.write(f"**IBAN:** {f.get('cont', 'N/A')}")
                with col_info2:
                    st.write(f"**Persoană Contact:** {f.get('nume_persoana', 'N/A')}")
                    st.write(f"**Email:** {f.get('email', 'N/A')}")
                    st.write(f"**Telefon:** {f.get('telefon', 'N/A')}")
    else:
        st.info("Nu există firme înregistrate momentan.")
