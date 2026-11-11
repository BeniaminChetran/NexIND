#----------------------------------
#-------piese.py-------------------
#----------------------------------

import streamlit as st
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from config import db_cursor

def render_piese():
    st.subheader("🔧 Gestiune Piese de Schimb")
    
    masini = [m['denumire'] for m in MasiniRepository.get_all()]
    sel_m = st.selectbox(
        "Selectează Mașina (Filtrare listă & Asociere piesă nouă)", 
        options=["Toate mașinile / General"] + masini,
        key="sel_masina_piese"
    )

    st.markdown("### ➕ Adaugă Piesă Nouă")
    with st.form("form_adauga_piesa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            denumire = st.text_input("Denumire Piesă *")
            cod_producator = st.text_input("Cod Producător")
            cod_comercial = st.text_input("Cod Comercial")
        with col2:
            subansamblu = st.text_input("Subansamblu")
            st.info(f"📌 Piesa se va înregistra pentru: **{sel_m}**")

        submitted = st.form_submit_button("💾 Salvează Piesa")
        if submitted:
            if denumire:
                PieseRepository.insert({
                    "denumire": denumire,
                    "cod_producator": cod_producator,
                    "cod_comercial": cod_comercial,
                    "subansamblu": subansamblu,
                    "masina_montaj": sel_m if sel_m != "Toate mașinile / General" else "General"
                })
                st.success(f"Piesa '{denumire}' a fost salvată cu succes!")
                st.rerun()
            else:
                st.error("Te rugăm să completezi denumirea piesei.")

    st.markdown("---")
    st.subheader("📋 Piese Înregistrate (Modificare & Ștergere)")
    
    piese_list = PieseRepository.get_filtrate(sel_m)
    if piese_list:
        for p in piese_list:
            masina_eticheta = p.get('masina_montaj', 'General')
            pid = p.get('id')
            with st.expander(f"🔩 {p['denumire']} (Mașini: {masina_eticheta})"):
                with st.form(f"form_mod_piesa_{pid}"):
                    cp1, cp2 = st.columns(2)
                    with cp1:
                        mod_den = st.text_input("Denumire Piesă", value=p.get('denumire', ''))
                        mod_prod = st.text_input("Cod Producător", value=p.get('cod_producator', ''))
                    with cp2:
                        mod_com = st.text_input("Cod Comercial", value=p.get('cod_comercial', ''))
                        mod_sub = st.text_input("Subansamblu", value=p.get('subansamblu', ''))
                    
                    bt1, bt2 = st.columns(2)
                    if bt1.form_submit_button("💾 Salvează Modificările"):
                        with db_cursor() as c:
                            c.execute(
                                "UPDATE piese SET denumire=%s, cod_producator=%s, cod_comercial=%s, subansamblu=%s WHERE id=%s",
                                (mod_den, mod_prod, mod_com, mod_sub, pid)
                            )
                        st.success("Modificări salvate!")
                        st.rerun()
                    if bt2.form_submit_button("🗑️ Șterge Piesa"):
                        with db_cursor() as c:
                            c.execute("DELETE FROM piese WHERE id=%s", (pid,))
                        st.success("Piesa a fost ștearsă!")
                        st.rerun()
    else:
        st.info("Nu există piese înregistrate pentru selecția curentă.")