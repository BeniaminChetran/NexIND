#-------------------------------------
#-------documentatii.py---------------
#-------------------------------------

import streamlit as st
from repositories.masini_repository import MasiniRepository
from config import db_cursor

def render_documentatii():
    st.subheader("📊 Documentații / Proceduri de reparații")
    masini = [m['denumire'] for m in MasiniRepository.get_all()]
    if not masini:
        st.warning("Adăugați mașini.")
        return
    sel_m = st.selectbox("Mașină", options=masini)
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s", (sel_m,))
        def_list = [r['defect'] for r in cur.fetchall() if r['defect']]
    def_sel = st.selectbox("Defect / Procedură", options=["+ Defect nou"] + def_list)
    def_final = st.text_input("Defect nou") if def_sel == "+ Defect nou" else def_sel
    
    if def_final and def_sel != "+ Defect nou":
        with db_cursor() as cur:
            cur.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s ORDER BY pas_numar", (sel_m, def_sel))
            pasi = cur.fetchall()
        for p in pasi:
            st.text_input(f"Pasul {p['pas_numar']}", value=p['descriere_pas'], key=f"pas_{p['id']}")