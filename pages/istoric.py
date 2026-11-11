#------------------------------------
#------istoric.py--------------------
#------------------------------------

import streamlit as st
import json
import threading
from datetime import date
import pandas as pd
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from services.pdf_service import genereaza_pdf
from services.sync_service import update_google_sheet
from config import db_cursor

def render_istoric():
    st.subheader("📋 Istoric Intervenții & Căutare Avansată")
    with st.expander("🔍 Filtrare", expanded=True):
        firme = [f['nume_firma'] for f in FirmeRepository.get_all()]
        masini = [m['denumire'] for m in MasiniRepository.get_all()]
        fc1, fc2, fc3 = st.columns(3)
        filtru_firma = fc1.selectbox("Firmă", ["Toate firmele"] + firme)
        filtru_masina = fc2.selectbox("Mașină", ["Toate mașinile"] + masini)
        foloseste_data = fc3.checkbox("Data specifică")
        filtru_data = st.date_input("Data", value=date.today()) if foloseste_data else None

    query = "SELECT id, firma, masina, data_creare FROM reparatii WHERE 1=1"
    params = []
    if filtru_firma != "Toate firmele": query += " AND firma = %s"; params.append(filtru_firma)
    if filtru_masina != "Toate mașinile": query += " AND masina = %s"; params.append(filtru_masina)
    if foloseste_data and filtru_data: query += " AND DATE(data_creare) = %s"; params.append(filtru_data)
    query += " ORDER BY id DESC LIMIT 100"

    with db_cursor() as cur:
        cur.execute(query, tuple(params))
        reparatii = cur.fetchall()

    st.markdown(f"**Rezultate:** {len(reparatii)}")
    if reparatii:
        optiuni = {f"Raport #{r['id']} | {r['firma']} - {r['masina']} ({str(r['data_creare'])[:10]})": r['id'] for r in reparatii}
        sel_str = st.selectbox("Selectează Raport", options=list(optiuni.keys()))
        rid = optiuni[sel_str]

        with db_cursor() as cur:
            cur.execute("SELECT * FROM reparatii WHERE id = %s", (rid,))
            rep = cur.fetchone()
        if rep:
            with st.form(f"form_mod_{rid}"):
                titlu = st.text_input("Titlu", value=rep['titlu'] or "")
                simptom = st.text_area("Simptom", value=rep['simptom'] or "")
                defect = st.text_area("Defect", value=rep['defect'] or "")
                solutie = st.text_area("Soluție", value=rep['solutie'] or "")
                durata = st.number_input("Durată", value=int(rep['durata'] or 60))
                stare = st.selectbox("Stare", ["Funcțională", "În testare", "Oprită / Necesar piese"])
                
                piese_db = json.loads(rep['piese_json']) if rep['piese_json'] else []
                df_p = pd.DataFrame(piese_db).rename(columns={"piesa": "Piesa", "cantitate": "Cantitate", "tip": "Tip"}) if piese_db else pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])
                ed_p = st.data_editor(df_p, num_rows="dynamic")

                if st.form_submit_button("💾 Salvează Modificările"):
                    p_val = ed_p.dropna(subset=["Piesa"]).rename(columns={"Piesa": "piesa", "Cantitate": "cantitate", "Tip": "tip"}).to_dict(orient="records")
                    with db_cursor() as c:
                        c.execute("UPDATE reparatii SET titlu=%s, simptom=%s, defect=%s, solutie=%s, durata=%s, stare_finala=%s, piese_json=%s WHERE id=%s",
                                  (titlu, simptom, defect, solutie, durata, stare, json.dumps(p_val, ensure_ascii=False), rid))
                    threading.Thread(target=update_google_sheet, args=({"status": "actualizat", "id": str(rid)},), daemon=True).start()
                    st.success("Actualizat!")
                    st.rerun()