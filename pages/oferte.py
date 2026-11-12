#----------------------------------
#-------pages/oferte.py------------
#----------------------------------

import streamlit as st
import pandas as pd
import json
from datetime import datetime, date
from repositories.firme_repository import FirmeRepository
from repositories.oferte_repository import OferteRepository
from services.pdf_service import genereaza_pdf_oferta

def render_oferte():
    st.subheader("💰 Generare & Gestiune Oferte de Preț")

    firme_list = FirmeRepository.get_all()
    if not firme_list:
        st.warning("⚠️ Adăugați cel puțin o firmă în Tabul de Firme înainte de a crea o ofertă.")
        return

    firme_dict = {f['nume_firma']: f for f in firme_list}
    sel_firma = st.selectbox("1. Selectează Clientul / Firma", options=list(firme_dict.keys()), key="oferta_sel_firma")
    client_obj = firme_dict[sel_firma]

    c1, c2 = st.columns(2)
    with c1:
        titlu_oferta = st.text_input("Titlu Ofertă / Obiectiv", value="Ofertă de preț servicii și piese", key="oferta_titlu")
        valabilitate = st.text_input("Valabilitate Ofertă", value="30 zile calendaristice", key="oferta_valabilitate")
    with c2:
        data_oferta = st.date_input("Data emiterii", value=date.today(), key="oferta_data")
        termeni_plata = st.text_input("Termeni de Plată", value="OP la 30 zile", key="oferta_plata")

    observatii = st.text_area("Observații / Mențiuni Speciale", placeholder="Condiții de livrare, garanție etc.", key="oferta_obs")

    st.markdown("##### 📋 Articole / Poziții Ofertă (Produse, Piese sau Servicii)")

    if "df_oferta_editor" not in st.session_state:
        st.session_state["df_oferta_editor"] = pd.DataFrame(columns=["Descriere", "UM", "Cantitate", "Pret Unitar (RON)"])

    edited_oferta_df = st.data_editor(
        st.session_state["df_oferta_editor"],
        num_rows="dynamic",
        column_config={
            "Descriere": st.column_config.TextColumn("Denumire Articol / Serviciu", required=True),
            "UM": st.column_config.SelectboxColumn("UM", options=["buc", "ore", "set", "ml", "kg"], default="buc", required=True),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.01, format="%.2f", default=1.0),
            "Pret Unitar (RON)": st.column_config.NumberColumn("Preț Unitar fără TVA (RON)", min_value=0.0, format="%.2f", default=0.0)
        },
        key="editor_linii_oferta"
    )

    if st.button("💾 Salvează și Generează PDF Ofertă", type="primary", key="btn_gen_pdf_oferta"):
        linii_valide = edited_oferta_df.dropna(subset=["Descriere"]).to_dict(orient="records")
        if not linii_valide:
            st.error("Adăugați cel puțin un articol în tabelul de oferte.")
            return

        subtotal = sum(float(l.get("Cantitate", 1)) * float(l.get("Pret Unitar (RON)", 0)) for l in linii_valide)
        tva = round(subtotal * 0.19, 2)
        total_general = round(subtotal + tva, 2)
        nr_oferta = datetime.now().strftime("%Y%m%d-%H%M")

        date_oferta_db = {
            "numar_oferta": nr_oferta,
            "data": data_oferta,
            "client": sel_firma,
            "cui_client": client_obj.get("cui", ""),
            "adresa_client": client_obj.get("adresa", ""),
            "titlu": titlu_oferta,
            "valabilitate": valabilitate,
            "termeni_plata": termeni_plata,
            "observatii": observatii,
            "articole": linii_valide,
            "subtotal": round(subtotal, 2),
            "tva": tva,
            "total_general": total_general,
            "status": "Emisă"
        }

        oferta_id = OferteRepository.insert(date_oferta_db)
        date_oferta_db["id"] = nr_oferta

        st.session_state["pdf_oferta_bytes"] = genereaza_pdf_oferta(date_oferta_db)
        st.session_state["pdf_oferta_nume"] = f"Oferta_{nr_oferta}_{sel_firma.replace(' ', '_')}.pdf"
        st.success(f"Oferta #{nr_oferta} a fost salvată în baza de date!")

    if "pdf_oferta_bytes" in st.session_state and st.session_state["pdf_oferta_bytes"]:
        st.download_button(
            label="📥 Descarcă PDF Ofertă de Preț",
            data=st.session_state["pdf_oferta_bytes"],
            file_name=st.session_state.get("pdf_oferta_nume", "Oferta_Pret.pdf"),
            mime="application/pdf",
            type="primary"
        )

    st.markdown("---")
    st.subheader("📂 Istoric Oferte Emise")
    oferte_salvate = OferteRepository.get_all()

    if oferte_salvate:
        for of in oferte_salvate:
            with st.expander(f"📄 Oferta #{of['numar_oferta']} | {of['firma']} — {of['total_general']} RON ({of['status']})"):
                col_o1, col_o2, col_o3 = st.columns([2, 1, 1])
                with col_o1:
                    st.write(f"**Obiect:** {of['titlu']}")
                    st.write(f"**Data:** {str(of['data_emitere'])[:10]}")
                with col_o2:
                    nou_status = st.selectbox(
                        "Status",
                        ["Emisă", "Acceptată", "Respinsă", "Facturată"],
                        index=["Emisă", "Acceptată", "Respinsă", "Facturată"].index(of['status']) if of['status'] in ["Emisă", "Acceptată", "Respinsă", "Facturată"] else 0,
                        key=f"status_of_{of['id']}"
                    )
                    if st.button("Actualizează Status", key=f"upd_of_{of['id']}"):
                        OferteRepository.update_status(of['id'], nou_status)
                        st.rerun()
                with col_o3:
                    if st.button("🗑️ Șterge Oferta", key=f"del_of_{of['id']}"):
                        OferteRepository.delete(of['id'])
                        st.rerun()
    else:
        st.info("Nu există oferte salvate în baza de date.")