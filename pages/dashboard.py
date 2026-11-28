# ------------------------------------------------
# --- pages/dashboard.py ------------------------
# ------------------------------------------------

import datetime
import json
import re
import pandas as pd
import plotly.express as px
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import (
    OPTIUNI_PRIORITATE_PIESA,
    OPTIUNI_STATUS_TEREN,
    NecesarPieseRepository,
    normalizeaza_prioritate_piesa,
)
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_repository import ReparatiiRepository
from repositories.taskuri_vizita_repository import (
    OPTIUNI_STARE_TASK_VIZITA,
    TaskuriVizitaRepository,
    normalizeaza_stare_task_vizita,
)

STARI_COMANDA_VALIDE_RAW = frozenset({
    "de comandat",
    "necesara",
    "necesare",
    "de căutat",
    "de cautat",
    "de ofertat",
    "comandată",
    "comandata",
    "ofertat",
    "ofertata",
    "ofertată",
    "în așteptare",
    "in asteptare",
    "anulată",
    "anulata",
})

SQL_NU_ESTE_INCHISA_STARE_FINALA = """
    LOWER(
        TRANSLATE(
            TRIM(COALESCE(stare_finala, '')),
            'ăâîșțĂÂÎȘȚ',
            'aaistAAIST'
        )
    ) NOT LIKE '%%inchis%%'
"""

SQL_NU_ESTE_INCHISA_MASINI_ALIAS = """
    LOWER(
        TRANSLATE(
            TRIM(COALESCE(m.stare, '')),
            'ăâîșțĂÂÎȘȚ',
            'aaistAAIST'
        )
    ) NOT LIKE '%%inchis%%'
"""

SQL_NU_ESTE_INCHISA_MASINI = """
    LOWER(
        TRANSLATE(
            TRIM(COALESCE(stare, '')),
            'ăâîșțĂÂÎȘȚ',
            'aaistAAIST'
        )
    ) NOT LIKE '%%inchis%%'
"""


def _norm_text(val: object) -> str:
    return " ".join(str(val or "").strip().lower().split())


def _este_stare_inchisa(val: object) -> bool:
    s = _norm_text(val)
    if not s:
        return False
    s_clean = (
        s.replace("ă", "a")
        .replace("â", "a")
        .replace("î", "i")
        .replace("ș", "s")
        .replace("ț", "t")
    )
    return "inchis" in s_clean


def _safe_int(val: object) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _safe_float(val: object, default: float = 1.0) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_json_list(raw_val: object) -> list[dict]:
    if not raw_val:
        return []
    data = raw_val
    if isinstance(raw_val, str):
        try:
            data = json.loads(raw_val)
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _goleste_cache_piese_si_cataloage():
    for fn in (
        _incarca_optiuni_lookup_piese,
        _incarca_fise_electronice_piese,
    ):
        try:
            fn.clear()
        except Exception:
            pass
    for repo in (PieseRepository, NecesarPieseRepository, ReparatiiRepository):
        try:
            repo.get_all.clear()
        except Exception:
            pass


def _goleste_toate_cache_dashboard():
    for fn in (
        incarca_date_dashboard,
        incarca_memento_intretinere,
        incarca_defecte_recurente,
        incarca_utilaje_dupa_stare,
        incarca_clienti_inactivi,
        _obtine_harta_firme,
    ):
        try:
            fn.clear()
        except Exception:
            pass
    _goleste_cache_piese_si_cataloage()
    try:
        TaskuriVizitaRepository.get_all.clear()
    except Exception:
        pass


def _executa_update_automat_db_sesiune() -> dict:
    """Rulează o singură dată pe sesiune la intrarea pe dashboard:
    asigură structura DB, sincronizează piesele din necesar_piese în catalogul `piese`
    și aliniază câmpurile de ofertare/legătură fără duplicate."""
    PieseRepository._asigura_coloane_piese()
    NecesarPieseRepository._asigura_tabela()
    TaskuriVizitaRepository._asigura_tabela()

    with db_cursor() as c:
        c.execute("""
            UPDATE necesar_piese
            SET data_ofertare = COALESCE(data_ofertare, CURRENT_TIMESTAMP)
            WHERE LOWER(TRIM(COALESCE(status_comanda, ''))) IN ('ofertat', 'ofertata', 'ofertată')
              AND data_ofertare IS NULL
        """)
        c.execute("""
            UPDATE necesar_piese np
            SET piesa_id = p.id
            FROM piese p
            WHERE np.piesa_id IS NULL
              AND LOWER(TRIM(COALESCE(p.denumire, ''))) = LOWER(TRIM(COALESCE(np.denumire_piesa, '')))
              AND TRIM(COALESCE(np.denumire_piesa, '')) <> ''
        """)

    piese_existente = PieseRepository.get_all() or []
    chei_existente: set[tuple[str, str]] = set()
    for p in piese_existente:
        den_ex = str(p.get("denumire") or "").strip()
        if den_ex:
            cod_ex = str(p.get("cod_producator") or p.get("cod_comercial") or "").strip()
            chei_existente.add((_norm_text(den_ex), _norm_text(cod_ex)))

    adaugate_catalog = 0
    necesar_rows = NecesarPieseRepository.get_all(include_ofertate=True) or []
    for nr in necesar_rows:
        den_clean = " ".join(str(nr.get("denumire_piesa") or "").split()).strip()
        if not den_clean:
            continue
        cod_clean = " ".join(str(nr.get("cod_producator") or "").split()).strip()
        cheie = (_norm_text(den_clean), _norm_text(cod_clean))
        if cheie in chei_existente:
            continue

        mas_clean = str(nr.get("masina") or "").strip() or "General"
        client_txt = str(nr.get("firma_client") or "").strip()
        prio_txt = normalizeaza_prioritate_piesa(nr.get("prioritate_piesa"))
        obs_txt = str(nr.get("observatii") or "").strip()
        meta_obs = " | ".join(
            part
            for part in (
                f"Client: {client_txt}" if client_txt else "",
                f"Prioritate: {prio_txt}",
                obs_txt,
            )
            if part
        )
        stare_init = _normalizeaza_stare_comanda(nr.get("status_comanda") or "De căutat")

        PieseRepository.insert({
            "denumire": den_clean,
            "cod_producator": cod_clean,
            "cod_comercial": cod_clean,
            "masina_montaj": mas_clean,
            "subansamblu": "",
            "parametri": meta_obs,
            "pret_achizitie": 0.0,
            "valuta_achizitie": "RON",
            "link_furnizor": "",
            "termen_livrare": "1",
            "stare_comandata": stare_init,
        })
        chei_existente.add(cheie)
        adaugate_catalog += 1

    if adaugate_catalog > 0:
        _goleste_cache_piese_si_cataloage()
        with db_cursor() as c:
            c.execute("""
                UPDATE necesar_piese np
                SET piesa_id = p.id
                FROM piese p
                WHERE np.piesa_id IS NULL
                  AND LOWER(TRIM(COALESCE(p.denumire, ''))) = LOWER(TRIM(COALESCE(np.denumire_piesa, '')))
                  AND TRIM(COALESCE(np.denumire_piesa, '')) <> ''
            """)
        NecesarPieseRepository.get_all.clear()

    return {"adaugate_catalog": adaugate_catalog}


@st.cache_data(ttl=300)
def _obtine_harta_firme() -> tuple[list[str], dict[str, int]]:
    firme_all = FirmeRepository.get_all() or []
    nume_to_id: dict[str, int] = {}
    for f in firme_all:
        nume = str(f.get("nume_firma") or "").strip()
        fid = _safe_int(f.get("id"))
        if nume and fid is not None:
            nume_to_id[nume] = fid
    return sorted(nume_to_id.keys()), nume_to_id


