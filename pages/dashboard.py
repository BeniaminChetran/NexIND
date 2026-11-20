import streamlit as st
import pandas as pd
import plotly.express as px
from config import db_cursor


@st.cache_data(ttl=120)
def incarca_date_dashboard():
    with db_cursor() as c:
        c.execute("""
            SELECT
                COUNT(*) AS interventii,
                COALESCE(SUM(durata),0) AS minute,
                COUNT(DISTINCT firma) AS clienti,
                COUNT(DISTINCT masina) AS utilaje,
                COUNT(*) FILTER (WHERE stare_finala='Oprită / Necesar piese') AS utilaje_oprite,
                COUNT(*) FILTER (WHERE LOWER(COALESCE(stare_finala, '')) LIKE '%supraveghere%') AS utilaje_supraveghere
            FROM reparatii
            WHERE DATE_TRUNC('month', data_creare) = DATE_TRUNC('month', CURRENT_DATE)
        """)
        kpi_res = c.fetchone()

        c.execute(
            "SELECT defect, COUNT(*) AS aparitii FROM reparatii "
            "WHERE defect IS NOT NULL AND defect <> '' "
            "GROUP BY defect ORDER BY aparitii DESC LIMIT 10"
        )
        top_def = c.fetchall()

        c.execute(
            "SELECT firma, COUNT(*) AS interventii FROM reparatii "
            "GROUP BY firma ORDER BY interventii DESC LIMIT 10"
        )
        top_cli = c.fetchall()

        c.execute(
            "SELECT masina, COUNT(*) AS interventii FROM reparatii "
            "GROUP BY masina ORDER BY interventii DESC LIMIT 10"
        )
        top_ut = c.fetchall()

        c.execute(
            "SELECT masina, defect, COUNT(*) AS repetitii FROM reparatii "
            "WHERE defect IS NOT NULL AND defect <> '' AND data_creare > CURRENT_DATE - INTERVAL '180 day' "
            "GROUP BY masina, defect HAVING COUNT(*) >= 3 ORDER BY repetitii DESC LIMIT 20"
        )
        def_rec = c.fetchall()

        c.execute(
            "SELECT denumire, data_intretinere FROM masini "
            "WHERE data_intretinere IS NOT NULL AND CAST(data_intretinere AS DATE) <= CURRENT_DATE + INTERVAL '30 day' "
            "ORDER BY data_intretinere"
        )
        mas_scad = c.fetchall()

    return kpi_res, top_def, top_cli, top_ut, def_rec, mas_scad


@st.cache_data(ttl=120)
def incarca_utilaje_dupa_stare(mod: str):
    """
    mod:
      - 'oprite' -> utilaje oprite
      - 'supraveghere' -> utilaje în stare 'Funcțională sub supraveghere'
    """
    with db_cursor() as c:
        if mod == "supraveghere":
            c.execute("""
                SELECT
                    id,
                    COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă') AS firma,
                    COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat') AS utilaj,
                    COALESCE(
                        NULLIF(TRIM(defect), ''),
                        NULLIF(TRIM(solutie), ''),
                        NULLIF(TRIM(titlu), ''),
                        'Nespecificat'
                    ) AS motiv_oprire,
                    COALESCE(stare_finala, 'Funcțională sub supraveghere') AS stare,
                    TO_CHAR(data_creare, 'YYYY-MM-DD') AS data_inregistrare
                FROM reparatii
                WHERE LOWER(COALESCE(stare_finala, '')) LIKE '%supraveghere%'
                ORDER BY data_creare DESC NULLS LAST, id DESC
            """)
        else:
            c.execute("""
                SELECT
                    id,
                    COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă') AS firma,
                    COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat') AS utilaj,
                    COALESCE(
                        NULLIF(TRIM(defect), ''),
                        NULLIF(TRIM(titlu), ''),
                        'Nespecificat'
                    ) AS motiv_oprire,
                    COALESCE(stare_finala, 'Oprită / Necesar piese') AS stare,
                    TO_CHAR(data_creare, 'YYYY-MM-DD') AS data_inregistrare
                FROM reparatii
                WHERE stare_finala = 'Oprită / Necesar piese'
                   OR LOWER(COALESCE(stare_finala, '')) LIKE '%oprit%'
                ORDER BY data_creare DESC NULLS LAST, id DESC
            """)
        rows = c.fetchall() or []
    return [dict(r) for r in rows]


