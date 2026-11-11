#------------------------------------------
#-------reparatii_electronice.py-----------
#------------------------------------------

import streamlit as st
import pandas as pd
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.reparatii_electronice_repository import ReparatiiElectroniceRepository
from services.pdf_service import genereaza_pdf_electronic

def render_reparatii_electronice():
    st.subheader("⚡ Gestiune Reparații Electronice & Mecatronice")

    @st.fragment
    def render_form_electronic():
        if "electrice_salvat" not in st.session_state: st.session_state["electrice_salvat"] = False
        if "electrice_pdf" not in st.session_state: st.session_state["electrice_pdf"] = None
        if "electrice_id" not in st.session_state: st.session_state["electrice_id"] = None

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
                if "df_comp_editor" in st.session_state: del st.session_state["df_comp_editor"]
                st.rerun()
            return

        sel_firma = st.selectbox("1. Alege Firma", options=list(firme_dict.keys()), key="el_sel_firma")
        firma_obj = firme_dict[sel_firma]

        # Opțiune dacă aparține sau nu unei mașini
        masini_db = MasiniRepository.get_by_firma(firma_obj['id'])
        masini_nume = [m['denumire'] for m in masini_db]

        apartenenta_masina = st.checkbox("Echipamentul / Piesa aparține unei mașini înregistrate?")
        sel_masina = "General / Fără mașină"
        masina_obj_id = None

        if apartenenta_masina and masini_nume:
            sel_masina = st.selectbox("Alege Mașina", options=masini_nume)
            m_match = next((m for m in masini_db if m['denumire'] == sel_masina), None)
            if m_match: masina_obj_id = m_match['id']

        c1, c2 = st.columns(2)
        with c1:
            piesa_subansamblu = st.text_input("Piesă sau Subansamblu (ex: Placă de bază CNC, Invertor, Unitate comandă)")
            defect_reclamat = st.text_area("Defect Reclamat")
        with c2:
            stare_finala = st.selectbox("Stare Finală Reparație", ["Funcțional", "Nefuncțional", "Înlocuit complet"])
            tehnician = st.text_input("Tehnician Electronică", value="Tehnician Service")
            verificator = st.text_input("Verificat de", value=firma_obj.get('nume_persoana', 'Client'))

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
            use_container_width=True
        )

        if st.button("💾 Salvează Fișa Electronică", type="primary"):
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
                    st.session_state["electrice_salvat"] = True
                    st.rerun()

    render_form_electronic()