@st.cache_data(ttl=120)
def incarca_date_dashboard():
    with db_cursor() as c:
        c.execute(f"""
            SELECT
                COUNT(*) AS interventii,
                COALESCE(SUM(durata), 0) AS minute,
                COUNT(DISTINCT NULLIF(TRIM(firma), '')) AS clienti,
                COUNT(DISTINCT NULLIF(TRIM(masina), '')) AS utilaje,
                COUNT(*) FILTER (
                    WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                      AND stare_finala = 'Oprită / Necesar piese'
                ) AS utilaje_oprite,
                COUNT(*) FILTER (
                    WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                      AND LOWER(COALESCE(stare_finala, '')) LIKE '%%supraveghere%%'
                ) AS utilaje_supraveghere
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
              AND data_creare >= DATE_TRUNC('month', CURRENT_DATE)
              AND data_creare < (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')
        """)
        kpi_res = dict(c.fetchone() or {})

        c.execute(f"""
            SELECT
                COUNT(*) AS total_masini_rep,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(stare_finala, '')) LIKE 'funcțional%%'
                       OR LOWER(COALESCE(stare_finala, '')) LIKE 'functional%%'
                ) AS reusite_masini_rep
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
        """)
        masini_rep_res = dict(c.fetchone() or {})

        try:
            c.execute("""
                SELECT
                    COUNT(*) AS total_el_rep,
                    COUNT(*) FILTER (
                        WHERE LOWER(COALESCE(stare_finala, '')) IN ('funcțional', 'functional')
                    ) AS reusite_el_rep
                FROM reparatii_electronice
            """)
            el_rep_res = dict(c.fetchone() or {})
        except Exception:
            el_rep_res = {"total_el_rep": 0, "reusite_el_rep": 0}

        c.execute(f"""
            SELECT defect, COUNT(*) AS aparitii
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
              AND defect IS NOT NULL AND TRIM(defect) <> ''
            GROUP BY defect
            ORDER BY aparitii DESC
            LIMIT 10
        """)
        top_def = [dict(r) for r in (c.fetchall() or [])]

        c.execute(f"""
            SELECT firma, COUNT(*) AS interventii
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
              AND firma IS NOT NULL AND TRIM(firma) <> ''
            GROUP BY firma
            ORDER BY interventii DESC
            LIMIT 10
        """)
        top_cli = [dict(r) for r in (c.fetchall() or [])]

        c.execute(f"""
            SELECT masina, COUNT(*) AS interventii
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
              AND masina IS NOT NULL AND TRIM(masina) <> ''
            GROUP BY masina
            ORDER BY interventii DESC
            LIMIT 10
        """)
        top_ut = [dict(r) for r in (c.fetchall() or [])]

    return kpi_res, masini_rep_res, el_rep_res, top_def, top_cli, top_ut


