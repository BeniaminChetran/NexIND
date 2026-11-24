# ------------------------------------------
# -------pages/mentenanta.py----------------
# ------------------------------------------

from datetime import date, timedelta
import json
import re
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

_FRECVENTE_TITLU_MAP = {
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
}

_COLS_VIZ_OPERATIUNI = [
    "Ordine",
    "Operațiune / Verificare",
    "Denumire parametru",
    "Valoare",
    "UM",
    "Piese necesare",
    "Materiale consumabile",
    "Documentație",
    "Efectuat",
]


@st.cache_resource
def _asigura_tabela_recurente_db() -> bool:
    with db_cursor() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS client_operatiuni_mentenanta_recurente (
                id SERIAL PRIMARY KEY,
                nr_fisa VARCHAR(64) NOT NULL,
                firma_id INTEGER,
                masina_id INTEGER,
                firma_nume VARCHAR(255) NOT NULL DEFAULT '',
                masina_nume VARCHAR(255) NOT NULL DEFAULT '',
                tip_masina VARCHAR(255) NOT NULL DEFAULT '',
                frecventa VARCHAR(64) NOT NULL DEFAULT 'Lunară',
                titlu_pdf VARCHAR(512) NOT NULL DEFAULT '',
                punct_lucru VARCHAR(255) NOT NULL DEFAULT '',
                producator_model VARCHAR(255) NOT NULL DEFAULT '',
                serie_fabricatie VARCHAR(255) NOT NULL DEFAULT '',
                nr_inventar VARCHAR(255) NOT NULL DEFAULT '',
                ore_functionare VARCHAR(120) NOT NULL DEFAULT '',
                ore_cumulate VARCHAR(120) NOT NULL DEFAULT '',
                nivel_grila VARCHAR(255) NOT NULL DEFAULT '',
                stare_initiala VARCHAR(255) NOT NULL DEFAULT '',
                stare_finala VARCHAR(255) NOT NULL DEFAULT '',
                operatiuni_json TEXT NOT NULL DEFAULT '[]',
                recomandari_iiot TEXT NOT NULL DEFAULT '',
                tehnician VARCHAR(255) NOT NULL DEFAULT '',
                verificator VARCHAR(255) NOT NULL DEFAULT '',
                functie_verificator VARCHAR(255) NOT NULL DEFAULT '',
                data_interventie DATE,
                urmatoarea_revizie DATE,
                creat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ENABLE ROW LEVEL SECURITY;")
        c.execute("ALTER TABLE fise_mentenanta_tip_masina ENABLE ROW LEVEL SECURITY;")
    return True


def _invalideaza_cache_fise_recurente() -> None:
    clear_fn = getattr(_incarca_fise_recurente_db_cached, "clear", None)
    if callable(clear_fn):
        try:
            clear_fn()
        except Exception:
            pass


def _genereaza_nr_fisa_unic() -> str:
    _asigura_tabela_recurente_db()
    with db_cursor() as c:
        c.execute("SELECT COALESCE(MAX(id), 0) + 1 AS urm FROM client_operatiuni_mentenanta_recurente")
        row = c.fetchone()
        urm = int(row["urm"] if isinstance(row, dict) else row[0]) if row else 1
    return f"FM-{urm:04d}"


def _frecventa_in_titlu(frecventa: str) -> str:
    f = str(frecventa or "lunare").strip().lower()
    return _FRECVENTE_TITLU_MAP.get(f, f or "lunare")


def construieste_titlu_operatiuni_pdf(
    frecventa: str,
    masina: str,
    tip_masina: str,
    data_str: str,
    firma: str,
    nr_fisa: str = "",
) -> str:
    frec_txt = _frecventa_in_titlu(frecventa)
    m_txt = str(masina or "-").strip()
    t_txt = str(tip_masina or "-").strip()
    d_txt = str(data_str or "").strip()[:10]
    f_txt = str(firma or "-").strip()
    tip_ment = str(frecventa or "Lunară").strip()
    nr_txt = str(nr_fisa or "").strip()
    baza = f"Operatiuni de intretinere {frec_txt} la masina {m_txt} tip {t_txt} {d_txt} {f_txt}".strip()
    extra = f" - {tip_ment}"
    if nr_txt:
        extra += f" - {nr_txt}"
    return f"{baza}{extra}"


def construieste_nume_fisier_pdf(titlu_pdf: str) -> str:
    baza = re.sub(r'[\\/:*?"<>|]+', "", str(titlu_pdf or "Operatiuni de intretinere")).strip()
    baza = re.sub(r"\s+", "_", baza)
    return f"{baza}.pdf"


def _insereaza_fisa_recurenta_db(payload: dict) -> tuple[int, str]:
    _asigura_tabela_recurente_db()
    nr_fisa = _genereaza_nr_fisa_unic()
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=payload.get("frecventa") or "Lunară",
        masina=payload.get("masina_nume") or "",
        tip_masina=payload.get("tip_masina") or "",
        data_str=str(payload.get("data_interventie") or ""),
        firma=payload.get("firma_nume") or "",
        nr_fisa=nr_fisa,
    )
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
                nr_fisa,
                payload.get("firma_id"),
                payload.get("masina_id"),
                payload.get("firma_nume", ""),
                payload.get("masina_nume", ""),
                payload.get("tip_masina", ""),
                payload.get("frecventa", "Lunară"),
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
            ),
        )
        ret = c.fetchone()
        row_id = int(ret["id"] if isinstance(ret, dict) else ret[0]) if ret else 0
    _invalideaza_cache_fise_recurente()
    return row_id, nr_fisa


