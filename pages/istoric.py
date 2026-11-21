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
from repositories.reparatii_repository import ReparatiiRepository
from repositories.documentatie_repository import DocumentatieRepository
from services.pdf_service import genereaza_pdf
from config import db_cursor


def _cauta_docs_pentru_raport(termen: str) -> list[dict]:
    """Caută înregistrări relevante în indexul de documentație după cod / simptom / defect."""
    q = str(termen or "").strip().lower()
    try:
        toate_doc = DocumentatieRepository.get_all() or []
    except Exception:
        return []

    if not q:
        return toate_doc[:6]

    potrivite = []
    for d in toate_doc:
        blob = " ".join([
            str(d.get("tag_sectiune") or ""),
            str(d.get("titlu") or ""),
            str(d.get("tip_sistem") or ""),
            str(d.get("coduri_eroare_hmi") or ""),
            str(d.get("coduri_eroare_driver") or ""),
            str(d.get("interval_pagini") or ""),
            str(d.get("piese_necesare") or ""),
            str(d.get("text_indexat") or ""),
        ]).lower()
        if q in blob:
            potrivite.append(d)
    return potrivite[:6]


def _formateaza_piese_pentru_index(piese_lista: list[dict]) -> str:
    """Transformă lista de piese din raport într-un rezumat lizibil."""
    if not piese_lista:
        return ""
    parti = []
    for p in piese_lista:
        if not isinstance(p, dict):
            continue
        den = str(p.get("Piesa") or p.get("piesa") or "").strip()
        if not den:
            continue
        cant = p.get("Cantitate") if p.get("Cantitate") is not None else p.get("cantitate", 1)
        tip = str(p.get("Tip") or p.get("tip") or "").strip()
        det = f"{den} ({cant} buc" + (f", {tip}" if tip else "") + ")"
        parti.append(det)
    return ", ".join(parti)