@st.cache_data(ttl=120)
def incarca_memento_intretinere(zile_inainte: int = 14) -> list[dict]:
    zile = max(0, int(zile_inainte))
    try:
        with db_cursor() as c:
            c.execute(f"""
                SELECT
                    m.id,
                    COALESCE(NULLIF(TRIM(f.nume_firma), ''), 'Fără firmă') AS firma,
                    m.denumire AS utilaj,
                    m.data_intretinere::date AS data_scadenta,
                    (m.data_intretinere::date - CURRENT_DATE) AS zile_ramase
                FROM masini m
                LEFT JOIN firme f ON f.id = m.firma_id
                WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                  AND {SQL_NU_ESTE_INCHISA_MASINI_ALIAS}
                  AND m.data_intretinere IS NOT NULL
                  AND m.data_intretinere::date <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY m.data_intretinere::date ASC, firma ASC, m.denumire ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        try:
            with db_cursor() as c:
                c.execute(f"""
                    SELECT
                        id,
                        'Fără firmă' AS firma,
                        denumire AS utilaj,
                        data_intretinere::date AS data_scadenta,
                        (data_intretinere::date - CURRENT_DATE) AS zile_ramase
                    FROM masini
                    WHERE COALESCE(fara_intretinere, FALSE) = FALSE
                      AND {SQL_NU_ESTE_INCHISA_MASINI}
                      AND data_intretinere IS NOT NULL
                      AND data_intretinere::date <= (CURRENT_DATE + make_interval(days => %s))
                    ORDER BY data_intretinere::date ASC, denumire ASC
                """, (zile,))
                return [dict(r) for r in (c.fetchall() or [])]
        except Exception:
            with db_cursor() as c:
                c.execute("""
                    SELECT
                        id,
                        'Fără firmă' AS firma,
                        denumire AS utilaj,
                        data_intretinere::date AS data_scadenta,
                        (data_intretinere::date - CURRENT_DATE) AS zile_ramase
                    FROM masini
                    WHERE COALESCE(fara_intretinere, FALSE) = FALSE
                      AND data_intretinere IS NOT NULL
                      AND data_intretinere::date <= (CURRENT_DATE + make_interval(days => %s))
                    ORDER BY data_intretinere::date ASC, denumire ASC
                """, (zile,))
                return [dict(r) for r in (c.fetchall() or [])]


@st.cache_data(ttl=120)
def incarca_defecte_recurente(zile_inainte: int = 180) -> list[dict]:
    zile = max(1, int(zile_inainte))
    with db_cursor() as c:
        c.execute(f"""
            SELECT
                COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă') AS firma,
                COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat') AS masina,
                TRIM(defect) AS defect,
                COUNT(*) AS repetitii
            FROM reparatii
            WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
              AND defect IS NOT NULL
              AND TRIM(defect) <> ''
              AND data_creare >= (CURRENT_DATE - make_interval(days => %s))
            GROUP BY
                COALESCE(NULLIF(TRIM(firma), ''), 'Fără firmă'),
                COALESCE(NULLIF(TRIM(masina), ''), 'Utilaj nespecificat'),
                TRIM(defect)
            HAVING COUNT(*) >= 3
            ORDER BY repetitii DESC, firma ASC, masina ASC
            LIMIT 50
        """, (zile,))
        return [dict(r) for r in (c.fetchall() or [])]


@st.cache_data(ttl=120)
def incarca_utilaje_dupa_stare(mod: str) -> list[dict]:
    with db_cursor() as c:
        if mod == "supraveghere":
            c.execute(f"""
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
                WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                  AND LOWER(COALESCE(stare_finala, '')) LIKE '%%supraveghere%%'
                ORDER BY data_creare DESC NULLS LAST, id DESC
            """)
        else:
            c.execute(f"""
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
                WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                  AND (
                    stare_finala = 'Oprită / Necesar piese'
                    OR LOWER(COALESCE(stare_finala, '')) LIKE '%%oprit%%'
                  )
                ORDER BY data_creare DESC NULLS LAST, id DESC
            """)
        return [dict(r) for r in (c.fetchall() or [])]


def actualizeaza_stare_reparatie(reparatie_id: int, stare_noua: str):
    with db_cursor() as c:
        c.execute(
            "UPDATE reparatii SET stare_finala = %s WHERE id = %s",
            (stare_noua, int(reparatie_id)),
        )
    incarca_date_dashboard.clear()
    incarca_utilaje_dupa_stare.clear()
    incarca_defecte_recurente.clear()


@st.cache_data(ttl=120)
def incarca_clienti_inactivi(zile_inactivitate: int = 90) -> list[dict]:
    zile = max(1, int(zile_inactivitate))
    try:
        with db_cursor() as c:
            c.execute(f"""
                WITH ultima_rep AS (
                    SELECT
                        LOWER(TRIM(firma)) AS firma_norm,
                        MAX(data_creare) AS ultima_data
                    FROM reparatii
                    WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                      AND firma IS NOT NULL AND TRIM(firma) <> ''
                    GROUP BY LOWER(TRIM(firma))
                )
                SELECT
                    f.nume_firma AS "Client / Firmă",
                    COALESCE(TO_CHAR(u.ultima_data, 'YYYY-MM-DD'), 'Fără intervenții') AS "Ultima intervenție"
                FROM firme f
                LEFT JOIN ultima_rep u ON u.firma_norm = LOWER(TRIM(f.nume_firma))
                WHERE u.ultima_data IS NULL
                   OR u.ultima_data < (CURRENT_DATE - make_interval(days => %s))::timestamp
                ORDER BY u.ultima_data ASC NULLS FIRST, f.nume_firma ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        with db_cursor() as c:
            c.execute(f"""
                SELECT
                    TRIM(firma) AS "Client / Firmă",
                    TO_CHAR(MAX(data_creare), 'YYYY-MM-DD') AS "Ultima intervenție",
                    COUNT(*) AS "Total intervenții istoric"
                FROM reparatii
                WHERE {SQL_NU_ESTE_INCHISA_STARE_FINALA}
                  AND firma IS NOT NULL AND TRIM(firma) <> ''
                GROUP BY TRIM(firma)
                HAVING MAX(data_creare) < (CURRENT_DATE - make_interval(days => %s))::timestamp
                ORDER BY MAX(data_creare) ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]


def _mod_key(este_supraveghere: bool) -> str:
    return "supr" if este_supraveghere else "oprit"


def _randare_lista_utilaje_stare(items: list[dict], este_supraveghere: bool):
    items_active = [it for it in items if not _este_stare_inchisa(it.get("stare"))]
    if not items_active:
        st.info("Nu există utilaje active în această categorie.")
        return

    prefix = _mod_key(este_supraveghere)
    for item in items_active:
        rep_id = item["id"]
        col_info, col_act1, col_act2, col_act3 = st.columns([4.4, 1.15, 1.3, 1.15], vertical_alignment="center")
        with col_info:
            st.markdown(
                f"**{item['firma']}** — {item['utilaj']} "
                f"`#{rep_id} • {item['data_inregistrare']}`  \n"
                f"**Motiv / Detalii:** {item['motiv_oprire']}"
            )
        with col_act1:
            if st.button("✅ Activ", key=f"btn_activ_{prefix}_{rep_id}", use_container_width=True):
                actualizeaza_stare_reparatie(rep_id, "Funcțională")
                st.toast(f"✅ #{rep_id} ({item['utilaj']}) trecut pe Funcțională!")
        with col_act2:
            if not este_supraveghere:
                if st.button("👀 Supraveghere", key=f"btn_supr_{rep_id}", use_container_width=True):
                    actualizeaza_stare_reparatie(rep_id, "Funcțională sub supraveghere")
                    st.toast(f"👀 #{rep_id} ({item['utilaj']}) trecut pe Funcțională sub supraveghere!")
        with col_act3:
            if st.button("🔒 Închisă", key=f"btn_inchisa_{prefix}_{rep_id}", use_container_width=True):
                actualizeaza_stare_reparatie(rep_id, "Închisă")
                st.toast(f"🔒 #{rep_id} ({item['utilaj']}) marcat ca Închisă și scos din listele active.")


def _extrage_furnizor_piesa(piesa_row: dict) -> str:
    for k in ("furnizor", "nume_furnizor", "furnizor_principal", "supplier", "link_furnizor"):
        val = str(piesa_row.get(k) or "").strip()
        if val:
            return val
    return "Fără furnizor setat"


def _actualizeaza_stare_in_raport_json(
    tabela: str,
    record_id: int,
    den_piesa: str,
    stare_noua: str,
    item_idx: int | None = None,
) -> bool:
    if tabela not in ("reparatii", "reparatii_electronice"):
        return False

    camp_json = "piese_json" if tabela == "reparatii" else "componente_json"
    with db_cursor() as c:
        c.execute(f"SELECT {camp_json} FROM {tabela} WHERE id = %s", (int(record_id),))
        row = c.fetchone()
        if not row:
            return False
        row_dict = row if isinstance(row, dict) else dict(row)
        items = _parse_json_list(row_dict.get(camp_json))
        if not items:
            return False

        modificat = False
        den_target = _norm_text(den_piesa)

        def _aplica_pe_item(it: dict) -> bool:
            if tabela == "reparatii_electronice":
                it["Stare"] = stare_noua
            else:
                it["Tip"] = stare_noua
            it["stare_comandata"] = stare_noua
            return True

        if item_idx is not None and 0 <= item_idx < len(items):
            cand = items[item_idx]
            den_cand = _norm_text(
                cand.get("Componenta / Cod / Parametri")
                or cand.get("Componenta")
                or cand.get("Piesa")
                or cand.get("piesa")
                or cand.get("denumire")
            )
            if not den_target or den_cand == den_target:
                modificat = _aplica_pe_item(cand)

        if not modificat and den_target:
            for item in items:
                den_item = _norm_text(
                    item.get("Componenta / Cod / Parametri")
                    or item.get("Componenta")
                    or item.get("Piesa")
                    or item.get("piesa")
                    or item.get("denumire")
                )
                if den_item == den_target:
                    modificat = _aplica_pe_item(item)

        if modificat:
            c.execute(
                f"UPDATE {tabela} SET {camp_json} = %s WHERE id = %s",
                (json.dumps(items, ensure_ascii=False), int(record_id)),
            )
    return modificat


@st.cache_data(ttl=300)
def _incarca_optiuni_lookup_piese() -> tuple[list[str], dict[str, dict]]:
    piese_catalog = PieseRepository.get_all() or []
    optiuni = ["✍️ Piesă nouă (scriu manual)"]
    detalii: dict[str, dict] = {}
    vazute: set[str] = set()

    for p in piese_catalog:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or "").strip()
        mas = str(p.get("masina_montaj") or "").strip()
        eticheta = (
            f"{den}"
            + (f" [{cod}]" if cod else "")
            + (f" ({mas})" if mas and mas != "General" else "")
        )
        if eticheta in vazute:
            continue
        vazute.add(eticheta)
        optiuni.append(eticheta)
        detalii[eticheta] = {"denumire": den, "cod_producator": cod}

    return optiuni, detalii


@st.cache_data(ttl=120)
def _incarca_fise_electronice_piese() -> list[dict]:
    try:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    id,
                    firma_nume,
                    masina_nume,
                    piesa_subansamblu,
                    componente_json
                FROM reparatii_electronice
                WHERE componente_json IS NOT NULL
                ORDER BY id DESC
            """)
            return [dict(row) for row in (c.fetchall() or [])]
    except Exception:
        return []


def render_memento_intretinere_dashboard():
    col_z, col_info = st.columns([1.4, 3.6], vertical_alignment="bottom")
    with col_z:
        zile_avans = st.selectbox(
            "Prag scadență:",
            options=[3, 7, 14, 21, 30, 60],
            index=2,
            format_func=lambda x: f"{x} zile",
            key="dash_memento_intretinere_zile",
        )

    alerta_rows = incarca_memento_intretinere(zile_avans)
    with col_info:
        if alerta_rows:
            st.warning(
                f"⏰ **{len(alerta_rows)}** utilaje active cu întreținerea scadentă în **{zile_avans}** zile (sau depășită)."
            )
        else:
            st.success(f"✅ Nicio întreținere scadentă la utilajele active în următoarele **{zile_avans}** zile.")

    if alerta_rows:
        df_m = pd.DataFrame([
            {
                "Firmă": r.get("firma") or "Fără firmă",
                "Utilaj": r.get("utilaj") or "",
                "Scadență": str(r.get("data_scadenta") or ""),
                "Zile": int(r.get("zile_ramase") or 0),
                "Status": (
                    "🚨 Depășită"
                    if int(r.get("zile_ramase") or 0) < 0
                    else ("⚠️ Azi" if int(r.get("zile_ramase") or 0) == 0 else "🔔 În curând")
                ),
            }
            for r in alerta_rows
        ])
        st.dataframe(df_m, hide_index=True, use_container_width=True)


def render_piese_prioritare_bon_deschis():
    """Bon deschis vizibil direct: adaugă piesa și în catalogul `piese`, păstrează prioritate + stare,
    și scoate piesa din lista activă imediat ce e marcată ca Ofertată (păstrând istoricul)."""
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []
    optiuni_piese, detalii_piese = _incarca_optiuni_lookup_piese()

    h_left, h_right = st.columns([3.4, 1.6], vertical_alignment="center")
    with h_left:
        st.subheader("🎯 Bon Deschis Piese Prioritare (Căutare & Ofertare Client)")
        st.caption("Piesele notate intră și în catalogul general și ies din lista activă odată marcate ca **Ofertată**.")
    with h_right:
        with st.popover("➕ Notează piesă la client", use_container_width=True):
            if not firme_nume:
                st.warning("⚠️ Nu există firme în baza de date.")
            else:
                firma_teren = st.selectbox("Client / Firmă *", options=firme_nume, key="dash_prio_firma_sel")
                fid_teren = nume_to_id.get(firma_teren)
                masini_firma = [
                    str(m.get("denumire") or "").strip()
                    for m in masini_all
                    if str(m.get("denumire") or "").strip()
                    and not _este_stare_inchisa(m.get("stare"))
                    and (fid_teren is None or _safe_int(m.get("firma_id")) == fid_teren)
                ]
                opt_masini_teren = ["-- Fără mașină --"] + list(dict.fromkeys(masini_firma))

                piesa_aleasa_lookup = st.selectbox(
                    "Din catalog sau piesă nouă",
                    options=optiuni_piese,
                    key="dash_prio_lookup_piesa",
                )
                este_piesa_noua = piesa_aleasa_lookup == "✍️ Piesă nouă (scriu manual)"
                piesa_din_db = detalii_piese.get(piesa_aleasa_lookup, {})
                den_implicit = "" if este_piesa_noua else str(piesa_din_db.get("denumire") or "")
                cod_implicit = "" if este_piesa_noua else str(piesa_din_db.get("cod_producator") or "")

                with st.form("form_piesa_prioritara_bon", clear_on_submit=True):
                    piesa_teren = st.text_input(
                        "Denumire piesă *",
                        value=den_implicit,
                        disabled=not este_piesa_noua,
                        placeholder="ex: rulment, senzor, electrovalvă...",
                    )
                    cod_teren = st.text_input("Cod producător", value=cod_implicit)
                    masina_teren = st.selectbox("Utilaj (opțional)", options=opt_masini_teren)
                    fc1, fc2, fc3 = st.columns(3)
                    with fc1:
                        cant_teren = st.number_input("Cant.", min_value=0.01, value=1.0, step=1.0, format="%.2f")
                    with fc2:
                        prioritate_teren = st.selectbox("Prioritate", options=OPTIUNI_PRIORITATE_PIESA, index=0)
                    with fc3:
                        stare_init_teren = st.selectbox("Stare", options=OPTIUNI_STATUS_TEREN, index=0)
                    obs_teren = st.text_input("Observații scurte", placeholder="furnizor / detalii ofertare...")
                    salveaza_teren = st.form_submit_button("Salvează pe bon", type="primary", use_container_width=True)

                if salveaza_teren:
                    try:
                        den_finala = den_implicit if not este_piesa_noua else piesa_teren
                        rez = NecesarPieseRepository.noteaza_piesa_pe_teren(
                            firma_client=firma_teren,
                            firma_id=fid_teren,
                            denumire_piesa=den_finala,
                            cantitate=cant_teren,
                            masina=masina_teren,
                            cod_producator=cod_teren,
                            prioritate_piesa=prioritate_teren,
                            status_comanda=stare_init_teren,
                            observatii=obs_teren,
                        )
                        _goleste_cache_piese_si_cataloage()
                        st.success(
                            f"✅ **{str(den_finala).strip()}** ({float(cant_teren):g}) adăugat pentru **{firma_teren}** "
                            f"[{rez.get('prioritate_piesa')} • {rez.get('status_comanda')}]."
                        )
                    except ValueError as ve:
                        st.error(f"⚠️ {ve}")
                    except Exception as e:
                        st.error(f"⚠️ Eroare la salvare: {e}")

    toate_prioritare = NecesarPieseRepository.get_all(include_ofertate=True) or []
    if not toate_prioritare:
        st.info("Nu există piese notate pe bonul prioritar.")
        return

    fp1, fp2, fp3, fp4, fp5 = st.columns([1.4, 1.0, 1.2, 1.4, 1.2], vertical_alignment="bottom")
    with fp1:
        firme_opt = ["Toate firmele"] + sorted({
            str(r.get("firma_client") or "").strip()
            for r in toate_prioritare
            if str(r.get("firma_client") or "").strip()
        })
        sel_firma_p = st.selectbox("Client", options=firme_opt, key="dash_prio_filtru_firma")
    with fp2:
        sel_prio_p = st.selectbox("Prioritate", options=["Toate", "Urgent", "Normal"], key="dash_prio_filtru_prio")
    with fp3:
        sel_stare_p = st.selectbox("Stare", options=["Toate active"] + OPTIUNI_STATUS_TEREN, key="dash_prio_filtru_stare")
    with fp4:
        cautare_p = st.text_input("Caută", placeholder="piesă / cod / furnizor...", key="dash_prio_cautare").strip().lower()
    with fp5:
        arata_istoric_ofertate = st.checkbox("Istoric ofertate", value=False, key="dash_prio_arata_ofertate")

    lista_vizibila = [
        r for r in toate_prioritare
        if arata_istoric_ofertate or _normalizeaza_stare_comanda(r.get("status_comanda")) != "Ofertată"
    ]
    if sel_firma_p != "Toate firmele":
        lista_vizibila = [r for r in lista_vizibila if str(r.get("firma_client") or "").strip() == sel_firma_p]
    if sel_prio_p != "Toate":
        lista_vizibila = [r for r in lista_vizibila if normalizeaza_prioritate_piesa(r.get("prioritate_piesa")) == sel_prio_p]
    if sel_stare_p != "Toate active":
        lista_vizibila = [r for r in lista_vizibila if _normalizeaza_stare_comanda(r.get("status_comanda")) == sel_stare_p]
    if cautare_p:
        lista_vizibila = [
            r for r in lista_vizibila
            if cautare_p in str(r.get("denumire_piesa") or "").lower()
            or cautare_p in str(r.get("cod_producator") or "").lower()
            or cautare_p in str(r.get("furnizor_piesa") or "").lower()
        ]

    if not lista_vizibila:
        st.success("✅ Nu mai sunt piese active pe bonul prioritar pentru filtrele alese.")
        return

    df_p_init = pd.DataFrame([
        {
            "id": int(r["id"]),
            "Prioritate": normalizeaza_prioritate_piesa(r.get("prioritate_piesa")),
            "Stare": _normalizeaza_stare_comanda(r.get("status_comanda")),
            "Client": str(r.get("firma_client") or ""),
            "Piesă": (
                f"{str(r.get('denumire_piesa') or '')}"
                + (f" [{str(r.get('cod_producator') or '').strip()}]" if str(r.get("cod_producator") or "").strip() else "")
            ),
            "Cant.": _safe_float(r.get("cantitate"), 1.0),
            "Furnizor": str(r.get("furnizor_piesa") or "").strip() or "Fără furnizor",
            "Observații": str(r.get("observatii") or ""),
            "Ofertată": False,
        }
        for r in lista_vizibila
    ])

    st.session_state.setdefault("dash_prio_editor_rev", 0)
    editor_prio_key = f"dash_editor_piese_prioritare_v{st.session_state['dash_prio_editor_rev']}"

    edited_p = st.data_editor(
        df_p_init,
        key=editor_prio_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["id", "Client", "Piesă", "Cant.", "Furnizor"],
        column_config={
            "id": None,
            "Prioritate": st.column_config.SelectboxColumn("Prioritate", options=OPTIUNI_PRIORITATE_PIESA, required=True, width="small"),
            "Stare": st.column_config.SelectboxColumn("Stare", options=OPTIUNI_STATUS_TEREN, required=True, width="medium"),
            "Client": st.column_config.TextColumn("Client", width="medium"),
            "Piesă": st.column_config.TextColumn("Piesă", width="large"),
            "Cant.": st.column_config.NumberColumn("Cant.", format="%.2f", width="small"),
            "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
            "Observații": st.column_config.TextColumn("Observații", width="medium"),
            "Ofertată": st.column_config.CheckboxColumn("📤 Ofertată", default=False, width="small"),
        },
    )

    if st.button("💾 Salvează piese prioritare", type="primary", key="btn_dash_save_piese_prioritare"):
        df_p_final = edited_p.copy()
        state_p = st.session_state.get(editor_prio_key)
        if isinstance(state_p, dict):
            for idx_key, changes in (state_p.get("edited_rows") or {}).items():
                idx = _safe_int(idx_key)
                if idx is not None and 0 <= idx < len(df_p_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_p_final.columns:
                            df_p_final.at[idx, col_name] = new_val

        orig_p_map = {
            int(r.id): (
                normalizeaza_prioritate_piesa(r.Prioritate),
                _normalizeaza_stare_comanda(r.Stare),
                str(r.Observații or "").strip(),
            )
            for r in df_p_init.itertuples(index=False)
        }

        nr_actualizate = 0
        nr_ofertate = 0
        erori_p = []

        for row in df_p_final.itertuples(index=False):
            nid = int(row.id)
            orig = orig_p_map.get(nid)
            if orig is None:
                continue

            prio_veche, stare_veche, obs_veche = orig
            prio_noua = normalizeaza_prioritate_piesa(row.Prioritate)
            stare_noua = _normalizeaza_stare_comanda(row.Stare)
            obs_noua = str(row.Observații or "").strip()
            marcat_ofertat_acum = bool(getattr(row, "Ofertată", False))

            try:
                if marcat_ofertat_acum or (stare_noua == "Ofertată" and stare_veche != "Ofertată"):
                    nota_extra = obs_noua if (obs_noua and obs_noua != obs_veche) else ""
                    NecesarPieseRepository.marcheaza_ofertat(nid, observatie_suplimentara=nota_extra)
                    nr_ofertate += 1
                    continue

                if prio_noua != prio_veche:
                    NecesarPieseRepository.update_prioritate_piesa(nid, prio_noua)
                    nr_actualizate += 1

                if stare_noua != stare_veche:
                    NecesarPieseRepository.update_status_comanda(nid, stare_noua)
                    nr_actualizate += 1

                if obs_noua != obs_veche:
                    with db_cursor() as c:
                        c.execute("UPDATE necesar_piese SET observatii = %s WHERE id = %s", (obs_noua, nid))
                    NecesarPieseRepository.get_all.clear()
                    nr_actualizate += 1
            except Exception as e:
                erori_p.append(f"#{nid} ({row.Piesă}): {e}")

        if erori_p:
            st.error("⚠️ Erori la salvare:\n" + "\n".join(erori_p))

        if nr_actualizate == 0 and nr_ofertate == 0:
            if not erori_p:
                st.info("ℹ️ Nu există modificări nesalvate.")
        else:
            _goleste_cache_piese_si_cataloage()
            st.session_state["dash_prio_editor_rev"] += 1
            parti = []
            if nr_ofertate:
                parti.append(f"**{nr_ofertate}** marcate ca **Ofertată** (scoase din bonul activ)")
            if nr_actualizate:
                parti.append(f"**{nr_actualizate}** actualizări")
            st.success("✅ " + " • ".join(parti) + ".")


def render_notite_vizita_dashboard():
    firme_nume, nume_to_id = _obtine_harta_firme()

    n_left, n_right = st.columns([3.2, 1.8], vertical_alignment="center")
    with n_left:
        st.subheader("📋 Notițe & Task-uri Vizită Client")
    with n_right:
        with st.popover("➕ Notiță nouă", use_container_width=True):
            if not firme_nume:
                st.warning("⚠️ Nu există firme în baza de date.")
            else:
                with st.form("form_adauga_notita_vizita", clear_on_submit=True):
                    data_viz = st.date_input("Data *", value=datetime.date.today())
                    firma_viz = st.selectbox("Firmă *", options=firme_nume)
                    stare_viz = st.selectbox("Stare *", options=OPTIUNI_STARE_TASK_VIZITA, index=0)
                    note_viz = st.text_area("Note vizită *", placeholder="ce trebuie verificat / ofertat / făcut...", height=80)
                    salveaza_nota = st.form_submit_button("Salvează notița", type="primary", use_container_width=True)

                if salveaza_nota:
                    try:
                        TaskuriVizitaRepository.insert(
                            data_vizita=data_viz,
                            firma=firma_viz,
                            firma_id=nume_to_id.get(firma_viz),
                            note_vizita=note_viz,
                            stare=stare_viz,
                        )
                        try:
                            TaskuriVizitaRepository.get_all.clear()
                        except Exception:
                            pass
                        st.success(f"✅ Notiță salvată pentru **{firma_viz}**.")
                    except ValueError as ve:
                        st.error(f"⚠️ {ve}")
                    except Exception as e:
                        st.error(f"⚠️ Eroare la salvare: {e}")

    taskuri = TaskuriVizitaRepository.get_all() or []
    if not taskuri:
        st.info("Nu există notițe înregistrate.")
        return

    ft1, ft2, ft3 = st.columns([1.3, 1.3, 1.4])
    with ft1:
        firme_filtrare = ["Toate firmele"] + sorted({
            str(r.get("firma") or "").strip()
            for r in taskuri
            if str(r.get("firma") or "").strip()
        })
        sel_firma_t = st.selectbox("Firmă", options=firme_filtrare, key="dash_task_filtru_firma")
    with ft2:
        sel_stare_t = st.selectbox(
            "Stare",
            options=["Active (fără Finalizat)", "Toate stările"] + OPTIUNI_STARE_TASK_VIZITA,
            key="dash_task_filtru_stare",
        )
    with ft3:
        cautare_t = st.text_input("Caută în note", placeholder="cuvânt cheie...", key="dash_task_cautare").strip().lower()

    filtrate_t = []
    for r in taskuri:
        firma_r = str(r.get("firma") or "").strip()
        stare_r = normalizeaza_stare_task_vizita(r.get("stare"))
        nota_r = str(r.get("note_vizita") or "")
        if sel_firma_t != "Toate firmele" and firma_r != sel_firma_t:
            continue
        if sel_stare_t == "Active (fără Finalizat)" and stare_r == "Finalizat":
            continue
        if sel_stare_t not in ("Active (fără Finalizat)", "Toate stările") and stare_r != sel_stare_t:
            continue
        if cautare_t and cautare_t not in nota_r.lower():
            continue
        filtrate_t.append(r)

    if not filtrate_t:
        st.info("Nu există notițe pentru filtrele selectate.")
        return

    df_t_init = pd.DataFrame([
        {
            "id": int(r["id"]),
            "Data": str(r.get("data_vizita") or ""),
            "Firmă": str(r.get("firma") or ""),
            "Note de vizită": str(r.get("note_vizita") or ""),
            "Stare": normalizeaza_stare_task_vizita(r.get("stare")),
            "Șterge": False,
        }
        for r in filtrate_t
    ])

    st.session_state.setdefault("dash_task_editor_rev", 0)
    editor_task_key = f"dash_editor_taskuri_v{st.session_state['dash_task_editor_rev']}"

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
            "Stare": st.column_config.SelectboxColumn("Stare", options=OPTIUNI_STARE_TASK_VIZITA, required=True, width="medium"),
            "Șterge": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
        },
    )

    if st.button("💾 Salvează notițe", type="primary", key="btn_dash_save_taskuri"):
        df_t_final = edited_t.copy()
        state_t = st.session_state.get(editor_task_key)
        if isinstance(state_t, dict):
            for idx_key, changes in (state_t.get("edited_rows") or {}).items():
                idx = _safe_int(idx_key)
                if idx is not None and 0 <= idx < len(df_t_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_t_final.columns:
                            df_t_final.at[idx, col_name] = new_val

        orig_t_map = {
            int(r.id): (str(getattr(r, "_3", "")).strip(), normalizeaza_stare_task_vizita(r.Stare))
            for r in df_t_init.itertuples(index=False)
        }
        nr_mod_t = 0
        nr_del_t = 0
        erori_t = []

        for row in df_t_final.itertuples(index=False):
            tid = int(row.id)
            if bool(getattr(row, "Șterge", False)):
                try:
                    TaskuriVizitaRepository.delete(tid)
                    nr_del_t += 1
                except Exception as e:
                    erori_t.append(f"Ștergere #{tid}: {e}")
                continue

            orig = orig_t_map.get(tid)
            if orig is None:
                continue

            nota_noua = str(getattr(row, "_3", "") or "").strip()
            stare_noua = normalizeaza_stare_task_vizita(row.Stare)
            nota_veche, stare_veche = orig

            if not nota_noua:
                erori_t.append(f"Notița #{tid} nu poate fi goală.")
                continue

            if nota_noua != nota_veche or stare_noua != stare_veche:
                try:
                    TaskuriVizitaRepository.update(tid, nota_noua, stare_noua)
                    nr_mod_t += 1
                except Exception as e:
                    erori_t.append(f"Actualizare #{tid}: {e}")

        if erori_t:
            st.error("⚠️ Erori la salvarea notițelor:\n" + "\n".join(erori_t))

        if nr_mod_t == 0 and nr_del_t == 0:
            if not erori_t:
                st.info("ℹ️ Nu există modificări nesalvate la notițe.")
        else:
            try:
                TaskuriVizitaRepository.get_all.clear()
            except Exception:
                pass
            st.session_state["dash_task_editor_rev"] += 1
            st.success(f"✅ Notițe actualizate: **{nr_mod_t}** modificate, **{nr_del_t}** șterse.")


def _colecteaza_randuri_piese_de_comandat() -> list[dict]:
    piese_db = PieseRepository.get_all() or []
    furnizor_map: dict[str, str] = {}
    piesa_id_by_name: dict[str, int | None] = {}
    stare_catalog_by_name: dict[str, str] = {}

    for p in piese_db:
        den = str(p.get("denumire") or p.get("nume") or "").strip()
        if den:
            cheie = _norm_text(den)
            furnizor_map[cheie] = _extrage_furnizor_piesa(p)
            piesa_id_by_name[cheie] = _safe_int(p.get("id"))
            stare_catalog_by_name[cheie] = _normalizeaza_stare_comanda(p.get("stare_comandata"))

    randuri: list[dict] = []
    idx_counter = 0

    for np_row in (NecesarPieseRepository.get_all(include_ofertate=False) or []):
        den_np = str(np_row.get("denumire_piesa") or "").strip()
        if not den_np:
            continue
        cheie = _norm_text(den_np)
        furnizor_np = (
            str(np_row.get("furnizor_piesa") or "").strip()
            or furnizor_map.get(cheie, "Fără furnizor")
        )
        idx_counter += 1
        randuri.append({
            "_row_id": idx_counter,
            "_necesar_id": _safe_int(np_row.get("id")),
            "_piesa_id": _safe_int(np_row.get("piesa_id")) or piesa_id_by_name.get(cheie),
            "_sursa_tbl": "necesar_piese",
            "_sursa_rec_id": _safe_int(np_row.get("id")),
            "_json_item_idx": None,
            "Furnizor": furnizor_np,
            "Piesă": den_np,
            "Cantitate": _safe_float(np_row.get("cantitate"), 1.0),
            "Status Comandă": _normalizeaza_stare_comanda(np_row.get("status_comanda")),
            "Sursă": "Teren",
            "Firmă": str(np_row.get("firma_client") or "").strip(),
        })

    for r in (ReparatiiRepository.get_all() or []):
        if _este_stare_inchisa(r.get("stare_finala")):
            continue
        piese_raw = _parse_json_list(r.get("piese_valide") or r.get("piese_json"))
        for item_idx, item in enumerate(piese_raw):
            den_piesa = str(item.get("Piesa") or item.get("piesa") or item.get("denumire") or "").strip()
            if not den_piesa:
                continue
            tip_piesa = str(item.get("Tip") or item.get("tip") or "").strip()
            stare_item = str(item.get("stare_comandata") or item.get("Stare") or tip_piesa or "").strip()
            if (
                stare_item.lower() not in STARI_COMANDA_VALIDE_RAW
                and tip_piesa.lower() not in STARI_COMANDA_VALIDE_RAW
            ):
                continue

            cheie = _norm_text(den_piesa)
            if stare_item:
                stare_curenta = (
                    "De comandat"
                    if stare_item.lower() in ("de comandat", "necesara", "necesare")
                    else _normalizeaza_stare_comanda(stare_item)
                )
            else:
                stare_curenta = stare_catalog_by_name.get(cheie, "De comandat")

            cant = item.get("Cantitate") if item.get("Cantitate") is not None else item.get("cantitate")
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii",
                "_sursa_rec_id": _safe_int(r.get("id")),
                "_json_item_idx": item_idx,
                "Furnizor": furnizor_map.get(cheie, "Fără furnizor"),
                "Piesă": den_piesa,
                "Cantitate": _safe_float(cant, 1.0),
                "Status Comandă": stare_curenta,
                "Sursă": "Mașini",
                "Firmă": str(r.get("firma") or "").strip(),
            })

    for f_el in _incarca_fise_electronice_piese():
        comp_raw = _parse_json_list(f_el.get("componente_json"))
        for comp_idx, comp in enumerate(comp_raw):
            den_comp = str(
                comp.get("Componenta / Cod / Parametri")
                or comp.get("Componenta")
                or comp.get("piesa")
                or comp.get("denumire")
                or ""
            ).strip()
            stare_comp = str(comp.get("stare_comandata") or comp.get("Stare") or "").strip()
            if not den_comp or stare_comp.lower() not in STARI_COMANDA_VALIDE_RAW:
                continue

            cheie = _norm_text(den_comp)
            stare_curenta = (
                "De comandat"
                if stare_comp.lower() in ("de comandat", "necesara", "necesare")
                else _normalizeaza_stare_comanda(stare_comp)
            )
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii_electronice",
                "_sursa_rec_id": _safe_int(f_el.get("id")),
                "_json_item_idx": comp_idx,
                "Furnizor": furnizor_map.get(cheie, "Fără furnizor"),
                "Piesă": den_comp,
                "Cantitate": _safe_float(comp.get("Cantitate"), 1.0),
                "Status Comandă": stare_curenta,
                "Sursă": "Electronică",
                "Firmă": str(f_el.get("firma_nume") or "").strip(),
            })

    return randuri