def _actualizeaza_fisa_recurenta_db(rec_id: int, nr_fisa: str, payload: dict) -> str:
    _asigura_tabela_recurente_db()
    nr_fisa_clean = str(nr_fisa or "").strip() or _genereaza_nr_fisa_unic()
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=payload.get("frecventa") or "Lunară",
        masina=payload.get("masina_nume") or "",
        tip_masina=payload.get("tip_masina") or "",
        data_str=str(payload.get("data_interventie") or ""),
        firma=payload.get("firma_nume") or "",
        nr_fisa=nr_fisa_clean,
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
                payload.get("frecventa", "Lunară"),
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


@st.cache_data(ttl=120)
def _incarca_fise_recurente_db_cached() -> list[dict]:
    _asigura_tabela_recurente_db()
    with db_cursor() as c:
        c.execute(
            """
            SELECT *
            FROM client_operatiuni_mentenanta_recurente
            ORDER BY id DESC
            LIMIT 50
            """
        )
        rows = [dict(r) for r in (c.fetchall() or [])]

    for r in rows:
        raw = r.get("operatiuni_json")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                r["operatiuni"] = parsed if isinstance(parsed, list) else []
            except Exception:
                r["operatiuni"] = []
        elif isinstance(raw, list):
            r["operatiuni"] = raw
        else:
            r["operatiuni"] = []
    return rows


def _incarca_fise_recurente_db() -> list[dict]:
    return [dict(r) for r in _incarca_fise_recurente_db_cached()]


def _sterge_fisa_recurenta_db(rec_id: int) -> None:
    _asigura_tabela_recurente_db()
    with db_cursor() as c:
        c.execute("DELETE FROM client_operatiuni_mentenanta_recurente WHERE id = %s", (int(rec_id),))
    _invalideaza_cache_fise_recurente()