def actualizeaza_stare_reparatie(reparatie_id: int, stare_noua: str):
    with db_cursor() as c:
        c.execute(
            "UPDATE reparatii SET stare_finala = %s WHERE id = %s",
            (stare_noua, int(reparatie_id)),
        )
    incarca_date_dashboard.clear()
    incarca_utilaje_dupa_stare.clear()


@st.cache_data(ttl=120)
def incarca_clienti_inactivi(zile_inactivitate: int = 90):
    """Returnează doar clienții inactivi (fără activitate în ultimele N zile)."""
    with db_cursor() as c:
        try:
            c.execute("""
                SELECT
                    f.nume AS "Client / Firmă",
                    COALESCE(NULLIF(TRIM(f.cui), ''), '-') AS "CUI",
                    TO_CHAR(MAX(r.data_creare), 'YYYY-MM-DD') AS "Ultima intervenție"
                FROM firme f
                LEFT JOIN reparatii r ON LOWER(TRIM(r.firma)) = LOWER(TRIM(f.nume))
                GROUP BY f.id, f.nume, f.cui
                HAVING MAX(r.data_creare) IS NULL
                    OR MAX(r.data_creare) < CURRENT_DATE - (%s * INTERVAL '1 day')
                ORDER BY f.nume ASC
            """, (int(zile_inactivitate),))
            rows = c.fetchall() or []
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass

        c.execute("""
            SELECT
                TRIM(firma) AS "Client / Firmă",
                TO_CHAR(MAX(data_creare), 'YYYY-MM-DD') AS "Ultima intervenție",
                COUNT(*) AS "Total intervenții istoric"
            FROM reparatii
            WHERE firma IS NOT NULL AND TRIM(firma) <> ''
            GROUP BY TRIM(firma)
            HAVING MAX(data_creare) < CURRENT_DATE - (%s * INTERVAL '1 day')
            ORDER BY MAX(data_creare) ASC
        """, (int(zile_inactivitate),))
        rows = c.fetchall() or []
    return [dict(r) for r in rows]


