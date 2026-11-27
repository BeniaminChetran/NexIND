# ------------------------------------------
# -------pages/mentenanta.py----------------
# ------------------------------------------

from datetime import date, timedelta
import json
import re
from typing import Any
import pandas as pd
import streamlit as st

from config import db_cursor
from pages.fise_mentenanta import (
    FRECVENTE_MENTENANTA,
    adauga_operatiune_in_catalog_db,
    construieste_nume_fisa_masina,
    formateaza_consumabile_text,
    formateaza_documentatii_text,
    formateaza_piese_text,
    incarca_catalog_operatiuni_db,
    render_builder_resurse_operatiune,
    reseteaza_builder_resurse_operatiune,
)
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.mentenanta_repository import INTERVALE_ZILE
from repositories.setari_repository import SetariRepository
from services.pdf_service import genereaza_pdf_mentenanta


# ==============================================================================
# CONFIGURARE CENTRALIZATA (FARA HARDCODING IN LOGICA / UI)
# ==============================================================================

DEFAULT_CONFIG: dict[str, Any] = {
    "frecventa_implicita": "Lunară",
    "frecventa_titlu_implicita": "lunare",
    "prefix_nr_fisa": "FM",
    "lungime_nr_fisa": 4,
    "limita_istoric_fise": 50,
    "cache_ttl_secunde": 120,
    "prag_interventii_implicit": 20,
    "durata_revizie_implicita_zile": 30,
    "tehnician_implicit": "Tehnician Nexus",
    "verificator_implicit": "Client",
    "sistem_catalog_implicit": "Personalizat",
    "placeholder_firma": "-- Alege firma --",
    "placeholder_masina": "-- Alege mașina --",
    "placeholder_catalog": "-- Introdu manual / copy-paste --",
    "sablon_titlu_pdf": "Operatiuni de intretinere {frecventa_titlu} la masina {masina} tip {tip_masina} {data} {firma}",
    "frecvente_titlu_map": {
        "zilnică": "zilnice",
        "zilnica": "zilnice",
        "săptămânală": "saptamanale",
        "saptamanala": "saptamanale",
        "lunară": "lunare",
        "lunara": "lunare",
        "trimestrială": "trimestriale",
        "trimestriala": "trimestriale",
        "anuală": "anuale",
        "anuala": "anuale",
    },
    "nivele_grila": [
        "Nivel A – Multimarcă (<20h)",
        "Nivel B – CNC Biglia / Matec / >20h / Inginerie",
    ],
    "stari_initiale": [
        "Funcțional",
        "Nefuncțional",
        "Degradare moderată",
        "Stare avansată de degradare",
    ],
    "stari_finale": [
        "Funcțional (parametri nominali)",
        "Funcțional cu restricții (necesită piese)",
        "Oprit siguranță",
    ],
    "coloane_operatiuni": [
        {"key": "Ordine", "label": "Ordine", "type": "number", "width": "small", "step": 1},
        {"key": "Operațiune / Verificare", "label": "Operațiune / Verificare", "type": "text", "width": "large"},
        {"key": "Denumire parametru", "label": "Denumire parametru", "type": "text", "width": "medium"},
        {"key": "Valoare", "label": "Valoare", "type": "text", "width": "small"},
        {"key": "UM", "label": "UM", "type": "text", "width": "small"},
        {"key": "Piese necesare", "label": "Piese necesare", "type": "text", "width": "medium"},
        {"key": "Materiale consumabile", "label": "Materiale consumabile", "type": "text", "width": "medium"},
        {"key": "Documentație", "label": "Documentație", "type": "text", "width": "medium"},
        {"key": "Efectuat", "label": "Efectuat", "type": "checkbox", "width": "small"},
    ],
    "mesaje": {
        "titlu_pagina": "🛡️ Fișă de Mentenanță Preventivă & Audit Tehnic",
        "fara_firme": "⚠️ Adăugați mai întâi cel puțin o firmă în modulul 'Firme'.",
        "selecteaza_client": "ℹ️ Selectează clientul și utilajul pentru a continua.",
        "selecteaza_utilaj": "ℹ️ Alege utilajul din lista clientului pentru a continua.",
        "sistem_blocat": "🔒 Dacă vrei să editezi fișele de întreținere, deblochează sistemul.",
        "fara_istoric": "Nu există încă fișe de mentenanță recurente salvate.",
        "operatiune_goala": "Selectează sau introdu o operațiune.",
        "operatiune_adaugata": "✅ Operațiunea a fost adăugată.",
        "selecteaza_pentru_stergere": "Selectează cel puțin o operațiune.",
    },
}


def _get_config(setari: dict | None = None) -> dict[str, Any]:
    """Imbina configuratia implicita cu eventualele suprascrieri din setarile din DB."""
    cfg = {
        k: (v.copy() if isinstance(v, (dict, list)) else v)
        for k, v in DEFAULT_CONFIG.items()
    }
    if not setari:
        return cfg

    if setari.get("tehnician_implicit"):
        cfg["tehnician_implicit"] = str(setari["tehnician_implicit"]).strip()

    extra_cfg = setari.get("mentenanta_config")
    if isinstance(extra_cfg, str):
        try:
            extra_cfg = json.loads(extra_cfg)
        except Exception:
            extra_cfg = {}

    if isinstance(extra_cfg, dict):
        for k, v in extra_cfg.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            elif v is not None:
                cfg[k] = v
    return cfg


# ==============================================================================
# ACCES DATE & CACHING (FARA DDL LA RUNTIME)
# ==============================================================================

