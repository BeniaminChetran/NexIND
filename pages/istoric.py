#----------------------------------
#-------istoric.py-----------------
#----------------------------------

import streamlit as st
from datetime import datetime
import pandas as pd
import json
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from services.pdf_service import genereaza_pdf
from config import db_cursor

def render_istoric():
    st.subheader("📜 Istoric Intervenții & Căutare Avansată (Lazy Loading)")
    
    with st.expander("🔍 Căutare și Filtrare Rapoarte", expanded=True):
        col_f1, col_f2 = st.columns(2)
        firme = ["Toate firmele"] + [f['nume_firma'] for f in FirmeRepository.get_all()]
        with col_f1:
            sel_f = st.selectbox("Filtrează după Firmă", options=firme)
        with col_f2:
            masini = ["Toate mașinile"] + [m['denumire'] for m in MasiniRepository.get_all()]
            sel_m = st.selectbox("Filtrează după Mașină", options=masini)

    # Preluare rapoarte direct din baza de date
    with db_cursor() as c:
        c.execute("""
            SELECT id, firma, masina, subansamblu, defect, cod_eroare, piese_json, 
                   titlu AS titlu_lucrare, simptom, solutie, stare_finala AS stare_fin, 
                   durata AS durata_min, optimizari, tehnician AS tehnician_nume, 
                   verificator AS verificator_nume, data_creare AS data, tip_interventie 
            FROM reparatii 
            ORDER BY id DESC
        """)
        rapoarte = c.fetchall()
    
    # Filtrare
    if sel_f != "Toate firmele":
        rapoarte = [r for r in rapoarte if r.get('firma') == sel_f]
    if sel_m != "Toate mașinile":
        rapoarte = [r for r in rapoarte if r.get('masina') == sel_m]

    st.write(f"**Rezultate găsite:** {len(rapoarte)} rapoarte")

    if not rapoarte:
        st.info("Nu există rapoarte care să corespundă filtrelor selectate.")
        return

    rapoarte_dict = {f"Raport #{r['id']} | {r.get('firma')} - {r.get('masina')} ({str(r.get('data', 'N/A'))[:10]})": r for r in rapoarte}
    
    sel_rap_key = st.selectbox("Selectează Raportul dorit pentru Vizualizare / Modificare", options=list(rapoarte_dict.keys()))
    
    if sel_rap_key:
        r_data = rapoarte_dict[sel_rap_key]
        rid = r_data['id']
        
        st.markdown(f"### ✏️ Modificare Raport #{rid}")
        
        with st.form(f"form_mod_istoric_{rid}"):
            titlu_lucrare = st.text_input("Titlu Lucrare", value=r_data.get('titlu_lucrare', ''))
            
            simptom = st.text_area("Simptom Inițial", value=r_data.get('simptom', ''))
            defect = st.text_area("Defect Constatat", value=r_data.get('defect', ''))
            solutie = st.text_area("Soluție / Lucrări Executate", value=r_data.get('solutie', ''))
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                durata_min = st.number_input("Durată (minute)", value=int(r_data.get('durata_min', 60) or 60), step=15)
                stare_optiuni = ["Funcțională", "În testare", "Oprită / Necesar piese"]
                stare_curenta = r_data.get('stare_fin', 'Funcțională')
                idx_stare = stare_optiuni.index(stare_curenta) if stare_curenta in stare_optiuni else 0
                stare_fin = st.selectbox("Stare Finală", options=stare_optiuni, index=idx_stare)
                
                tip_optiuni = ["reparatie", "diagnostic", "consultanta"]
                tip_curent = r_data.get('tip_interventie', 'reparatie')
                idx_tip = tip_optiuni.index(tip_curent) if tip_curent in tip_optiuni else 0
                tip_interventie = st.selectbox("Tip Intervenție", options=tip_optiuni, index=idx_tip)
            with col_d2:
                tehnician = st.text_input("Tehnician", value=r_data.get('tehnician_nume', 'Tehnician Nexus'))
                verificator = st.text_input("Verificator / Client", value=r_data.get('verificator_nume', 'Client'))

            st.markdown("#### 🔩 Gestiune Piese")
            piese_existente = r_data.get('piese_valide', [])
            if not piese_existente:
                piese_existente = r_data.get('piese_json', [])
            if isinstance(piese_existente, str):
                try: piese_existente = json.loads(piese_existente)
                except: piese_existente = []
            
            df_piese_hist = pd.DataFrame(piese_existente if piese_existente else [{"Piesa": "", "Cantitate": 1, "Tip": "Necesara"}])
            if "piesa" in df_piese_hist.columns and "Piesa" not in df_piese_hist.columns:
                df_piese_hist = df_piese_hist.rename(columns={"piesa": "Piesa", "cantitate": "Cantitate", "tip": "Tip"})

            piese_catalog = [p['denumire'] for p in PieseRepository.get_all()]
            
            edited_piese_hist = st.data_editor(df_piese_hist, num_rows="dynamic", column_config={
                "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
                "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
                "Tip": st.column_config.SelectboxColumn("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True)
            }, key=f"editor_piese_hist_{rid}")

            optimizari = st.text_area("Recomandări Tehnice", value=r_data.get('optimizari', ''))

            submitted_mod = st.form_submit_button("💾 Salvează Modificările Raportului", type="primary")
            if submitted_mod:
                piese_valide_nou = edited_piese_hist.dropna(subset=["Piesa"]).to_dict(orient="records")
                with db_cursor() as c:
                    c.execute("""
                        UPDATE reparatii 
                        SET titlu=%s, simptom=%s, defect=%s, solutie=%s, durata=%s, 
                            stare_finala=%s, tip_interventie=%s, tehnician=%s, verificator=%s, 
                            optimizari=%s, piese_json=%s 
                        WHERE id=%s
                    """, (
                        titlu_lucrare, simptom, defect, solutie, durata_min, 
                        stare_fin, tip_interventie, tehnician, verificator, 
                        optimizari, json.dumps(piese_valide_nou, ensure_ascii=False), rid
                    ))
                st.success("Modificările raportului au fost salvate cu succes!")
                st.rerun()

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("📄 Generează PDF Actualizat", key=f"btn_pdf_{rid}"):
                pdf_bytes = genereaza_pdf({
                    "id": rid, "client": r_data.get('firma'), "masina": r_data.get('masina'), 
                    "durata": r_data.get('durata_min', 60), "stare_finala": r_data.get('stare_fin', 'Funcțională'), 
                    "piese_json": r_data.get('piese_valide', r_data.get('piese_json', [])), 
                    "titlu": r_data.get('titlu_lucrare', ''), "simptom": r_data.get('simptom', ''), 
                    "defect": r_data.get('defect', ''), "solutie": r_data.get('solutie', ''), 
                    "optimizari": r_data.get('optimizari', ''), "tehnician": r_data.get('tehnician_nume', ''), 
                    "verificator": r_data.get('verificator_nume', ''), "data": datetime.now(), 
                    "tip_interventie": r_data.get('tip_interventie', 'reparatie')
                })
                st.download_button(
                    label="📥 Descarcă PDF Actualizat",
                    data=pdf_bytes,
                    file_name=f"Raport_{rid}_Actualizat.pdf",
                    mime="application/pdf",
                    key=f"dl_pdf_{rid}"
                )
        with col_b2:
            if st.button("🗑️ Șterge Raport", key=f"btn_del_{rid}", type="secondary"):
                with db_cursor() as c:
                    c.execute("DELETE FROM reparatii WHERE id=%s", (rid,))
                st.success(f"Raportul #{rid} a fost șters!")
                st.rerun()