def render_istoric():
    st.subheader("📜 Istoric Intervenții & Căutare Avansată")

    @st.fragment
    def render_istoric_izolat():
        with st.expander("🔍 Căutare și Filtrare Rapoarte", expanded=True):
            col_f1, col_f2 = st.columns(2)

            firme_db = FirmeRepository.get_all()
            firme_nume_opt = ["Toate firmele"] + [f['nume_firma'] for f in firme_db]

            with col_f1:
                sel_f = st.selectbox("Filtrează după Firmă", options=firme_nume_opt, key="hist_sel_f")

            masini_db_toate = MasiniRepository.get_all() or []
            masini_id_map = {
                str(m.get("denumire") or "").strip(): m.get("id")
                for m in masini_db_toate
                if m.get("denumire")
            }

            if sel_f != "Toate firmele":
                firma_selectata_obj = next((f for f in firme_db if f['nume_firma'] == sel_f), None)
                if firma_selectata_obj:
                    masini_db = MasiniRepository.get_by_firma(firma_selectata_obj['id'])
                    masini = ["Toate mașinile"] + [m['denumire'] for m in masini_db]
                else:
                    masini = ["Toate mașinile"]
            else:
                masini = ["Toate mașinile"] + [m['denumire'] for m in masini_db_toate]

            with col_f2:
                sel_m = st.selectbox("Filtrează după Mașină", options=masini, key="hist_sel_m")

        rapoarte = ReparatiiRepository.get_all()

        if sel_f != "Toate firmele":
            rapoarte = [r for r in rapoarte if r.get('firma') == sel_f]
        if sel_m != "Toate mașinile":
            rapoarte = [r for r in rapoarte if r.get('masina') == sel_m]

        st.write(f"**Rezultate găsite:** {len(rapoarte)} rapoarte")

        if not rapoarte:
            st.info("Nu există rapoarte care să corespundă filtrelor selectate.")
            return

        rapoarte_dict = {
            f"Raport #{r['id']} | {r.get('firma')} - {r.get('masina')} ({str(r.get('data', 'N/A'))[:10]})": r
            for r in rapoarte
        }

        sel_rap_key = st.selectbox(
            "Selectează Raportul dorit pentru Vizualizare / Modificare",
            options=list(rapoarte_dict.keys()),
            key="hist_sel_rap"
        )

        if sel_rap_key:
            r_data = rapoarte_dict[sel_rap_key]
            rid = r_data['id']

            st.markdown(f"### ✏️ Modificare Raport #{rid}")

            with st.form(f"form_mod_istoric_{rid}"):
                titlu_lucrare = st.text_input("Titlu Lucrare", value=r_data.get('titlu_lucrare', ''), key=f"hist_tit_{rid}")
                simptom = st.text_area("Simptom Inițial", value=r_data.get('simptom', ''), key=f"hist_simp_{rid}")
                defect = st.text_area("Defect Constatat", value=r_data.get('defect', ''), key=f"hist_def_{rid}")
                solutie = st.text_area("Soluție / Lucrări Executate", value=r_data.get('solutie', ''), key=f"hist_sol_{rid}")

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    durata_min = st.number_input("Durată (minute)", value=int(r_data.get('durata_min', 60) or 60), step=15, key=f"hist_dur_{rid}")
                    stare_optiuni = ["Funcțională", "În testare", "Oprită / Necesar piese"]
                    stare_curenta = r_data.get('stare_fin', 'Funcțională')
                    idx_stare = stare_optiuni.index(stare_curenta) if stare_curenta in stare_optiuni else 0
                    stare_fin = st.selectbox("Stare Finală", options=stare_optiuni, index=idx_stare, key=f"hist_stare_{rid}")

                    tip_optiuni = ["reparatie", "diagnostic", "consultanta"]
                    tip_curent = r_data.get('tip_interventie', 'reparatie')
                    idx_tip = tip_optiuni.index(tip_curent) if tip_curent in tip_optiuni else 0
                    tip_interventie = st.selectbox("Tip Intervenție", options=tip_optiuni, index=idx_tip, key=f"hist_tip_{rid}")
                with col_d2:
                    tehnician = st.text_input("Tehnician", value=r_data.get('tehnician_nume', 'Tehnician Nexus'), key=f"hist_tech_{rid}")
                    verificator = st.text_input("Verificator / Client", value=r_data.get('verificator_nume', 'Client'), key=f"hist_ver_{rid}")

                st.markdown("#### 🔩 Gestiune Piese")
                piese_existente = r_data.get('piese_valide', []) or r_data.get('piese_json', [])
                if isinstance(piese_existente, str):
                    try:
                        piese_existente = json.loads(piese_existente)
                    except Exception:
                        piese_existente = []

                df_piese_hist = pd.DataFrame(
                    piese_existente if piese_existente else [{"Piesa": "", "Cantitate": 1, "Tip": "Necesara"}]
                )
                if "piesa" in df_piese_hist.columns and "Piesa" not in df_piese_hist.columns:
                    df_piese_hist = df_piese_hist.rename(columns={"piesa": "Piesa", "cantitate": "Cantitate", "tip": "Tip"})

                piese_catalog = [p['denumire'] for p in PieseRepository.get_all()]

                edited_piese_hist = st.data_editor(
                    df_piese_hist,
                    num_rows="dynamic",
                    column_config={
                        "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
                        "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
                        "Tip": st.column_config.SelectboxColumn("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True)
                    },
                    key=f"editor_piese_hist_{rid}"
                )

                optimizari = st.text_area("Recomandări Tehnice", value=r_data.get('optimizari', ''), key=f"hist_opt_{rid}")

                if st.form_submit_button("💾 Salvează Modificările Raportului", type="primary"):
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
                    ReparatiiRepository.get_all.clear()
                    st.success("Modificările raportului au fost salvate cu succes!")

            # --- LEGATURA CU INDEXUL DE DOCUMENTATIE & SOLUTII [SOL] ---
            with st.expander("📚 Documentație indexată asociată & Salvare ca Soluție (`[SOL]`)", expanded=False):
                cod_err_rap = str(r_data.get("cod_eroare") or "").strip()
                if cod_err_rap.lower() in ("", "niciunul"):
                    cod_err_rap = ""
                termen_def = cod_err_rap or str(defect or simptom or titlu_lucrare or "").strip()[:60]
                q_hist_doc = st.text_input(
                    "Caută în indexul de documentație (cod eroare / simptom / defect)",
                    value=termen_def,
                    key=f"hist_q_doc_{rid}",
                )
                docs_gasite = _cauta_docs_pentru_raport(q_hist_doc)
                if docs_gasite:
                    for d in docs_gasite:
                        tag_d = d.get("tag_sectiune") or "[ERR]"
                        titlu_d = d.get("titlu") or "Fără titlu"
                        hmi_d = str(d.get("coduri_eroare_hmi") or "").strip()
                        drv_d = str(d.get("coduri_eroare_driver") or "").strip()
                        pag_d = str(d.get("interval_pagini") or "").strip()
                        url_d = str(d.get("gdrive_url") or "").strip()
                        st.markdown(
                            f"- **{tag_d} {titlu_d}**"
                            + (f" — HMI: `{hmi_d}`" if hmi_d else "")
                            + (f" — Driver/VFD: `{drv_d}`" if drv_d else "")
                            + (f" — Pagini: `{pag_d}`" if pag_d else "")
                            + (f" — [Google Drive]({url_d})" if url_d else "")
                        )
                else:
                    st.caption("Nu s-au găsit înregistrări în index pentru criteriul curent.")

                if st.button("➕ Salvează acest raport ca Soluție (`[SOL]`) în index", key=f"btn_promoveaza_sol_{rid}"):
                    piese_curente_lista = edited_piese_hist.dropna(subset=["Piesa"]).to_dict(orient="records")
                    piese_txt = _formateaza_piese_pentru_index(piese_curente_lista)
                    parti_text = []
                    if str(simptom or "").strip():
                        parti_text.append(f"Simptom: {str(simptom).strip()}")
                    if str(defect or "").strip():
                        parti_text.append(f"Defect: {str(defect).strip()}")
                    if str(solutie or "").strip():
                        parti_text.append(f"Soluție: {str(solutie).strip()}")
                    if str(optimizari or "").strip():
                        parti_text.append(f"Recomandări: {str(optimizari).strip()}")
                    if piese_txt:
                        parti_text.append(f"Piese necesare: {piese_txt}")

                    masina_nume_rap = str(r_data.get("masina") or "").strip()
                    mid_rap = masini_id_map.get(masina_nume_rap)

                    try:
                        DocumentatieRepository.insert({
                            "masina_id": int(mid_rap) if mid_rap is not None else None,
                            "categorie": "CNC",
                            "tip_sistem": str(r_data.get("subansamblu") or "").strip(),
                            "titlu": f"{titlu_lucrare or 'Intervenție'} — {masina_nume_rap or 'General'}",
                            "gdrive_file_id": "",
                            "gdrive_url": "",
                            "tip_fisier": "doc",
                            "tag_sectiune": "[SOL]",
                            "interval_pagini": "",
                            "coduri_eroare_hmi": cod_err_rap,
                            "coduri_eroare_driver": "",
                            "piese_necesare": piese_txt,
                            "text_indexat": "\n".join(parti_text),
                        })
                        st.success("✅ Raportul a fost adăugat în indexul de documentație cu eticheta `[SOL]`.")
                    except Exception as e:
                        st.error(f"Eroare la salvarea în index: {e}")

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
                    ReparatiiRepository.get_all.clear()
                    st.success(f"Raportul #{rid} a fost șters!")
                    st.rerun(scope="fragment")

    render_istoric_izolat()