def _randare_lista_utilaje_stare(items: list[dict], este_supraveghere: bool):
    for item in items:
        rep_id = item["id"]
        col_info, col_act1, col_act2 = st.columns([5.2, 1.3, 1.3], vertical_alignment="center")
        with col_info:
            st.markdown(
                f"<div style='font-size:13px; line-height:1.35;'>"
                f"<b>{item['firma']}</b> — {item['utilaj']} "
                f"<span style='color:#64748B;'>(#{rep_id} • {item['data_inregistrare']})</span><br/>"
                f"<span style='font-size:12px; color:#475569;'><b>Motiv / Detalii:</b> {item['motiv_oprire']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_act1:
            if st.button("✅ Activ", key=f"btn_activ_{mod_key(este_supraveghere)}_{rep_id}", use_container_width=True):
                actualizeaza_stare_reparatie(rep_id, "Funcțională")
                st.toast(f"✅ #{rep_id} ({item['utilaj']}) trecut pe Funcțională!")
                st.rerun()
        with col_act2:
            if not este_supraveghere:
                if st.button("👀 Supraveghere", key=f"btn_supr_{rep_id}", use_container_width=True):
                    actualizeaza_stare_reparatie(rep_id, "Funcțională sub supraveghere")
                    st.toast(f"👀 #{rep_id} ({item['utilaj']}) trecut pe Funcțională sub supraveghere!")
                    st.rerun()


def mod_key(este_supraveghere: bool) -> str:
    return "supr" if este_supraveghere else "oprit"


def render_dashboard():
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.title("📈 Dashboard CMMS")
    with col_refresh:
        if st.button("🔄 Actualizează", use_container_width=True):
            incarca_date_dashboard.clear()
            incarca_utilaje_dupa_stare.clear()
            incarca_clienti_inactivi.clear()
            st.rerun()

    kpi_res, top_def, top_cli, top_ut, def_rec, mas_scad = incarca_date_dashboard()

    interventii_luna = kpi_res["interventii"] if kpi_res else 0
    ore_lucrate = round(kpi_res["minute"] / 60, 1) if kpi_res else 0
    clienti_activi = kpi_res["clienti"] if kpi_res else 0
    utilaje_active = kpi_res["utilaje"] if kpi_res else 0
    utilaje_oprite = kpi_res["utilaje_oprite"] if kpi_res else 0
    utilaje_supr = kpi_res["utilaje_supraveghere"] if kpi_res else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔧 Intervenții luna curentă", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți activi", clienti_activi)
    c4.metric("⚙️ Utilaje active", utilaje_active)
    c5.metric("🚨 Utilaje Oprite", utilaje_oprite)
    c6.metric("👀 Sub supraveghere", utilaje_supr)

    st.session_state.setdefault("dash_sectiune_activa", None)

    b1, b2, b3, b4 = st.columns([1.5, 1.7, 1.5, 1.0])
    with b1:
        if st.button(
            "🛑 Utilaje oprite",
            use_container_width=True,
            type="primary" if st.session_state["dash_sectiune_activa"] == "utilaje_oprite" else "secondary",
            key="btn_dash_utilaje_oprite"
        ):
            st.session_state["dash_sectiune_activa"] = (
                None if st.session_state["dash_sectiune_activa"] == "utilaje_oprite" else "utilaje_oprite"
            )
    with b2:
        if st.button(
            "👀 Sub supraveghere",
            use_container_width=True,
            type="primary" if st.session_state["dash_sectiune_activa"] == "sub_supraveghere" else "secondary",
            key="btn_dash_sub_supraveghere"
        ):
            st.session_state["dash_sectiune_activa"] = (
                None if st.session_state["dash_sectiune_activa"] == "sub_supraveghere" else "sub_supraveghere"
            )
    with b3:
        if st.button(
            "💤 Clienți inactivi",
            use_container_width=True,
            type="primary" if st.session_state["dash_sectiune_activa"] == "clienti_inactivi" else "secondary",
            key="btn_dash_clienti_inactivi"
        ):
            st.session_state["dash_sectiune_activa"] = (
                None if st.session_state["dash_sectiune_activa"] == "clienti_inactivi" else "clienti_inactivi"
            )
    with b4:
        if st.session_state["dash_sectiune_activa"] is not None and st.button("✖ Ascunde", use_container_width=True, key="btn_dash_ascunde"):
            st.session_state["dash_sectiune_activa"] = None

    sectiune_activa = st.session_state.get("dash_sectiune_activa")

    if sectiune_activa == "utilaje_oprite":
        st.markdown("---")
        st.markdown("#### 🛑 Utilaje Oprite — Motiv & Firmă")
        date_oprite = incarca_utilaje_dupa_stare("oprite")
        if date_oprite:
            _randare_lista_utilaje_stare(date_oprite, este_supraveghere=False)
        else:
            st.info("Nu există utilaje oprite în acest moment.")
        return

    if sectiune_activa == "sub_supraveghere":
        st.markdown("---")
        st.markdown("#### 👀 Funcțională sub supraveghere")
        date_supr = incarca_utilaje_dupa_stare("supraveghere")
        if date_supr:
            _randare_lista_utilaje_stare(date_supr, este_supraveghere=True)
        else:
            st.info("Nu există utilaje în starea «Funcțională sub supraveghere».")
        return

    if sectiune_activa == "clienti_inactivi":
        st.markdown("---")
        st.markdown("#### 💤 Clienți Inactivi")
        zile_prag = st.selectbox(
            "Fără intervenții de cel puțin:",
            options=[30, 60, 90, 180],
            index=2,
            format_func=lambda x: f"{x} zile",
            key="sel_zile_clienti_inactivi"
        )
        date_inactivi = incarca_clienti_inactivi(zile_prag)
        if date_inactivi:
            st.dataframe(pd.DataFrame(date_inactivi), use_container_width=True, hide_index=True)
        else:
            st.info(f"Nu există clienți inactivi în ultimele {zile_prag} de zile.")
        return

    st.markdown("---")

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