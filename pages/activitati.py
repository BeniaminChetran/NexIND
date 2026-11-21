#----------------------------------
#-------pages/activitati.py--------
#----------------------------------

import streamlit as st
import threading
from datetime import datetime
import pandas as pd
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.reparatii_repository import ReparatiiRepository
from repositories.setari_repository import SetariRepository
from repositories.documentatie_repository import DocumentatieRepository
from services.pdf_service import genereaza_pdf
from services.sync_service import background_sync_task
from services.email_service import trimite_email_raport


def _extrage_email_client(firma_obj: dict) -> str:
    if not firma_obj:
        return ""
    for k in ("email_client", "email", "mail", "adresa_email"):
        val = str(firma_obj.get(k) or "").strip()
        if val:
            return val
    return ""


def _init_sau_reseteaza_act_draft(tehnician_def: str):
    st.session_state["act_draft"] = {
        "sel_firma": "-- Alege firma --",
        "sel_masina": "Nicio mașină",
        "sel_sub": "General",
        "titlu_lucrare": "Intervenție tehnică",
        "simptom": "",
        "defect": "",
        "cod_eroare": "Niciunul",
        "solutie": "",
        "durata_min": 60,
        "tip_interventie": "reparatie",
        "stare_fin": "Funcțională",
        "tehnician": tehnician_def,
        "verificator": "Client",
        "optimizari": "",
        "ultima_firma": "-- Alege firma --"
    }
    st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])
    st.session_state["act_editor_counter"] = st.session_state.get("act_editor_counter", 0) + 1


def _cauta_docs_rapide_interventie(termen: str, masina_id=None) -> list[dict]:
    """Caută rapid în documentatie_tehnica după cod eroare, utilaj sau cuvinte cheie."""
    q = str(termen or "").strip().lower()
    try:
        toate_doc = DocumentatieRepository.get_all() or []
    except Exception:
        return []

    rezultate = []
    for d in toate_doc:
        if masina_id is not None and d.get("masina_id") not in (None, masina_id):
            continue
        blob = " ".join([
            str(d.get("titlu") or ""),
            str(d.get("tip_sistem") or ""),
            str(d.get("coduri_eroare_hmi") or ""),
            str(d.get("coduri_eroare_driver") or ""),
            str(d.get("interval_pagini") or ""),
            str(d.get("text_indexat") or ""),
        ]).lower()
        if not q or q in blob:
            rezultate.append(d)
    return rezultate[:6]


