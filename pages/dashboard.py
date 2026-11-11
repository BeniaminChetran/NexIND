#--------------------------
#--------dashboard.py------
#--------------------------

import streamlit as st
import pandas as pd
import plotly.express as px
from repositories.masini_repository import MasiniRepository
from config import db_cursor

def render_dashboard():
    st.title("📈 Dashboard CMMS")

    with db_cursor() as c:
        c.execute("""
            SELECT
                COUNT(*) AS interventii,
                COALESCE(SUM(durata),0) AS minute,
                COUNT(DISTINCT firma) AS clienti,
                COUNT(DISTINCT masina) AS utilaje,
                COUNT(*) FILTER (WHERE stare_finala='Oprită / Necesar piese') AS utilaje_oprite
            FROM reparatii
            WHERE DATE_TRUNC('month', data_creare) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        kpi_res = c.fetchone()

    interventii_luna = kpi_res["interventii"] if kpi_res else 0
    ore_lucrate = round(kpi_res["minute"] / 60, 1) if kpi_res else 0
    clienti_activi = kpi_res["clienti"] if kpi_res else 0
    utilaje_active = kpi_res["utilaje"] if kpi_res else 0
    utilaje_oprite = kpi_res["utilaje_oprite"] if kpi_res else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🔧 Intervenții luna curentă", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți activi", clienti_activi)
    c4.metric("⚙️ Utilaje active", utilaje_active)
    c5.metric("🚨 Utilaje Oprite", utilaje_oprite)

    st.markdown("---")

    with db_cursor() as c:
        c.execute("SELECT defect, COUNT(*) AS aparitii FROM reparatii WHERE defect IS NOT NULL AND defect <> '' GROUP BY defect ORDER BY aparitii DESC LIMIT 10")
        top_def = c.fetchall()
        c.execute("SELECT firma, COUNT(*) AS interventii FROM reparatii GROUP BY firma ORDER BY interventii DESC LIMIT 10")
        top_cli = c.fetchall()
        c.execute("SELECT masina, COUNT(*) AS interventii FROM reparatii GROUP BY masina ORDER BY interventii DESC LIMIT 10")
        top_ut = c.fetchall()
        c.execute("SELECT masina, defect, COUNT(*) AS repetitii FROM reparatii WHERE defect IS NOT NULL AND defect <> '' AND data_creare > CURRENT_DATE - INTERVAL '180 day' GROUP BY masina, defect HAVING COUNT(*) >= 3 ORDER BY repetitii DESC LIMIT 20")
        def_rec = c.fetchall()
        c.execute("SELECT denumire, data_intretinere FROM masini WHERE data_intretinere IS NOT NULL AND CAST(data_intretinere AS DATE) <= CURRENT_DATE + INTERVAL '30 day' ORDER BY data_intretinere")
        mas_scad = c.fetchall()

    if top_def:
        fig_defecte = px.bar(pd.DataFrame(top_def), x="aparitii", y="defect", orientation="h", title="Top 10 Defecte")
        st.plotly_chart(fig_defecte, use_container_width=True, key="grafic_top_defecte_dashboard")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏢 Top Clienți")
        if top_cli:
            fig_clienti = px.bar(pd.DataFrame(top_cli), x="interventii", y="firma", orientation="h", title="Top Clienți după număr intervenții")
            st.plotly_chart(fig_clienti, use_container_width=True, key="grafic_top_clienti_dashboard")
    with col2:
        st.subheader("⚙️ Top Utilaje")
        if top_ut:
            fig_utilaje = px.bar(pd.DataFrame(top_ut), x="masina", y="interventii", title="Top Utilaje după număr intervenții")
            st.plotly_chart(fig_utilaje, use_container_width=True, key="grafic_top_utilaje_dashboard")

    st.markdown("---")
    st.subheader("⚠️ Defecte Recurente (Ultimele 180 zile)")
    if def_rec:
        for d in def_rec:
            st.warning(f"⚠️ **{d['masina']}**\nDefect: {d['defect']}\nNumăr apariții: {d['repetitii']}")
    else:
        st.success("Nu există defecte recurente identificate în ultimele 180 de zile.")

    st.markdown("---")
    st.subheader("📅 Întrețineri Scadente")
    if mas_scad:
        st.dataframe(pd.DataFrame(mas_scad), use_container_width=True)
    else:
        st.success("Nu există întrețineri programate în următoarele 30 de zile.")