def _normalizare_randuri_operatiuni(rows_in: list[dict], rows_exist: list[dict] | None = None) -> list[dict]:
    rez = []
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
        rez.append(
            {
                "Ordine": int(r.get("Ordine") or r.get("ordine") or idx),
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


def _curata_chei_operatiuni_sesiune() -> None:
    for k in [k for k in list(st.session_state.keys()) if k.startswith("ment_ops_rows_")]:
        del st.session_state[k]


def _init_sau_reseteaza_ment_draft(tehnician_def: str) -> None:
    st.session_state["ment_draft"] = {
        "sel_firma": "-- Alege firma --",
        "sel_masina": "-- Alege mașina --",
        "data_interventie": date.today(),
        "punct_lucru": "",
        "producator_model": "",
        "serie_fabricatie": "",
        "nr_inventar": "",
        "ore_functionare": "",
        "ore_cumulate": "",
        "nivel_grila": "Nivel A – Multimarcă (<20h)",
        "stare_initiala": "Funcțional",
        "stare_finala": "Funcțional (parametri nominali)",
        "recomandari_iiot": "",
        "tehnician": tehnician_def,
        "verificator": "Client",
        "functie_verificator": "",
        "ultima_firma": "-- Alege firma --",
        "ultima_masina": "-- Alege mașina --",
        "edit_rec_id": None,
        "edit_nr_fisa": "",
        "operatiuni_rows": [],
    }
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _incarca_fisa_din_istoric_pentru_editare(fisa: dict, firme_dict: dict) -> None:
    rows_salvate = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
    firma_nume = str(fisa.get("firma_nume") or "-- Alege firma --")
    if firma_nume not in firme_dict:
        firma_nume = "-- Alege firma --"

    data_raw = str(fisa.get("data_interventie") or "")[:10]
    try:
        data_int = date.fromisoformat(data_raw) if data_raw else date.today()
    except Exception:
        data_int = date.today()

    st.session_state["ment_draft"] = {
        "sel_firma": firma_nume,
        "sel_masina": str(fisa.get("masina_nume") or "-- Alege mașina --"),
        "data_interventie": data_int,
        "punct_lucru": str(fisa.get("punct_lucru") or ""),
        "producator_model": str(fisa.get("producator_model") or ""),
        "serie_fabricatie": str(fisa.get("serie_fabricatie") or ""),
        "nr_inventar": str(fisa.get("nr_inventar") or ""),
        "ore_functionare": str(fisa.get("ore_functionare") or ""),
        "ore_cumulate": str(fisa.get("ore_cumulate") or ""),
        "nivel_grila": str(fisa.get("nivel_grila") or "Nivel A – Multimarcă (<20h)"),
        "stare_initiala": str(fisa.get("stare_initiala") or "Funcțional"),
        "stare_finala": str(fisa.get("stare_finala") or "Funcțional (parametri nominali)"),
        "recomandari_iiot": str(fisa.get("recomandari_iiot") or ""),
        "tehnician": str(fisa.get("tehnician") or "Tehnician Nexus"),
        "verificator": str(fisa.get("verificator") or "Client"),
        "functie_verificator": str(fisa.get("functie_verificator") or ""),
        "ultima_firma": firma_nume,
        "ultima_masina": str(fisa.get("masina_nume") or "-- Alege mașina --"),
        "edit_rec_id": fisa.get("id"),
        "edit_nr_fisa": str(fisa.get("nr_fisa") or ""),
        "operatiuni_rows": rows_salvate,
    }
    if fisa.get("frecventa") in FRECVENTE_MENTENANTA:
        st.session_state["ment_frec_selectata"] = str(fisa.get("frecventa"))
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _render_tabel_operatiuni_identic(rows: list[dict], key_prefix: str, editable: bool):
    df_init = (
        pd.DataFrame([{c: r.get(c, "") for c in _COLS_VIZ_OPERATIUNI} for r in rows])
        if rows
        else pd.DataFrame(columns=_COLS_VIZ_OPERATIUNI)
    )

    return st.data_editor(
        df_init,
        hide_index=True,
        num_rows="dynamic" if editable else "fixed",
        use_container_width=True,
        disabled=[] if editable else _COLS_VIZ_OPERATIUNI,
        column_config={
            "Ordine": st.column_config.NumberColumn("Ordine", width="small", step=1),
            "Operațiune / Verificare": st.column_config.TextColumn("Operațiune / Verificare", width="large"),
            "Denumire parametru": st.column_config.TextColumn("Denumire parametru", width="medium"),
            "Valoare": st.column_config.TextColumn("Valoare", width="small"),
            "UM": st.column_config.TextColumn("UM", width="small"),
            "Piese necesare": st.column_config.TextColumn("Piese necesare", width="medium"),
            "Materiale consumabile": st.column_config.TextColumn("Materiale consumabile", width="medium"),
            "Documentație": st.column_config.TextColumn("Documentație", width="medium"),
            "Efectuat": st.column_config.CheckboxColumn("Efectuat", width="small"),
        },
        key=key_prefix,
    )


def _render_sectiune_operatiuni(
    masina_obj: dict,
    firma_nume: str,
    data_interv: date,
    is_unlocked: bool,
    frecventa_init: str,
    nr_fisa_curent: str,
):
    mid = masina_obj["id"]
    den_masina = str(masina_obj.get("denumire") or "").strip()
    tip_masina = str(masina_obj.get("tip_masina") or "").strip()

    frec_curr = st.session_state.get("ment_frec_selectata")
    if frec_curr not in FRECVENTE_MENTENANTA:
        frec_curr = frecventa_init if frecventa_init in FRECVENTE_MENTENANTA else "Lunară"

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

    rows_curente = list(st.session_state[rows_key] or [])

    if is_unlocked:
        catalog_db = incarca_catalog_operatiuni_db()
        st.markdown("#### 📎 Încarcă / Setează operațiune, parametri, piese necesare, consumabile și documentații")
        opt_cat = {"-- Introdu manual / copy-paste --": None}
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

        if st.button("➕ Adaugă operațiunea în tabel", key=f"ment_btn_add_op_{b_key}"):
            if not op_noua:
                st.warning("Selectează sau introdu o operațiune.")
            else:
                if salveaza_db and item_cat is None:
                    adauga_operatiune_in_catalog_db(
                        sistem="Personalizat",
                        operatiune=op_noua,
                        parametru=prm_nou,
                        valoare=val_nou,
                        um=um_nou,
                        piese=piese_op,
                        consumabile=cons_op,
                        documentatii=docs_op,
                    )
                rows_curente.append(
                    {
                        "Ordine": len(rows_curente) + 1,
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
                st.session_state[rows_key] = rows_curente
                reseteaza_builder_resurse_operatiune(b_key)
                st.toast("✅ Operațiunea a fost adăugată.")
                st.rerun()

        if rows_curente:
            st.markdown("#### 🗑️ Ștergere una sau mai multe operațiuni deodată")
            opt_del = {
                f"{i+1}. {str(r.get('Operațiune / Verificare') or '')[:85]}": i
                for i, r in enumerate(rows_curente)
            }
            de_sters = st.multiselect(
                "Selectează operațiunile de șters",
                options=list(opt_del.keys()),
                key=f"ment_ms_del_ops_{mid}",
            )
            if st.button("🗑️ Șterge operațiunile selectate", key=f"ment_btn_del_ops_{mid}"):
                if not de_sters:
                    st.warning("Selectează cel puțin o operațiune.")
                else:
                    indici_sters = {opt_del[k] for k in de_sters}
                    ramase = []
                    for r_item in [item for idx_r, item in enumerate(rows_curente) if idx_r not in indici_sters]:
                        copie = dict(r_item)
                        copie["Ordine"] = len(ramase) + 1
                        ramase.append(copie)
                    st.session_state[rows_key] = ramase
                    st.toast(f"🗑️ Au fost șterse {len(indici_sters)} operațiuni.")
                    st.rerun()
    else:
        st.warning("dacă vrei să editezi fișele de întreținere deblochează sistemul")

    df_ed = _render_tabel_operatiuni_identic(
        rows=rows_curente,
        key_prefix=f"ment_ed_ops_table_{mid}_{st.session_state.get('ment_counter', 0)}",
        editable=is_unlocked,
    )

    if is_unlocked and df_ed is not None:
        st.session_state[rows_key] = _normalizare_randuri_operatiuni(
            df_ed.fillna("").to_dict(orient="records"),
            rows_exist=rows_curente,
        )

    toate_linkurile = []
    for r in (st.session_state[rows_key] or []):
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


def _construieste_payload_pdf_fisa(fisa: dict, ops_hist: list[dict], titlu_pdf_hist: str, frec_hist: str, tip_hist: str, nr_fisa: str) -> dict:
    payload = dict(fisa)
    payload["operatiuni"] = ops_hist
    payload["titlu_pdf_operatiuni"] = titlu_pdf_hist
    payload["checklist_json"] = {
        "fisa_specifica_utilaj": {
            "titlu": construieste_nume_fisa_masina(fisa.get("masina_nume") or "", tip_hist, frec_hist),
            "titlu_pdf": titlu_pdf_hist,
            "frecventa": frec_hist,
            "nr_fisa": nr_fisa,
            "randuri": ops_hist,
        }
    }
    return payload


def render_mentenanta():
    st.subheader("🛡️ Fișă de Mentenanță Preventivă & Audit Tehnic")
    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    setari = SetariRepository.get_setari()
    tehnician_def = setari.get("tehnician_implicit") or "Tehnician Nexus"

    st.session_state.setdefault("ment_salvat", False)
    st.session_state.setdefault("ment_pdf_bytes", None)
    st.session_state.setdefault("ment_pdf_name", None)
    st.session_state.setdefault("ment_nr_fisa_salvat", None)
    if "ment_draft" not in st.session_state:
        _init_sau_reseteaza_ment_draft(tehnician_def)

    draft = st.session_state["ment_draft"]
    firme_db = FirmeRepository.get_all() or []
    if not firme_db:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în modulul 'Firme'.")
        return
    firme_dict = {f["nume_firma"]: f for f in firme_db}

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
            if st.button("🔄 Resetează formularul", use_container_width=True):
                st.session_state["ment_salvat"] = False
                st.session_state["ment_pdf_bytes"] = None
                st.session_state["ment_pdf_name"] = None
                st.session_state["ment_nr_fisa_salvat"] = None
                _curata_chei_operatiuni_sesiune()
                _init_sau_reseteaza_ment_draft(tehnician_def)
                st.rerun()
        return

    if draft.get("edit_rec_id") is not None:
        st.info(f"✏️ **Editare fișă {draft.get('edit_nr_fisa') or ''}** — operațiunile din fișa salvată sunt încărcate în tabel.")

    opt_firme = ["-- Alege firma --"] + list(firme_dict.keys())
    idx_f = opt_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in opt_firme else 0
    col_id1, col_id2, col_id3 = st.columns(3)
    with col_id1:
        sel_firma = st.selectbox("1. Beneficiar / Client *", options=opt_firme, index=idx_f)
        draft["sel_firma"] = sel_firma

    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Selectează clientul și utilajul pentru a continua.")
        _render_istoric_mentenanta()
        return

    firma_obj = firme_dict[sel_firma]
    if draft.get("ultima_firma") != sel_firma and draft.get("edit_rec_id") is None:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = firma_obj.get("nume_persoana") or "Client"
        draft["punct_lucru"] = firma_obj.get("adresa") or ""
        draft["sel_masina"] = "-- Alege mașina --"
        draft["ultima_masina"] = "-- Alege mașina --"

    masini_db = MasiniRepository.get_by_firma(firma_obj["id"]) or []
    masini_dict = {m["denumire"]: m for m in masini_db}
    opt_masini = ["-- Alege mașina --"] + list(masini_dict.keys())
    idx_m = opt_masini.index(draft["sel_masina"]) if draft.get("sel_masina") in opt_masini else 0

    with col_id2:
        sel_masina = st.selectbox("2. Denumire Echipament / Mașină *", options=opt_masini, index=idx_m)
        draft["sel_masina"] = sel_masina

    with col_id3:
        data_interv = st.date_input("3. Data Intervenției", value=draft.get("data_interventie", date.today()))
        draft["data_interventie"] = data_interv

    if sel_masina == "-- Alege mașina --":
        st.info("ℹ️ Alege utilajul din lista clientului pentru a continua.")
        _render_istoric_mentenanta()
        return

    masina_obj = masini_dict[sel_masina]
    total_int_m = int(masina_obj.get("total_interventii", 0))
    prag_int_m = int(masina_obj.get("prag_interventii", 20))

    if draft.get("ultima_masina") != sel_masina and draft.get("edit_rec_id") is None:
        draft["ultima_masina"] = sel_masina
        draft["producator_model"] = str(masina_obj.get("tip_masina") or "")
        draft["serie_fabricatie"] = str(masina_obj.get("serie") or "")
        draft["nivel_grila"] = (
            "Nivel B – CNC Biglia / Matec / >20h / Inginerie"
            if total_int_m >= prag_int_m
            else "Nivel A – Multimarcă (<20h)"
        )

    tip_int_masina = masina_obj.get("tip_intretinere") or "Lunară"
    interval_din_db = int(masina_obj.get("interval_intretinere_zile") or 0)
    durata_implicita_zile = interval_din_db if interval_din_db > 0 else INTERVALE_ZILE.get(tip_int_masina, 30)

    with st.expander("📋 Date Identificare Echipament & Stare Tehnică", expanded=False):
        d1, d2, d3, d4 = st.columns(4)
        draft["punct_lucru"] = d1.text_input("Punct de Lucru / Oraș", value=str(draft.get("punct_lucru", "")))
        draft["producator_model"] = d2.text_input("Producător / Model", value=str(draft.get("producator_model", "")))
        draft["serie_fabricatie"] = d3.text_input("Serie Fabricație", value=str(draft.get("serie_fabricatie", "")))
        draft["nr_inventar"] = d4.text_input("Nr. Inventar Intern", value=str(draft.get("nr_inventar", "")))

        e1, e2, e3 = st.columns(3)
        draft["ore_functionare"] = e1.text_input("Ore Funcționare Utilaj", value=str(draft.get("ore_functionare", "")), placeholder="ex: 14520")
        draft["ore_cumulate"] = e2.text_input("Ore Cumulate (din 20h)", value=str(draft.get("ore_cumulate", "")), placeholder="ex: 6 / 20")
        opt_grila = [
            "Nivel A – Multimarcă (<20h)",
            "Nivel B – CNC Biglia / Matec / >20h / Inginerie",
        ]
        idx_gr = opt_grila.index(draft["nivel_grila"]) if draft.get("nivel_grila") in opt_grila else 0
        draft["nivel_grila"] = e3.selectbox("Nivel Grilă Aplicabilă", options=opt_grila, index=idx_gr)

        s1, s2, s3 = st.columns(3)
        opt_stare_ini = [
            "Funcțional",
            "Nefuncțional",
            "Degradare moderată",
            "Stare avansată de degradare",
        ]
        idx_si = opt_stare_ini.index(draft["stare_initiala"]) if draft.get("stare_initiala") in opt_stare_ini else 0
        draft["stare_initiala"] = s1.selectbox("Stare Inițială Utilaj", options=opt_stare_ini, index=idx_si)

        opt_stare_fin = [
            "Funcțional (parametri nominali)",
            "Funcțional cu restricții (necesită piese)",
            "Oprit siguranță",
        ]
        idx_sf = opt_stare_fin.index(draft["stare_finala"]) if draft.get("stare_finala") in opt_stare_fin else 0
        draft["stare_finala"] = s2.selectbox("Stare Finală Utilaj", options=opt_stare_fin, index=idx_sf)

        urmatoarea_rev_default = data_interv + timedelta(days=durata_implicita_zile)
        urmatoarea_revizie = s3.date_input(
            f"Următoarea Revizie ({tip_int_masina})",
            value=urmatoarea_rev_default,
        )

    nr_fisa_curent = draft.get("edit_nr_fisa") or _genereaza_nr_fisa_unic()

    with st.expander(f"🛠️ Operațiuni Mentenanță — {sel_masina} ({masina_obj.get('tip_masina') or '-'})", expanded=True):
        df_ops_utilaj, nume_fisa_activa, frec_fisa_activa, _ = _render_sectiune_operatiuni(
            masina_obj=masina_obj,
            firma_nume=sel_firma,
            data_interv=data_interv,
            is_unlocked=is_unlocked,
            frecventa_init=tip_int_masina,
            nr_fisa_curent=nr_fisa_curent,
        )

    st.markdown("---")
    st.markdown("### Recomandări Tehnice, Audit Upgrade / IIoT & Recepție Lucrări")
    draft["recomandari_iiot"] = st.text_area(
        "Constatări suplimentare & Recomandări de modernizare (Retrofit PLC / Senzoristică IIoT / Mentenanță Predictivă)",
        value=str(draft.get("recomandari_iiot", "")),
        height=95,
    )

    r1, r2, r3 = st.columns(3)
    draft["tehnician"] = r1.text_input("Inginer / Tehnician Service", value=str(draft.get("tehnician", tehnician_def)))
    draft["verificator"] = r2.text_input("Reprezentant Beneficiar (Nume & Prenume)", value=str(draft.get("verificator", "")))
    draft["functie_verificator"] = r3.text_input("Funcție Reprezentant Beneficiar", value=str(draft.get("functie_verificator", "")))

    if st.button("💾 Salvează Fișa de Mentenanță & Generează PDF", type="primary", use_container_width=True):
        try:
            rows_key = f"ment_ops_rows_{masina_obj['id']}"
            ops_final = _normalizare_randuri_operatiuni(
                (df_ops_utilaj.fillna("").to_dict(orient="records"))
                if df_ops_utilaj is not None and not df_ops_utilaj.empty
                else (st.session_state.get(rows_key) or []),
                rows_exist=st.session_state.get(rows_key) or [],
            )

            fisa_payload = {
                "firma_id": firma_obj["id"],
                "masina_id": masina_obj["id"],
                "firma_nume": sel_firma,
                "masina_nume": sel_masina,
                "tip_masina": str(masina_obj.get("tip_masina") or "").strip(),
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
                )
            else:
                _, nr_fisa_salvat = _insereaza_fisa_recurenta_db(fisa_payload)

            titlu_pdf_final = construieste_titlu_operatiuni_pdf(
                frecventa=frec_fisa_activa,
                masina=sel_masina,
                tip_masina=str(masina_obj.get("tip_masina") or "").strip(),
                data_str=str(data_interv),
                firma=sel_firma,
                nr_fisa=nr_fisa_salvat,
            )
            fisa_payload["nr_fisa"] = nr_fisa_salvat
            fisa_payload["titlu_pdf_operatiuni"] = titlu_pdf_final
            fisa_payload["checklist_json"] = {
                "fisa_specifica_utilaj": {
                    "titlu": nume_fisa_activa,
                    "titlu_pdf": titlu_pdf_final,
                    "frecventa": frec_fisa_activa,
                    "nr_fisa": nr_fisa_salvat,
                    "randuri": ops_final,
                }
            }

            pdf_bytes = genereaza_pdf_mentenanta(fisa_payload)
            nume_pdf_cur = construieste_nume_fisier_pdf(titlu_pdf_final)

            _curata_chei_operatiuni_sesiune()
            st.session_state["ment_nr_fisa_salvat"] = nr_fisa_salvat
            st.session_state["ment_pdf_bytes"] = pdf_bytes
            st.session_state["ment_pdf_name"] = nume_pdf_cur
            st.session_state["ment_salvat"] = True
            _init_sau_reseteaza_ment_draft(tehnician_def)
            st.rerun()
        except Exception as exc:
            st.error(f"⚠️ Eroare la salvarea fișei / generarea PDF: {exc}")

    _render_istoric_mentenanta()


def _render_istoric_mentenanta():
    st.markdown("---")
    st.subheader("📂 Istoric Fișe de Mentenanță Preventivă")
    fise_salvate = _incarca_fise_recurente_db()
    if not fise_salvate:
        st.info("Nu există încă fișe de mentenanță recurente salvate.")
        return

    firme_dict = {
        str(f.get("nume_firma") or ""): f
        for f in (FirmeRepository.get_all() or [])
        if str(f.get("nume_firma") or "").strip()
    }

    for fisa in fise_salvate:
        rec_id = fisa["id"]
        nr_fisa = str(fisa.get("nr_fisa") or "")
        data_str = str(fisa.get("data_interventie") or "")[:10]
        frec_hist = str(fisa.get("frecventa") or "Lunară")
        tip_hist = str(fisa.get("tip_masina") or fisa.get("producator_model") or "")
        titlu_pdf_hist = str(fisa.get("titlu_pdf") or "").strip() or construieste_titlu_operatiuni_pdf(
            frecventa=frec_hist,
            masina=fisa.get("masina_nume") or "",
            tip_masina=tip_hist,
            data_str=data_str,
            firma=fisa.get("firma_nume") or "",
            nr_fisa=nr_fisa,
        )

        with st.expander(f"🛡️ {nr_fisa} | {fisa.get('firma_nume')} — {fisa.get('masina_nume')} ({frec_hist}) | {data_str}"):
            c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1], vertical_alignment="center")
            with c1:
                st.write(f"**Titlu:** {titlu_pdf_hist}")
                st.write(f"**Nr. fișă:** {nr_fisa} | **Tip mentenanță:** {frec_hist} | **Tehnician:** {fisa.get('tehnician') or '-'}")
            with c2:
                if st.button("✏️ Editează", key=f"edit_ment_rec_{rec_id}", use_container_width=True):
                    _curata_chei_operatiuni_sesiune()
                    _incarca_fisa_din_istoric_pentru_editare(fisa, firme_dict)
                    st.rerun()
            with c3:
                pdf_state_key = f"ment_hist_pdf_{rec_id}"
                nume_pdf_hist = construieste_nume_fisier_pdf(titlu_pdf_hist)
                if st.button("📄 Generează PDF", key=f"prep_ment_rec_{rec_id}", use_container_width=True):
                    ops_hist = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
                    payload_pdf = _construieste_payload_pdf_fisa(fisa, ops_hist, titlu_pdf_hist, frec_hist, tip_hist, nr_fisa)
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
                if st.button("🗑️ Șterge", key=f"del_ment_rec_{rec_id}", use_container_width=True):
                    _sterge_fisa_recurenta_db(rec_id)
                    st.session_state.pop(f"ment_hist_pdf_{rec_id}", None)
                    st.rerun()

            ops_rows = _normalizare_randuri_operatiuni(fisa.get("operatiuni") or [])
            _render_tabel_operatiuni_identic(
                rows=ops_rows,
                key_prefix=f"hist_ops_table_{rec_id}",
                editable=False,
            )