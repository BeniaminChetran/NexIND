#------------------------------------------
#-------reparatii_electronice.py-----------
#------------------------------------------

import streamlit as st
import pandas as pd
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.reparatii_electronice_repository import ReparatiiElectroniceRepository
from repositories.setari_repository import SetariRepository
from services.pdf_service import genereaza_pdf_electronic

def _init_sau_reseteaza_el_draft(tehnician_def: str):
    st.session_state["el_draft"] = {
        "sel_firma": "-- Alege firma --",
        "apartenenta_masina": False,
        "sel_masina": "General / Fără mașină",
        "piesa_subansamblu": "",
        "defect_reclamat": "",
        "stare_finala": "Funcțional",
        "tehnician": tehnician_def,
        "verificator": "Client",
        "ultima_firma": "-- Alege firma --"
    }
    st.session_state["df_comp_editor"] = pd.DataFrame(columns=["Componenta / Cod / Parametri", "Stare"])
    st.session_state["el_editor_counter"] = st.session_state.get("el_editor_counter", 0) + 1

def render_reparatii_electronice():
    st.subheader("⚡ Gestiune Reparații Electronice & Mecatronice")

    setari_el = SetariRepository.get_setari()
    tehnician_def_el = setari_el.get("tehnician_implicit") or "Tehnician Nexus"

    if "el_draft" not in st.session_state:
        _init_sau_reseteaza_el_draft(tehnician_def_el)
    if "electrice_salvat" not in st.session_state:
        st.session_state["electrice_salvat"] = False
    if "electrice_pdf" not in st.session_state:
        st.session_state["electrice_pdf"] = None
    if "electrice_id" not in st.session_state:
        st.session_state["electrice_id"] = None

    draft = st.session_state["el_draft"]

    firme_db = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f for f in firme_db}

    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă.")
        return

    if st.session_state["electrice_salvat"]:
        st.success("✅ Fișa de reparație electronică a fost salvată cu succes!")
        if st.session_state["electrice_pdf"]:
            st.download_button(
                label="📥 Descarcă Raport PDF Reparație Electronică",
                data=st.session_state["electrice_pdf"],
                file_name=f"Raport_Electronic_{st.session_state['electrice_id']}.pdf",
                mime="application/pdf",
                type="primary"
            )
        if st.button("➕ Adaugă altă reparație electronică"):
            st.session_state["electrice_salvat"] = False
            st.session_state["electrice_pdf"] = None
            st.session_state["electrice_id"] = None
            _init_sau_reseteaza_el_draft(tehnician_def_el)
            st.rerun()
        return

    top_e1, top_e2 = st.columns([4, 1], vertical_alignment="center")
    with top_e1:
        st.caption("💾 Datele fișei electronice se păstrează automat la schimbarea tab-ului.")
    with top_e2:
        if st.button("❌ Anulare Fișă", key="btn_anulare_el_top", use_container_width=True):
            _init_sau_reseteaza_el_draft(tehnician_def_el)
            st.toast("🗑️ Datele fișei electronice au fost resetate.")
            st.rerun()

    optiuni_firme = ["-- Alege firma --"] + list(firme_dict.keys())
    idx_f = optiuni_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in optiuni_firme else 0
    sel_firma = st.selectbox("1. Alege Firma", options=optiuni_firme, index=idx_f)
    draft["sel_firma"] = sel_firma

    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Selectați o firmă pentru a continua.")
        return

    firma_obj = firme_dict[sel_firma]
    if draft.get("ultima_firma") != sel_firma:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = firma_obj.get('nume_persoana') or firma_obj.get('persoana_contact') or 'Client'

    masini_db = MasiniRepository.get_by_firma(firma_obj['id'])
    masini_nume = [m['denumire'] for m in masini_db]

    apartenenta_masina = st.checkbox(
        "Echipamentul / Piesa aparține unei mașini înregistrate?",
        value=bool(draft.get("apartenenta_masina", False))
    )
    draft["apartenenta_masina"] = apartenenta_masina

    sel_masina = "General / Fără mașină"
    masina_obj_id = None

    if apartenenta_masina and masini_nume:
        idx_m = masini_nume.index(draft["sel_masina"]) if draft.get("sel_masina") in masini_nume else 0
        sel_masina = st.selectbox("Alege Mașina", options=masini_nume, index=idx_m)
        draft["sel_masina"] = sel_masina
        m_match = next((m for m in masini_db if m['denumire'] == sel_masina), None)
        if m_match:
            masina_obj_id = m_match['id']
    else:
        draft["sel_masina"] = "General / Fără mașină"

    c1, c2 = st.columns(2)
    with c1:
        piesa_subansamblu = st.text_input(
            "Piesă sau Subansamblu (ex: Placă de bază CNC, Invertor, Unitate comandă)",
            value=str(draft.get("piesa_subansamblu", ""))
        )
        draft["piesa_subansamblu"] = piesa_subansamblu

        defect_reclamat = st.text_area("Defect Reclamat", value=str(draft.get("defect_reclamat", "")))
        draft["defect_reclamat"] = defect_reclamat
    with c2:
        opt_stari = ["Funcțional", "Nefuncțional", "Înlocuit complet"]
        idx_st = opt_stari.index(draft["stare_finala"]) if draft.get("stare_finala") in opt_stari else 0
        stare_finala = st.selectbox("Stare Finală Reparație", options=opt_stari, index=idx_st)
        draft["stare_finala"] = stare_finala

        tehnician = st.text_input("Tehnician Electronică", value=str(draft.get("tehnician", tehnician_def_el)))
        draft["tehnician"] = tehnician

        verificator = st.text_input("Verificat de", value=str(draft.get("verificator", "Client")))
        draft["verificator"] = verificator

    st.markdown("#### 🔌 Componente Electronice / Elemente Defecte sau Înlocuite")
    st.info("Adăugați componente electronice (cu cod piesă/parametri) sau elemente mecanice mici (arcuri, rotițe, micromotoare).")

    if "df_comp_editor" not in st.session_state:
        st.session_state["df_comp_editor"] = pd.DataFrame(columns=["Componenta / Cod / Parametri", "Stare"])

    edited_comp_df = st.data_editor(
        st.session_state["df_comp_editor"], 
        num_rows="dynamic", 
        column_config={
            "Componenta / Cod / Parametri": st.column_config.TextColumn("Componentă / Cod / Parametri (ex: C 100uF 50V, Rotiță dințată z=15)", required=True),
            "Stare": st.column_config.SelectboxColumn("Stare Componentă", options=["Inlocuita", "Necesara", "Reparata"], required=True)
        },
        key=f"el_comp_editor_{st.session_state.get('el_editor_counter', 0)}",
        use_container_width=True
    )
    st.session_state["df_comp_editor"] = edited_comp_df

    be1, be2 = st.columns([2, 1])
    with be1:
        salveaza_el = st.button("💾 Salvează Fișa Electronică", type="primary", use_container_width=True)
    with be2:
        if st.button("❌ Anulare Fișă", key="btn_anulare_el_jos", use_container_width=True):
            _init_sau_reseteaza_el_draft(tehnician_def_el)
            st.rerun()

    if salveaza_el:
        if not piesa_subansamblu.strip():
            st.error("Completați denumirea piesei sau subansamblului.")
        else:
            componente_valide = edited_comp_df.dropna(subset=["Componenta / Cod / Parametri"]).to_dict(orient="records")
            
            payload = {
                "firma_id": firma_obj['id'],
                "masina_id": masina_obj_id,
                "firma_nume": sel_firma,
                "masina_nume": sel_masina,
                "piesa_subansamblu": piesa_subansamblu,
                "defect_reclamat": defect_reclamat,
                "componente_json": componente_valide,
                "stare_finala": stare_finala,
                "tehnician": tehnician,
                "verificator": verificator
            }

            rid = ReparatiiElectroniceRepository.insert(payload)
            if rid:
                pdf_bytes = genereaza_pdf_electronic({
                    "id": rid,
                    "client": sel_firma,
                    "masina": sel_masina,
                    "piesa_subansamblu": piesa_subansamblu,
                    "defect_reclamat": defect_reclamat,
                    "componente_json": componente_valide,
                    "stare_finala": stare_finala,
                    "tehnician": tehnician,
                    "verificator": verificator,
                    "data": datetime.now()
                })

                st.session_state["electrice_id"] = rid
                st.session_state["electrice_pdf"] = pdf_bytes
                _init_sau_reseteaza_el_draft(tehnician_def_el)
                st.session_state["electrice_salvat"] = True
                st.rerun()