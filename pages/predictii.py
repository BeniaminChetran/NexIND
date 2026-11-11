#-----------------------------------
#------predictii.py-----------------
#-----------------------------------

import streamlit as st
import json
import pandas as pd
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from services.predictive_service import get_predictive_piese_data
from config import db_cursor

def render_predictii():
    st.subheader("🔮 Tab Predicții & Analiză Mentenanță Preventivă (Health Score)")
    firme_list = FirmeRepository.get_all()
    nume_firme = [f['nume_firma'] for f in firme_list]

    if not nume_firme:
        st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        return

    p1, p2 = st.columns(2)
    with p1:
        sel_firma = st.selectbox("Selectează Firma", options=nume_firme, key="pred_firma_tab")
    
    firma_obj = next((f for f in firme_list if f['nume_firma'] == sel_firma), None)
    masini_firma = MasiniRepository.get_by_firma(firma_obj['id']) if firma_obj else []
    nume_masini = [m['denumire'] for m in masini_firma]

    with p2:
        sel_masina = st.selectbox("Selectează Mașina", options=nume_masini if nume_masini else ["Nicio mașină disponibilă"], key="pred_masina_tab")

    st.markdown("---")
    if sel_masina and sel_masina != "Nicio mașină disponibilă":
        with db_cursor() as cur:
            cur.execute("""
                SELECT defect, COUNT(*) as frecventa, MAX(data_creare) as ultima_aparitie, 
                       ARRAY_AGG(DISTINCT subansamblu) as subansambluri_afectate
                FROM reparatii WHERE firma = %s AND masina = %s AND defect IS NOT NULL AND defect != ''
                GROUP BY defect ORDER BY frecventa DESC
            """, (sel_firma, sel_masina))
            defecte_recurente = cur.fetchall()

            cur.execute("SELECT COUNT(*) as oprite FROM reparatii WHERE firma = %s AND masina = %s AND stare_finala = 'Oprită / Necesar piese'", (sel_firma, sel_masina))
            utilaj_oprit_count = cur.fetchone()['oprite']

        score = max(0, min(100, 100 - sum(d['frecventa'] * 5 for d in defecte_recurente) - (utilaj_oprit_count * 15)))
        st.markdown(f"### 🛡️ Index de Sănătate Echipament (Health Score): **{sel_masina}**")
        st.progress(score / 100)
        
        if score >= 90: st.success(f"🟢 Health Score: {score}% (Excelent)")
        elif score >= 70: st.info(f"🟡 Health Score: {score}% (Bun)")
        elif score >= 50: st.warning(f"🟠 Health Score: {score}% (Atenție)")
        else: st.error(f"🔴 Health Score: {score}% (Risc Ridicat)")

        st.markdown("---")
        st.subheader("📈 Analiză Defecte Recurente")
        for d in defecte_recurente:
            st.warning(f"🚨 **Defect:** {d['defect']} | **Apariții:** {d['frecventa']} | **Ultima:** {str(d['ultima_aparitie'])[:10]}")

        st.markdown("---")
        st.subheader("🔩 Istoric Consum Piese")
        reparatii_piese = get_predictive_piese_data(sel_firma, sel_masina)
        total_piese = {}
        for rep in reparatii_piese:
            try:
                for p in json.loads(rep['piese_json']) if isinstance(rep['piese_json'], str) else rep['piese_json']:
                    n = p.get('piesa') or p.get('Piesa')
                    if n and n != "Selectează...":
                        total_piese[n] = total_piese.get(n, 0) + int(p.get('cantitate', 1))
            except: pass
        if total_piese:
            st.dataframe(pd.DataFrame(list(total_piese.items()), columns=["Piesă", "Cantitate Totală"]), use_container_width=True)
        else:
            st.info("Nici o piesă înregistrată.")