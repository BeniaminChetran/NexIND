import streamlit as st
import pandas as pd
import plotly.express as px
import json
import datetime


from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import NecesarPieseRepository
from repositories.taskuri_vizita_repository import (
    OPTIUNI_STARE_TASK_VIZITA,
    TaskuriVizitaRepository,
    normalizeaza_stare_task_vizita,
)
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_repository import ReparatiiRepository
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import NecesarPieseRepository
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

        # Reparații la mașini (din tabela reparatii): reușite vs total
        c.execute("""
            SELECT
                COUNT(*) AS total_masini_rep,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(stare_finala, '')) LIKE 'funcțional%%'
                       OR LOWER(COALESCE(stare_finala, '')) LIKE 'functional%%'
                ) AS reusite_masini_rep
            FROM reparatii
        """)
        masini_rep_res = c.fetchone() or {}

        # Reparații electronice: reușite vs total
        try:
            c.execute("""
                SELECT
                    COUNT(*) AS total_el_rep,
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(stare_finala, '')) = 'funcțional'
                           OR LOWER(COALESCE(stare_finala, '')) = 'functional'
                    ) AS reusite_el_rep
                FROM reparatii_electronice
            """)
            el_rep_res = c.fetchone() or {}
        except Exception:
            el_rep_res = {"total_el_rep": 0, "reusite_el_rep": 0}

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

    return kpi_res, masini_rep_res, el_rep_res, top_def, top_cli, top_ut, def_rec, mas_scad


