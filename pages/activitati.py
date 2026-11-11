#------------------------------
#--------activitati.py---------
#------------------------------

import streamlit as st
import json
import threading
from datetime import datetime
import pandas as pd
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.reparatii_repository import ReparatiiRepository
from services.pdf_service import genereaza_pdf
from services.sync_service import background_sync_task
from config import db_cursor

def render_activitati():
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")
    
    if "raport_salvat" not in st.session_state: st.session_state["raport_salvat"] = False
    if "ultimul_id_salvat" not in st.session_state: st.session_state["ultimul_id_salvat"] = None
    if "ultimul_pdf_bytes" not in st.session_state: st.session_state["ultimul_pdf_bytes"] = None

    firme_db = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f for f in firme_db}
    if not firme_dict:
        st.warning("⚠️ Adăugați cel puțin o firmă.")
        return

    # Dacă raportul a fost salvat, afișăm butoanele de acțiune rapidă (Download + Activitate Nouă)
    if st.session_state["raport_salvat"]:
        st.success("✅ Activitate salvată cu succes! E-mailul a fost trimis în fundal.")
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.session_state["ultimul_pdf_bytes"]:
                st.download_button(
                    label="📥 Descarcă Raport PDF",
                    data=st.session_state["ultimul_pdf_bytes"],
                    file_name=f"Raport_{st.session_state['ultimul_id_salvat']}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
        with col_act2:
            if st.button("➕ Introdu o activitate nouă"):
                st.session_state["raport_salvat"] = False
                st.session_state["ultimul_id_salvat"] = None
                st.session_state["ultimul_pdf_bytes"] = None
                if "df_piese_editor" in st.session_state: del st.session_state["df_piese_editor"]
                st.rerun()
        st.markdown("---")
        return

    col_f1, col_f2 = st.columns([4, 1])
    with col_f1:
        sel_firma = st.selectbox("1. Alege Firma", options=list(firme_dict.keys()), disabled=st.session_state["raport_salvat"])
    with col_f2:
        st.write(""); st.write("")
        if st.button("🔄 Sync Mașini"): st.rerun()

    firma_obj = firme_dict[sel_firma]
    masini_db = MasiniRepository.get_by_firma(firma_obj['id'])
    masini_nume = [m['denumire'] for m in masini_db]

    sel_masina = st.selectbox("2. Alege Mașina", options=masini_nume if masini_nume else ["Nicio mașină"], disabled=st.session_state["raport_salvat"])
    
    subansambluri, erori = [], []
    if masini_db and sel_masina != "Nicio mașină":
        m_match = next((m for m in masini_db if m['denumire'] == sel_masina), None)
        if m_match:
            if m_match['subansambluri']: subansambluri = [s.strip() for s in m_match['subansambluri'].split(",")]
            if m_match['erori']: erori = [e.strip() for e in m_match['erori'].split(",")]

    sel_subansamblu = st.selectbox("3. Subansamblu", options=subansambluri if subansambluri else ["General"], disabled=st.session_state["raport_salvat"])
    
    c1, c2 = st.columns(2)
    with c1:
        titlu_lucrare = st.text_input("Titlu", value="Intervenție tehnică", disabled=st.session_state["raport_salvat"])
        simptom = st.text_area("Simptom", disabled=st.session_state["raport_salvat"])
        defect = st.text_area("Defect", disabled=st.session_state["raport_salvat"])
        cod_eroare = st.selectbox("Cod Eroare", options=["Niciunul"] + erori, disabled=st.session_state["raport_salvat"])
    with c2:
        solutie = st.text_area("Soluție", disabled=st.session_state["raport_salvat"])
        durata_min = st.number_input("Durată (min)", value=60, step=15, disabled=st.session_state["raport_salvat"])
        tip_interventie = st.selectbox("Tip", ["reparatie", "diagnostic", "consultanta"], disabled=st.session_state["raport_salvat"])
        stare_fin = st.selectbox("Stare Finală", ["Funcțională", "În testare", "Oprită / Necesar piese"], disabled=st.session_state["raport_salvat"])

    if "df_piese_editor" not in st.session_state:
        st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])

    piese_catalog = [p['denumire'] for p in PieseRepository.get_all()]
    edited_df = st.data_editor(st.session_state["df_piese_editor"], num_rows="dynamic", column_config={
        "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
        "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
        "Tip": st.column_config.SelectboxColumn("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True)
    }, disabled=st.session_state["raport_salvat"])

    c_t1, c_t2 = st.columns(2)
    tehnician = c_t1.text_input("Tehnician", value="Tehnician Nexus", disabled=st.session_state["raport_salvat"])
    verificator = c_t2.selectbox("Verificat de", options=[firma_obj['nume_persoana']] if firma_obj['nume_persoana'] else ["Client"], disabled=st.session_state["raport_salvat"])
    optimizari = st.text_area("Recomandări", disabled=st.session_state["raport_salvat"])

    if not st.session_state["raport_salvat"]:
        if st.button("💾 Salvează Activitatea", type="primary"):
            piese_valide = edited_df.dropna(subset=["Piesa"]).to_dict(orient="records")
            data_rep = {
                "firma": sel_firma, "masina": sel_masina, "subansamblu": sel_subansamblu, "defect": defect,
                "cod_eroare": cod_eroare, "piese_valide": piese_valide, "titlu_lucrare": titlu_lucrare,
                "simptom": simptom, "solutie": solutie, "stare_fin": stare_fin, "durata_min": durata_min,
                "optimizari": optimizari, "tehnician_nume": tehnician, "verificator_nume": verificator, "tip_interventie": tip_interventie
            }
            rid = ReparatiiRepository.insert(data_rep)
            if rid:
                pdf_bytes = genereaza_pdf({
                    "id": rid, "client": sel_firma, "masina": sel_masina, "durata": durata_min, 
                    "stare_finala": stare_fin, "piese_json": [{"piesa": p.get("Piesa"), "cantitate": p.get("Cantitate"), "tip": p.get("Tip")} for p in piese_valide], 
                    "titlu": titlu_lucrare, "simptom": simptom, "defect": defect, "solutie": solutie, 
                    "optimizari": optimizari, "tehnician": tehnician, "verificator": verificator, 
                    "data": datetime.now(), "tip_interventie": tip_interventie
                })
                
                st.session_state["ultimul_id_salvat"] = rid
                st.session_state["ultimul_pdf_bytes"] = pdf_bytes

                threading.Thread(target=background_sync_task, args=(
                    {"status": "nefacturat", "id": str(rid), "data": datetime.now().strftime("%Y-%m-%d"), "tip_interventie": tip_interventie, "ora": f"{durata_min} min", "firma": sel_firma, "masina": sel_masina},
                    firma_obj['email'], f"Raport #{rid} - {sel_firma}", f"Vă atașăm raportul #{rid}.", pdf_bytes, f"Raport_{rid}.pdf"
                ), daemon=True).start()

            st.session_state["raport_salvat"] = True
            st.rerun()