#------------------------------------
#--------masini.py-------------------
#------------------------------------

import streamlit as st
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository

def render_masini():
    st.subheader("🏭 Gestiune Mașini și Echipamente")
    firme = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f['id'] for f in firme}
    m_firma = st.selectbox("Firma Proprietară", options=["Nicio firmă"] + list(firme_dict.keys()))

    with st.form("form_m", clear_on_submit=True):
        den = st.text_input("Denumire *")
        tip = st.text_input("Tip")
        if st.form_submit_button("💾 Salvează"):
            if m_firma != "Nicio firmă" and den:
                MasiniRepository.insert({"firma_id": firme_dict[m_firma], "denumire": den, "tip_masina": tip})
                st.success("Salvat!")
                st.rerun()

    for m in MasiniRepository.get_all():
        st.write(f"⚙️ {m['denumire']}")