def render_activitati():
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")

    setari_act = SetariRepository.get_setari() or {}
    tehnician_def = setari_act.get("tehnician_implicit") or "Tehnician Nexus"

    if "act_draft" not in st.session_state:
        _init_sau_reseteaza_act_draft(tehnician_def)
    if "raport_salvat" not in st.session_state:
        st.session_state["raport_salvat"] = False
    if "ultimul_id_salvat" not in st.session_state:
        st.session_state["ultimul_id_salvat"] = None
    if "ultimul_pdf_bytes" not in st.session_state:
        st.session_state["ultimul_pdf_bytes"] = None
    if "ultim_email_client" not in st.session_state:
        st.session_state["ultim_email_client"] = ""
    if "ultim_firma_raport" not in st.session_state:
        st.session_state["ultim_firma_raport"] = ""
    if "email_raport_trimis" not in st.session_state:
        st.session_state["email_raport_trimis"] = False

    draft = st.session_state["act_draft"]

    if st.session_state["raport_salvat"]:
        rid_s = st.session_state["ultimul_id_salvat"]
        st.success(f"✅ Raportul #{rid_s} a fost salvat în baza de date! Verifică raportul, apoi confirmă trimiterea pe email.")
        if st.session_state.pop("solutie_indexata_flash", False):
            st.info("📚 Soluția (`[SOL]`) a fost adăugată și în indexul de documentație.")

        col_act1, col_act2, col_act3 = st.columns([1.4, 1.8, 1.3])
        with col_act1:
            if st.session_state["ultimul_pdf_bytes"]:
                st.download_button(
                    label="📥 Descarcă Raport PDF",
                    data=st.session_state["ultimul_pdf_bytes"],
                    file_name=f"Raport_{rid_s}.pdf",
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True
                )
        with col_act2:
            if st.session_state["email_raport_trimis"]:
                st.info("✉️ Raportul a fost confirmat și trimis pe email.")
            else:
                if st.button("✅ Confirmă Verificarea & Trimite Raportul pe Email", type="primary", use_container_width=True):
                    ok_mail, info_mail = trimite_email_raport(
                        destinatar_client=st.session_state.get("ultim_email_client", ""),
                        subiect=f"Raport #{rid_s} - {st.session_state.get('ultim_firma_raport', '')}",
                        corp_mesaj=f"Vă atașăm raportul de intervenție #{rid_s}.",
                        pdf_bytes=st.session_state["ultimul_pdf_bytes"],
                        nume_fisier=f"Raport_{rid_s}.pdf",
                    )
                    if ok_mail:
                        st.session_state["email_raport_trimis"] = True
                        st.success(f"✅ Email trimis cu succes! ({info_mail})")
                        st.rerun()
                    else:
                        st.error(f"⚠️ Eroare la trimiterea emailului: {info_mail}")
        with col_act3:
            if st.button("➕ Activitate nouă", use_container_width=True):
                st.session_state["raport_salvat"] = False
                st.session_state["ultimul_id_salvat"] = None
                st.session_state["ultimul_pdf_bytes"] = None
                st.session_state["ultim_email_client"] = ""
                st.session_state["ultim_firma_raport"] = ""
                st.session_state["email_raport_trimis"] = False
                _init_sau_reseteaza_act_draft(tehnician_def)
                st.rerun()
        return

    firme_db = FirmeRepository.get_all()
    if not firme_db:
        st.warning("⚠️ Adăugați cel puțin o firmă în tabul de Firme.")
        return

    firme_dict = {f['nume_firma']: f for f in firme_db}
    optiuni_firme = ["-- Alege firma --"] + list(firme_dict.keys())

    top_a1, top_a2 = st.columns([4, 1], vertical_alignment="center")
    with top_a1:
        st.caption("💾 Datele activității în lucru se păstrează automat la schimbarea tab-ului.")
    with top_a2:
        if st.button("❌ Anulare Activitate", key="btn_anulare_act", use_container_width=True):
            _init_sau_reseteaza_act_draft(tehnician_def)
            st.toast("🗑️ Datele activității au fost resetate.")
            st.rerun()

    idx_curent = optiuni_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in optiuni_firme else 0

    c_sel1, c_sel2, c_sel3 = st.columns(3)
    with c_sel1:
        sel_firma = st.selectbox("1. Alege Firma", options=optiuni_firme, index=idx_curent)
        draft["sel_firma"] = sel_firma

    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Vă rugăm să selectați o firmă din listă pentru a continua.")
        return

    firma_obj = firme_dict[sel_firma]
    persoana_contact_firma = firma_obj.get('nume_persoana') or firma_obj.get('persoana_contact') or "Client"
    email_client_sel = _extrage_email_client(firma_obj)

    if draft.get("ultima_firma") != sel_firma:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = persoana_contact_firma

    masini_db = MasiniRepository.get_by_firma(firma_obj['id'])
    masini_nume = [m['denumire'] for m in masini_db] if masini_db else ["Nicio mașină"]
    idx_masina = masini_nume.index(draft["sel_masina"]) if draft.get("sel_masina") in masini_nume else 0

    with c_sel2:
        sel_masina = st.selectbox("2. Alege Mașina", options=masini_nume, index=idx_masina)
        draft["sel_masina"] = sel_masina

    subansambluri, erori = [], []
    masina_id_sel = None
    if masini_db and sel_masina != "Nicio mașină":
        m_match = next((m for m in masini_db if m['denumire'] == sel_masina), None)
        if m_match:
            masina_id_sel = m_match.get("id")
            if m_match['subansambluri']: subansambluri = [s.strip() for s in m_match['subansambluri'].split(",") if s.strip()]
            if m_match['erori']: erori = [e.strip() for e in m_match['erori'].split(",") if e.strip()]

    opt_sub = subansambluri if subansambluri else ["General"]
    idx_sub = opt_sub.index(draft["sel_sub"]) if draft.get("sel_sub") in opt_sub else 0
    with c_sel3:
        sel_subansamblu = st.selectbox("3. Subansamblu", options=opt_sub, index=idx_sub)
        draft["sel_sub"] = sel_subansamblu

    st.markdown("---")

    piese_catalog = [p['denumire'] for p in PieseRepository.get_all()]
    if "df_piese_editor" not in st.session_state:
        st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])

    st.markdown("##### 🔩 Piese Utilizate / Necesare")
    edited_df = st.data_editor(
        st.session_state["df_piese_editor"],
        num_rows="dynamic",
        column_config={
            "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
            "Tip": st.column_config.SelectboxColumn("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True)
        },
        key=f"act_editor_piese_{st.session_state.get('act_editor_counter', 0)}",
        use_container_width=True
    )
    st.session_state["df_piese_editor"] = edited_df

    st.markdown("##### 📋 Detalii Intervenție Tehnică")
    c1, c2 = st.columns(2)
    with c1:
        titlu_lucrare = st.text_input("Titlu", value=str(draft.get("titlu_lucrare", "Intervenție tehnică")))
        draft["titlu_lucrare"] = titlu_lucrare

        simptom = st.text_area("Simptom", value=str(draft.get("simptom", "")))
        draft["simptom"] = simptom

        defect = st.text_area("Defect", value=str(draft.get("defect", "")))
        draft["defect"] = defect

        opt_erori = ["Niciunul"] + erori
        idx_err = opt_erori.index(draft["cod_eroare"]) if draft.get("cod_eroare") in opt_erori else 0
        cod_eroare = st.selectbox("Cod Eroare", options=opt_erori, index=idx_err)
        draft["cod_eroare"] = cod_eroare
    with c2:
        solutie = st.text_area("Soluție", value=str(draft.get("solutie", "")))
        draft["solutie"] = solutie

        durata_min = st.number_input("Durată (min)", value=int(draft.get("durata_min", 60)), step=15)
        draft["durata_min"] = durata_min

        opt_tip = ["reparatie", "diagnostic", "consultanta"]
        idx_tip = opt_tip.index(draft["tip_interventie"]) if draft.get("tip_interventie") in opt_tip else 0
        tip_interventie = st.selectbox("Tip", options=opt_tip, index=idx_tip)
        draft["tip_interventie"] = tip_interventie

        opt_stare = ["Funcțională", "În testare", "Oprită / Necesar piese"]
        idx_stare = opt_stare.index(draft["stare_fin"]) if draft.get("stare_fin") in opt_stare else 0
        stare_fin = st.selectbox("Stare Finală", options=opt_stare, index=idx_stare)
        draft["stare_fin"] = stare_fin

    c_t1, c_t2 = st.columns(2)
    tehnician = c_t1.text_input("Tehnician", value=str(draft.get("tehnician", tehnician_def)))
    draft["tehnician"] = tehnician

    opt_verif = list(dict.fromkeys([persoana_contact_firma, "Client"]))
    idx_verif = opt_verif.index(draft["verificator"]) if draft.get("verificator") in opt_verif else 0
    verificator = c_t2.selectbox("Verificat de", options=opt_verif, index=idx_verif)
    draft["verificator"] = verificator

    optimizari = st.text_area("Recomandări", value=str(draft.get("optimizari", "")))
    draft["optimizari"] = optimizari

    # --- CONSULTARE RAPIDA INDEX GDRIVE IN TIMPUL INTERVENTIEI ---
    with st.expander("📚 Consultare rapidă Index GDrive (cod eroare / utilaj / simptom)", expanded=False):
        cod_sugerat = "" if cod_eroare == "Niciunul" else cod_eroare
        q_doc = st.text_input(
            "Filtru rapid în documentația indexată",
            value=cod_sugerat,
            placeholder="ex: 414, AL.24, encoder, invertor...",
            key="act_quick_doc_search",
        )
        docs_rapide = _cauta_docs_rapide_interventie(q_doc, masina_id=masina_id_sel)
        if docs_rapide:
            for d in docs_rapide:
                hmi_d = str(d.get("coduri_eroare_hmi") or "").strip()
                drv_d = str(d.get("coduri_eroare_driver") or "").strip()
                pag_d = str(d.get("interval_pagini") or "").strip()
                st.markdown(
                    f"- **{d.get('tag_sectiune') or '[ERR]'} {d.get('titlu')}**"
                    + (f" — Cod HMI: `{hmi_d}`" if hmi_d else "")
                    + (f" — Driver/VFD: `{drv_d}`" if drv_d else "")
                    + (f" — Pagini: `{pag_d}`" if pag_d else "")
                    + (f" — [Google Drive]({d.get('gdrive_url')})" if d.get("gdrive_url") else "")
                )
        else:
            st.caption("Nu s-au găsit înregistrări în index pentru filtrul curent.")

    salveaza_in_index_sol = st.checkbox(
        "💾 Salvează soluția și în Indexul de Documentație (`[SOL]`) la finalizare",
        value=False,
        key="act_save_to_doc_sol",
    )

    b_col1, b_col2 = st.columns([2, 1])
    with b_col1:
        submitted = st.button("💾 Salvează Activitatea", type="primary", use_container_width=True)
    with b_col2:
        if st.button("❌ Anulare Activitate", key="btn_anulare_act_jos", use_container_width=True):
            _init_sau_reseteaza_act_draft(tehnician_def)
            st.rerun()

    if submitted:
        piese_valide = edited_df.dropna(subset=["Piesa"]).to_dict(orient="records")
        data_rep = {
            "firma": sel_firma, "masina": sel_masina, "subansamblu": sel_subansamblu, "defect": defect,
            "cod_eroare": cod_eroare, "piese_valide": piese_valide, "titlu_lucrare": titlu_lucrare,
            "simptom": simptom, "solutie": solutie, "stare_fin": stare_fin, "durata_min": durata_min,
            "optimizari": optimizari, "tehnician_nume": tehnician, "verificator_nume": verificator, "tip_interventie": tip_interventie
        }
        rid = ReparatiiRepository.insert(data_rep)
        if rid:
            if salveaza_in_index_sol and (str(solutie or "").strip() or str(defect or "").strip()):
                try:
                    cod_curat = "" if cod_eroare == "Niciunul" else str(cod_eroare).strip()
                    text_sol_parti = []
                    if str(simptom or "").strip():
                        text_sol_parti.append(f"Simptom: {str(simptom).strip()}")
                    if str(defect or "").strip():
                        text_sol_parti.append(f"Defect: {str(defect).strip()}")
                    if str(solutie or "").strip():
                        text_sol_parti.append(f"Soluție: {str(solutie).strip()}")
                    if str(optimizari or "").strip():
                        text_sol_parti.append(f"Recomandări: {str(optimizari).strip()}")

                    DocumentatieRepository.insert({
                        "masina_id": int(masina_id_sel) if masina_id_sel is not None else None,
                        "categorie": "CNC",
                        "tip_sistem": str(sel_subansamblu or "").strip(),
                        "titlu": f"{titlu_lucrare} ({sel_masina})" if sel_masina != "Nicio mașină" else titlu_lucrare,
                        "gdrive_file_id": "",
                        "gdrive_url": "",
                        "tip_fisier": "doc",
                        "tag_sectiune": "[SOL]",
                        "interval_pagini": "",
                        "coduri_eroare_hmi": cod_curat,
                        "coduri_eroare_driver": "",
                        "text_indexat": "\n".join(text_sol_parti),
                    })
                    st.session_state["solutie_indexata_flash"] = True
                except Exception:
                    pass

            pdf_bytes = genereaza_pdf({
                "id": rid, "client": sel_firma, "masina": sel_masina, "durata": durata_min,
                "stare_finala": stare_fin, "piese_json": [{"piesa": p.get("Piesa"), "cantitate": p.get("Cantitate"), "tip": p.get("Tip")} for p in piese_valide],
                "titlu": titlu_lucrare, "simptom": simptom, "defect": defect, "solutie": solutie,
                "optimizari": optimizari, "tehnician": tehnician, "verificator": verificator,
                "data": datetime.now(), "tip_interventie": tip_interventie
            })

            st.session_state["ultimul_id_salvat"] = rid
            st.session_state["ultimul_pdf_bytes"] = pdf_bytes
            st.session_state["ultim_email_client"] = email_client_sel
            st.session_state["ultim_firma_raport"] = sel_firma
            st.session_state["email_raport_trimis"] = False

            threading.Thread(target=background_sync_task, args=({
                "status": "nefacturat",
                "id": str(rid),
                "data": datetime.now().strftime("%Y-%m-%d"),
                "tip_interventie": tip_interventie,
                "ora": f"{durata_min} min",
                "firma": sel_firma,
                "masina": sel_masina,
                "tehnician": tehnician,
                "verificator": verificator
            },), daemon=True).start()

            _init_sau_reseteaza_act_draft(tehnician_def)
            st.session_state["raport_salvat"] = True
            st.rerun()