def render_piese_de_comandat_dashboard():
    st.subheader("🛒 Piese De Comandat / Necesare & Furnizori")
    randuri = _colecteaza_randuri_piese_de_comandat()
    if not randuri:
        st.info("Nu există piese marcate ca necesare / de comandat / de căutat / de ofertat.")
        return

    df = pd.DataFrame(randuri)

    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1.5])
    with c1:
        filtru_sursa = st.selectbox("Sursă", options=["Toate", "Teren", "Mașini", "Electronică"], key="dash_piese_cmd_sursa")
    with c2:
        opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].unique().tolist())
        filtru_furn = st.selectbox("Furnizor", options=opt_furn, key="dash_piese_cmd_furn")
    with c3:
        filtru_stare = st.selectbox("Status", options=["Toate stările"] + OPTIUNI_STARE_COMANDA, key="dash_piese_cmd_stare")
    with c4:
        cautare_piesa = st.text_input("Caută piesă", placeholder="cod / denumire...", key="dash_piese_cmd_cautare").strip().lower()

    df_f = df
    if filtru_sursa != "Toate":
        df_f = df_f[df_f["Sursă"] == filtru_sursa]
    if filtru_furn != "Toți furnizorii":
        df_f = df_f[df_f["Furnizor"] == filtru_furn]
    if filtru_stare != "Toate stările":
        df_f = df_f[df_f["Status Comandă"] == filtru_stare]
    if cautare_piesa:
        df_f = df_f[df_f["Piesă"].str.lower().str.contains(re.escape(cautare_piesa), na=False)]

    if df_f.empty:
        st.info("Nu există piese care să corespundă filtrelor selectate.")
        return

    cols_afis = ["_row_id", "Furnizor", "Piesă", "Cantitate", "Status Comandă", "Sursă", "Firmă"]
    df_editor_init = df_f[cols_afis].reset_index(drop=True)

    st.session_state.setdefault("dash_piese_editor_rev", 0)
    editor_dash_key = f"dash_editor_stare_piese_v{st.session_state['dash_piese_editor_rev']}"

    edited_df = st.data_editor(
        df_editor_init,
        key=editor_dash_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["_row_id", "Furnizor", "Piesă", "Cantitate", "Sursă", "Firmă"],
        column_config={
            "_row_id": None,
            "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
            "Piesă": st.column_config.TextColumn("Piesă", width="large"),
            "Cantitate": st.column_config.NumberColumn("Cant.", format="%.2f", width="small"),
            "Status Comandă": st.column_config.SelectboxColumn("Status Comandă", options=OPTIUNI_STARE_COMANDA, required=True, width="medium"),
            "Sursă": st.column_config.TextColumn("Sursă", width="small"),
            "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
        },
    )

    if st.button("💾 Actualizează stările din tabel", type="primary", key="btn_dash_update_stare_piese"):
        df_final = edited_df.copy()
        if "Status Comandă" in df_final.columns:
            df_final["Status Comandă"] = df_final["Status Comandă"].astype(object)

        state_ed = st.session_state.get(editor_dash_key)
        if isinstance(state_ed, dict):
            for idx_key, changes in (state_ed.get("edited_rows") or {}).items():
                idx = _safe_int(idx_key)
                if idx is not None and 0 <= idx < len(df_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_final.columns:
                            df_final.at[idx, col_name] = (
                                _normalizeaza_stare_comanda(new_val) if col_name == "Status Comandă" else new_val
                            )

        meta_map = {
            int(r["_row_id"]): {
                "_necesar_id": _safe_int(r.get("_necesar_id")),
                "_piesa_id": _safe_int(r.get("_piesa_id")),
                "_sursa_tbl": str(r.get("_sursa_tbl") or "").strip(),
                "_sursa_rec_id": _safe_int(r.get("_sursa_rec_id")),
                "_json_item_idx": _safe_int(r.get("_json_item_idx")),
            }
            for r in df_f.to_dict(orient="records")
        }

        orig_map = {
            int(r["_row_id"]): _normalizeaza_stare_comanda(r["Status Comandă"])
            for r in df_editor_init.to_dict(orient="records")
        }

        nr_mod = 0
        erori_salvare: list[str] = []

        for row in df_final.to_dict(orient="records"):
            rid = int(row["_row_id"])
            stare_noua = _normalizeaza_stare_comanda(row.get("Status Comandă"))
            stare_veche = orig_map.get(rid)
            if stare_veche == stare_noua:
                continue

            meta = meta_map.get(rid) or {}
            salvat_ceva = False
            sursa_tbl = meta.get("_sursa_tbl") or ""
            denumire_piesa = str(row.get("Piesă") or "")

            necesar_id = meta.get("_necesar_id")
            if sursa_tbl == "necesar_piese" and necesar_id is not None:
                try:
                    NecesarPieseRepository.update_status_comanda(necesar_id, stare_noua)
                    salvat_ceva = True
                except Exception as e:
                    erori_salvare.append(f"Necesar #{necesar_id} ({denumire_piesa}): {e}")

            piesa_id = meta.get("_piesa_id")
            if sursa_tbl != "necesar_piese" and piesa_id is not None:
                try:
                    PieseRepository.update_stare_comandata(piesa_id, stare_noua)
                    salvat_ceva = True
                except Exception as e:
                    erori_salvare.append(f"Piesa #{piesa_id} ({denumire_piesa}): {e}")

            sursa_rec_id = meta.get("_sursa_rec_id")
            if sursa_tbl in ("reparatii", "reparatii_electronice") and sursa_rec_id is not None:
                try:
                    if _actualizeaza_stare_in_raport_json(
                        sursa_tbl,
                        sursa_rec_id,
                        denumire_piesa,
                        stare_noua,
                        item_idx=meta.get("_json_item_idx"),
                    ):
                        salvat_ceva = True
                except Exception as e:
                    erori_salvare.append(f"{sursa_tbl} #{sursa_rec_id} ({denumire_piesa}): {e}")

            if salvat_ceva:
                nr_mod += 1

        if erori_salvare:
            st.error("⚠️ Erori la salvare:\n" + "\n".join(erori_salvare))

        if nr_mod == 0:
            if not erori_salvare:
                st.info("ℹ️ Nu există modificări nesalvate.")
        else:
            _goleste_cache_piese_si_cataloage()
            st.session_state["dash_piese_editor_rev"] += 1
            st.success(f"✅ Stări actualizate pentru **{nr_mod}** poziții.")


def _comuta_sectiune_activa(nume_sectiune: str):
    curenta = st.session_state.get("dash_sectiune_activa")
    st.session_state["dash_sectiune_activa"] = None if curenta == nume_sectiune else nume_sectiune


def _ascunde_sectiune_activa():
    st.session_state["dash_sectiune_activa"] = None


def render_dashboard():
    # 1. Update automat în baza de date o singură dată pe sesiune la intrarea pe pagină
    if not st.session_state.get("dash_auto_sync_done", False):
        try:
            rez_sync = _executa_update_automat_db_sesiune()
            st.session_state["dash_auto_sync_done"] = True
            if rez_sync.get("adaugate_catalog", 0) > 0:
                st.toast(f"🔄 Sincronizate automat {rez_sync['adaugate_catalog']} piese noi în catalog.")
        except Exception as exc:
            st.session_state["dash_auto_sync_done"] = True
            st.warning(f"⚠️ Actualizarea automată la intrarea pe pagină a întâmpinat o problemă: {exc}")

    col_title, col_refresh = st.columns([5.2, 0.8], vertical_alignment="center")
    with col_title:
        st.title("📈 Dashboard CMMS")
    with col_refresh:
        if st.button("🔄", help="Reîmprospătează datele", use_container_width=True, key="btn_dash_refresh_unic"):
            _goleste_toate_cache_dashboard()
            st.session_state["dash_auto_sync_done"] = False
            st.rerun()

    kpi_res, masini_rep_res, el_rep_res, top_def, top_cli, top_ut = incarca_date_dashboard()

    interventii_luna = int(kpi_res.get("interventii") or 0)
    ore_lucrate = round(_safe_float(kpi_res.get("minute"), 0.0) / 60.0, 1)
    clienti_activi = int(kpi_res.get("clienti") or 0)
    utilaje_active = int(kpi_res.get("utilaje") or 0)
    utilaje_oprite = int(kpi_res.get("utilaje_oprite") or 0)
    utilaje_supr = int(kpi_res.get("utilaje_supraveghere") or 0)

    reusite_masini = int(masini_rep_res.get("reusite_masini_rep") or 0)
    total_masini = int(masini_rep_res.get("total_masini_rep") or 0)
    pct_masini = f"{round((reusite_masini / total_masini) * 100)}%" if total_masini > 0 else "0%"

    reusite_el = int(el_rep_res.get("reusite_el_rep") or 0)
    total_el = int(el_rep_res.get("total_el_rep") or 0)
    pct_el = f"{round((reusite_el / total_el) * 100)}%" if total_el > 0 else "0%"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🔧 Intervenții lună", interventii_luna)
    c2.metric("⏱ Ore lucrate", ore_lucrate)
    c3.metric("🏢 Clienți activi", clienti_activi)
    c4.metric("⚙️ Utilaje active", utilaje_active)
    c5.metric("🚨 Oprite", utilaje_oprite)
    c6.metric("👀 Supraveghere", utilaje_supr)

    st.session_state.setdefault("dash_sectiune_activa", None)
    sectiune_activa = st.session_state.get("dash_sectiune_activa")

    b1, b2, b3, b4 = st.columns([1.4, 1.6, 1.4, 0.9])
    with b1:
        st.button(
            "🛑 Utilaje oprite",
            use_container_width=True,
            type="primary" if sectiune_activa == "utilaje_oprite" else "secondary",
            key="btn_dash_utilaje_oprite",
            on_click=_comuta_sectiune_activa,
            args=("utilaje_oprite",),
        )
    with b2:
        st.button(
            "👀 Sub supraveghere",
            use_container_width=True,
            type="primary" if sectiune_activa == "sub_supraveghere" else "secondary",
            key="btn_dash_sub_supraveghere",
            on_click=_comuta_sectiune_activa,
            args=("sub_supraveghere",),
        )
    with b3:
        st.button(
            "💤 Clienți inactivi",
            use_container_width=True,
            type="primary" if sectiune_activa == "clienti_inactivi" else "secondary",
            key="btn_dash_clienti_inactivi",
            on_click=_comuta_sectiune_activa,
            args=("clienti_inactivi",),
        )
    with b4:
        if sectiune_activa is not None:
            st.button(
                "✖ Ascunde",
                use_container_width=True,
                key="btn_dash_ascunde",
                on_click=_ascunde_sectiune_activa,
            )

    if sectiune_activa == "utilaje_oprite":
        with st.container(border=True):
            date_oprite = incarca_utilaje_dupa_stare("oprite")
            if date_oprite:
                _randare_lista_utilaje_stare(date_oprite, este_supraveghere=False)
            else:
                st.info("Nu există utilaje oprite în acest moment.")
    elif sectiune_activa == "sub_supraveghere":
        with st.container(border=True):
            date_supr = incarca_utilaje_dupa_stare("supraveghere")
            if date_supr:
                _randare_lista_utilaje_stare(date_supr, este_supraveghere=True)
            else:
                st.info("Nu există utilaje sub supraveghere.")
    elif sectiune_activa == "clienti_inactivi":
        with st.container(border=True):
            zile_prag = st.selectbox(
                "Fără intervenții de cel puțin:",
                options=[30, 60, 90, 180],
                index=2,
                format_func=lambda x: f"{x} zile",
                key="sel_zile_clienti_inactivi",
            )
            date_inactivi = incarca_clienti_inactivi(zile_prag)
            if date_inactivi:
                st.dataframe(pd.DataFrame(date_inactivi), use_container_width=True, hide_index=True)
            else:
                st.info(f"Nu există clienți inactivi în ultimele {zile_prag} de zile.")

    # Navigare pe 3 tab-uri pentru ergonomie și mai puțin scroll
    tab_azi, tab_comenzi, tab_analiza = st.tabs([
        "🎯 Azi / De rezolvat",
        "🛒 Comenzi & Furnizori",
        "📅 Întrețineri & Analiză",
    ])

    with tab_azi:
        render_piese_prioritare_bon_deschis()
        st.markdown("---")
        render_notite_vizita_dashboard()

    with tab_comenzi:
        render_piese_de_comandat_dashboard()

    with tab_analiza:
        m_r1, m_r2 = st.columns(2)
        m_r1.metric("⚙️ Reparații Mașini Reușite", f"{reusite_masini} / {total_masini}", delta=pct_masini)
        m_r2.metric("⚡ Reparații Electronice Reușite", f"{reusite_el} / {total_el}", delta=pct_el)

        st.markdown("---")
        st.subheader("📅 Întrețineri Scadente")
        render_memento_intretinere_dashboard()

        st.markdown("---")
        st.subheader("⚠️ Defecte Recurente")
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            zile_defecte = st.selectbox(
                "Perioadă:",
                options=[30, 60, 90, 180, 365, 730, 1095],
                index=3,
                format_func=lambda x: f"Ultimele {x} zile",
                key="dash_defecte_recurente_zile",
            )

        def_rec_toate = incarca_defecte_recurente(zile_defecte)
        firme_disp = ["Toate firmele"] + sorted({d["firma"] for d in def_rec_toate if d.get("firma")})
        with f_col2:
            firma_sel = st.selectbox("Firmă:", options=firme_disp, key="dash_defecte_recurente_firma")

        masini_disp = ["Toate mașinile"] + sorted({
            d["masina"]
            for d in def_rec_toate
            if d.get("masina") and (firma_sel == "Toate firmele" or d.get("firma") == firma_sel)
        })
        with f_col3:
            masina_sel = st.selectbox("Mașină:", options=masini_disp, key="dash_defecte_recurente_masina")

        def_rec_filtrate = [
            d
            for d in def_rec_toate
            if (firma_sel == "Toate firmele" or d.get("firma") == firma_sel)
            and (masina_sel == "Toate mașinile" or d.get("masina") == masina_sel)
        ]

        if def_rec_filtrate:
            for d in def_rec_filtrate:
                st.warning(
                    f"⚠️ **{d['firma']} — {d['masina']}**  \n"
                    f"Defect: {d['defect']} • Apariții: **{d['repetitii']}**"
                )
        else:
            st.success(f"Nu există defecte recurente în ultimele {zile_defecte} zile pentru filtrele selectate.")

        st.markdown("---")
        if top_def:
            fig_defecte = px.bar(pd.DataFrame(top_def), x="aparitii", y="defect", orientation="h", title="Top 10 Defecte")
            st.plotly_chart(fig_defecte, use_container_width=True, key="grafic_top_defecte_dashboard")

        col1, col2 = st.columns(2)
        with col1:
            if top_cli:
                fig_clienti = px.bar(
                    pd.DataFrame(top_cli),
                    x="interventii",
                    y="firma",
                    orientation="h",
                    title="Top Clienți după număr intervenții",
                )
                st.plotly_chart(fig_clienti, use_container_width=True, key="grafic_top_clienti_dashboard")
        with col2:
            if top_ut:
                fig_utilaje = px.bar(
                    pd.DataFrame(top_ut),
                    x="masina",
                    y="interventii",
                    title="Top Utilaje după număr intervenții",
                )
                st.plotly_chart(fig_utilaje, use_container_width=True, key="grafic_top_utilaje_dashboard")