#----------------------------------
#-------piese.py-------------------
#----------------------------------

import streamlit as st
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository

def render_piese():
    st.subheader("🔧 Gestiune Piese de Schimb")
    masini = [m['denumire'] for m in MasiniRepository.get_all()]
    sel_m = st.selectbox("Filtrează după Mașină", options=["Toate mașinile / General"] + masini)

    with st.form("form_p", clear_on_submit=True):
        den = st.text_input("Denumire Piesă *")
        if st.form_submit_button("💾 Salvează"):
            if den:
                PieseRepository.insert({"denumire": den, "masina_montaj": sel_m if sel_m != "Toate mașinile / General" else "General"})
                st.success("Salvat!")
                st.rerun()

    for p in PieseRepository.get_filtrate(sel_m):
        st.write(f"🔩 {p['denumire']} ({p['masina_montaj']})")