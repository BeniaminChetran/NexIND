#----------------------------------
#-------masuratori.py--------------
#----------------------------------

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.masuratori_repository import MasuratoriRepository
from config import db_cursor

def render_masuratori():
    st.subheader("📏 Înregistrare Parametri Tehnici & Grafic Evoluție")

    firme_db = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f['id'] for f in firme_db}

    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în baza de date.")
        return

    col1, col2 = st.columns(2)
    with col1:
        sel_firma_nume = st.selectbox("1. Alege Firma", options=list(firme_dict.keys()), key="masuratori_sel_firma")
        firma_id = firme_dict[sel_firma_nume]

    masini_db = MasiniRepository.get_by_firma(firma_id)
    masini_dict = {m['denumire']: m for m in masini_db}

    with col2:
        if not masini_dict:
            st.warning("⚠️ Nu există mașini înregistrate pentru această firmă.")
            return
        sel_masina_nume = st.selectbox("2. Alege Mașina", options=list(masini_dict.keys()), key="masuratori_sel_masina")
        masina_obj = masini_dict[sel_masina_nume]
        masina_id = masina_obj['id']

    st.markdown("---")

    @st.fragment
    def render_form_si_grafic(firma_id_val, masina_obj_val):
        m_id = masina_obj_val['id']
        m_nume = masina_obj_val['denumire']

        subansambluri_existente = []
        if masina_obj_val.get('subansambluri'):
            subansambluri_existente = [s.strip() for s in masina_obj_val['subansambluri'].split(",") if s.strip()]

        st.markdown(f"### ➕ Introducere Măsurătoare Nouă ({m_nume})")
        
        with st.form("form_adauga_masuratoare", clear_on_submit=False):
            f_col1, f_col2 = st.columns(2)
            
            with f_col1:
                subansamblu_input = st.text_input(
                    "Subansamblu (ex: Rulment ax principal, Pompă hidraulică)", 
                    help="Dacă scrii un subansamblu nou, acesta se va adăuga automat în lista de subansambluri a mașinii."
                )
                parametru_input = st.text_input("Parametru măsurat (ex: Temperatură, Joc axial, Presiune, Vibrații)")

            with f_col2:
                valoare_input = st.number_input(
                    "Valoare Măsurată (cu semn +/-)", 
                    format="%.3f", 
                    step=0.001,
                    help="Acceptă valori pozitive sau negative (ex: +23.450 sau -0.125)"
                )
                
                unitati_optiuni = ["°C", "bar", "mm", "mm/s", "RPM", "V", "A", "Hz", "dB", "kW", "Ohm", "%", "Altul"]
                unitate_input = st.selectbox("Unitate de Măsură", options=unitati_optiuni)
                if unitate_input == "Altul":
                    unitate_custom = st.text_input("Specifică unitatea de măsură")
                    if unitate_custom:
                        unitate_input = unitate_custom

            btn_salveaza = st.form_submit_button("💾 Salvează Măsurătoarea", type="primary")

            if btn_salveaza:
                if not subansamblu_input.strip() or not parametru_input.strip():
                    st.error("Te rugăm să completezi subansamblul și denumirea parametrului.")
                else:
                    sub_curat = subansamblu_input.strip()
                    
                    # Salvare prin repository
                    MasuratoriRepository.insert({
                        "firma_id": firma_id_val,
                        "masina_id": m_id,
                        "subansamblu": sub_curat,
                        "parametru": parametru_input.strip(),
                        "valoare": valoare_input,
                        "unitate_masura": unitate_input,
                        "data_masurare": datetime.now()
                    })

                    # Actualizare subansambluri mașină dacă e nou
                    if sub_curat.lower() not in [s.lower() for s in subansambluri_existente]:
                        subansambluri_existente.append(sub_curat)
                        lista_noua_str = ", ".join(subansambluri_existente)
                        with db_cursor() as c:
                            c.execute("UPDATE masini SET subansambluri = %s WHERE id = %s", (lista_noua_str, m_id))
                        masina_obj_val['subansambluri'] = lista_noua_str

                    st.success(f"Măsurătoarea pentru '{parametru_input}' ({valoare_input:+.3f} {unitate_input}) a fost salvată!")

        st.markdown("---")
        st.markdown(f"### 📈 Grafic Evoluție Parametri Măsurați — **{m_nume}**")

        # Preluare date prin repository
        masuratori_db = MasuratoriRepository.get_by_masina(m_id)

        if not masuratori_db:
            st.info("Nu există încă măsurători înregistrate pentru această mașină.")
            return

        df_masuratori = pd.DataFrame(masuratori_db)
        df_masuratori['data_masurare'] = pd.to_datetime(df_masuratori['data_masurare'])
        df_masuratori['valoare'] = df_masuratori['valoare'].astype(float)
        df_masuratori['eticheta_parametru'] = df_masuratori['subansamblu'] + " - " + df_masuratori['parametru'] + " (" + df_masuratori['unitate_masura'] + ")"

        parametri_unic = list(df_masuratori['eticheta_parametru'].unique())
        sel_param_grafic = st.multiselect("Filtrează Parametrii pe Grafic", options=parametri_unic, default=parametri_unic)

        if sel_param_grafic:
            df_filtrat = df_masuratori[df_masuratori['eticheta_parametru'].isin(sel_param_grafic)]

            fig = px.line(
                df_filtrat,
                x="data_masurare",
                y="valoare",
                color="eticheta_parametru",
                markers=True,
                title=f"Evoluția în Timp a Parametrilor Tehnici ({m_nume})",
                labels={
                    "data_masurare": "Timp (Data & Ora)",
                    "valoare": "Valoare Măsurată",
                    "eticheta_parametru": "Parametru / Subansamblu"
                },
                hover_data={"valoare": ":+.3f", "unitate_masura": True, "subansamblu": True}
            )

            fig.update_layout(
                xaxis=dict(autorange=True, title="Timp Scurs"),
                yaxis=dict(autorange=True, title="Valoare Parametru"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="plotly_dark",
                height=450
            )

            st.plotly_chart(fig, use_container_width=True, key=f"grafic_masuratori_{m_id}")

            st.markdown("#### 📋 Tabel Istoric Măsurători")
            df_afisare = df_filtrat[['data_masurare', 'subansamblu', 'parametru', 'valoare', 'unitate_masura']].copy()
            df_afisare.columns = ["Data & Ora", "Subansamblu", "Parametru", "Valoare Măsurată", "Unitate"]
            df_afisare["Valoare Măsurată"] = df_afisare["Valoare Măsurată"].map("{:+.3f}".format)
            st.dataframe(df_afisare, use_container_width=True)

    render_form_si_grafic(firma_id, masina_obj)