@st.cache_data(ttl=120)
def incarca_memento_intretinere(zile_inainte: int = 14):
    zile = max(0, int(zile_inainte))
    try:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    m.id,
                    COALESCE(
                        NULLIF(TRIM(to_jsonb(f)->>'nume_firma'), ''),
                        NULLIF(TRIM(to_jsonb(f)->>'nume'), ''),
                        NULLIF(TRIM(to_jsonb(f)->>'denumire'), ''),
                        'Fără firmă'
                    ) AS firma,
                    m.denumire AS utilaj,
                    CAST(m.data_intretinere AS DATE) AS data_scadenta,
                    (CAST(m.data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                FROM masini m
                LEFT JOIN firme f ON f.id = m.firma_id
                WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                  AND m.data_intretinere IS NOT NULL
                  AND CAST(m.data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY CAST(m.data_intretinere AS DATE) ASC, firma ASC, m.denumire ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    id,
                    'Fără firmă' AS firma,
                    denumire AS utilaj,
                    CAST(data_intretinere AS DATE) AS data_scadenta,
                    (CAST(m.data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                FROM masini m
                WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                  AND m.data_intretinere IS NOT NULL
                  AND CAST(m.data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY CAST(m.data_intretinere AS DATE) ASC, m.denumire ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]

@st.cache_data(ttl=120)
def incarca_defecte_recurente(zile_inainte: int = 180):
    zile = max(1, int(zile_inainte))
    with db_cursor() as c:
        c.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă') AS firma,
                COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat') AS masina,
                defect,
                COUNT(*) AS repetitii
            FROM reparatii
            WHERE defect IS NOT NULL AND defect <> ''
              AND data_creare > CURRENT_DATE - make_interval(days => %s)
            GROUP BY COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă'), COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat'), defect
            HAVING COUNT(*) >= 3
            ORDER BY repetitii DESC, firma ASC, masina ASC
            LIMIT 50
            """,
            (zile,),
        )
        return [dict(r) for r in (c.fetchall() or [])]

def render_memento_intretinere_dashboard():
    st.markdown("### 🔔 Memento Scadențe Întreținere")
    col_z, col_info = st.columns([1.4, 3.6], vertical_alignment="bottom")
    with col_z:
        zile_avans = st.selectbox(
            "Anunță-mă cu cel puțin:",
            options=[3, 7, 14, 21, 30, 60],
            index=2,
            format_func=lambda x: f"{x} zile înainte",
            key="dash_memento_intretinere_zile",
        )

    alerta_rows = incarca_memento_intretinere(zile_avans)
    with col_info:
        if alerta_rows:
            st.warning(
                f"⏰ Ai **{len(alerta_rows)}** utilaje cu întreținerea scadentă în următoarele **{zile_avans}** zile (sau deja depășite)."
            )
        else:
            st.success(f"✅ Nicio întreținere scadentă în următoarele **{zile_avans}** zile.")

    if alerta_rows:
        df_m = pd.DataFrame([
            {
                "Firmă": r.get("firma") or "Fără firmă",
                "Utilaj": r.get("utilaj") or "",
                "Data scadentă": str(r.get("data_scadenta") or ""),
                "Zile rămase": int(r.get("zile_ramase") or 0),
                "Status memento": (
                    "🚨 Depășită" if int(r.get("zile_ramase") or 0) < 0
                    else ("⚠️ Azi" if int(r.get("zile_ramase") or 0) == 0 else "🔔 În curând")
                ),
            }
            for r in alerta_rows
        ])
        df_m = df_m[["Firmă", "Utilaj", "Data scadentă", "Zile rămase", "Status memento"]]
        st.dataframe(df_m, hide_index=True, use_container_width=True)

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
    zile = int(zile_inactivitate)

    try:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    f.nume AS "Client / Firmă",
                    TO_CHAR(MAX(r.data_creare), 'YYYY-MM-DD') AS "Ultima intervenție"
                FROM firme f
                LEFT JOIN reparatii r ON LOWER(TRIM(r.firma)) = LOWER(TRIM(f.nume))
                GROUP BY f.id, f.nume
                HAVING MAX(r.data_creare) IS NULL
                    OR MAX(r.data_creare) < (CURRENT_DATE - make_interval(days => %s))::timestamp
                ORDER BY f.nume ASC
            """, (zile,))
            rows = c.fetchall() or []
            if rows:
                return [dict(r) for r in rows]
    except Exception:
        pass

    with db_cursor() as c:
        c.execute("""
            SELECT
                TRIM(firma) AS "Client / Firmă",
                TO_CHAR(MAX(data_creare), 'YYYY-MM-DD') AS "Ultima intervenție",
                COUNT(*) AS "Total intervenții istoric"
            FROM reparatii
            WHERE firma IS NOT NULL AND TRIM(firma) <> ''
            GROUP BY TRIM(firma)
            HAVING MAX(data_creare) < (CURRENT_DATE - make_interval(days => %s))::timestamp
            ORDER BY MAX(data_creare) ASC
        """, (zile,))
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

    kpi_res, masini_rep_res, el_rep_res, top_def, top_cli, top_ut, def_rec, mas_scad = incarca_date_dashboard()

    interventii_luna = kpi_res["interventii"] if kpi_res else 0
    ore_lucrate = round(kpi_res["minute"] / 60, 1) if kpi_res else 0
    clienti_activi = kpi_res["clienti"] if kpi_res else 0
    utilaje_active = kpi_res["utilaje"] if kpi_res else 0
    utilaje_oprite = kpi_res["utilaje_oprite"] if kpi_res else 0
    utilaje_supr = kpi_res["utilaje_supraveghere"] if kpi_res else 0

    reusite_masini = int(masini_rep_res.get("reusite_masini_rep") or 0)
    total_masini = int(masini_rep_res.get("total_masini_rep") or 0)
    pct_masini = f"{round((reusite_masini / total_masini) * 100)}%" if total_masini > 0 else "0%"

    reusite_el = int(el_rep_res.get("reusite_el_rep") or 0)
    total_el = int(el_rep_res.get("total_el_rep") or 0)
    pct_el = f"{round((reusite_el / total_el) * 100)}%" if total_el > 0 else "0%"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔧 Intervenții luna curentă", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți activi", clienti_activi)
    c4.metric("⚙️ Utilaje active", utilaje_active)
    c5.metric("🚨 Utilaje Oprite", utilaje_oprite)
    c6.metric("👀 Sub supraveghere", utilaje_supr)

    # -------Afisare piese de comandat-----------
    st.markdown("---")
    with st.expander("🛒 Piese De Comandat / Necesare & Furnizori", expanded=True):
        render_piese_de_comandat_dashboard()
    # -------end Afisare piese de comandat-----------

    m_r1, m_r2 = st.columns(2)
    m_r1.metric("⚙️ Reparații Mașini Reușite", f"{reusite_masini} / {total_masini}", delta=pct_masini)
    m_r2.metric("⚡ Reparații Electronice Reușite", f"{reusite_el} / {total_el}", delta=pct_el)

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

    # 1. ÎNTREȚINERI SCADENTE
    st.subheader("📅 Întrețineri Scadente")
    render_memento_intretinere_dashboard()

    st.markdown("---")

    # 2. DEFECTE RECURENTE
    st.subheader("⚠️ Defecte Recurente")
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        zile_defecte = st.selectbox(
            "Perioadă analizată:",
            options=[30, 60, 90, 180, 365, 730,1095],
            index=3,
            format_func=lambda x: f"Ultimele {x} zile",
            key="dash_defecte_recurente_zile",
        )

    def_rec_toate = incarca_defecte_recurente(zile_defecte)
    firme_disp = ["Toate firmele"] + sorted({d["firma"] for d in def_rec_toate if d.get("firma")})
    with f_col2:
        firma_sel = st.selectbox("Firmă:", options=firme_disp, key="dash_defecte_recurente_firma")

    masini_disp = ["Toate mașinile"] + sorted({
        d["masina"] for d in def_rec_toate
        if d.get("masina") and (firma_sel == "Toate firmele" or d.get("firma") == firma_sel)
    })
    with f_col3:
        masina_sel = st.selectbox("Mașină:", options=masini_disp, key="dash_defecte_recurente_masina")

    def_rec_filtrate = [
        d for d in def_rec_toate
        if (firma_sel == "Toate firmele" or d.get("firma") == firma_sel)
        and (masina_sel == "Toate mașinile" or d.get("masina") == masina_sel)
    ]

    if def_rec_filtrate:
        for d in def_rec_filtrate:
            st.warning(
                f"⚠️ **{d['firma']} — {d['masina']}**\n"
                f"Defect: {d['defect']}\n"
                f"Număr apariții: {d['repetitii']}"
            )
    else:
        st.success(f"Nu există defecte recurente identificate pentru filtrele selectate (ultimele {zile_defecte} zile).")
        
    with col_refresh:
        if st.button("🔄 Actualizează", use_container_width=True, key="btn_dash_refresh_top"):
            incarca_date_dashboard.clear()
            incarca_memento_intretinere.clear()
            incarca_defecte_recurente.clear()
            incarca_utilaje_dupa_stare.clear()
            incarca_clienti_inactivi.clear()
            st.rerun()

    # 3. GRAFICELE (Top 10 Defecte, Top Clienți, Top Utilaje)
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

def _extrage_furnizor_piesa(piesa_row: dict) -> str:
    for k in ("furnizor", "nume_furnizor", "furnizor_principal", "supplier", "link_furnizor"):
        val = str(piesa_row.get(k) or "").strip()
        if val:
            return val
    return "Fără furnizor setat"


def _actualizeaza_stare_in_raport_json(tabela: str, record_id: int, den_piesa: str, stare_noua: str) -> bool:
    camp_json = "piese_json" if tabela == "reparatii" else "componente_json"
    with db_cursor() as c:
        c.execute(f"SELECT {camp_json} FROM {tabela} WHERE id = %s", (int(record_id),))
        row = c.fetchone() or {}
        if not isinstance(row, dict):
            row = dict(row)
        raw_val = row.get(camp_json)
        items = raw_val
        if isinstance(raw_val, str):
            try:
                items = json.loads(raw_val)
            except Exception:
                items = []
        if not isinstance(items, list):
            return False

        modificat = False
        den_target = " ".join(str(den_piesa or "").strip().lower().split())
        for item in items:
            if not isinstance(item, dict):
                continue
            den_item = str(
                item.get("Componenta / Cod / Parametri")
                or item.get("Componenta")
                or item.get("Piesa")
                or item.get("piesa")
                or item.get("denumire")
                or ""
            ).strip()
            den_item_norm = " ".join(den_item.lower().split())
            if den_item_norm == den_target or (den_target and (den_target in den_item_norm or den_item_norm in den_target)):
                if tabela == "reparatii_electronice":
                    item["Stare"] = stare_noua
                elif tabela == "reparatii":
                    item["Tip"] = stare_noua
                item["stare_comandata"] = stare_noua
                modificat = True

        if modificat:
            c.execute(
                f"UPDATE {tabela} SET {camp_json} = %s WHERE id = %s",
                (json.dumps(items, ensure_ascii=False), int(record_id)),
            )
            if hasattr(c, "connection") and hasattr(c.connection, "commit"):
                c.connection.commit()
    return modificat

def render_piese_de_comandat_dashboard():
    st.markdown("### 🛒 Piese De Comandat / Necesare & Stare Comandă")

    # --- NOTARE RAPIDĂ PIESE PE TEREN (TABEL SEPARAT `necesar_piese`) ---
    firme_all = FirmeRepository.get_all() or []
    masini_all = MasiniRepository.get_all() or []

    firme_nume = sorted({
        str(f.get("nume_firma") or f.get("nume") or f.get("denumire") or "").strip()
        for f in firme_all
        if str(f.get("nume_firma") or f.get("nume") or f.get("denumire") or "").strip()
    })

    # --- NOTARE RAPIDĂ PIESE PE TEREN (TABEL SEPARAT `necesar_piese`) ---
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []

    with st.expander("📝 Notare Rapidă Piese pe Teren (Client obligatoriu • Mașină opțională)", expanded=False):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            firma_teren = st.selectbox(
                "Client / Firmă *",
                options=firme_nume,
                key="dash_teren_firma_sel",
            )
            fid_teren = nume_to_id.get(firma_teren)
            masini_firma = [
                str(m.get("denumire") or "").strip()
                for m in masini_all
                if str(m.get("denumire") or "").strip()
                and (fid_teren is None or m.get("firma_id") == fid_teren)
            ]
            opt_masini_teren = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma))

            with st.form("form_notare_rapida_teren", clear_on_submit=True):
                c_t1, c_t2 = st.columns([2.2, 2.2])
                with c_t1:
                    piesa_teren = st.text_input(
                        "Denumire piesă *",
                        placeholder="ex: Electrovana 24V / Rulment 6205",
                    )
                    cod_teren = st.text_input(
                        "Cod producător (opțional)",
                        placeholder="ex: cod reper notat la client",
                    )
                with c_t2:
                    masina_teren = st.selectbox(
                        "Mașină (opțional)",
                        options=opt_masini_teren,
                    )
                    cant_teren = st.number_input(
                        "Cantitate *",
                        min_value=0.01,
                        value=1.0,
                        step=1.0,
                        format="%.2f",
                    )

                obs_teren = st.text_input(
                    "Observații / detalii notate la client (opțional)",
                    placeholder="ex: cerută la vizită, verificare ofertă...",
                )
                st.caption(
                    "Regulă automată: dacă piesa **nu există** în catalogul de piese → intră la **De căutat**; "
                    "dacă **este deja** în catalog → intră la **De ofertat**."
                )
                salveaza_teren = st.form_submit_button("➕ Notează Piesa pentru Comandă", type="primary")

            if salveaza_teren:
                try:
                    rez = NecesarPieseRepository.noteaza_piesa_pe_teren(
                        firma_client=firma_teren,
                        firma_id=fid_teren,
                        denumire_piesa=piesa_teren,
                        cantitate=cant_teren,
                        masina=masina_teren,
                        cod_producator=cod_teren,
                        observatii=obs_teren,
                    )
                    incarca_date_dashboard.clear()
                    mesaj_catalog = (
                        "era deja în catalog → trecută la **De ofertat**"
                        if rez.get("existenta_in_catalog")
                        else "nu era în catalog → adăugată în catalog și trecută la **De căutat**"
                    )
                    st.success(
                        f"✅ Notat **{piesa_teren.strip()}** (cant. **{float(cant_teren):g}**, client **{firma_teren}**): "
                        f"{mesaj_catalog}."
                    )
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

    st.caption(
        "Schimbă direct în tabel coloana **Status Comandă** (`De căutat`, `De ofertat`, `De comandat`, `Comandată`, `În așteptare`, `Anulată`) "
        "și apasă **💾 Actualizează Stările în Tabel**."
    )

    piese_db = PieseRepository.get_all() or []
    furnizor_map = {}
    piesa_id_by_name = {}
    stare_catalog_by_name = {}

    for p in piese_db:
        den = str(p.get("denumire") or p.get("nume") or "").strip()
        if den:
            cheie = " ".join(den.lower().split())
            furnizor_map[cheie] = _extrage_furnizor_piesa(p)
            piesa_id_by_name[cheie] = p.get("id")
            stare_catalog_by_name[cheie] = _normalizeaza_stare_comanda(p.get("stare_comandata"))

    randuri = []
    idx_counter = 0

    # 0. Piese notate pe teren / din tabelul `necesar_piese`
    necesar_rows = NecesarPieseRepository.get_all() or []
    for np_row in necesar_rows:
        den_np = str(np_row.get("denumire_piesa") or "").strip()
        if not den_np:
            continue
        cheie = " ".join(den_np.lower().split())
        try:
            cant_num = float(np_row.get("cantitate") or 1.0)
        except Exception:
            cant_num = 1.0

        furnizor_np = str(np_row.get("furnizor_piesa") or "").strip() or furnizor_map.get(cheie, "Fără furnizor setat")
        idx_counter += 1
        randuri.append({
            "_row_id": idx_counter,
            "_necesar_id": np_row.get("id"),
            "_piesa_id": np_row.get("piesa_id") or piesa_id_by_name.get(cheie),
            "_sursa_tbl": "necesar_piese",
            "_sursa_rec_id": np_row.get("id"),
            "Furnizor": furnizor_np,
            "Piesă": den_np,
            "Cantitate": cant_num,
            "Status Comandă": _normalizeaza_stare_comanda(np_row.get("status_comanda")),
            "Sursă": "Teren / Necesar",
            "Firmă": str(np_row.get("firma_client") or "").strip(),
            "Mașină": str(np_row.get("masina") or "").strip() or "-",
            "Raport": f"NP #{np_row.get('id')}",
        })

    # 1. Piese din rapoartele de Mașini (reparatii)
    rapoarte = ReparatiiRepository.get_all() or []
    for r in rapoarte:
        piese_raw = r.get("piese_valide")
        if not piese_raw:
            piese_raw = r.get("piese_json") or []
        if isinstance(piese_raw, str):
            try:
                piese_raw = json.loads(piese_raw)
            except Exception:
                piese_raw = []

        for item in piese_raw:
            if not isinstance(item, dict):
                continue
            den_piesa = str(item.get("Piesa") or item.get("piesa") or item.get("denumire") or "").strip()
            tip_piesa = str(item.get("Tip") or item.get("tip") or "").strip()
            stare_item = str(item.get("stare_comandata") or item.get("Stare") or tip_piesa or "").strip()
            if not den_piesa:
                continue
            if stare_item.lower() not in (
                "de comandat", "necesara", "necesare",
                "de căutat", "de cautat",
                "de ofertat",
                "comandată", "comandata",
                "anulată", "anulata",
            ) and tip_piesa.lower() not in (
                "de comandat", "necesara", "necesare",
                "de căutat", "de cautat",
                "de ofertat",
                "comandată", "comandata",
                "anulată", "anulata",
            ):
                continue

            cant = item.get("Cantitate")
            if cant is None:
                cant = item.get("cantitate", 1)
            try:
                cant_num = float(cant)
            except Exception:
                cant_num = 1.0

            cheie = " ".join(den_piesa.lower().split())
            if stare_item.strip():
                stare_curenta = (
                    "De comandat"
                    if stare_item.lower() in ("de comandat", "necesara", "necesare")
                    else _normalizeaza_stare_comanda(stare_item)
                )
            elif cheie in stare_catalog_by_name:
                stare_curenta = stare_catalog_by_name[cheie]
            else:
                stare_curenta = "De comandat"

            furnizor = furnizor_map.get(cheie, "Fără furnizor setat")
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii",
                "_sursa_rec_id": r.get("id"),
                "Furnizor": furnizor,
                "Piesă": den_piesa,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Sursă": "Mașini",
                "Firmă": r.get("firma") or "",
                "Mașină": r.get("masina") or "",
                "Raport": f"#{r.get('id')}",
            })

    # 2. Piese din rapoartele de Reparații Electronice (reparatii_electronice)
    try:
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii_electronice ORDER BY id DESC")
            fise_el = [dict(row) for row in (c.fetchall() or [])]
    except Exception:
        fise_el = []

    for f_el in fise_el:
        comp_raw = f_el.get("componente_json") or []
        if isinstance(comp_raw, str):
            try:
                comp_raw = json.loads(comp_raw)
            except Exception:
                comp_raw = []

        for comp in comp_raw:
            if not isinstance(comp, dict):
                continue
            den_comp = str(
                comp.get("Componenta / Cod / Parametri")
                or comp.get("Componenta")
                or comp.get("piesa")
                or comp.get("denumire")
                or ""
            ).strip()
            stare_comp = str(comp.get("stare_comandata") or comp.get("Stare") or "").strip()
            if not den_comp or stare_comp.lower() not in (
                "necesara", "necesare", "de comandat",
                "de căutat", "de cautat",
                "de ofertat",
                "comandată", "comandata",
                "anulată", "anulata",
            ):
                continue

            cant_c = comp.get("Cantitate", 1.0)
            try:
                cant_num = float(cant_c)
            except Exception:
                cant_num = 1.0

            cheie = " ".join(den_comp.lower().split())
            stare_curenta = (
                "De comandat"
                if stare_comp.lower() in ("de comandat", "necesara", "necesare")
                else _normalizeaza_stare_comanda(stare_comp)
            )
            furnizor = furnizor_map.get(cheie, "Fără furnizor setat")
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii_electronice",
                "_sursa_rec_id": f_el.get("id"),
                "Furnizor": furnizor,
                "Piesă": den_comp,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Sursă": "Electronică",
                "Firmă": f_el.get("firma_nume") or "",
                "Mașină": f_el.get("masina_nume") or f_el.get("piesa_subansamblu") or "",
                "Raport": f"EL #{f_el.get('id')}",
            })

    if not randuri:
        st.info("Nu există piese marcate ca necesare / de comandat / de căutat / de ofertat.")
        return

    df = pd.DataFrame(randuri)

    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1.4])
    with c1:
        filtru_sursa = st.selectbox(
            "Filtrează după sursă",
            options=["Toate", "Teren / Necesar", "Mașini", "Electronică"],
            key="dash_piese_cmd_sursa",
        )
    with c2:
        opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].unique().tolist())
        filtru_furn = st.selectbox(
            "Filtrează după furnizor",
            options=opt_furn,
            key="dash_piese_cmd_furn",
        )
    with c3:
        filtru_stare = st.selectbox(
            "Filtrează după status",
            options=["Toate stările"] + OPTIUNI_STARE_COMANDA,
            key="dash_piese_cmd_stare",
        )
    with c4:
        cautare_piesa = st.text_input(
            "Caută piesă / cod",
            placeholder="ex: L6376PD, SFH6106...",
            key="dash_piese_cmd_cautare",
        ).strip().lower()

    df_f = df.copy()
    if filtru_sursa != "Toate":
        df_f = df_f[df_f["Sursă"] == filtru_sursa]
    if filtru_furn != "Toți furnizorii":
        df_f = df_f[df_f["Furnizor"] == filtru_furn]
    if filtru_stare != "Toate stările":
        df_f = df_f[df_f["Status Comandă"] == filtru_stare]
    if cautare_piesa:
        df_f = df_f[df_f["Piesă"].str.lower().str.contains(cautare_piesa, na=False)]

    if df_f.empty:
        st.info("Nu există piese care să corespundă filtrelor selectate.")
        return

    cols_afis = [
        "_row_id",
        "Furnizor",
        "Piesă",
        "Cantitate",
        "Status Comandă",
        "Sursă",
        "Firmă",
        "Mașină",
        "Raport",
    ]
    df_editor_init = df_f[cols_afis].reset_index(drop=True)
    editor_dash_key = f"dash_editor_stare_piese_{filtru_sursa}_{filtru_furn}_{filtru_stare}"

    edited_df = st.data_editor(
        df_editor_init,
        key=editor_dash_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["_row_id", "Furnizor", "Piesă", "Cantitate", "Sursă", "Firmă", "Mașină", "Raport"],
        column_config={
            "_row_id": None,
            "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
            "Piesă": st.column_config.TextColumn("Piesă", width="large"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", format="%.2f", width="small"),
            "Status Comandă": st.column_config.SelectboxColumn(
                "Status Comandă",
                options=OPTIUNI_STARE_COMANDA,
                required=True,
                width="medium",
            ),
            "Sursă": st.column_config.TextColumn("Sursă", width="small"),
            "Firmă": st.column_config.TextColumn("Firmă", width="small"),
            "Mașină": st.column_config.TextColumn("Mașină", width="small"),
            "Raport": st.column_config.TextColumn("Raport", width="small"),
        },
    )

    if st.button("💾 Actualizează Stările în Tabel", type="primary", key="btn_dash_update_stare_piese"):
        df_final = edited_df.copy()
        if "Status Comandă" in df_final.columns:
            df_final["Status Comandă"] = df_final["Status Comandă"].astype(object)

        state_ed = st.session_state.get(editor_dash_key)
        if isinstance(state_ed, dict):
            for idx_key, changes in (state_ed.get("edited_rows") or {}).items():
                try:
                    idx = int(idx_key)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(df_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_final.columns:
                            df_final.at[idx, col_name] = (
                                _normalizeaza_stare_comanda(new_val) if col_name == "Status Comandă" else new_val
                            )

        meta_map = {}
        for _, r in df_f.iterrows():
            k = int(r["_row_id"])
            if k not in meta_map:
                nid_raw = r.get("_necesar_id")
                pid_raw = r.get("_piesa_id")
                sid_raw = r.get("_sursa_rec_id")
                meta_map[k] = {
                    "_necesar_id": int(nid_raw) if pd.notna(nid_raw) and str(nid_raw).strip() != "" else None,
                    "_piesa_id": int(pid_raw) if pd.notna(pid_raw) and str(pid_raw).strip() != "" else None,
                    "_sursa_tbl": str(r.get("_sursa_tbl") or "").strip(),
                    "_sursa_rec_id": int(sid_raw) if pd.notna(sid_raw) and str(sid_raw).strip() != "" else None,
                }

        orig_map = {
            int(r["_row_id"]): _normalizeaza_stare_comanda(r["Status Comandă"])
            for _, r in df_editor_init.iterrows()
        }
        nr_mod = 0
        erori_salvare = []

        for _, row in df_final.iterrows():
            rid = int(row["_row_id"])
            stare_noua = _normalizeaza_stare_comanda(row.get("Status Comandă"))
            stare_veche = _normalizeaza_stare_comanda(orig_map.get(rid))
            if stare_veche != stare_noua:
                meta = meta_map.get(rid) or {}
                salvat_ceva = False
                sursa_tbl = str(meta.get("_sursa_tbl") or "").strip()

                necesar_id = meta.get("_necesar_id")
                if sursa_tbl == "necesar_piese" and necesar_id is not None:
                    try:
                        NecesarPieseRepository.update_status_comanda(int(necesar_id), stare_noua)
                        salvat_ceva = True
                    except Exception as e:
                        erori_salvare.append(f"Necesar #{necesar_id} ({row.get('Piesă')}): {e}")

                piesa_id = meta.get("_piesa_id")
                if sursa_tbl != "necesar_piese" and piesa_id is not None and pd.notna(piesa_id):
                    try:
                        PieseRepository.update_stare_comandata(int(piesa_id), stare_noua)
                        salvat_ceva = True
                    except Exception as e:
                        erori_salvare.append(f"Piesa #{piesa_id} ({row.get('Piesă')}): {e}")

                sursa_rec_id = meta.get("_sursa_rec_id")
                if sursa_tbl in ("reparatii", "reparatii_electronice") and sursa_rec_id is not None and pd.notna(sursa_rec_id):
                    try:
                        if _actualizeaza_stare_in_raport_json(
                            sursa_tbl,
                            int(sursa_rec_id),
                            str(row.get("Piesă") or ""),
                            stare_noua,
                        ):
                            salvat_ceva = True
                    except Exception as e:
                        erori_salvare.append(f"{sursa_tbl} #{sursa_rec_id} ({row.get('Piesă')}): {e}")

                if salvat_ceva:
                    nr_mod += 1

        if editor_dash_key in st.session_state:
            del st.session_state[editor_dash_key]

        incarca_date_dashboard.clear()
        if erori_salvare:
            st.error("⚠️ Au apărut erori la salvare:\n" + "\n".join(erori_salvare))
        elif nr_mod == 0:
            st.info("ℹ️ Nu există modificări nesalvate la statusul comenzii.")
        else:
            st.success(f"✅ Stările au fost actualizate în baza de date pentru **{nr_mod}** poziții.")
            st.rerun()

    with st.expander("📦 Centralizator cantități pe Status Comandă, Furnizor & Piesă", expanded=False):
        df_sum = (
            df_f.groupby(["Status Comandă", "Furnizor", "Piesă"], as_index=False)["Cantitate"]
            .sum()
            .sort_values(["Status Comandă", "Furnizor", "Piesă"])
        )
        st.dataframe(df_sum, hide_index=True, use_container_width=True)
        
def _obtine_harta_firme() -> tuple[list[str], dict[str, int]]:
    """Returnează (lista ordonată de nume_firma, dicționar {nume_firma: id})."""
    firme_all = FirmeRepository.get_all() or []
    nume_to_id: dict[str, int] = {}
    for f in firme_all:
        nume = str(f.get("nume_firma") or "").strip()
        fid = f.get("id")
        if nume and fid is not None:
            nume_to_id[nume] = int(fid)
    return sorted(nume_to_id.keys()), nume_to_id


def render_notite_vizita_dashboard():
    st.markdown("### 📋 Notițe & Task-uri Vizită Client")

    firme_nume, nume_to_id = _obtine_harta_firme()

    with st.expander("➕ Adaugă Notiță / Task de la Client", expanded=False):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            with st.form("form_adauga_notita_vizita", clear_on_submit=True):
                cn1, cn2 = st.columns([1.1, 1.9])
                with cn1:
                    data_viz = st.date_input("Data *", value=datetime.date.today())
                    stare_viz = st.selectbox(
                        "Stare *",
                        options=OPTIUNI_STARE_TASK_VIZITA,
                        index=0,
                    )
                with cn2:
                    firma_viz = st.selectbox("Firmă (Client) *", options=firme_nume)
                    note_viz = st.text_area(
                        "Note de vizită *",
                        placeholder="ex: De verificat senzor presiune linie 2, de proiectat suport motor, cerut ofertă...",
                        height=95,
                    )

                salveaza_nota = st.form_submit_button("💾 Salvează Notița", type="primary")

            if salveaza_nota:
                try:
                    TaskuriVizitaRepository.insert(
                        data_vizita=data_viz,
                        firma=firma_viz,
                        firma_id=nume_to_id.get(firma_viz),
                        note_vizita=note_viz,
                        stare=stare_viz,
                    )
                    st.success(f"✅ Notiță salvată pentru **{firma_viz}** ({stare_viz}).")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

    taskuri = TaskuriVizitaRepository.get_all() or []
    if not taskuri:
        st.info("Nu există notițe sau task-uri de vizită înregistrate.")
        return

    df_t = pd.DataFrame(taskuri)
    df_t["data_str"] = df_t["data_vizita"].astype(str)

    ft1, ft2, ft3 = st.columns([1.3, 1.2, 1.2])
    with ft1:
        firme_filtrare = ["Toate firmele"] + sorted(df_t["firma"].unique().tolist())
        sel_firma_t = st.selectbox("Firmă", options=firme_filtrare, key="dash_task_filtru_firma")
    with ft2:
        sel_stare_t = st.selectbox(
            "Stare",
            options=["Active (fără Finalizat)", "Toate stările"] + OPTIUNI_STARE_TASK_VIZITA,
            key="dash_task_filtru_stare",
        )
    with ft3:
        cautare_t = st.text_input(
            "Caută în note",
            placeholder="cuvânt cheie...",
            key="dash_task_cautare",
        ).strip().lower()

    df_tf = df_t.copy()
    if sel_firma_t != "Toate firmele":
        df_tf = df_tf[df_tf["firma"] == sel_firma_t]
    if sel_stare_t == "Active (fără Finalizat)":
        df_tf = df_tf[df_tf["stare"] != "Finalizat"]
    elif sel_stare_t != "Toate stările":
        df_tf = df_tf[df_tf["stare"] == sel_stare_t]
    if cautare_t:
        df_tf = df_tf[df_tf["note_vizita"].str.lower().str.contains(cautare_t, na=False)]

    if df_tf.empty:
        st.info("Nu există notițe pentru filtrele selectate.")
        return

    df_t_init = pd.DataFrame([
        {
            "id": int(r["id"]),
            "Data": str(r["data_vizita"]),
            "Firmă": str(r["firma"]),
            "Note de vizită": str(r["note_vizita"]),
            "Stare": normalizeaza_stare_task_vizita(r["stare"]),
            "Șterge": False,
        }
        for _, r in df_tf.iterrows()
    ])

    editor_task_key = f"dash_editor_taskuri_{sel_firma_t}_{sel_stare_t}_{len(df_t_init)}"
    edited_t = st.data_editor(
        df_t_init,
        key=editor_task_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["id", "Data", "Firmă"],
        column_config={
            "id": None,
            "Data": st.column_config.TextColumn("Data", width="small"),
            "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
            "Note de vizită": st.column_config.TextColumn("Note de vizită", width="large", required=True),
            "Stare": st.column_config.SelectboxColumn(
                "Stare",
                options=OPTIUNI_STARE_TASK_VIZITA,
                required=True,
                width="medium",
            ),
            "Șterge": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
        },
    )

    if st.button("💾 Salvează Modificările Notițe", type="primary", key="btn_dash_save_taskuri"):
        df_t_final = edited_t.copy()
        state_t = st.session_state.get(editor_task_key)
        if isinstance(state_t, dict):
            for idx_key, changes in (state_t.get("edited_rows") or {}).items():
                try:
                    idx = int(idx_key)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(df_t_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_t_final.columns:
                            df_t_final.at[idx, col_name] = new_val

        orig_t_map = {int(r["id"]): r for _, r in df_t_init.iterrows()}
        nr_mod_t = 0
        nr_del_t = 0

        for _, row in df_t_final.iterrows():
            tid = int(row["id"])
            if bool(row.get("Șterge", False)):
                TaskuriVizitaRepository.delete(tid)
                nr_del_t += 1
                continue

            orig = orig_t_map.get(tid)
            if orig is None:
                continue

            nota_noua = str(row.get("Note de vizită") or "").strip()
            stare_noua = normalizeaza_stare_task_vizita(row.get("Stare"))
            if (
                nota_noua != str(orig["Note de vizită"]).strip()
                or stare_noua != normalizeaza_stare_task_vizita(orig["Stare"])
            ) and nota_noua:
                TaskuriVizitaRepository.update(tid, nota_noua, stare_noua)
                nr_mod_t += 1

        if editor_task_key in st.session_state:
            del st.session_state[editor_task_key]

        if nr_mod_t == 0 and nr_del_t == 0:
            st.info("ℹ️ Nu există modificări nesalvate la notițe.")
        else:
            st.success(f"✅ Notițe actualizate: **{nr_mod_t}** modificate, **{nr_del_t}** șterse.")
            st.rerun()