def _parse_json_list(raw: Any) -> list[dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl_secunde"], show_spinner=False)
def _get_setari_cached() -> dict:
    return dict(SetariRepository.get_setari() or {})


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl_secunde"], show_spinner=False)
def _get_firme_cached() -> list[dict]:
    return [dict(f) for f in (FirmeRepository.get_all() or [])]


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl_secunde"], show_spinner=False)
def _get_masini_by_firma_cached(firma_id: int) -> list[dict]:
    return [dict(m) for m in (MasiniRepository.get_by_firma(firma_id) or [])]


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl_secunde"], show_spinner=False)
def _get_catalog_operatiuni_cached() -> list[dict]:
    return [dict(item) for item in (incarca_catalog_operatiuni_db() or [])]


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl_secunde"], show_spinner=False)
def _incarca_fise_recurente_db_cached(limita: int) -> list[dict]:
    with db_cursor() as c:
        c.execute(
            """
            SELECT *
            FROM client_operatiuni_mentenanta_recurente
            ORDER BY id DESC
            LIMIT %s
            """,
            (int(limita),),
        )
        rows = [dict(r) for r in (c.fetchall() or [])]

    for r in rows:
        r["operatiuni"] = _parse_json_list(r.get("operatiuni_json"))
    return rows


def _invalideaza_cache_fise_recurente() -> None:
    _incarca_fise_recurente_db_cached.clear()


def _invalideaza_cache_catalog() -> None:
    _get_catalog_operatiuni_cached.clear()


def _formateaza_nr_fisa(numar: int, cfg: dict[str, Any]) -> str:
    prefix = str(cfg.get("prefix_nr_fisa") or "FM").strip()
    lungime = int(cfg.get("lungime_nr_fisa") or 4)
    return f"{prefix}-{int(numar):0{lungime}d}"


def _estimeaza_nr_fisa_urmator(cfg: dict[str, Any]) -> str:
    with db_cursor() as c:
        c.execute("SELECT COALESCE(MAX(id), 0) + 1 AS urm FROM client_operatiuni_mentenanta_recurente")
        row = c.fetchone()
        urm = int(row["urm"] if isinstance(row, dict) else row[0]) if row else 1
    return _formateaza_nr_fisa(urm, cfg)


def _frecventa_in_titlu(frecventa: str, cfg: dict[str, Any]) -> str:
    f_default = str(cfg.get("frecventa_titlu_implicita") or "lunare")
    f = str(frecventa or f_default).strip().lower()
    frec_map = cfg.get("frecvente_titlu_map") or {}
    return frec_map.get(f, f or f_default)


def construieste_titlu_operatiuni_pdf(
    frecventa: str,
    masina: str,
    tip_masina: str,
    data_str: str,
    firma: str,
    nr_fisa: str = "",
    cfg: dict[str, Any] | None = None,
) -> str:
    cfg_activ = cfg or DEFAULT_CONFIG
    frec_implicita = str(cfg_activ.get("frecventa_implicita") or "Lunară")
    frec_txt = _frecventa_in_titlu(frecventa, cfg_activ)
    sablon = str(cfg_activ.get("sablon_titlu_pdf") or DEFAULT_CONFIG["sablon_titlu_pdf"])

    baza = sablon.format(
        frecventa_titlu=frec_txt,
        masina=str(masina or "-").strip(),
        tip_masina=str(tip_masina or "-").strip(),
        data=str(data_str or "").strip()[:10],
        firma=str(firma or "-").strip(),
    ).strip()

    tip_ment = str(frecventa or frec_implicita).strip()
    nr_txt = str(nr_fisa or "").strip()
    extra = f" - {tip_ment}" + (f" - {nr_txt}" if nr_txt else "")
    return f"{baza}{extra}"


def construieste_nume_fisier_pdf(titlu_pdf: str) -> str:
    baza = re.sub(r'[\/:*?"<>|]+', "", str(titlu_pdf or "Operatiuni de intretinere")).strip()
    baza = re.sub(r"\s+", "_", baza)
    return f"{baza}.pdf"


def _insereaza_fisa_recurenta_db(payload: dict, cfg: dict[str, Any]) -> tuple[int, str]:
    """Insereaza atomic si genereaza nr_fisa exact pe baza ID-ului real din DB (fara race condition)."""
    frec_implicita = str(cfg.get("frecventa_implicita") or "Lunară")
    nr_fisa_provizoriu = _estimeaza_nr_fisa_urmator(cfg)
    ops_json = json.dumps(payload.get("operatiuni") or [], ensure_ascii=False)

    with db_cursor() as c:
        c.execute(
            """
            INSERT INTO client_operatiuni_mentenanta_recurente (
                nr_fisa, firma_id, masina_id, firma_nume, masina_nume, tip_masina,
                frecventa, titlu_pdf, punct_lucru, producator_model, serie_fabricatie,
                nr_inventar, ore_functionare, ore_cumulate, nivel_grila,
                stare_initiala, stare_finala, operatiuni_json, recomandari_iiot,
                tehnician, verificator, functie_verificator, data_interventie, urmatoarea_revizie
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                nr_fisa_provizoriu,
                payload.get("firma_id"),
                payload.get("masina_id"),
                payload.get("firma_nume", ""),
                payload.get("masina_nume", ""),
                payload.get("tip_masina", ""),
                payload.get("frecventa", frec_implicita),
                "",
                payload.get("punct_lucru", ""),
                payload.get("producator_model", ""),
                payload.get("serie_fabricatie", ""),
                payload.get("nr_inventar", ""),
                payload.get("ore_functionare", ""),
                payload.get("ore_cumulate", ""),
                payload.get("nivel_grila", ""),
                payload.get("stare_initiala", ""),
                payload.get("stare_finala", ""),
                ops_json,
                payload.get("recomandari_iiot", ""),
                payload.get("tehnician", ""),
                payload.get("verificator", ""),
                payload.get("functie_verificator", ""),
                payload.get("data_interventie"),
                payload.get("urmatoarea_revizie"),
            ),
        )
        ret = c.fetchone()
        row_id = int(ret["id"] if isinstance(ret, dict) else ret[0]) if ret else 0

        nr_fisa_final = _formateaza_nr_fisa(row_id, cfg)
        titlu_pdf = construieste_titlu_operatiuni_pdf(
            frecventa=payload.get("frecventa") or frec_implicita,
            masina=payload.get("masina_nume") or "",
            tip_masina=payload.get("tip_masina") or "",
            data_str=str(payload.get("data_interventie") or ""),
            firma=payload.get("firma_nume") or "",
            nr_fisa=nr_fisa_final,
            cfg=cfg,
        )
        c.execute(
            """
            UPDATE client_operatiuni_mentenanta_recurente
            SET nr_fisa = %s, titlu_pdf = %s
            WHERE id = %s
            """,
            (nr_fisa_final, titlu_pdf, row_id),
        )

    _invalideaza_cache_fise_recurente()
    return row_id, nr_fisa_final


def _actualizeaza_fisa_recurenta_db(rec_id: int, nr_fisa: str, payload: dict, cfg: dict[str, Any]) -> str:
    frec_implicita = str(cfg.get("frecventa_implicita") or "Lunară")
    nr_fisa_clean = str(nr_fisa or "").strip() or _formateaza_nr_fisa(int(rec_id), cfg)
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=payload.get("frecventa") or frec_implicita,
        masina=payload.get("masina_nume") or "",
        tip_masina=payload.get("tip_masina") or "",
        data_str=str(payload.get("data_interventie") or ""),
        firma=payload.get("firma_nume") or "",
        nr_fisa=nr_fisa_clean,
        cfg=cfg,
    )
    ops_json = json.dumps(payload.get("operatiuni") or [], ensure_ascii=False)
    with db_cursor() as c:
        c.execute(
            """
            UPDATE client_operatiuni_mentenanta_recurente
            SET firma_id = %s,
                masina_id = %s,
                firma_nume = %s,
                masina_nume = %s,
                tip_masina = %s,
                frecventa = %s,
                titlu_pdf = %s,
                punct_lucru = %s,
                producator_model = %s,
                serie_fabricatie = %s,
                nr_inventar = %s,
                ore_functionare = %s,
                ore_cumulate = %s,
                nivel_grila = %s,
                stare_initiala = %s,
                stare_finala = %s,
                operatiuni_json = %s,
                recomandari_iiot = %s,
                tehnician = %s,
                verificator = %s,
                functie_verificator = %s,
                data_interventie = %s,
                urmatoarea_revizie = %s
            WHERE id = %s
            """,
            (
                payload.get("firma_id"),
                payload.get("masina_id"),
                payload.get("firma_nume", ""),
                payload.get("masina_nume", ""),
                payload.get("tip_masina", ""),
                payload.get("frecventa", frec_implicita),
                titlu_pdf,
                payload.get("punct_lucru", ""),
                payload.get("producator_model", ""),
                payload.get("serie_fabricatie", ""),
                payload.get("nr_inventar", ""),
                payload.get("ore_functionare", ""),
                payload.get("ore_cumulate", ""),
                payload.get("nivel_grila", ""),
                payload.get("stare_initiala", ""),
                payload.get("stare_finala", ""),
                ops_json,
                payload.get("recomandari_iiot", ""),
                payload.get("tehnician", ""),
                payload.get("verificator", ""),
                payload.get("functie_verificator", ""),
                payload.get("data_interventie"),
                payload.get("urmatoarea_revizie"),
                int(rec_id),
            ),
        )
    _invalideaza_cache_fise_recurente()
    return nr_fisa_clean


def _sterge_fisa_recurenta_db(rec_id: int) -> None:
    with db_cursor() as c:
        c.execute("DELETE FROM client_operatiuni_mentenanta_recurente WHERE id = %s", (int(rec_id),))
    _invalideaza_cache_fise_recurente()


# ==============================================================================
# NORMALIZARE & PAYLOAD BUILDERS (UNICA SURSA DE ADEVAR)
# ==============================================================================

def _normalizare_randuri_operatiuni(rows_in: list[dict], rows_exist: list[dict] | None = None) -> list[dict]:
    rez: list[dict] = []
    exist_list = rows_exist or []

    for idx, r in enumerate(rows_in or [], start=1):
        if not isinstance(r, dict):
            continue
        op_txt = str(r.get("Operațiune / Verificare") or r.get("operatiune") or "").strip()
        prm_txt = str(r.get("Denumire parametru") or r.get("parametru") or "").strip()
        val_txt = str(r.get("Valoare") or r.get("valoare") or "").strip()
        um_txt = str(r.get("UM") or r.get("um") or "").strip()
        piese_txt = str(r.get("Piese necesare") or formateaza_piese_text(r.get("piese") or [])).strip()
        cons_txt = str(r.get("Materiale consumabile") or formateaza_consumabile_text(r.get("consumabile") or [])).strip()
        doc_txt = str(r.get("Documentație") or formateaza_documentatii_text(r.get("documentatii") or [])).strip()

        if not any([op_txt, prm_txt, val_txt, um_txt, piese_txt, cons_txt, doc_txt]):
            continue

        ef_raw = r.get("Efectuat", True)
        if isinstance(ef_raw, str):
            ef_val = ef_raw.strip().lower() not in ("false", "0", "nu", "no")
        else:
            ef_val = bool(ef_raw)

        vechi = exist_list[idx - 1] if (idx - 1) < len(exist_list) and isinstance(exist_list[idx - 1], dict) else {}
        try:
            ordine_val = int(r.get("Ordine") or r.get("ordine") or len(rez) + 1)
        except Exception:
            ordine_val = len(rez) + 1

        rez.append(
            {
                "Ordine": ordine_val,
                "Operațiune / Verificare": op_txt,
                "Denumire parametru": prm_txt,
                "Valoare": val_txt,
                "UM": um_txt,
                "Piese necesare": piese_txt,
                "Materiale consumabile": cons_txt,
                "Documentație": doc_txt,
                "Efectuat": ef_val,
                "piese": r.get("piese") if isinstance(r.get("piese"), list) else (vechi.get("piese") or []),
                "consumabile": r.get("consumabile") if isinstance(r.get("consumabile"), list) else (vechi.get("consumabile") or []),
                "documentatii": r.get("documentatii") if isinstance(r.get("documentatii"), list) else (vechi.get("documentatii") or []),
            }
        )
    return rez


def _construieste_payload_complet_pdf(
    baza_fisa: dict,
    operatiuni: list[dict],
    titlu_pdf: str,
    frecventa: str,
    tip_masina: str,
    nr_fisa: str,
    nume_fisa_specifica: str | None = None,
) -> dict:
    payload = dict(baza_fisa)
    masina_nume = payload.get("masina_nume") or ""
    titlu_fisa = nume_fisa_specifica or construieste_nume_fisa_masina(masina_nume, tip_masina, frecventa)

    payload["nr_fisa"] = nr_fisa
    payload["operatiuni"] = operatiuni
    payload["titlu_pdf_operatiuni"] = titlu_pdf
    payload["checklist_json"] = {
        "fisa_specifica_utilaj": {
            "titlu": titlu_fisa,
            "titlu_pdf": titlu_pdf,
            "frecventa": frecventa,
            "nr_fisa": nr_fisa,
            "randuri": operatiuni,
        }
    }
    return payload


# ==============================================================================
# GESTIONARE SESSION_STATE & CALLBACK-URI (FARA ST.RERUN INUTIL)
# ==============================================================================

def _curata_chei_sesiune_mentenanta() -> None:
    prefixe = (
        "ment_ops_rows_",
        "ment_ed_ops_table_",
        "ment_ms_del_ops_",
        "ment_frec_fisa_",
        "ment_sel_cat_",
        "ment_sel_doc_",
        "ment_inp_op_",
        "ment_inp_prm_",
        "ment_inp_val_",
        "ment_inp_um_",
        "ment_chk_db_",
    )
    for k in list(st.session_state.keys()):
        if k.startswith(prefixe):
            del st.session_state[k]


def _creaza_draft_nou(cfg: dict[str, Any]) -> dict[str, Any]:
    nivele = cfg.get("nivele_grila") or DEFAULT_CONFIG["nivele_grila"]
    stari_ini = cfg.get("stari_initiale") or DEFAULT_CONFIG["stari_initiale"]
    stari_fin = cfg.get("stari_finale") or DEFAULT_CONFIG["stari_finale"]

    return {
        "sel_firma": cfg["placeholder_firma"],
        "sel_masina": cfg["placeholder_masina"],
        "data_interventie": date.today(),
        "punct_lucru": "",
        "producator_model": "",
        "serie_fabricatie": "",
        "nr_inventar": "",
        "ore_functionare": "",
        "ore_cumulate": "",
        "nivel_grila": nivele[0] if nivele else "",
        "stare_initiala": stari_ini[0] if stari_ini else "",
        "stare_finala": stari_fin[0] if stari_fin else "",
        "recomandari_iiot": "",
        "tehnician": cfg["tehnician_implicit"],
        "verificator": cfg["verificator_implicit"],
        "functie_verificator": "",
        "ultima_firma": cfg["placeholder_firma"],
        "ultima_masina": cfg["placeholder_masina"],
        "edit_rec_id": None,
        "edit_nr_fisa": "",
        "operatiuni_rows": [],
    }


def _init_sau_reseteaza_ment_draft(cfg: dict[str, Any]) -> None:
    st.session_state["ment_draft"] = _creaza_draft_nou(cfg)


def _cb_reseteaza_formular_complet(cfg: dict[str, Any]) -> None:
    st.session_state["ment_salvat"] = False
    st.session_state["ment_pdf_bytes"] = None
    st.session_state["ment_pdf_name"] = None
    st.session_state["ment_nr_fisa_salvat"] = None
    _curata_chei_sesiune_mentenanta()
    _init_sau_reseteaza_ment_draft(cfg)


def _cb_incarca_fisa_pentru_editare(fisa: dict, firme_dict: dict[str, dict], cfg: dict[str, Any]) -> None:
    _curata_chei_sesiune_mentenanta()
    st.session_state["ment_salvat"] = False
    st.session_state["ment_pdf_bytes"] = None
    st.session_state["ment_pdf_name"] = None
    st.session_state["ment_nr_fisa_salvat"] = None

    rows_salvate = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
    firma_nume = str(fisa.get("firma_nume") or cfg["placeholder_firma"])
    if firma_nume not in firme_dict:
        firma_nume = cfg["placeholder_firma"]

    data_raw = str(fisa.get("data_interventie") or "")[:10]
    try:
        data_int = date.fromisoformat(data_raw) if data_raw else date.today()
    except Exception:
        data_int = date.today()

    draft_nou = _creaza_draft_nou(cfg)
    draft_nou.update(
        {
            "sel_firma": firma_nume,
            "sel_masina": str(fisa.get("masina_nume") or cfg["placeholder_masina"]),
            "data_interventie": data_int,
            "punct_lucru": str(fisa.get("punct_lucru") or ""),
            "producator_model": str(fisa.get("producator_model") or ""),
            "serie_fabricatie": str(fisa.get("serie_fabricatie") or ""),
            "nr_inventar": str(fisa.get("nr_inventar") or ""),
            "ore_functionare": str(fisa.get("ore_functionare") or ""),
            "ore_cumulate": str(fisa.get("ore_cumulate") or ""),
            "nivel_grila": str(fisa.get("nivel_grila") or draft_nou["nivel_grila"]),
            "stare_initiala": str(fisa.get("stare_initiala") or draft_nou["stare_initiala"]),
            "stare_finala": str(fisa.get("stare_finala") or draft_nou["stare_finala"]),
            "recomandari_iiot": str(fisa.get("recomandari_iiot") or ""),
            "tehnician": str(fisa.get("tehnician") or cfg["tehnician_implicit"]),
            "verificator": str(fisa.get("verificator") or cfg["verificator_implicit"]),
            "functie_verificator": str(fisa.get("functie_verificator") or ""),
            "ultima_firma": firma_nume,
            "ultima_masina": str(fisa.get("masina_nume") or cfg["placeholder_masina"]),
            "edit_rec_id": fisa.get("id"),
            "edit_nr_fisa": str(fisa.get("nr_fisa") or ""),
            "operatiuni_rows": rows_salvate,
        }
    )
    st.session_state["ment_draft"] = draft_nou
    if fisa.get("frecventa") in FRECVENTE_MENTENANTA:
        st.session_state["ment_frec_selectata"] = str(fisa.get("frecventa"))


def _cb_sterge_operatiuni_selectate(rows_key: str, ms_key: str, opt_del: dict[str, int], msg_warn: str) -> None:
    selectate = st.session_state.get(ms_key) or []
    if not selectate:
        st.session_state["ment_flash_warn"] = msg_warn
        return

    indici_sters = {opt_del[k] for k in selectate if k in opt_del}
    rows_curente = list(st.session_state.get(rows_key) or [])
    ramase: list[dict] = []
    for idx_r, item in enumerate(rows_curente):
        if idx_r not in indici_sters:
            copie = dict(item)
            copie["Ordine"] = len(ramase) + 1
            ramase.append(copie)

    st.session_state[rows_key] = ramase
    st.session_state[ms_key] = []
    st.session_state["ment_flash_toast"] = f"🗑️ Au fost șterse {len(indici_sters)} operațiuni."


def _cb_sterge_fisa_istoric(rec_id: int) -> None:
    _sterge_fisa_recurenta_db(rec_id)
    st.session_state.pop(f"ment_hist_pdf_{rec_id}", None)
    st.session_state["ment_flash_toast"] = "🗑️ Fișa a fost ștearsă din istoric."


# ==============================================================================
# COMPONENTE UI
# ==============================================================================

def _construieste_column_config(cfg: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    coloane_def = cfg.get("coloane_operatiuni") or DEFAULT_CONFIG["coloane_operatiuni"]
    nume_coloane: list[str] = []
    col_config: dict[str, Any] = {}

    for col in coloane_def:
        key = col["key"]
        label = col.get("label", key)
        width = col.get("width", "medium")
        ctype = col.get("type", "text")
        nume_coloane.append(key)

        if ctype == "number":
            col_config[key] = st.column_config.NumberColumn(label, width=width, step=col.get("step", 1))
        elif ctype == "checkbox":
            col_config[key] = st.column_config.CheckboxColumn(label, width=width)
        else:
            col_config[key] = st.column_config.TextColumn(label, width=width)

    return nume_coloane, col_config


def _render_tabel_operatiuni_identic(rows: list[dict], key_prefix: str, editable: bool, cfg: dict[str, Any]):
    nume_coloane, col_config = _construieste_column_config(cfg)
    df_init = (
        pd.DataFrame([{c: r.get(c, "") for c in nume_coloane} for r in rows])
        if rows
        else pd.DataFrame(columns=nume_coloane)
    )

    return st.data_editor(
        df_init,
        hide_index=True,
        num_rows="dynamic" if editable else "fixed",
        use_container_width=True,
        disabled=[] if editable else nume_coloane,
        column_config=col_config,
        key=key_prefix,
    )


def _render_sectiune_operatiuni(
    masina_obj: dict,
    firma_nume: str,
    data_interv: date,
    is_unlocked: bool,
    frecventa_init: str,
    nr_fisa_curent: str,
    cfg: dict[str, Any],
):
    mid = masina_obj["id"]
    den_masina = str(masina_obj.get("denumire") or "").strip()
    tip_masina = str(masina_obj.get("tip_masina") or "").strip()
    frec_implicita = str(cfg.get("frecventa_implicita") or "Lunară")
    mesaje = cfg["mesaje"]

    frec_curr = st.session_state.get("ment_frec_selectata")
    if frec_curr not in FRECVENTE_MENTENANTA:
        frec_curr = frecventa_init if frecventa_init in FRECVENTE_MENTENANTA else frec_implicita

    frec_sel = st.selectbox(
        "Tip mentenanță realizată / Frecvență",
        options=FRECVENTE_MENTENANTA,
        index=FRECVENTE_MENTENANTA.index(frec_curr),
        key=f"ment_frec_fisa_{mid}",
    )
    st.session_state["ment_frec_selectata"] = frec_sel

    nume_fisa = construieste_nume_fisa_masina(den_masina, tip_masina, frec_sel)
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=frec_sel,
        masina=den_masina,
        tip_masina=tip_masina,
        data_str=str(data_interv),
        firma=firma_nume,
        nr_fisa=nr_fisa_curent,
        cfg=cfg,
    )
    st.caption(f"Fișă: **{nume_fisa}** | Titlu PDF: **{titlu_pdf}**")

    draft = st.session_state["ment_draft"]
    rows_key = f"ment_ops_rows_{mid}"
    if rows_key not in st.session_state:
        st.session_state[rows_key] = (
            _normalizare_randuri_operatiuni(draft.get("operatiuni_rows") or [])
            if draft.get("edit_rec_id") is not None
            else []
        )

    if is_unlocked:
        catalog_db = _get_catalog_operatiuni_cached()
        st.markdown("#### 📎 Încarcă / Setează operațiune, parametri, piese necesare, consumabile și documentații")
        placeholder_cat = cfg["placeholder_catalog"]
        opt_cat = {placeholder_cat: None}
        for it in catalog_db:
            opt_cat[f"[{it['sistem']}] {it['operatiune']}"] = it

        sel_cat_label = st.selectbox(
            "Alege operațiunea din Catalogul DB (sau introdu manual / copy-paste)",
            options=list(opt_cat.keys()),
            key=f"ment_sel_cat_{mid}",
        )
        item_cat = opt_cat.get(sel_cat_label)
        b_key = f"ment_res_m{mid}_{item_cat['id'] if item_cat else 'man'}"

        c_op, c_prm, c_val, c_um = st.columns([2.2, 1.2, 0.9, 0.7])
        with c_op:
            op_noua = st.text_input(
                "Operațiune / Verificare (manual sau copy-paste)",
                value=(item_cat["operatiune"] if item_cat else ""),
                key=f"ment_inp_op_{b_key}",
            ).strip()
        with c_prm:
            prm_nou = st.text_input(
                "Denumire parametru",
                value=(item_cat.get("parametru") or "" if item_cat else ""),
                placeholder="ex: Tensiune / Joc",
                key=f"ment_inp_prm_{b_key}",
            ).strip()
        with c_val:
            val_nou = st.text_input(
                "Valoare",
                value=(item_cat.get("valoare") or "" if item_cat else ""),
                placeholder="ex: 24.0 / 0.02",
                key=f"ment_inp_val_{b_key}",
            ).strip()
        with c_um:
            um_nou = st.text_input(
                "UM",
                value=(item_cat.get("um") or "" if item_cat else ""),
                placeholder="ex: V / mm",
                key=f"ment_inp_um_{b_key}",
            ).strip()

        piese_op, cons_op, docs_op, _extra_op = render_builder_resurse_operatiune(
            prefix_key=b_key,
            piese_init=(item_cat.get("piese") if item_cat else []),
            consumabile_init=(item_cat.get("consumabile") if item_cat else []),
            documentatii_init=(item_cat.get("documentatii") if item_cat else []),
        )

        salveaza_db = st.checkbox(
            "Salvează această operațiune și în Catalogul DB",
            value=(item_cat is None),
            key=f"ment_chk_db_{b_key}",
        )

        # Adaugarea se face INAINTE de randarea tabelului -> se reflecta imediat in acelasi ciclu, FARA st.rerun()!
        if st.button("➕ Adaugă operațiunea în tabel", key=f"ment_btn_add_op_{b_key}"):
            if not op_noua:
                st.warning(mesaje["operatiune_goala"])
            else:
                if salveaza_db and item_cat is None:
                    adauga_operatiune_in_catalog_db(
                        sistem=str(cfg.get("sistem_catalog_implicit") or "Personalizat"),
                        operatiune=op_noua,
                        parametru=prm_nou,
                        valoare=val_nou,
                        um=um_nou,
                        piese=piese_op,
                        consumabile=cons_op,
                        documentatii=docs_op,
                    )
                    _invalideaza_cache_catalog()

                lista_actuala = list(st.session_state.get(rows_key) or [])
                lista_actuala.append(
                    {
                        "Ordine": len(lista_actuala) + 1,
                        "Operațiune / Verificare": op_noua,
                        "Denumire parametru": prm_nou,
                        "Valoare": val_nou,
                        "UM": um_nou,
                        "Piese necesare": formateaza_piese_text(piese_op),
                        "Materiale consumabile": formateaza_consumabile_text(cons_op),
                        "Documentație": formateaza_documentatii_text(docs_op),
                        "Efectuat": True,
                        "piese": piese_op,
                        "consumabile": cons_op,
                        "documentatii": docs_op,
                    }
                )
                st.session_state[rows_key] = lista_actuala
                reseteaza_builder_resurse_operatiune(b_key)
                st.toast(mesaje["operatiune_adaugata"])

        rows_curente = list(st.session_state.get(rows_key) or [])
        if rows_curente:
            st.markdown("#### 🗑️ Ștergere una sau mai multe operațiuni deodată")
            opt_del = {
                f"{i + 1}. {str(r.get('Operațiune / Verificare') or '')[:85]}": i
                for i, r in enumerate(rows_curente)
            }
            ms_key = f"ment_ms_del_ops_{mid}"
            de_sters = st.multiselect(
                "Selectează operațiunile de șters",
                options=list(opt_del.keys()),
                key=ms_key,
            )
            st.button(
                "🗑️ Șterge operațiunile selectate",
                key=f"ment_btn_del_ops_{mid}",
                on_click=_cb_sterge_operatiuni_selectate,
                args=(rows_key, ms_key, opt_del, mesaje["selecteaza_pentru_stergere"]),
            )
    else:
        st.warning(mesaje["sistem_blocat"])

    rows_pentru_tabel = list(st.session_state.get(rows_key) or [])
    edit_id_tag = draft.get("edit_rec_id") if draft.get("edit_rec_id") is not None else "nou"
    df_ed = _render_tabel_operatiuni_identic(
        rows=rows_pentru_tabel,
        key_prefix=f"ment_ed_ops_table_{mid}_{edit_id_tag}_{len(rows_pentru_tabel)}",
        editable=is_unlocked,
        cfg=cfg,
    )

    if is_unlocked and df_ed is not None:
        st.session_state[rows_key] = _normalizare_randuri_operatiuni(
            df_ed.fillna("").to_dict(orient="records"),
            rows_exist=rows_pentru_tabel,
        )

    toate_linkurile = []
    for r in (st.session_state.get(rows_key) or []):
        ord_r = r.get("Ordine", "")
        for d_it in (r.get("documentatii") or []):
            u = str(d_it.get("url") or "").strip()
            t = str(d_it.get("titlu") or "Link").strip()
            if u.startswith(("http://", "https://")):
                toate_linkurile.append((f"Op.{ord_r} — {t}", u))

    if toate_linkurile:
        opt_l = {lbl: url for lbl, url in toate_linkurile}
        cd1, cd2 = st.columns([3.5, 1.5], vertical_alignment="center")
        sel_l = cd1.selectbox("Deschide link documentație", options=list(opt_l.keys()), key=f"ment_sel_doc_{mid}")
        cd2.link_button("📂 Deschide Documentația", opt_l[sel_l], use_container_width=True)

    return df_ed, nume_fisa, frec_sel, titlu_pdf


def _render_istoric_mentenanta(firme_dict: dict[str, dict], cfg: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("📂 Istoric Fișe de Mentenanță Preventivă")
    mesaje = cfg["mesaje"]

    fise_salvate = _incarca_fise_recurente_db_cached(int(cfg["limita_istoric_fise"]))
    if not fise_salvate:
        st.info(mesaje["fara_istoric"])
        return

    # Filtrare rapida in memorie pentru reducerea randarii DOM-ului
    cf1, cf2 = st.columns([2, 1])
    filtru_text = cf1.text_input(
        "🔍 Caută în istoric (Nr. fișă, firmă, utilaj, frecvență)",
        value="",
        key="ment_filtru_istoric_txt",
    ).strip().lower()
    firme_istoric = ["Toate firmele"] + sorted({str(f.get("firma_nume") or "") for f in fise_salvate if f.get("firma_nume")})
    filtru_firma = cf2.selectbox("Filtrează după firmă", options=firme_istoric, key="ment_filtru_istoric_firma")

    fise_filtrate = []
    for fisa in fise_salvate:
        if filtru_firma != "Toate firmele" and str(fisa.get("firma_nume") or "") != filtru_firma:
            continue
        if filtru_text:
            haystack = " ".join(
                str(fisa.get(k) or "") for k in ("nr_fisa", "firma_nume", "masina_nume", "frecventa", "data_interventie")
            ).lower()
            if filtru_text not in haystack:
                continue
        fise_filtrate.append(fisa)

    if not fise_filtrate:
        st.info("Nicio fișă nu corespunde filtrelor selectate.")
        return

    frec_implicita = str(cfg.get("frecventa_implicita") or "Lunară")
    for fisa in fise_filtrate:
        rec_id = fisa["id"]
        nr_fisa = str(fisa.get("nr_fisa") or "")
        data_str = str(fisa.get("data_interventie") or "")[:10]
        frec_hist = str(fisa.get("frecventa") or frec_implicita)
        tip_hist = str(fisa.get("tip_masina") or fisa.get("producator_model") or "")
        titlu_pdf_hist = str(fisa.get("titlu_pdf") or "").strip() or construieste_titlu_operatiuni_pdf(
            frecventa=frec_hist,
            masina=fisa.get("masina_nume") or "",
            tip_masina=tip_hist,
            data_str=data_str,
            firma=fisa.get("firma_nume") or "",
            nr_fisa=nr_fisa,
            cfg=cfg,
        )

        with st.expander(f"🛡️ {nr_fisa} | {fisa.get('firma_nume')} — {fisa.get('masina_nume')} ({frec_hist}) | {data_str}"):
            c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1], vertical_alignment="center")
            with c1:
                st.write(f"**Titlu:** {titlu_pdf_hist}")
                st.write(
                    f"**Nr. fișă:** {nr_fisa} | **Tip mentenanță:** {frec_hist} | "
                    f"**Tehnician:** {fisa.get('tehnician') or '-'}"
                )
            with c2:
                st.button(
                    "✏️ Editează",
                    key=f"edit_ment_rec_{rec_id}",
                    use_container_width=True,
                    on_click=_cb_incarca_fisa_pentru_editare,
                    args=(fisa, firme_dict, cfg),
                )
            with c3:
                pdf_state_key = f"ment_hist_pdf_{rec_id}"
                nume_pdf_hist = construieste_nume_fisier_pdf(titlu_pdf_hist)
                if st.button("📄 Generează PDF", key=f"prep_ment_rec_{rec_id}", use_container_width=True):
                    ops_hist = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
                    payload_pdf = _construieste_payload_complet_pdf(
                        baza_fisa=fisa,
                        operatiuni=ops_hist,
                        titlu_pdf=titlu_pdf_hist,
                        frecventa=frec_hist,
                        tip_masina=tip_hist,
                        nr_fisa=nr_fisa,
                    )
                    st.session_state[pdf_state_key] = genereaza_pdf_mentenanta(payload_pdf)

                if st.session_state.get(pdf_state_key):
                    st.download_button(
                        label="📥 Descarcă PDF",
                        data=st.session_state[pdf_state_key],
                        file_name=nume_pdf_hist,
                        mime="application/pdf",
                        key=f"dl_ment_rec_{rec_id}",
                        use_container_width=True,
                    )
            with c4:
                st.button(
                    "🗑️ Șterge",
                    key=f"del_ment_rec_{rec_id}",
                    use_container_width=True,
                    on_click=_cb_sterge_fisa_istoric,
                    args=(rec_id,),
                )

            ops_rows = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
            if ops_rows:
                nume_coloane, _ = _construieste_column_config(cfg)
                df_hist = pd.DataFrame([{c: r.get(c, "") for c in nume_coloane} for r in ops_rows])
                st.dataframe(df_hist, hide_index=True, use_container_width=True)


# ==============================================================================
# PUNCT PRINCIPAL DE INTRARE
# ==============================================================================

def render_mentenanta():
    setari = _get_setari_cached()
    cfg = _get_config(setari)
    mesaje = cfg["mesaje"]

    st.subheader(mesaje["titlu_pagina"])

    # Afisare notificari generate in callback-uri fara rerun suplimentar
    if toast_msg := st.session_state.pop("ment_flash_toast", None):
        st.toast(toast_msg)
    if warn_msg := st.session_state.pop("ment_flash_warn", None):
        st.warning(warn_msg)

    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    st.session_state.setdefault("ment_salvat", False)
    st.session_state.setdefault("ment_pdf_bytes", None)
    st.session_state.setdefault("ment_pdf_name", None)
    st.session_state.setdefault("ment_nr_fisa_salvat", None)
    if "ment_draft" not in st.session_state:
        _init_sau_reseteaza_ment_draft(cfg)

    draft = st.session_state["ment_draft"]
    firme_db = _get_firme_cached()
    if not firme_db:
        st.warning(mesaje["fara_firme"])
        return

    firme_dict = {
        str(f.get("nume_firma") or "").strip(): f
        for f in firme_db
        if str(f.get("nume_firma") or "").strip()
    }

    if st.session_state["ment_salvat"]:
        nr_f_salvat = st.session_state.get("ment_nr_fisa_salvat") or ""
        st.success(f"✅ Fișa de Mentenanță Preventivă **{nr_f_salvat}** a fost salvată!")
        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            if st.session_state["ment_pdf_bytes"]:
                nume_pdf = st.session_state.get("ment_pdf_name") or f"Operatiuni_de_intretinere_{nr_f_salvat}.pdf"
                st.download_button(
                    label="📥 Descarcă PDF",
                    data=st.session_state["ment_pdf_bytes"],
                    file_name=nume_pdf,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )
        with c_dl2:
            st.button(
                "🔄 Resetează formularul",
                use_container_width=True,
                on_click=_cb_reseteaza_formular_complet,
                args=(cfg,),
            )
        return

    if draft.get("edit_rec_id") is not None:
        st.info(
            f"✏️ **Editare fișă {draft.get('edit_nr_fisa') or ''}** — "
            "operațiunile din fișa salvată sunt încărcate în tabel."
        )

    placeholder_firma = cfg["placeholder_firma"]
    placeholder_masina = cfg["placeholder_masina"]
    opt_firme = [placeholder_firma] + list(firme_dict.keys())
    idx_f = opt_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in opt_firme else 0

    col_id1, col_id2, col_id3 = st.columns(3)
    with col_id1:
        sel_firma = st.selectbox("1. Beneficiar / Client *", options=opt_firme, index=idx_f)
        draft["sel_firma"] = sel_firma

    if sel_firma == placeholder_firma:
        st.info(mesaje["selecteaza_client"])
        _render_istoric_mentenanta(firme_dict, cfg)
        return

    firma_obj = firme_dict[sel_firma]
    if draft.get("ultima_firma") != sel_firma and draft.get("edit_rec_id") is None:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = firma_obj.get("nume_persoana") or cfg["verificator_implicit"]
        draft["punct_lucru"] = firma_obj.get("adresa") or ""
        draft["sel_masina"] = placeholder_masina
        draft["ultima_masina"] = placeholder_masina

    masini_db = _get_masini_by_firma_cached(int(firma_obj["id"]))
    masini_dict = {m["denumire"]: m for m in masini_db if m.get("denumire")}
    opt_masini = [placeholder_masina] + list(masini_dict.keys())
    idx_m = opt_masini.index(draft["sel_masina"]) if draft.get("sel_masina") in opt_masini else 0

    with col_id2:
        sel_masina = st.selectbox("2. Denumire Echipament / Mașină *", options=opt_masini, index=idx_m)
        draft["sel_masina"] = sel_masina

    with col_id3:
        data_interv = st.date_input("3. Data Intervenției", value=draft.get("data_interventie", date.today()))
        draft["data_interventie"] = data_interv

    if sel_masina == placeholder_masina:
        st.info(mesaje["selecteaza_utilaj"])
        _render_istoric_mentenanta(firme_dict, cfg)
        return

    masina_obj = masini_dict[sel_masina]
    total_int_m = int(masina_obj.get("total_interventii", 0))
    prag_int_m = int(masina_obj.get("prag_interventii") or cfg["prag_interventii_implicit"])
    nivele_grila = cfg["nivele_grila"]

    if draft.get("ultima_masina") != sel_masina and draft.get("edit_rec_id") is None:
        draft["ultima_masina"] = sel_masina
        draft["producator_model"] = str(masina_obj.get("tip_masina") or "")
        draft["serie_fabricatie"] = str(masina_obj.get("serie") or "")
        if len(nivele_grila) > 1:
            draft["nivel_grila"] = nivele_grila[1] if total_int_m >= prag_int_m else nivele_grila[0]
        elif nivele_grila:
            draft["nivel_grila"] = nivele_grila[0]

    frec_implicita = str(cfg.get("frecventa_implicita") or "Lunară")
    tip_int_masina = masina_obj.get("tip_intretinere") or frec_implicita
    interval_din_db = int(masina_obj.get("interval_intretinere_zile") or 0)
    durata_implicita_zile = (
        interval_din_db
        if interval_din_db > 0
        else INTERVALE_ZILE.get(tip_int_masina, int(cfg["durata_revizie_implicita_zile"]))
    )

    with st.expander("📋 Date Identificare Echipament & Stare Tehnică", expanded=False):
        d1, d2, d3, d4 = st.columns(4)
        draft["punct_lucru"] = d1.text_input("Punct de Lucru / Oraș", value=str(draft.get("punct_lucru", "")))
        draft["producator_model"] = d2.text_input("Producător / Model", value=str(draft.get("producator_model", "")))
        draft["serie_fabricatie"] = d3.text_input("Serie Fabricație", value=str(draft.get("serie_fabricatie", "")))
        draft["nr_inventar"] = d4.text_input("Nr. Inventar Intern", value=str(draft.get("nr_inventar", "")))

        e1, e2, e3 = st.columns(3)
        draft["ore_functionare"] = e1.text_input(
            "Ore Funcționare Utilaj",
            value=str(draft.get("ore_functionare", "")),
            placeholder="ex: 14520",
        )
        draft["ore_cumulate"] = e2.text_input(
            f"Ore Cumulate (din {prag_int_m}h)",
            value=str(draft.get("ore_cumulate", "")),
            placeholder=f"ex: 6 / {prag_int_m}",
        )
        idx_gr = nivele_grila.index(draft["nivel_grila"]) if draft.get("nivel_grila") in nivele_grila else 0
        draft["nivel_grila"] = e3.selectbox("Nivel Grilă Aplicabilă", options=nivele_grila, index=idx_gr)

        s1, s2, s3 = st.columns(3)
        opt_stare_ini = cfg["stari_initiale"]
        idx_si = opt_stare_ini.index(draft["stare_initiala"]) if draft.get("stare_initiala") in opt_stare_ini else 0
        draft["stare_initiala"] = s1.selectbox("Stare Inițială Utilaj", options=opt_stare_ini, index=idx_si)

        opt_stare_fin = cfg["stari_finale"]
        idx_sf = opt_stare_fin.index(draft["stare_finala"]) if draft.get("stare_finala") in opt_stare_fin else 0
        draft["stare_finala"] = s2.selectbox("Stare Finală Utilaj", options=opt_stare_fin, index=idx_sf)

        urmatoarea_rev_default = data_interv + timedelta(days=durata_implicita_zile)
        urmatoarea_revizie = s3.date_input(
            f"Următoarea Revizie ({tip_int_masina})",
            value=urmatoarea_rev_default,
        )

    nr_fisa_curent = draft.get("edit_nr_fisa") or _estimeaza_nr_fisa_urmator(cfg)

    with st.expander(f"🛠️ Operațiuni Mentenanță — {sel_masina} ({masina_obj.get('tip_masina') or '-'})", expanded=True):
        df_ops_utilaj, nume_fisa_activa, frec_fisa_activa, _ = _render_sectiune_operatiuni(
            masina_obj=masina_obj,
            firma_nume=sel_firma,
            data_interv=data_interv,
            is_unlocked=is_unlocked,
            frecventa_init=tip_int_masina,
            nr_fisa_curent=nr_fisa_curent,
            cfg=cfg,
        )

    st.markdown("---")
    st.markdown("### Recomandări Tehnice, Audit Upgrade / IIoT & Recepție Lucrări")
    draft["recomandari_iiot"] = st.text_area(
        "Constatări suplimentare & Recomandări de modernizare (Retrofit PLC / Senzoristică IIoT / Mentenanță Predictivă)",
        value=str(draft.get("recomandari_iiot", "")),
        height=95,
    )

    r1, r2, r3 = st.columns(3)
    draft["tehnician"] = r1.text_input(
        "Inginer / Tehnician Service",
        value=str(draft.get("tehnician", cfg["tehnician_implicit"])),
    )
    draft["verificator"] = r2.text_input(
        "Reprezentant Beneficiar (Nume & Prenume)",
        value=str(draft.get("verificator", "")),
    )
    draft["functie_verificator"] = r3.text_input(
        "Funcție Reprezentant Beneficiar",
        value=str(draft.get("functie_verificator", "")),
    )

    if st.button("💾 Salvează Fișa de Mentenanță & Generează PDF", type="primary", use_container_width=True):
        try:
            rows_key = f"ment_ops_rows_{masina_obj['id']}"
            ops_final = _normalizare_randuri_operatiuni(
                (df_ops_utilaj.fillna("").to_dict(orient="records"))
                if df_ops_utilaj is not None and not df_ops_utilaj.empty
                else (st.session_state.get(rows_key) or []),
                rows_exist=st.session_state.get(rows_key) or [],
            )

            tip_masina_cur = str(masina_obj.get("tip_masina") or "").strip()
            fisa_payload = {
                "firma_id": firma_obj["id"],
                "masina_id": masina_obj["id"],
                "firma_nume": sel_firma,
                "masina_nume": sel_masina,
                "tip_masina": tip_masina_cur,
                "nume_fisa": nume_fisa_activa,
                "frecventa": frec_fisa_activa,
                "punct_lucru": draft["punct_lucru"],
                "producator_model": draft["producator_model"],
                "serie_fabricatie": draft["serie_fabricatie"],
                "nr_inventar": draft["nr_inventar"],
                "ore_functionare": draft["ore_functionare"],
                "ore_cumulate": draft["ore_cumulate"],
                "nivel_grila": draft["nivel_grila"],
                "stare_initiala": draft["stare_initiala"],
                "stare_finala": draft["stare_finala"],
                "operatiuni": ops_final,
                "recomandari_iiot": draft["recomandari_iiot"],
                "tehnician": draft["tehnician"],
                "verificator": draft["verificator"],
                "functie_verificator": draft["functie_verificator"],
                "data_interventie": data_interv,
                "urmatoarea_revizie": urmatoarea_revizie,
            }

            edit_id = draft.get("edit_rec_id")
            if edit_id is not None:
                nr_fisa_salvat = _actualizeaza_fisa_recurenta_db(
                    int(edit_id),
                    str(draft.get("edit_nr_fisa") or ""),
                    fisa_payload,
                    cfg,
                )
            else:
                _, nr_fisa_salvat = _insereaza_fisa_recurenta_db(fisa_payload, cfg)

            titlu_pdf_final = construieste_titlu_operatiuni_pdf(
                frecventa=frec_fisa_activa,
                masina=sel_masina,
                tip_masina=tip_masina_cur,
                data_str=str(data_interv),
                firma=sel_firma,
                nr_fisa=nr_fisa_salvat,
                cfg=cfg,
            )
            fisa_payload = _construieste_payload_complet_pdf(
                baza_fisa=fisa_payload,
                operatiuni=ops_final,
                titlu_pdf=titlu_pdf_final,
                frecventa=frec_fisa_activa,
                tip_masina=tip_masina_cur,
                nr_fisa=nr_fisa_salvat,
                nume_fisa_specifica=nume_fisa_activa,
            )

            pdf_bytes = genereaza_pdf_mentenanta(fisa_payload)
            nume_pdf_cur = construieste_nume_fisier_pdf(titlu_pdf_final)

            _curata_chei_sesiune_mentenanta()
            st.session_state["ment_nr_fisa_salvat"] = nr_fisa_salvat
            st.session_state["ment_pdf_bytes"] = pdf_bytes
            st.session_state["ment_pdf_name"] = nume_pdf_cur
            st.session_state["ment_salvat"] = True
            _init_sau_reseteaza_ment_draft(cfg)
            st.rerun()
        except Exception as exc:
            st.error(f"⚠️ Eroare la salvarea fișei / generarea PDF: {exc}")

    _render_istoric_mentenanta(firme_dict, cfg)
