#------------------------------------------
#-------pages/predictii.py-----------------
#------------------------------------------

import streamlit as st
import pandas as pd
import json
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from config import db_cursor

def render_predictii():
    st.subheader("🔮 Tab Predicții & Analiză Mentenanță Preventivă (Health Score)")
    st.markdown("Selectează firma și mașina dorită pentru a calcula indicele de sănătate (Health Score) și a analiza defectele recurente.")

    firme_list_pred = FirmeRepository.get_all()
    if not firme_list_pred:
        st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        return

    nume_firme_pred = [f['nume_firma'] for f in firme_list_pred]

    p1, p2 = st.columns(2)
    with p1:
        sel_firma_pred = st.selectbox("Selectează Firma", options=nume_firme_pred, key="pred_firma_tab3")
    
    firma_obj_pred = next((f for f in firme_list_pred if f['nume_firma'] == sel_firma_pred), None)
    
    # Preluare mașini pentru firma selectată
    masini_firma_pred = []
    if firma_obj_pred:
        with db_cursor() as c:
            c.execute("""
                SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina 
                FROM masini m
                WHERE m.firma_id = %s 
                ORDER BY m.denumire
            """, (firma_obj_pred['id'],))
            masini_firma_pred = c.fetchall()

    nume_masini_pred = [m['denumire'] for m in masini_firma_pred]

    with p2:
        if nume_masini_pred:
            sel_masina_pred = st.selectbox("Selectează Mașina", options=nume_masini_pred, key="pred_masina_tab3")
        else:
            sel_masina_pred = None
            st.selectbox("Selectează Mașina", options=["Nicio mașină disponibilă"], disabled=True, key="pred_masina_gol_tab3")

    st.markdown("---")

    if sel_masina_pred and sel_masina_pred != "Nicio mașină disponibilă":
        with db_cursor() as cur_pred:
            cur_pred.execute("""
                SELECT defect, COUNT(*) as frecventa, MAX(data_creare) as ultima_aparitie, 
                       ARRAY_AGG(DISTINCT subansamblu) as subansambluri_afectate
                FROM reparatii
                WHERE firma = %s AND masina = %s AND defect IS NOT NULL AND defect != ''
                GROUP BY defect
                ORDER BY frecventa DESC
            """, (sel_firma_pred, sel_masina_pred))
            defecte_recurente = cur_pred.fetchall()

            cur_pred.execute("""
                SELECT COUNT(*) as oprite
                FROM reparatii
                WHERE firma = %s AND masina = %s AND stare_finala = 'Oprită / Necesar piese'
            """, (sel_firma_pred, sel_masina_pred))
            res_oprite = cur_pred.fetchone()
            utilaj_oprit_count = res_oprite['oprite'] if res_oprite else 0

        score = 100
        for d in defecte_recurente:
            frecv = d['frecventa']
            score -= (frecv * 5)
            if frecv >= 3:
                score -= 10
        
        if utilaj_oprit_count > 0:
            score -= (utilaj_oprit_count * 15)
        
        score = max(0, min(100, score))

        st.markdown(f"### 🛡️ Index de Sănătate Echipament (Health Score): **{sel_masina_pred}**")
        col_sc1, col_sc2 = st.columns([2, 1])
        with col_sc1:
            st.progress(score / 100)
        with col_sc2:
            if score >= 90:
                st.success(f"🟢 Health Score: {score}% (Excelent)")
            elif score >= 70:
                st.info(f"🟡 Health Score: {score}% (Bun)")
            elif score >= 50:
                st.warning(f"🟠 Health Score: {score}% (Atenție)")
            else:
                st.error(f"🔴 Health Score: {score}% (Risc Ridicat)")

        st.markdown("---")
        st.markdown(f"### 📈 Analiză Defecte Recurente pentru: **{sel_masina_pred}** ({sel_firma_pred})")

        if defecte_recurente:
            for d in defecte_recurente:
                frecventa = d['frecventa']
                ultima = str(d['ultima_aparitie'])[:10]
                subansambluri = ", ".join([str(s) for s in d['subansambluri_afectate'] if s])

                if frecventa >= 3:
                    st.error(
                        f"🚨 **Alertă Critică (Defect Recurent Frecvent):** \"{d['defect']}\"\n\n"
                        f"- **Număr apariții:** {frecventa} intervenții\n"
                        f"- **Ultima semnalare:** {ultima}\n"
                        f"- **Subansamblu vizat:** {subansambluri or 'General'}\n\n"
                        f"💡 *Recomandare de mentenanță predictivă:* Acest defect s-a repetat de {frecventa} ori. Se recomandă revizia capitală a subansamblului!"
                    )
                elif frecventa == 2:
                    st.warning(
                        f"⚠️ **Atenționare (Defect Repetat):** \"{d['defect']}\"\n\n"
                        f"- **Număr apariții:** {frecventa} intervenții\n"
                        f"- **Ultima semnalare:** {ultima}\n"
                        f"- **Subansamblu vizat:** {subansambluri or 'General'}"
                    )
                else:
                    st.info(f"ℹ️ **Defect izolat:** \"{d['defect']}\" (Apărut o singură dată la {ultima}).")
        else:
            st.success("✅ Nu există defecte recurente înregistrate pentru această mașină.")
    else:
        st.info("Vă rugăm să selectați o firmă care deține mașini pentru a vizualiza predicțiile.")