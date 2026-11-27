# ----------------------------------
# -------pages/de_facut.py----------
# ----------------------------------

import datetime
import inspect
import json
import time
import pandas as pd
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
from repositories.setari_repository import SetariRepository
from repositories.taskuri_vizita_repository import (
    OPTIUNI_STARE_TASK_VIZITA,
    TaskuriVizitaRepository,
    formateaza_ora_limita,
    formateaza_termen_complet,
    normalizeaza_stare_task_vizita,
)

# Compatibilitate @st.fragment și st.rerun(scope="app") indiferent de versiunea Streamlit
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None) or (lambda fn: fn)
_RERUN_SUPPORTS_SCOPE = "scope" in inspect.signature(st.rerun).parameters

try:
    from repositories.furnizori_repository import FurnizoriRepository

    _HAS_FURNIZORI_REPO = True
except Exception:
    FurnizoriRepository = None
    _HAS_FURNIZORI_REPO = False

try:
    from repositories.cereri_oferta_repository import (
        OPTIUNI_STATUS_CERERE_OFERTA,
        CereriOfertaRepository,
        normalizeaza_status_cerere_oferta,
    )

    _HAS_CERERI_REPO = True
except Exception:
    OPTIUNI_STATUS_CERERE_OFERTA = [
        "Trimis - aștept",
        "Primită - de făcut către client",
        "Ofertat la client",
        "Închisă",
    ]
    CereriOfertaRepository = None
    _HAS_CERERI_REPO = False

    def normalizeaza_status_cerere_oferta(val):
        s = str(val or "").strip()
        return s if s in OPTIUNI_STATUS_CERERE_OFERTA else "Trimis - aștept"


# ---------------------------------------------------------
# HELPERS & NORMALIZARE
# ---------------------------------------------------------

def _rerun_app(toast_msg: str | None = None) -> None:
    """Forțează rerun la nivel de aplicație (inclusiv din interiorul unui @st.fragment)."""
    if toast_msg:
        st.session_state["df_toast_msg"] = toast_msg
    if _RERUN_SUPPORTS_SCOPE:
        st.rerun(scope="app")
    else:
        st.rerun()


def _clear_fn(fn) -> None:
    if fn is not None and hasattr(fn, "clear"):
        try:
            fn.clear()
        except Exception:
            pass


def _to_float_safe(val, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".")
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def _to_int_or_none(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _norm_text(val) -> str:
    return " ".join(str(val or "").strip().lower().split())


def _extrage_furnizor_piesa(piesa_row: dict) -> str:
    for k in ("furnizor", "nume_furnizor", "furnizor_principal", "supplier", "link_furnizor"):
        val = str(piesa_row.get(k) or "").strip()
        if val:
            return val
    return "Fără furnizor setat"


def _extrage_piese_inlocuitoare(row_dict: dict) -> str:
    for k in ("piese_inlocuitoare", "echivalente", "cod_echivalent", "piese_echivalente", "inlocuitor"):
        val = str(row_dict.get(k) or "").strip()
        if val:
            return val
    return "-"


def _extrage_link_gdrive(piesa_row: dict, link_global: str = "") -> str:
    if link_global and link_global.startswith(("http://", "https://")):
        return link_global
    for k in ("link_gdrive", "gdrive_url", "gdrive_link", "url_documentatie", "documentatie_url", "link_doc"):
        val = str(piesa_row.get(k) or "").strip()
        if val.startswith(("http://", "https://")):
            return val
    return ""


def _parse_json_list(raw_val) -> list:
    if not raw_val:
        return []
    if isinstance(raw_val, list):
        return raw_val
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


# ---------------------------------------------------------
# DATA ACCESS & REPOSITORY ADAPTERS (SQL IZOLAT DE UI)
# ---------------------------------------------------------

class _DeFacutDataAdapter:
    """
    Izolează operațiile SQL care nu au încă metodă dedicată în repository-uri.
    Poate fi mutat direct în repository-urile corespunzătoare fără a atinge UI-ul.
    """

    @staticmethod
    def fetch_reparatii_electronice_recente(limit: int = 500) -> list[dict]:
        try:
            with db_cursor() as c:
                c.execute(
                    """
                    SELECT id, firma_nume, masina_nume, piesa_subansamblu, componente_json
                    FROM reparatii_electronice
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
                return [dict(row) for row in (c.fetchall() or [])]
        except Exception:
            return []

    @staticmethod
    def update_stare_in_raport_json(tabela: str, record_id: int, den_piesa: str, stare_noua: str) -> bool:
        if tabela not in ("reparatii", "reparatii_electronice"):
            return False
        camp_json = "piese_json" if tabela == "reparatii" else "componente_json"
        den_target = _norm_text(den_piesa)
        if not den_target:
            return False

        def _get_item_norm(it: dict) -> str:
            return _norm_text(
                it.get("Componenta / Cod / Parametri")
                or it.get("Componenta")
                or it.get("Piesa")
                or it.get("piesa")
                or it.get("denumire")
            )

        with db_cursor() as c:
            c.execute(f"SELECT {camp_json} FROM {tabela} WHERE id = %s", (int(record_id),))
            row = c.fetchone() or {}
            if not isinstance(row, dict):
                row = dict(row)
            items = _parse_json_list(row.get(camp_json))
            if not items:
                return False

            exact_matches = [it for it in items if isinstance(it, dict) and _get_item_norm(it) == den_target]
            targets = exact_matches if exact_matches else [
                it for it in items
                if isinstance(it, dict) and (den_target in _get_item_norm(it) or _get_item_norm(it) in den_target)
            ]
            if not targets:
                return False

            for item in targets:
                if tabela == "reparatii_electronice":
                    item["Stare"] = stare_noua
                else:
                    item["Tip"] = stare_noua
                item["stare_comandata"] = stare_noua

            c.execute(
                f"UPDATE {tabela} SET {camp_json} = %s WHERE id = %s",
                (json.dumps(items, ensure_ascii=False), int(record_id)),
            )
        return True

    @staticmethod
    def fetch_linii_cereri_batch(cereri_ids: list[int]) -> dict[int, list[dict]]:
        linii_by_cid: dict[int, list[dict]] = {int(cid): [] for cid in cereri_ids}
        if not cereri_ids:
            return linii_by_cid

        if hasattr(CereriOfertaRepository, "get_linii_by_cereri_ids"):
            try:
                return CereriOfertaRepository.get_linii_by_cereri_ids(cereri_ids) or linii_by_cid
            except Exception:
                pass

        try:
            with db_cursor() as c:
                c.execute(
                    """
                    SELECT *
                    FROM cereri_oferta_linii
                    WHERE cerere_id = ANY(%s)
                    ORDER BY id ASC
                    """,
                    (cereri_ids,),
                )
                for r in (c.fetchall() or []):
                    row_d = dict(r)
                    cid_r = _to_int_or_none(row_d.get("cerere_id"))
                    if cid_r in linii_by_cid:
                        linii_by_cid[cid_r].append(row_d)
                return linii_by_cid
        except Exception:
            for cid in cereri_ids:
                try:
                    linii_by_cid[cid] = CereriOfertaRepository.get_linii_by_cerere(cid) or []
                except Exception:
                    linii_by_cid[cid] = []
            return linii_by_cid

    @staticmethod
    def insert_linie_cerere_rfq(cerere_id: int, linie: dict) -> None:
        if hasattr(CereriOfertaRepository, "adauga_linie_cerere"):
            CereriOfertaRepository.adauga_linie_cerere(int(cerere_id), linie)
            return
        if hasattr(CereriOfertaRepository, "insert_linie"):
            CereriOfertaRepository.insert_linie(int(cerere_id), linie)
            return

        with db_cursor() as c:
            c.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cereri_oferta_linii'
                """
            )
            cols_db = {
                (r["column_name"] if isinstance(r, dict) else r[0])
                for r in (c.fetchall() or [])
            }
            if not cols_db:
                return

            valori = {
                "cerere_id": int(cerere_id),
                "piesa_id": linie.get("piesa_id"),
                "furnizor_nume": str(linie.get("furnizor_nume") or "").strip(),
                "denumire_piesa": str(linie.get("denumire_piesa") or "").strip(),
                "cod_producator": str(linie.get("cod_producator") or "").strip(),
                "piese_inlocuitoare": str(linie.get("piese_inlocuitoare") or "").strip(),
                "cantitate": _to_float_safe(linie.get("cantitate"), 1.0),
                "pret_unitar": _to_float_safe(linie.get("pret_unitar"), 0.0),
                "moneda": str(linie.get("moneda") or "EUR").strip().upper(),
                "termen_livrare_zile": str(linie.get("termen_livrare_zile") or "").strip(),
                "selectat_pentru_client": bool(linie.get("selectat_pentru_client", False)),
            }
            cols_ins = [k for k in valori.keys() if k in cols_db]
            placeholders = ", ".join(["%s"] * len(cols_ins))
            c.execute(
                f"INSERT INTO cereri_oferta_linii ({', '.join(cols_ins)}) VALUES ({placeholders})",
                tuple(valori[k] for k in cols_ins),
            )

    @staticmethod
    def fetch_memento_intretinere(zile: int) -> list[dict]:
        if hasattr(MasiniRepository, "get_intretineri_scadente"):
            try:
                return MasiniRepository.get_intretineri_scadente(zile) or []
            except Exception:
                pass

        try:
            with db_cursor() as c:
                c.execute(
                    """
                    SELECT
                        m.id,
                        COALESCE(NULLIF(TRIM(f.nume_firma), ''), 'Fără firmă') AS firma,
                        m.denumire AS utilaj,
                        CAST(m.data_intretinere AS DATE) AS data_scadenta,
                        (CAST(m.data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                    FROM masini m
                    LEFT JOIN firme f ON f.id = m.firma_id
                    WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                      AND m.data_intretinere IS NOT NULL
                      AND CAST(m.data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                    ORDER BY CAST(m.data_intretinere AS DATE) ASC, firma ASC, m.denumire ASC
                    """,
                    (zile,),
                )
                return [dict(r) for r in (c.fetchall() or [])]
        except Exception:
            with db_cursor() as c:
                c.execute(
                    """
                    SELECT
                        id,
                        'Fără firmă' AS firma,
                        denumire AS utilaj,
                        CAST(data_intretinere AS DATE) AS data_scadenta,
                        (CAST(data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                    FROM masini
                    WHERE COALESCE(fara_intretinere, FALSE) = FALSE
                      AND data_intretinere IS NOT NULL
                      AND CAST(data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                    ORDER BY CAST(data_intretinere AS DATE) ASC, denumire ASC
                    """,
                    (zile,),
                )
                return [dict(r) for r in (c.fetchall() or [])]


# ---------------------------------------------------------
# CACHE QUERIES
# ---------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _obtine_link_gdrive_setari() -> str:
    try:
        setari = SetariRepository.get_setari() or {}
    except Exception:
        setari = {}
    link = str(setari.get("locatie_documentatii_gdrive") or "").strip()
    return link if link.startswith(("http://", "https://")) else ""


@st.cache_data(ttl=180, show_spinner=False)
def _obtine_harta_firme_cached() -> tuple[list[str], dict[str, int]]:
    firme_all = FirmeRepository.get_all() or []
    nume_to_id: dict[str, int] = {}
    for f in firme_all:
        nume = str(f.get("nume_firma") or "").strip()
        fid = _to_int_or_none(f.get("id"))
        if nume and fid is not None:
            nume_to_id[nume] = fid
    return sorted(nume_to_id.keys()), nume_to_id


@st.cache_data(ttl=180, show_spinner=False)
def _obtine_masini_cached() -> list[dict]:
    return MasiniRepository.get_all() or []


@st.cache_data(ttl=120, show_spinner=False)
def _obtine_taskuri_cached() -> list[dict]:
    return TaskuriVizitaRepository.get_all() or []


@st.cache_data(ttl=120, show_spinner=False)
def _obtine_necesar_piese_cached() -> list[dict]:
    return NecesarPieseRepository.get_all() or []


@st.cache_data(ttl=300, show_spinner=False)
def _obtine_furnizori_cunoscuti_cached() -> list[str]:
    nume_set: set[str] = set()
    if _HAS_FURNIZORI_REPO and FurnizoriRepository is not None:
        try:
            for fn in FurnizoriRepository.get_active_names():
                if fn:
                    nume_set.add(str(fn).strip())
        except Exception:
            pass
    try:
        for p in (PieseRepository.get_all() or []):
            fn_p = _extrage_furnizor_piesa(p)
            if fn_p and fn_p != "Fără furnizor setat":
                nume_set.add(fn_p)
    except Exception:
        pass
    return sorted(nume_set, key=lambda x: x.lower())


@st.cache_data(ttl=120, show_spinner=False)
def _obtine_cereri_cu_detalii_cached() -> list[dict]:
    if not _HAS_CERERI_REPO or CereriOfertaRepository is None:
        return []

    cereri_raw = CereriOfertaRepository.get_cereri() or []
    if not cereri_raw:
        return []

    cereri_ids = [int(c["id"]) for c in cereri_raw if _to_int_or_none(c.get("id")) is not None]
    linii_by_cid = _DeFacutDataAdapter.fetch_linii_cereri_batch(cereri_ids)

    rezultat: list[dict] = []
    for c in cereri_raw:
        item = dict(c)
        cid = _to_int_or_none(item.get("id"))
        linii = linii_by_cid.get(cid, []) if cid is not None else []
        piese_lista: list[str] = []
        furn_lista: list[str] = []

        for l in linii:
            den_p = str(l.get("denumire_piesa") or "").strip()
            cod_p = str(l.get("cod_producator") or "").strip()
            lbl_p = f"{den_p} [{cod_p}]" if den_p and cod_p else (den_p or cod_p)
            if lbl_p and lbl_p not in piese_lista:
                piese_lista.append(lbl_p)
            fn_l = str(l.get("furnizor_nume") or "").strip()
            if fn_l and fn_l not in furn_lista:
                furn_lista.append(fn_l)

        item["_linii"] = linii
        item["_piese_str"] = ", ".join(piese_lista) if piese_lista else "-"
        item["_furnizori_str"] = ", ".join(furn_lista) if furn_lista else "-"
        item["_furnizori_set"] = {x.lower() for x in furn_lista if x}
        rezultat.append(item)

    return rezultat


@st.cache_data(ttl=300, show_spinner=False)
def _incarca_optiuni_lookup_piese():
    piese_catalog = PieseRepository.get_all() or []
    optiuni = ["✍️ Piesă nouă (scriu manual)"]
    detalii = {}
    vazute = set()

    for p in piese_catalog:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or "").strip()
        mas = str(p.get("masina_montaj") or "").strip()
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + (f" ({mas})" if mas and mas != "General" else "")
        if eticheta in vazute:
            continue
        vazute.add(eticheta)
        optiuni.append(eticheta)
        detalii[eticheta] = {
            "piesa_id": p.get("id"),
            "denumire": den,
            "cod_producator": cod,
            "piese_inlocuitoare": _extrage_piese_inlocuitoare(p),
        }

    return optiuni, detalii


@st.cache_data(ttl=180, show_spinner=False)
def incarca_memento_intretinere(zile_inainte: int = 14):
    return _DeFacutDataAdapter.fetch_memento_intretinere(max(0, int(zile_inainte)))


def _goleste_cache_taskuri():
    _clear_fn(_obtine_taskuri_cached)
    _clear_fn(_colecteaza_piese_necesare)
    _clear_fn(getattr(TaskuriVizitaRepository, "get_all", None))


def _goleste_cache_piese_si_rfq():
    _clear_fn(_colecteaza_piese_necesare)
    _clear_fn(_obtine_necesar_piese_cached)
    _clear_fn(_incarca_optiuni_lookup_piese)
    _clear_fn(_obtine_furnizori_cunoscuti_cached)
    _clear_fn(_obtine_cereri_cu_detalii_cached)
    for repo in (PieseRepository, NecesarPieseRepository, ReparatiiRepository, CereriOfertaRepository, FurnizoriRepository):
        if repo is None:
            continue
        for method_name in ("get_all", "get_active_names", "get_recente_pentru_piese", "get_cereri", "get_linii_by_cerere", "get_linii_by_cereri_ids"):
            _clear_fn(getattr(repo, method_name, None))


def _goleste_cache_de_facut():
    _clear_fn(incarca_memento_intretinere)
    _clear_fn(_obtine_link_gdrive_setari)
    _goleste_cache_taskuri()
    _goleste_cache_piese_si_rfq()
    _clear_fn(_obtine_harta_firme_cached)
    _clear_fn(_obtine_masini_cached)
    _clear_fn(getattr(SetariRepository, "get_setari", None))

    for repo in (FirmeRepository, MasiniRepository):
        for method_name in ("get_all", "get_by_firma", "get_intretineri_scadente"):
            _clear_fn(getattr(repo, method_name, None))


# ---------------------------------------------------------
# OPERAȚII SCRIERE & COLECTARE PIESE
# ---------------------------------------------------------

def _salveaza_modificari_piese(
    df_orig_rows: list[dict],
    edited_df: pd.DataFrame,
    col_prio: str,
    col_status: str,
) -> tuple[int, list[str]]:
    """
    Salvează modificările de prioritate și status comandă din orice data_editor de piese.
    Returnează (nr_modificate, lista_erori).
    """
    meta_map = {}
    orig_status_map = {}
    orig_prio_map = {}

    for r in df_orig_rows:
        rid = int(r["_row_id"])
        meta_map[rid] = {
            "_necesar_id": _to_int_or_none(r.get("_necesar_id")),
            "_piesa_id": _to_int_or_none(r.get("_piesa_id")),
            "_sursa_tbl": str(r.get("_sursa_tbl") or "").strip(),
            "_sursa_rec_id": _to_int_or_none(r.get("_sursa_rec_id")),
            "Piesă": str(r.get("Piesă") or ""),
        }
        orig_status_map[rid] = _normalizeaza_stare_comanda(r.get(col_status))
        orig_prio_map[rid] = normalizeaza_prioritate_piesa(r.get(col_prio))

    nr_mod = 0
    erori_salvare: list[str] = []

    for _, row in edited_df.iterrows():
        rid = int(row["_row_id"])
        stare_noua = _normalizeaza_stare_comanda(row.get(col_status))
        stare_veche = orig_status_map.get(rid)
        prio_noua = normalizeaza_prioritate_piesa(row.get(col_prio))
        prio_veche = orig_prio_map.get(rid)

        if stare_veche == stare_noua and prio_veche == prio_noua:
            continue

        meta = meta_map.get(rid) or {}
        salvat_ceva = False
        sursa_tbl = str(meta.get("_sursa_tbl") or "").strip()
        den_piesa = meta.get("Piesă") or str(row.get("Piesă") or "")

        necesar_id = meta.get("_necesar_id")
        if sursa_tbl == "necesar_piese" and necesar_id is not None:
            try:
                if stare_veche != stare_noua:
                    NecesarPieseRepository.update_status_comanda(necesar_id, stare_noua)
                if prio_veche != prio_noua:
                    NecesarPieseRepository.update_prioritate_piesa(necesar_id, prio_noua)
                salvat_ceva = True
            except Exception as e:
                erori_salvare.append(f"Necesar #{necesar_id} ({den_piesa}): {e}")

        piesa_id = meta.get("_piesa_id")
        if piesa_id is not None and stare_veche != stare_noua:
            try:
                PieseRepository.update_stare_comandata(piesa_id, stare_noua)
                salvat_ceva = True
            except Exception as e:
                erori_salvare.append(f"Piesa #{piesa_id} ({den_piesa}): {e}")

        sursa_rec_id = meta.get("_sursa_rec_id")
        if sursa_tbl in ("reparatii", "reparatii_electronice") and sursa_rec_id is not None and stare_veche != stare_noua:
            try:
                if _DeFacutDataAdapter.update_stare_in_raport_json(sursa_tbl, sursa_rec_id, den_piesa, stare_noua):
                    salvat_ceva = True
            except Exception as e:
                erori_salvare.append(f"{sursa_tbl} #{sursa_rec_id} ({den_piesa}): {e}")

        if salvat_ceva:
            nr_mod += 1

    return nr_mod, erori_salvare


def _salveaza_toate_ofertele_cerere_rfq(cerere_id: int, df_lin_edit: pd.DataFrame) -> None:
    linii_existente: list[dict] = []
    linii_noi: list[dict] = []

    for _, r in df_lin_edit.iterrows():
        den_p = str(r.get("Piesă") or "").strip()
        if not den_p:
            continue
        lid = _to_int_or_none(r.get("id"))
        mon = str(r.get("Monedă") or "EUR").strip().upper()
        if mon not in ("EUR", "RON"):
            mon = "EUR"

        item = {
            "furnizor_nume": str(r.get("Furnizor") or "").strip(),
            "denumire_piesa": den_p,
            "cod_producator": str(r.get("Cod Prod.") or "").strip(),
            "piese_inlocuitoare": str(r.get("Piese înlocuitoare") or "").strip(),
            "cantitate": max(0.01, _to_float_safe(r.get("Cant."), 1.0)),
            "pret_unitar": max(0.0, _to_float_safe(r.get("Preț Unitar"), 0.0)),
            "moneda": mon,
            "termen_livrare_zile": str(r.get("Termen livrare") or "").strip(),
            "selectat_pentru_client": bool(r.get("Selectat Client", False)),
        }
        if lid is not None:
            item["id"] = lid
            linii_existente.append(item)
        else:
            linii_noi.append(item)

    if linii_existente:
        CereriOfertaRepository.salveaza_oferta_primita_furnizor(int(cerere_id), linii_existente)
    for ln_noua in linii_noi:
        _DeFacutDataAdapter.insert_linie_cerere_rfq(int(cerere_id), ln_noua)


@st.cache_data(ttl=120, show_spinner=False)
def _colecteaza_piese_necesare(link_gdrive_global: str = "") -> list[dict]:
    piese_db = PieseRepository.get_all() or []
    catalog_by_key: dict[str, dict] = {}

    for p in piese_db:
        den = str(p.get("denumire") or p.get("nume") or "").strip()
        if den:
            cheie = _norm_text(den)
            catalog_by_key[cheie] = {
                "furnizor": _extrage_furnizor_piesa(p),
                "piesa_id": p.get("id"),
                "stare_catalog": _normalizeaza_stare_comanda(p.get("stare_comandata")),
                "gdrive": _extrage_link_gdrive(p, link_gdrive_global),
                "inloc": _extrage_piese_inlocuitoare(p),
            }

    randuri = []
    idx_counter = 0
    stari_valide_low = {
        "de comandat", "necesara", "necesare",
        "de căutat", "de cautat",
        "de ofertat",
        "comandată", "comandata",
        "în așteptare", "in asteptare",
        "anulată", "anulata",
    }

    # 1. Teren / Necesar
    for np_row in _obtine_necesar_piese_cached():
        den_np = str(np_row.get("denumire_piesa") or "").strip()
        if not den_np:
            continue
        cheie = _norm_text(den_np)
        cat = catalog_by_key.get(cheie, {})

        furnizor_np = str(np_row.get("furnizor_piesa") or "").strip() or cat.get("furnizor", "Fără furnizor setat")
        link_gd = cat.get("gdrive") or _extrage_link_gdrive(np_row, link_gdrive_global)
        piese_inloc_np = _extrage_piese_inlocuitoare(np_row)
        if piese_inloc_np == "-":
            piese_inloc_np = cat.get("inloc", "-")

        idx_counter += 1
        randuri.append({
            "_row_id": idx_counter,
            "_necesar_id": np_row.get("id"),
            "_piesa_id": np_row.get("piesa_id") or cat.get("piesa_id"),
            "_sursa_tbl": "necesar_piese",
            "_sursa_rec_id": np_row.get("id"),
            "Stare Piesă": normalizeaza_prioritate_piesa(np_row.get("prioritate_piesa")),
            "Piesă": den_np,
            "Cantitate": _to_float_safe(np_row.get("cantitate"), 1.0),
            "Status Comandă": _normalizeaza_stare_comanda(np_row.get("status_comanda")),
            "Furnizor": furnizor_np,
            "Sursă": "Teren / Necesar",
            "Firmă": str(np_row.get("firma_client") or "").strip(),
            "Mașină": str(np_row.get("masina") or "").strip() or "-",
            "Piese înlocuitoare": piese_inloc_np,
            "Doc GDrive": link_gd,
            "Raport": f"NP #{np_row.get('id')}",
        })

    def _adauga_din_rapoarte(lista_rapoarte: list[dict], sursa_tbl: str, sursa_eticheta: str, prefix_raport: str):
        nonlocal idx_counter
        for r in lista_rapoarte:
            if sursa_tbl == "reparatii":
                items_raw = r.get("piese_valide") or _parse_json_list(r.get("piese_json"))
                firma_val = r.get("firma") or ""
                masina_val = r.get("masina") or ""
            else:
                items_raw = _parse_json_list(r.get("componente_json"))
                firma_val = r.get("firma_nume") or ""
                masina_val = r.get("masina_nume") or r.get("piesa_subansamblu") or ""

            for item in items_raw:
                if not isinstance(item, dict):
                    continue
                den_p = str(
                    item.get("Componenta / Cod / Parametri")
                    or item.get("Componenta")
                    or item.get("Piesa")
                    or item.get("piesa")
                    or item.get("denumire")
                    or ""
                ).strip()
                if not den_p:
                    continue

                tip_p = str(item.get("Tip") or item.get("tip") or "").strip()
                stare_item = str(item.get("stare_comandata") or item.get("Stare") or tip_p or "").strip()
                if stare_item.lower() not in stari_valide_low and tip_p.lower() not in stari_valide_low:
                    continue

                cheie = _norm_text(den_p)
                cat = catalog_by_key.get(cheie, {})

                if stare_item:
                    stare_curenta = (
                        "De comandat"
                        if stare_item.lower() in ("de comandat", "necesara", "necesare")
                        else _normalizeaza_stare_comanda(stare_item)
                    )
                elif "stare_catalog" in cat:
                    stare_curenta = cat["stare_catalog"]
                else:
                    stare_curenta = "De comandat"

                piese_inloc = _extrage_piese_inlocuitoare(item)
                if piese_inloc == "-":
                    piese_inloc = cat.get("inloc", "-")

                cant_raw = item.get("Cantitate") if item.get("Cantitate") is not None else item.get("cantitate", 1.0)
                idx_counter += 1
                randuri.append({
                    "_row_id": idx_counter,
                    "_necesar_id": None,
                    "_piesa_id": cat.get("piesa_id"),
                    "_sursa_tbl": sursa_tbl,
                    "_sursa_rec_id": r.get("id"),
                    "Stare Piesă": "Normal",
                    "Piesă": den_p,
                    "Cantitate": _to_float_safe(cant_raw, 1.0),
                    "Status Comandă": stare_curenta,
                    "Furnizor": cat.get("furnizor", "Fără furnizor setat"),
                    "Sursă": sursa_eticheta,
                    "Firmă": firma_val,
                    "Mașină": masina_val,
                    "Piese înlocuitoare": piese_inloc,
                    "Doc GDrive": cat.get("gdrive") or link_gdrive_global,
                    "Raport": f"{prefix_raport}#{r.get('id')}",
                })

    # 2. Reparații Mașini
    if hasattr(ReparatiiRepository, "get_recente_pentru_piese"):
        rapoarte = ReparatiiRepository.get_recente_pentru_piese(limit=500) or []
    else:
        rapoarte = ReparatiiRepository.get_all() or []
    _adauga_din_rapoarte(rapoarte, "reparatii", "Mașini", "")

    # 3. Reparații Electronice
    fise_el = _DeFacutDataAdapter.fetch_reparatii_electronice_recente(limit=500)
    _adauga_din_rapoarte(fise_el, "reparatii_electronice", "Electronică", "EL ")

    ord_status = {
        "De comandat": 1,
        "De ofertat": 2,
        "De căutat": 3,
        "În așteptare": 4,
        "Comandată": 5,
        "Anulată": 6,
    }
    randuri.sort(
        key=lambda x: (
            0 if x.get("Stare Piesă") == "Urgent" else 1,
            ord_status.get(x.get("Status Comandă"), 9),
            str(x.get("Firmă") or "").lower(),
            str(x.get("Piesă") or "").lower(),
        )
    )
    return randuri


# ---------------------------------------------------------
# SECȚIUNEA 1: PRIVIRE DE ANSAMBLU (CU EDITARE PIESE PRIORITARE)
# ---------------------------------------------------------

def render_privire_ansamblu_de_facut(piese_rows: list[dict], taskuri: list[dict]):
    taskuri_urgente = [t for t in taskuri if t.get("stare") == "Urgent"]
    taskuri_active = [t for t in taskuri if t.get("stare") != "Finalizat"]

    piese_urgente = [
        p for p in piese_rows
        if p.get("Stare Piesă") == "Urgent" and p.get("Status Comandă") not in ("Comandată", "Anulată")
    ]
    piese_de_comandat = [p for p in piese_rows if p.get("Status Comandă") == "De comandat"]
    piese_de_ofertat = [p for p in piese_rows if p.get("Status Comandă") == "De ofertat"]
    piese_de_cautat = [p for p in piese_rows if p.get("Status Comandă") == "De căutat"]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🚨 Task-uri Urgente", len(taskuri_urgente), delta=f"{len(taskuri_active)} active")
    m2.metric("🔥 Piese Urgente", len(piese_urgente))
    m3.metric("🛒 De comandat", len(piese_de_comandat))
    m4.metric("💶 De ofertat", len(piese_de_ofertat))
    m5.metric("🔎 De căutat", len(piese_de_cautat))

    c_ov1, c_ov2 = st.columns(2, gap="medium")
    with c_ov1:
        st.markdown("##### 🚨 Task-uri Urgente (Vizite Clienți)")
        if taskuri_urgente:
            for t in taskuri_urgente[:8]:
                termen_txt = formateaza_termen_complet(t.get("de_facut_pana_la"), t.get("ora_limita"))
                este_fin = t.get("stare") == "Finalizat"
                strike_style = "text-decoration:line-through;opacity:0.65;" if este_fin else ""
                st.markdown(
                    f"""
                    <div style="background:#FEF2F2;border-left:5px solid #DC2626;padding:8px 12px;margin-bottom:6px;border-radius:4px;{strike_style}">
                        <div style="color:#B91C1C;font-size:1.08rem;font-weight:700;">
                            🚨 {t.get('firma') or '-'} {f"• {t.get('masina')}" if t.get('masina') else ""}
                        </div>
                        <div style="color:#7F1D1D;font-size:1.02rem;margin-top:2px;">{t.get('note_vizita') or ''}</div>
                        <div style="color:#991B1B;font-size:0.92rem;margin-top:2px;">⏰ Până la: <b>{termen_txt}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ Niciun task urgent în așteptare.")

    with c_ov2:
        st.markdown("##### 🔥 Piese Prioritare (Urgent / De ofertat / De căutat)")
        piese_active_ord = [
            p for p in piese_rows
            if p.get("Stare Piesă") == "Urgent" or p.get("Status Comandă") in ("De comandat", "De ofertat", "De căutat")
        ][:12]

        if piese_active_ord:
            df_po = pd.DataFrame([
                {
                    "_row_id": int(p["_row_id"]),
                    "Prioritate": normalizeaza_prioritate_piesa(p.get("Stare Piesă")),
                    "Status": _normalizeaza_stare_comanda(p.get("Status Comandă")),
                    "Piesă": p.get("Piesă"),
                    "Cant.": p.get("Cantitate"),
                    "Firmă": p.get("Firmă") or "-",
                    "Doc GDrive": p.get("Doc GDrive") if str(p.get("Doc GDrive") or "").startswith(("http://", "https://")) else None,
                }
                for p in piese_active_ord
            ])

            ver_po = st.session_state.get("df_editor_piese_prio_ver", 0)
            edited_po = st.data_editor(
                df_po,
                key=f"df_editor_piese_prioritare_v{ver_po}",
                hide_index=True,
                num_rows="fixed",
                use_container_width=True,
                disabled=["_row_id", "Piesă", "Cant.", "Firmă", "Doc GDrive"],
                column_config={
                    "_row_id": None,
                    "Prioritate": st.column_config.SelectboxColumn(
                        "Prioritate",
                        options=OPTIUNI_PRIORITATE_PIESA,
                        required=True,
                        width="small",
                    ),
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        options=OPTIUNI_STARE_COMANDA,
                        required=True,
                        width="medium",
                    ),
                    "Piesă": st.column_config.TextColumn("Piesă", width="medium"),
                    "Cant.": st.column_config.NumberColumn("Cant.", format="%.2f", width="small"),
                    "Firmă": st.column_config.TextColumn("Firmă", width="small"),
                    "Doc GDrive": st.column_config.LinkColumn("Doc GDrive", display_text="📂 GDrive", width="small"),
                },
            )

            if st.button("💾 Salvează Piese Prioritare", type="primary", key="btn_df_save_piese_prioritare"):
                nr_mod_po, erori_po = _salveaza_modificari_piese(
                    df_orig_rows=piese_active_ord,
                    edited_df=edited_po,
                    col_prio="Prioritate",
                    col_status="Status",
                )
                if nr_mod_po > 0:
                    _goleste_cache_piese_si_rfq()
                    st.session_state["df_editor_stare_piese_ver"] = st.session_state.get("df_editor_stare_piese_ver", 0) + 1

                if erori_po:
                    st.error("⚠️ Au apărut erori la salvare:\n" + "\n".join(erori_po))
                elif nr_mod_po == 0:
                    st.info("ℹ️ Nu există modificări nesalvate la piesele prioritare.")
                else:
                    st.session_state["df_editor_piese_prio_ver"] = ver_po + 1
                    _rerun_app(f"✅ Actualizate {nr_mod_po} piese prioritare.")
        else:
            st.success("✅ Nicio piesă în așteptare.")


# ---------------------------------------------------------
# SECȚIUNEA 2: NOTIȚE & TASK-URI VIZITĂ
# ---------------------------------------------------------

def _on_nota_firma_change():
    st.session_state["df_nota_masina_sel"] = "-- Fără mașină (opțional) --"


def _randeaza_lista_carduri_taskuri(task_list: list[dict], nivel: str):
    if nivel == "urgent":
        bg, border, text_col, badge = "#FEF2F2", "#DC2626", "#991B1B", "🚨 URGENT"
    elif nivel == "finalizat":
        bg, border, text_col, badge = "#F3F4F6", "#6B7280", "#4B5563", "✅ FINALIZAT"
    else:
        bg, border, text_col, badge = "#FEF9C3", "#D97706", "#854D0E", "🟡 NORMAL"

    for t in task_list:
        tid = int(t["id"])
        termen_str = formateaza_termen_complet(t.get("de_facut_pana_la"), t.get("ora_limita"))
        masina_str = f" — <i>{t.get('masina')}</i>" if t.get("masina") else ""
        este_fin = t.get("stare") == "Finalizat"
        nota_css = "text-decoration:line-through;opacity:0.75;" if este_fin else ""

        c_card, c_done, c_del = st.columns([6.2, 1.1, 0.9], vertical_alignment="center")
        with c_card:
            st.markdown(
                f"""
                <div style="background:{bg};border-left:5px solid {border};padding:10px 14px;border-radius:6px;margin-bottom:6px;">
                    <div style="color:{text_col};font-size:1.05rem;font-weight:700;{nota_css}">
                        {badge} • {t.get('firma') or '-'}{masina_str}
                    </div>
                    <div style="color:{text_col};font-size:1.0rem;margin-top:4px;{nota_css}">
                        {t.get('note_vizita') or ''}
                    </div>
                    <div style="color:{text_col};font-size:0.86rem;opacity:0.9;margin-top:4px;">
                        📅 Vizită: {str(t.get('data_vizita') or '')[:10]} &nbsp;|&nbsp;
                        ⏰ Termen: <b>{termen_str}</b> &nbsp;|&nbsp;
                        Stare: <b>{t.get('stare')}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_done:
            if not este_fin and st.button("✅ Completed", key=f"btn_done_task_{nivel}_{tid}", use_container_width=True):
                if hasattr(TaskuriVizitaRepository, "mark_completed"):
                    TaskuriVizitaRepository.mark_completed(tid)
                else:
                    TaskuriVizitaRepository.update(
                        tid,
                        str(t.get("note_vizita") or ""),
                        "Finalizat",
                        de_facut_pana_la=t.get("de_facut_pana_la"),
                    )
                _goleste_cache_taskuri()
                _rerun_app("✅ Task marcat ca Finalizat.")
        with c_del:
            if st.button("🗑️ Șterge", key=f"btn_del_task_{nivel}_{tid}", use_container_width=True):
                TaskuriVizitaRepository.delete(tid)
                _goleste_cache_taskuri()
                _rerun_app("🗑️ Task șters.")


def render_notite_vizita_de_facut(taskuri: list[dict]):
    with st.expander("📋 Notițe & Task-uri Vizită Client", expanded=True):
        firme_nume, nume_to_id = _obtine_harta_firme_cached()
        masini_all = _obtine_masini_cached()

        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            cf1, cf2 = st.columns([1.5, 1.5])
            with cf1:
                firma_viz = st.selectbox(
                    "Firmă (Client) *",
                    options=firme_nume,
                    key="df_nota_firma_sel",
                    on_change=_on_nota_firma_change,
                )
            fid_viz = nume_to_id.get(firma_viz)
            masini_firma_v = [
                str(m.get("denumire") or "").strip()
                for m in masini_all
                if str(m.get("denumire") or "").strip() and (fid_viz is None or m.get("firma_id") == fid_viz)
            ]
            opt_masini_viz = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma_v))
            cur_mas_viz = st.session_state.get("df_nota_masina_sel", "-- Fără mașină (opțional) --")
            idx_mas_viz = opt_masini_viz.index(cur_mas_viz) if cur_mas_viz in opt_masini_viz else 0

            with cf2:
                masina_viz = st.selectbox(
                    "Mașină (opțional)",
                    options=opt_masini_viz,
                    index=idx_mas_viz,
                    key="df_nota_masina_sel",
                )

            with st.form("form_adauga_notita_vizita_df", clear_on_submit=True):
                cn1, cn2, cn3, cn4 = st.columns([1.15, 1.25, 1.0, 1.3], vertical_alignment="bottom")
                with cn1:
                    data_viz = st.date_input("Data vizitei *", value=datetime.date.today())
                with cn2:
                    de_facut_pana = st.date_input(
                        "De făcut până la *",
                        value=datetime.date.today() + datetime.timedelta(days=3),
                    )
                with cn3:
                    ora_limita_inp = st.time_input("Ora due date", value=datetime.time(17, 0))
                with cn4:
                    stare_viz = st.selectbox("Stare *", options=OPTIUNI_STARE_TASK_VIZITA, index=0)

                note_viz = st.text_area(
                    "Note de vizită *",
                    placeholder="ex: De verificat senzor presiune linie 2, de proiectat suport motor...",
                    height=110,
                )
                salveaza_nota = st.form_submit_button("💾 Salvează Notița", type="primary")

            if salveaza_nota:
                try:
                    try:
                        TaskuriVizitaRepository.insert(
                            data_vizita=data_viz,
                            de_facut_pana_la=de_facut_pana,
                            ora_limita=ora_limita_inp,
                            firma=firma_viz,
                            firma_id=fid_viz,
                            masina=masina_viz,
                            note_vizita=note_viz,
                            stare=stare_viz,
                        )
                    except TypeError:
                        TaskuriVizitaRepository.insert(
                            data_vizita=data_viz,
                            de_facut_pana_la=de_facut_pana,
                            firma=firma_viz,
                            firma_id=fid_viz,
                            masina=masina_viz,
                            note_vizita=note_viz,
                            stare=stare_viz,
                        )
                    _goleste_cache_taskuri()
                    _rerun_app(f"✅ Notiță salvată pentru {firma_viz} ({stare_viz}).")
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

        st.markdown("---")
        if not taskuri:
            st.info("Nu există notițe sau task-uri de vizită înregistrate.")
            return

        taskuri_urgente = [t for t in taskuri if t.get("stare") == "Urgent"]
        taskuri_normale = [t for t in taskuri if t.get("stare") not in ("Urgent", "Finalizat")]
        taskuri_finalizate = [t for t in taskuri if t.get("stare") == "Finalizat"]

        st.markdown("#### 🚨 Task-uri Urgente")
        if taskuri_urgente:
            _randeaza_lista_carduri_taskuri(taskuri_urgente, nivel="urgent")
        else:
            st.caption("Nu există task-uri urgente active.")

        st.markdown("#### 🟡 Task-uri Nivel Normal")
        if taskuri_normale:
            _randeaza_lista_carduri_taskuri(taskuri_normale, nivel="normal")
        else:
            st.caption("Nu există task-uri normale active.")

        if taskuri_finalizate:
            with st.expander(f"✅ Task-uri Finalizate ({len(taskuri_finalizate)})", expanded=False):
                _randeaza_lista_carduri_taskuri(taskuri_finalizate, nivel="finalizat")

        with st.expander("✏️ Editare Rapidă în Tabel", expanded=False):
            df_t_init = pd.DataFrame([
                {
                    "id": int(r["id"]),
                    "Data": str(r["data_vizita"])[:10],
                    "De făcut până la": r["de_facut_pana_la"] if pd.notna(r["de_facut_pana_la"]) else None,
                    "Ora limită": formateaza_ora_limita(r.get("ora_limita")),
                    "Stare": normalizeaza_stare_task_vizita(r["stare"]),
                    "Firmă": str(r["firma"]),
                    "Mașină": str(r.get("masina") or "-"),
                    "Note de vizită": str(r["note_vizita"]),
                    "Completed": r["stare"] == "Finalizat",
                    "Șterge": False,
                }
                for r in taskuri
            ])

            ver_task_ed = st.session_state.get("df_editor_taskuri_ver", 0)
            editor_task_key = f"df_editor_taskuri_v{ver_task_ed}"

            edited_t = st.data_editor(
                df_t_init,
                key=editor_task_key,
                hide_index=True,
                num_rows="fixed",
                use_container_width=True,
                disabled=["id", "Data", "Firmă", "Mașină"],
                column_config={
                    "id": None,
                    "Data": st.column_config.TextColumn("Data", width="small"),
                    "De făcut până la": st.column_config.DateColumn("De făcut până la", width="small"),
                    "Ora limită": st.column_config.TextColumn("Ora (HH:MM)", width="small"),
                    "Stare": st.column_config.SelectboxColumn("Stare", options=OPTIUNI_STARE_TASK_VIZITA, required=True, width="medium"),
                    "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
                    "Mașină": st.column_config.TextColumn("Mașină", width="medium"),
                    "Note de vizită": st.column_config.TextColumn("Note de vizită", width="large", required=True),
                    "Completed": st.column_config.CheckboxColumn("✅ Completed", default=False, width="small"),
                    "Șterge": st.column_config.CheckboxColumn("🗑️ Șterge", default=False, width="small"),
                },
            )

            if st.button("💾 Salvează Modificările din Tabel", type="primary", key="btn_df_save_taskuri"):
                orig_t_map = {int(r["id"]): r for _, r in df_t_init.iterrows()}
                nr_mod_t = 0
                nr_del_t = 0

                for _, row in edited_t.iterrows():
                    tid = int(row["id"])
                    if bool(row.get("Șterge", False)):
                        TaskuriVizitaRepository.delete(tid)
                        nr_del_t += 1
                        continue

                    orig = orig_t_map.get(tid)
                    if orig is None:
                        continue

                    nota_noua = str(row.get("Note de vizită") or "").strip()
                    stare_noua = "Finalizat" if bool(row.get("Completed", False)) else normalizeaza_stare_task_vizita(row.get("Stare"))
                    termen_raw = row.get("De făcut până la")
                    termen_nou = termen_raw if isinstance(termen_raw, datetime.date) else None
                    termen_vechi = orig["De făcut până la"] if isinstance(orig["De făcut până la"], datetime.date) else None
                    ora_noua = formateaza_ora_limita(row.get("Ora limită"))
                    ora_veche = formateaza_ora_limita(orig.get("Ora limită"))

                    if (
                        nota_noua != str(orig["Note de vizită"]).strip()
                        or stare_noua != normalizeaza_stare_task_vizita(orig["Stare"])
                        or termen_nou != termen_vechi
                        or ora_noua != ora_veche
                    ) and nota_noua:
                        try:
                            TaskuriVizitaRepository.update(
                                tid,
                                nota_noua,
                                stare_noua,
                                de_facut_pana_la=termen_nou,
                                ora_limita=ora_noua,
                            )
                        except TypeError:
                            TaskuriVizitaRepository.update(tid, nota_noua, stare_noua, de_facut_pana_la=termen_nou)
                        nr_mod_t += 1

                if nr_mod_t == 0 and nr_del_t == 0:
                    st.info("ℹ️ Nu există modificări nesalvate la notițe.")
                else:
                    st.session_state["df_editor_taskuri_ver"] = ver_task_ed + 1
                    _goleste_cache_taskuri()
                    _rerun_app(f"✅ Actualizate: {nr_mod_t} modificate, {nr_del_t} șterse.")


# ---------------------------------------------------------
# SECȚIUNEA 3: NOTARE RAPIDĂ PIESE PE TEREN (FRAGMENT)
# ---------------------------------------------------------

def _on_teren_firma_change():
    st.session_state["df_teren_masina_sel"] = "-- Fără mașină (opțional) --"


def _on_teren_lookup_change():
    _, detalii_piese = _incarca_optiuni_lookup_piese()
    ales = st.session_state.get("df_teren_lookup_piesa", "✍️ Piesă nouă (scriu manual)")
    este_noua = ales == "✍️ Piesă nouă (scriu manual)"
    det = detalii_piese.get(ales, {})
    st.session_state["df_teren_den_manual"] = "" if este_noua else str(det.get("denumire") or "")
    st.session_state["df_teren_cod_manual"] = "" if este_noua else str(det.get("cod_producator") or "")
    st.session_state["df_teren_status_sel"] = "De căutat" if este_noua else "De ofertat"


@_fragment
def _fragment_notare_rapida_teren():
    firme_nume, nume_to_id = _obtine_harta_firme_cached()
    masini_all = _obtine_masini_cached()
    optiuni_piese, detalii_piese = _incarca_optiuni_lookup_piese()

    if not firme_nume:
        st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        return

    c_fm1, c_fm2 = st.columns([1.5, 1.5])
    with c_fm1:
        firma_teren = st.selectbox(
            "Client / Firmă *",
            options=firme_nume,
            key="df_teren_firma_sel",
            on_change=_on_teren_firma_change,
        )
    fid_teren = nume_to_id.get(firma_teren)
    masini_firma = [
        str(m.get("denumire") or "").strip()
        for m in masini_all
        if str(m.get("denumire") or "").strip() and (fid_teren is None or m.get("firma_id") == fid_teren)
    ]
    opt_masini_teren = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma))
    cur_mas_teren = st.session_state.get("df_teren_masina_sel", "-- Fără mașină (opțional) --")
    idx_mas_teren = opt_masini_teren.index(cur_mas_teren) if cur_mas_teren in opt_masini_teren else 0

    with c_fm2:
        masina_teren = st.selectbox(
            "Mașină (opțional)",
            options=opt_masini_teren,
            index=idx_mas_teren,
            key="df_teren_masina_sel",
        )

    cur_lookup = st.session_state.get("df_teren_lookup_piesa", optiuni_piese[0])
    idx_lookup = optiuni_piese.index(cur_lookup) if cur_lookup in optiuni_piese else 0
    piesa_aleasa_lookup = st.selectbox(
        "Alege piesă din DB (sau «Piesă nouă»)",
        options=optiuni_piese,
        index=idx_lookup,
        key="df_teren_lookup_piesa",
        on_change=_on_teren_lookup_change,
    )

    este_piesa_noua = piesa_aleasa_lookup == "✍️ Piesă nouă (scriu manual)"
    piesa_din_db = detalii_piese.get(piesa_aleasa_lookup, {})
    den_implicit = "" if este_piesa_noua else str(piesa_din_db.get("denumire") or "")

    st.session_state.setdefault("df_teren_den_manual", "")
    st.session_state.setdefault("df_teren_cod_manual", "")
    st.session_state.setdefault("df_teren_cant_num", 1.0)
    st.session_state.setdefault("df_teren_prio_sel", "Normal")
    st.session_state.setdefault("df_teren_status_sel", "De căutat")
    st.session_state.setdefault("df_teren_obs_txt", "")

    with st.form("form_notare_rapida_teren_df", clear_on_submit=False):
        c_t1, c_t2 = st.columns([2.3, 1.5])
        with c_t1:
            piesa_teren = st.text_input(
                "Denumire piesă *",
                key="df_teren_den_manual",
                disabled=not este_piesa_noua,
                placeholder="scrie denumirea piesei noi...",
            )
        with c_t2:
            cod_teren = st.text_input(
                "Cod producător (opțional)",
                key="df_teren_cod_manual",
                placeholder="ex: cod reper notat la client",
            )

        c_t3, c_t4, c_t5 = st.columns([1.1, 1.3, 1.5])
        with c_t3:
            cant_teren = st.number_input(
                "Cantitate *",
                min_value=0.01,
                step=1.0,
                format="%.2f",
                key="df_teren_cant_num",
            )
        with c_t4:
            prioritate_teren = st.selectbox("Stare piesă *", options=OPTIUNI_PRIORITATE_PIESA, key="df_teren_prio_sel")
        with c_t5:
            status_teren = st.selectbox("Status Comandă *", options=OPTIUNI_STATUS_TEREN, key="df_teren_status_sel")

        obs_teren = st.text_area(
            "Observații / detalii notate la client (opțional)",
            placeholder="ex: cerută la vizită, verificare ofertă...",
            height=85,
            key="df_teren_obs_txt",
        )
        salveaza_teren = st.form_submit_button("➕ Notează Piesa pentru Comandă", type="primary")

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
                status_comanda=status_teren,
                observatii=obs_teren,
            )
            _goleste_cache_piese_si_rfq()
            mesaj_cat = "existentă în catalog" if rez.get("existenta_in_catalog") else "adăugată și în catalogul `piese`"
            _rerun_app(f"✅ Salvat {str(den_finala).strip()} ({mesaj_cat}).")
        except ValueError as ve:
            st.error(f"⚠️ {ve}")


def render_notare_rapida_teren():
    with st.expander("📝 Notare Rapidă Piese pe Teren (Client obligatoriu • Mașină opțională)", expanded=False):
        _fragment_notare_rapida_teren()


# ---------------------------------------------------------
# SECȚIUNEA 4: TABEL PIESE DE COMANDAT (FRAGMENT)
# ---------------------------------------------------------

@_fragment
def _fragment_tabel_piese_de_comandat(randuri_initiale: list[dict]):
    link_gdrive_global = _obtine_link_gdrive_setari()
    randuri = _colecteaza_piese_necesare(link_gdrive_global) or randuri_initiale

    if not randuri:
        st.info("Nu există piese marcate ca necesare / de comandat / de căutat / de ofertat.")
        return

    df = pd.DataFrame(randuri)

    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1.4])
    with c1:
        filtru_sursa = st.selectbox(
            "Filtrează după sursă",
            options=["Toate", "Teren / Necesar", "Mașini", "Electronică"],
            key="df_piese_cmd_sursa",
        )
    with c2:
        opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].unique().tolist())
        filtru_furn = st.selectbox("Filtrează după furnizor", options=opt_furn, key="df_piese_cmd_furn")
    with c3:
        filtru_stare = st.selectbox("Filtrează după status", options=["Toate stările"] + OPTIUNI_STARE_COMANDA, key="df_piese_cmd_stare")
    with c4:
        cautare_piesa = st.text_input("Caută piesă / cod", placeholder="ex: L6376PD, SFH6106...", key="df_piese_cmd_cautare").strip().lower()

    mask = pd.Series(True, index=df.index)
    if filtru_sursa != "Toate":
        mask &= df["Sursă"] == filtru_sursa
    if filtru_furn != "Toți furnizorii":
        mask &= df["Furnizor"] == filtru_furn
    if filtru_stare != "Toate stările":
        mask &= df["Status Comandă"] == filtru_stare
    if cautare_piesa:
        mask &= df["Piesă"].str.lower().str.contains(cautare_piesa, na=False)

    df_f = df.loc[mask]
    if df_f.empty:
        st.info("Nu există piese care să corespundă filtrelor selectate.")
        return

    cols_afis = [
        "_row_id",
        "Stare Piesă",
        "Piesă",
        "Cantitate",
        "Status Comandă",
        "Furnizor",
        "Sursă",
        "Firmă",
        "Mașină",
        "Piese înlocuitoare",
        "Doc GDrive",
        "Raport",
    ]
    df_editor_init = df_f[cols_afis].reset_index(drop=True)
    df_editor_init["Doc GDrive"] = df_editor_init["Doc GDrive"].apply(
        lambda x: x if str(x or "").startswith(("http://", "https://")) else None
    )

    ver_dash = st.session_state.get("df_editor_stare_piese_ver", 0)
    editor_dash_key = f"df_editor_stare_piese_{filtru_sursa}_{filtru_furn}_{filtru_stare}_v{ver_dash}"

    edited_df = st.data_editor(
        df_editor_init,
        key=editor_dash_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["_row_id", "Piesă", "Cantitate", "Furnizor", "Sursă", "Firmă", "Mașină", "Piese înlocuitoare", "Doc GDrive", "Raport"],
        column_config={
            "_row_id": None,
            "Stare Piesă": st.column_config.SelectboxColumn("Stare Piesă", options=OPTIUNI_PRIORITATE_PIESA, required=True, width="small"),
            "Piesă": st.column_config.TextColumn("Piesă", width="large"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", format="%.2f", width="small"),
            "Status Comandă": st.column_config.SelectboxColumn("Status Comandă", options=OPTIUNI_STARE_COMANDA, required=True, width="medium"),
            "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
            "Sursă": st.column_config.TextColumn("Sursă", width="small"),
            "Firmă": st.column_config.TextColumn("Firmă", width="small"),
            "Mașină": st.column_config.TextColumn("Mașină", width="small"),
            "Piese înlocuitoare": st.column_config.TextColumn("Piese înlocuitoare", width="medium"),
            "Doc GDrive": st.column_config.LinkColumn("Doc GDrive", display_text="📂 GDrive", width="small"),
            "Raport": st.column_config.TextColumn("Raport", width="small"),
        },
    )

    if st.button("💾 Actualizează Stările în Tabel", type="primary", key="btn_df_update_stare_piese"):
        nr_mod, erori_salvare = _salveaza_modificari_piese(
            df_orig_rows=df_f.to_dict("records"),
            edited_df=edited_df,
            col_prio="Stare Piesă",
            col_status="Status Comandă",
        )

        if nr_mod > 0:
            _goleste_cache_piese_si_rfq()
            st.session_state["df_editor_piese_prio_ver"] = st.session_state.get("df_editor_piese_prio_ver", 0) + 1

        if erori_salvare:
            st.error("⚠️ Au apărut erori la salvare:\n" + "\n".join(erori_salvare))
        elif nr_mod == 0:
            st.info("ℹ️ Nu există modificări nesalvate.")
        else:
            st.session_state["df_editor_stare_piese_ver"] = ver_dash + 1
            _rerun_app(f"✅ Stările au fost actualizate pentru {nr_mod} poziții.")


def render_tabel_piese_de_comandat(randuri: list[dict]):
    with st.expander("🛒 Piese De Comandat / Necesare & Furnizori", expanded=False):
        _fragment_tabel_piese_de_comandat(randuri)


# ---------------------------------------------------------
# SECȚIUNEA 5: CERERI OFERTĂ FURNIZORI - RFQ (FRAGMENT)
# ---------------------------------------------------------

def _on_rfq_filter_change() -> None:
    st.session_state["df_rfq_main_open"] = True
    st.session_state["df_rfq_tbl_open"] = True


def _sync_expander_state(state_key: str, widget_key: str, default: bool = False) -> bool:
    if widget_key in st.session_state:
        val = bool(st.session_state[widget_key])
        st.session_state[state_key] = val
        return val
    return bool(st.session_state.get(state_key, default))


@_fragment
def _fragment_cereri_oferta_furnizori():
    cereri_all = _obtine_cereri_cu_detalii_cached()
    firme_nume, nume_to_id = _obtine_harta_firme_cached()
    masini_all = _obtine_masini_cached()
    furnizori_cunoscuti = _obtine_furnizori_cunoscuti_cached()
    necesar_rows = _obtine_necesar_piese_cached()
    optiuni_piese_cat, detalii_piese_cat = _incarca_optiuni_lookup_piese()

    # 1. CREEAZĂ CERERE DE OFERTĂ CĂTRE FURNIZORI
    sub1_open = _sync_expander_state("df_rfq_sub1_open", "exp_rfq_sub1", False)
    with st.expander("1. Creează Cerere de Ofertă către Furnizori", expanded=sub1_open, key="exp_rfq_sub1"):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            cf_a, cf_b, cf_c = st.columns([1.4, 1.4, 1.2])
            with cf_a:
                firma_rfq = st.selectbox("Client / Firmă *", options=firme_nume, key="df_rfq_firma_sel")
            fid_rfq = nume_to_id.get(firma_rfq)

            masini_firma_rfq = [
                m for m in masini_all
                if str(m.get("denumire") or "").strip() and (fid_rfq is None or m.get("firma_id") == fid_rfq)
            ]
            mapa_masini_rfq = {str(m.get("denumire")).strip(): m for m in masini_firma_rfq}
            opt_masini_rfq = ["-- Fără mașină (opțional) --"] + sorted(mapa_masini_rfq.keys())
            with cf_b:
                masina_rfq = st.selectbox("Mașină (opțional)", options=opt_masini_rfq, key="df_rfq_masina_sel")
            mid_rfq = mapa_masini_rfq.get(masina_rfq, {}).get("id") if not masina_rfq.startswith("--") else None

            with cf_c:
                termen_rfq = st.date_input(
                    "Termen răspuns furnizor",
                    value=datetime.date.today() + datetime.timedelta(days=2),
                    key="df_rfq_termen_data",
                )

            furn_col1, furn_col2 = st.columns([2.2, 1.8])
            with furn_col1:
                furn_selectati = st.multiselect("Furnizori (nomenclator / catalog)", options=furnizori_cunoscuti, key="df_rfq_furn_multi")
            with furn_col2:
                furn_manual = st.text_input(
                    "Furnizori suplimentari (separați prin virgulă)",
                    placeholder="ex: Furnizor A, Furnizor B",
                    key="df_rfq_furn_manual",
                )

            piese_din_necesar_client = [
                np_r for np_r in necesar_rows
                if str(np_r.get("firma_client") or "").strip().lower() == str(firma_rfq or "").strip().lower()
            ]
            opt_piese_nec = {
                f"{r.get('denumire_piesa')} (cant. {r.get('cantitate')})": r
                for r in piese_din_necesar_client
                if str(r.get("denumire_piesa") or "").strip()
            }
            piese_nec_alese = st.multiselect(
                "Preia piese din necesarul clientului (opțional)",
                options=list(opt_piese_nec.keys()),
                key="df_rfq_piese_nec_multi",
            )

            with st.form("form_creeaza_cerere_rfq", clear_on_submit=True):
                cp1, cp2, cp3, cp4 = st.columns([2.2, 1.3, 0.9, 1.4])
                with cp1:
                    piesa_extra_den = st.text_input("Sau adaugă piesă manuală în cerere", placeholder="ex: Rulment 6206 / Electrovana")
                with cp2:
                    piesa_extra_cod = st.text_input("Cod producător", placeholder="opțional")
                with cp3:
                    piesa_extra_cant = st.number_input("Cant.", min_value=0.01, value=1.0, step=1.0, format="%.2f")
                with cp4:
                    piesa_extra_inloc = st.text_input("Piese înlocuitoare", placeholder="ex: SKF 6206, FAG 6206")

                obs_rfq = st.text_area("Observații cerere ofertă", height=70, placeholder="detalii tehnice, coduri...")
                btn_creeaza_rfq = st.form_submit_button("📤 Creează Cererea de Ofertă", type="primary")

            if btn_creeaza_rfq:
                linii_de_trimis = []
                for lbl_n in piese_nec_alese:
                    nr = opt_piese_nec.get(lbl_n) or {}
                    linii_de_trimis.append({
                        "piesa_id": nr.get("piesa_id"),
                        "denumire_piesa": nr.get("denumire_piesa"),
                        "cod_producator": nr.get("cod_producator", ""),
                        "piese_inlocuitoare": _extrage_piese_inlocuitoare(nr) if _extrage_piese_inlocuitoare(nr) != "-" else "",
                        "cantitate": _to_float_safe(nr.get("cantitate"), 1.0),
                        "pret_unitar": 0.0,
                        "moneda": "EUR",
                        "termen_livrare_zile": "",
                    })

                if str(piesa_extra_den or "").strip():
                    linii_de_trimis.append({
                        "piesa_id": None,
                        "denumire_piesa": str(piesa_extra_den).strip(),
                        "cod_producator": str(piesa_extra_cod or "").strip(),
                        "piese_inlocuitoare": str(piesa_extra_inloc or "").strip(),
                        "cantitate": _to_float_safe(piesa_extra_cant, 1.0),
                        "pret_unitar": 0.0,
                        "moneda": "EUR",
                        "termen_livrare_zile": "",
                    })

                furn_finale = list(dict.fromkeys(
                    list(furn_selectati or [])
                    + [x.strip() for x in str(furn_manual or "").split(",") if x.strip()]
                ))

                try:
                    cer_noua = CereriOfertaRepository.creeaza_cerere(
                        firma_nume=firma_rfq,
                        firma_id=fid_rfq,
                        masina_nume=masina_rfq,
                        masina_id=mid_rfq,
                        termen_raspuns=termen_rfq,
                        observatii=obs_rfq,
                        linii_piese=linii_de_trimis,
                        furnizori_selectati=furn_finale,
                    )
                    _goleste_cache_piese_si_rfq()
                    st.toast(f"✅ Cererea {cer_noua.get('cod_cerere')} a fost creată.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

    # 2. TABEL CERERI DE OFERTĂ CĂTRE FURNIZORI
    tbl_open = _sync_expander_state("df_rfq_tbl_open", "exp_rfq_tbl", False)
    with st.expander(f"2. Tabel Cereri de Ofertă către Furnizori ({len(cereri_all)})", expanded=tbl_open, key="exp_rfq_tbl"):
        if not cereri_all:
            st.info("Nu există cereri de ofertă către furnizori înregistrate.")
        else:
            clienti_disp = ["Toți clienții"] + sorted({
                str(c.get("firma_nume") or "").strip() for c in cereri_all if str(c.get("firma_nume") or "").strip()
            })
            furn_disp = ["Toți furnizorii"] + sorted({
                fn for c in cereri_all for fn in (c.get("_furnizori_str") or "").split(", ") if fn and fn != "-"
            })
            stari_disp = ["Toate"] + OPTIUNI_STATUS_CERERE_OFERTA

            cur_st = st.session_state.get("df_rfq_filtru_status", "Toate")
            cur_cli = st.session_state.get("df_rfq_filtru_client", "Toți clienții")
            cur_furn = st.session_state.get("df_rfq_filtru_furnizor", "Toți furnizorii")

            fc1, fc2, fc3, fc4 = st.columns([1.3, 1.4, 1.4, 1.5])
            with fc1:
                filtru_st_cer = st.selectbox(
                    "Stare cerere",
                    options=stari_disp,
                    index=stari_disp.index(cur_st) if cur_st in stari_disp else 0,
                    key="df_rfq_filtru_status",
                    on_change=_on_rfq_filter_change,
                )
            with fc2:
                filtru_cli_cer = st.selectbox(
                    "Client",
                    options=clienti_disp,
                    index=clienti_disp.index(cur_cli) if cur_cli in clienti_disp else 0,
                    key="df_rfq_filtru_client",
                    on_change=_on_rfq_filter_change,
                )
            with fc3:
                filtru_furn_cer = st.selectbox(
                    "Furnizor",
                    options=furn_disp,
                    index=furn_disp.index(cur_furn) if cur_furn in furn_disp else 0,
                    key="df_rfq_filtru_furnizor",
                    on_change=_on_rfq_filter_change,
                )
            with fc4:
                filtru_piesa_cer = st.text_input(
                    "Piesă / cod",
                    placeholder="ex: rulment, cod...",
                    key="df_rfq_filtru_piesa",
                    on_change=_on_rfq_filter_change,
                ).strip().lower()

            cereri_filtrate = [
                c for c in cereri_all
                if (filtru_st_cer == "Toate" or normalizeaza_status_cerere_oferta(c.get("status_cerere")) == filtru_st_cer)
                and (filtru_cli_cer == "Toți clienții" or str(c.get("firma_nume") or "").strip() == filtru_cli_cer)
                and (filtru_furn_cer == "Toți furnizorii" or filtru_furn_cer.lower() in (c.get("_furnizori_set") or set()))
                and (not filtru_piesa_cer or filtru_piesa_cer in str(c.get("_piese_str") or "").lower())
            ]

            if not cereri_filtrate:
                st.info("Nu există cereri care să corespundă filtrelor selectate.")
            else:
                df_cer = pd.DataFrame([
                    {
                        "Stare cerere": normalizeaza_status_cerere_oferta(c.get("status_cerere")),
                        "Client": str(c.get("firma_nume") or "-"),
                        "Mașină": str(c.get("masina_nume") or "-"),
                        "Piesă": str(c.get("_piese_str") or "-"),
                        "Cod Cerere": str(c.get("cod_cerere") or ""),
                    }
                    for c in cereri_filtrate
                ])
                st.dataframe(df_cer, hide_index=True, use_container_width=True)

    # 3. PRELUARE, ANALIZĂ OFERTE PRIMITE & OFERTĂ CLIENT
    df_lin_edit = pd.DataFrame()
    cer_activa = None
    cid_activa = None
    preluare_open = _sync_expander_state("df_rfq_preluare_open", "exp_rfq_preluare", False)

    with st.expander(
        "Preluare, Analiză Oferte Primite de la Furnizori & Legătură cu Oferta către Client",
        expanded=preluare_open,
        key="exp_rfq_preluare",
    ):
        if not cereri_all:
            st.info("Nu există cereri de ofertă de analizat.")
        else:
            filtru_st_an = st.session_state.get("df_rfq_filtru_status", "Toate")
            filtru_cli_an = st.session_state.get("df_rfq_filtru_client", "Toți clienții")
            filtru_furn_an = st.session_state.get("df_rfq_filtru_furnizor", "Toți furnizorii")
            filtru_piesa_an = str(st.session_state.get("df_rfq_filtru_piesa") or "").strip().lower()

            cereri_analiza = [
                c for c in cereri_all
                if (filtru_st_an == "Toate" or normalizeaza_status_cerere_oferta(c.get("status_cerere")) == filtru_st_an)
                and (filtru_cli_an == "Toți clienții" or str(c.get("firma_nume") or "").strip() == filtru_cli_an)
                and (filtru_furn_an == "Toți furnizorii" or filtru_furn_an.lower() in (c.get("_furnizori_set") or set()))
                and (not filtru_piesa_an or filtru_piesa_an in str(c.get("_piese_str") or "").lower())
            ] or cereri_all

            mapa_cereri = {
                f"{c.get('cod_cerere') or '-'}, {c.get('firma_nume') or '-'}, {c.get('masina_nume') or '-'}, {c.get('_piese_str') or '-'} ({normalizeaza_status_cerere_oferta(c.get('status_cerere'))})": c
                for c in cereri_analiza
            }
            opts_cer = list(mapa_cereri.keys())
            sel_cer_lbl = st.selectbox("Selectează cererea pentru analiză:", options=opts_cer, key="df_rfq_sel_analiza")
            cer_activa = mapa_cereri[sel_cer_lbl]
            cid_activa = int(cer_activa["id"])

            # Curățenie session_state la schimbarea cererii active
            prev_cid = st.session_state.get("_df_rfq_prev_cid")
            if prev_cid is not None and prev_cid != cid_activa:
                for k_old in list(st.session_state.keys()):
                    if k_old.startswith(f"df_rfq_linii_editor_{prev_cid}_") or k_old in (
                        f"df_rfq_st_sel_{prev_cid}",
                        f"df_rfq_sursa_reper_sel_{prev_cid}",
                    ):
                        del st.session_state[k_old]
            st.session_state["_df_rfq_prev_cid"] = cid_activa

            linii_cer = cer_activa.get("_linii") if "_linii" in cer_activa else (CereriOfertaRepository.get_linii_by_cerere(cid_activa) or [])

            cs_left, cs_right = st.columns([2.0, 2.0], vertical_alignment="bottom")
            with cs_left:
                st_curent = normalizeaza_status_cerere_oferta(cer_activa.get("status_cerere"))
                nou_st_cer = st.selectbox(
                    "Stare cerere",
                    options=OPTIUNI_STATUS_CERERE_OFERTA,
                    index=OPTIUNI_STATUS_CERERE_OFERTA.index(st_curent),
                    key=f"df_rfq_st_sel_{cid_activa}",
                )
            with cs_right:
                if st.button("🔄 Actualizează Starea Cererii", key=f"df_rfq_btn_st_{cid_activa}", use_container_width=True):
                    CereriOfertaRepository.update_status_cerere(cid_activa, nou_st_cer)
                    _goleste_cache_taskuri()
                    _goleste_cache_piese_si_rfq()
                    _rerun_app(f"✅ Starea cererii {cer_activa.get('cod_cerere')} -> {nou_st_cer}.")

            # Surse repere
            piese_unice_cerere: dict[str, dict] = {}
            for l in linii_cer:
                den_u = str(l.get("denumire_piesa") or "").strip()
                if den_u and den_u not in piese_unice_cerere:
                    piese_unice_cerere[den_u] = l

            firma_cer_curenta = str(cer_activa.get("firma_nume") or "").strip().lower()
            necesar_client_cer = [
                np_r for np_r in necesar_rows
                if str(np_r.get("firma_client") or "").strip().lower() == firma_cer_curenta
                and str(np_r.get("denumire_piesa") or "").strip()
            ]

            surse_repere_map: dict[str, dict] = {}
            for den_c, l_obj in piese_unice_cerere.items():
                lbl_s = f"[Cerere] {den_c}"
                surse_repere_map[lbl_s] = {
                    "piesa_id": l_obj.get("piesa_id"),
                    "denumire_piesa": den_c,
                    "cod_producator": str(l_obj.get("cod_producator") or "").strip(),
                    "cantitate": _to_float_safe(l_obj.get("cantitate"), 1.0),
                    "piese_inlocuitoare": (
                        "" if str(l_obj.get("piese_inlocuitoare") or "").strip() in ("", "-")
                        else str(l_obj.get("piese_inlocuitoare")).strip()
                    ),
                }

            for np_r in necesar_client_cer:
                den_n = str(np_r.get("denumire_piesa") or "").strip()
                lbl_n = f"[Necesar client] {den_n} (cant. {np_r.get('cantitate')})"
                if lbl_n not in surse_repere_map:
                    inloc_n = _extrage_piese_inlocuitoare(np_r)
                    surse_repere_map[lbl_n] = {
                        "piesa_id": np_r.get("piesa_id"),
                        "denumire_piesa": den_n,
                        "cod_producator": str(np_r.get("cod_producator") or "").strip(),
                        "cantitate": _to_float_safe(np_r.get("cantitate"), 1.0),
                        "piese_inlocuitoare": "" if inloc_n == "-" else inloc_n,
                    }

            for et_cat in optiuni_piese_cat[1:]:
                det_c = detalii_piese_cat.get(et_cat) or {}
                lbl_c = f"[Catalog] {et_cat}"
                if lbl_c not in surse_repere_map:
                    inloc_c = str(det_c.get("piese_inlocuitoare") or "").strip()
                    surse_repere_map[lbl_c] = {
                        "piesa_id": det_c.get("piesa_id"),
                        "denumire_piesa": str(det_c.get("denumire") or "").strip(),
                        "cod_producator": str(det_c.get("cod_producator") or "").strip(),
                        "cantitate": 1.0,
                        "piese_inlocuitoare": "" if inloc_c == "-" else inloc_c,
                    }

            opt_surse_repere = ["✍️ Alt reper / piesă nouă (scriu manual)"] + list(surse_repere_map.keys())

            with st.expander("➕ Adaugă încă o ofertă furnizor / reper suplimentar în tabel", expanded=False):
                repere_deja_in_cerere = {k.lower() for k in piese_unice_cerere.keys()}
                repere_lipsa_din_necesar = [
                    np_r for np_r in necesar_client_cer
                    if str(np_r.get("denumire_piesa") or "").strip().lower() not in repere_deja_in_cerere
                ]
                if repere_lipsa_din_necesar:
                    if st.button(
                        f"📥 Preia în tabel toate reperele din necesarul clientului ({len(repere_lipsa_din_necesar)} repere)",
                        key=f"df_rfq_import_all_nec_{cid_activa}",
                        use_container_width=True,
                    ):
                        furn_implicit = (
                            str(linii_cer[0].get("furnizor_nume") or "").strip()
                            if linii_cer
                            else ""
                        )
                        for np_l in repere_lipsa_din_necesar:
                            inloc_l = _extrage_piese_inlocuitoare(np_l)
                            _DeFacutDataAdapter.insert_linie_cerere_rfq(
                                cid_activa,
                                {
                                    "piesa_id": np_l.get("piesa_id"),
                                    "furnizor_nume": furn_implicit,
                                    "denumire_piesa": str(np_l.get("denumire_piesa") or "").strip(),
                                    "cod_producator": str(np_l.get("cod_producator") or "").strip(),
                                    "piese_inlocuitoare": "" if inloc_l == "-" else inloc_l,
                                    "cantitate": _to_float_safe(np_l.get("cantitate"), 1.0),
                                    "pret_unitar": 0.0,
                                    "moneda": "EUR",
                                    "termen_livrare_zile": "",
                                    "selectat_pentru_client": True,
                                },
                            )
                        st.session_state[f"df_rfq_linii_ver_{cid_activa}"] = st.session_state.get(f"df_rfq_linii_ver_{cid_activa}", 0) + 1
                        _goleste_cache_piese_si_rfq()
                        st.toast(f"✅ Adăugate {len(repere_lipsa_din_necesar)} repere în tabel.")
                        st.rerun()

                sursa_reper_sel = st.selectbox(
                    "Alege reper din cerere / necesar / catalog sau scrie un reper nou",
                    options=opt_surse_repere,
                    index=1 if len(opt_surse_repere) > 1 else 0,
                    key=f"df_rfq_sursa_reper_sel_{cid_activa}",
                )
                este_reper_manual = sursa_reper_sel == "✍️ Alt reper / piesă nouă (scriu manual)"
                ref_piesa = surse_repere_map.get(sursa_reper_sel, {})

                with st.form(f"form_add_oferta_supl_{cid_activa}", clear_on_submit=True):
                    oa1, oa2, oa3 = st.columns([2.0, 1.4, 1.2])
                    with oa1:
                        den_manual_add = st.text_input(
                            "Denumire reper / piesă *",
                            value="" if este_reper_manual else str(ref_piesa.get("denumire_piesa") or ""),
                            placeholder="scrie denumirea reperului suplimentar...",
                        )
                    with oa2:
                        cod_manual_add = st.text_input(
                            "Cod producător",
                            value="" if este_reper_manual else str(ref_piesa.get("cod_producator") or ""),
                            placeholder="opțional",
                        )
                    with oa3:
                        inloc_add = st.text_input(
                            "Piese înlocuitoare / echiv.",
                            value="" if este_reper_manual else str(ref_piesa.get("piese_inlocuitoare") or ""),
                            placeholder="opțional",
                        )

                    oa4, oa5, oa6, oa7, oa8, oa9 = st.columns([1.4, 1.2, 0.8, 1.0, 0.8, 1.0])
                    with oa4:
                        furn_sel_add = st.selectbox(
                            "Furnizor (nomenclator)",
                            options=["-- Scrie manual --"] + furnizori_cunoscuti,
                        )
                    with oa5:
                        furn_txt_add = st.text_input(
                            "Sau nume furnizor",
                            placeholder="ex: Furnizor B",
                        )
                    with oa6:
                        cant_add = st.number_input(
                            "Cant.",
                            min_value=0.01,
                            value=1.0 if este_reper_manual else _to_float_safe(ref_piesa.get("cantitate"), 1.0),
                            step=1.0,
                            format="%.2f",
                        )
                    with oa7:
                        pret_add = st.number_input("Preț Unitar", min_value=0.0, value=0.0, step=1.0, format="%.2f")
                    with oa8:
                        mon_add = st.selectbox("Monedă", options=["EUR", "RON"], index=0)
                    with oa9:
                        termen_add = st.text_input("Termen livrare", placeholder="ex: stoc / 3 zile")

                    sel_client_add = st.checkbox("✅ Include direct în oferta către client", value=True)

                    if st.form_submit_button("➕ Adaugă Rând în Tabelul de Oferte", type="primary"):
                        furn_final_add = (
                            furn_txt_add.strip()
                            if furn_txt_add.strip()
                            else ("" if furn_sel_add.startswith("--") else furn_sel_add.strip())
                        )
                        den_final_add = str(den_manual_add or "").strip()
                        if not den_final_add:
                            st.error("⚠️ Completează denumirea reperului / piesei.")
                        else:
                            _DeFacutDataAdapter.insert_linie_cerere_rfq(
                                cid_activa,
                                {
                                    "piesa_id": None if este_reper_manual else ref_piesa.get("piesa_id"),
                                    "furnizor_nume": furn_final_add,
                                    "denumire_piesa": den_final_add,
                                    "cod_producator": str(cod_manual_add or "").strip(),
                                    "piese_inlocuitoare": str(inloc_add or "").strip(),
                                    "cantitate": _to_float_safe(cant_add, 1.0),
                                    "pret_unitar": _to_float_safe(pret_add, 0.0),
                                    "moneda": mon_add,
                                    "termen_livrare_zile": str(termen_add or "").strip(),
                                    "selectat_pentru_client": bool(sel_client_add),
                                },
                            )
                            st.session_state[f"df_rfq_linii_ver_{cid_activa}"] = st.session_state.get(f"df_rfq_linii_ver_{cid_activa}", 0) + 1
                            _goleste_cache_piese_si_rfq()
                            st.toast(f"✅ Reperul «{den_final_add}» a fost adăugat în tabel.")
                            st.rerun()

            df_lin_init = pd.DataFrame(
                [
                    {
                        "id": int(l["id"]),
                        "Furnizor": str(l.get("furnizor_nume") or ""),
                        "Piesă": str(l.get("denumire_piesa") or ""),
                        "Cod Prod.": str(l.get("cod_producator") or ""),
                        "Piese înlocuitoare": str(l.get("piese_inlocuitoare") or ""),
                        "Cant.": _to_float_safe(l.get("cantitate"), 1.0),
                        "Preț Unitar": _to_float_safe(l.get("pret_unitar"), 0.0),
                        "Monedă": str(l.get("moneda") or "EUR"),
                        "Termen livrare": str(l.get("termen_livrare_zile") or ""),
                        "Selectat Client": bool(l.get("selectat_pentru_client", False)),
                    }
                    for l in linii_cer
                ]
                if linii_cer
                else [
                    {
                        "id": None,
                        "Furnizor": "",
                        "Piesă": "",
                        "Cod Prod.": "",
                        "Piese înlocuitoare": "",
                        "Cant.": 1.0,
                        "Preț Unitar": 0.0,
                        "Monedă": "EUR",
                        "Termen livrare": "",
                        "Selectat Client": False,
                    }
                ]
            )

            ver_linii = st.session_state.get(f"df_rfq_linii_ver_{cid_activa}", 0)
            st.caption("💡 Poți edita prețurile existente și poți adăuga direct rânduri noi jos în tabel pentru alte repere/oferte/furnizori.")
            df_lin_edit = st.data_editor(
                df_lin_init,
                key=f"df_rfq_linii_editor_{cid_activa}_v{ver_linii}",
                hide_index=True,
                num_rows="dynamic",
                use_container_width=True,
                disabled=["id"],
                column_config={
                    "id": None,
                    "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                    "Piesă": st.column_config.TextColumn("Piesă", width="large", required=True),
                    "Cod Prod.": st.column_config.TextColumn("Cod Prod.", width="small"),
                    "Piese înlocuitoare": st.column_config.TextColumn("Piese înlocuitoare", width="medium"),
                    "Cant.": st.column_config.NumberColumn("Cant.", min_value=0.01, default=1.0, format="%.2f", width="small"),
                    "Preț Unitar": st.column_config.NumberColumn("Preț Unitar", min_value=0.0, default=0.0, format="%.2f", width="small"),
                    "Monedă": st.column_config.SelectboxColumn("Monedă", options=["EUR", "RON"], default="EUR", width="small"),
                    "Termen livrare": st.column_config.TextColumn("Termen livrare", width="small"),
                    "Selectat Client": st.column_config.CheckboxColumn("✅ Client", default=False, width="small"),
                },
            )

            ca_b1, ca_b2 = st.columns(2)
            with ca_b1:
                if st.button(
                    "💾 Salvează Ofertele Primite de la Furnizori (+ Task Ofertă Client)",
                    type="primary",
                    key=f"df_rfq_save_primita_{cid_activa}",
                    use_container_width=True,
                ):
                    _salveaza_toate_ofertele_cerere_rfq(cid_activa, df_lin_edit)
                    st.session_state[f"df_rfq_linii_ver_{cid_activa}"] = ver_linii + 1
                    _goleste_cache_taskuri()
                    _goleste_cache_piese_si_rfq()
                    _rerun_app(f"✅ Ofertele furnizorilor pentru {cer_activa.get('firma_nume')} au fost salvate.")

            with ca_b2:
                if st.button(
                    "🚀 Pregătește Liniile în Oferta către Client",
                    key=f"df_rfq_prep_oferta_client_{cid_activa}",
                    use_container_width=True,
                ):
                    _salveaza_toate_ofertele_cerere_rfq(cid_activa, df_lin_edit)
                    firme_all = FirmeRepository.get_all() or []
                    firma_nume = str(cer_activa.get("firma_nume") or "").strip()
                    firma_obj = next((f for f in firme_all if str(f.get("nume_firma") or "").strip() == firma_nume), {})
                    adaos_client = _to_float_safe(firma_obj.get("adaos_comercial"), 20.0)

                    df_valide = df_lin_edit[df_lin_edit["Piesă"].fillna("").astype(str).str.strip() != ""].copy()
                    linii_sel = [r for _, r in df_valide.iterrows() if bool(r.get("Selectat Client", False))]
                    if not linii_sel:
                        linii_sel = [r for _, r in df_valide.iterrows()]

                    contor_piese: dict[str, int] = {}
                    for r in linii_sel:
                        k_p = str(r.get("Piesă") or "").strip().lower()
                        contor_piese[k_p] = contor_piese.get(k_p, 0) + 1

                    randuri_oferta = []
                    for idx_r, r in enumerate(linii_sel, start=1):
                        cant = _to_float_safe(r.get("Cant."), 1.0)
                        pret_furn = _to_float_safe(r.get("Preț Unitar"), 0.0)
                        pret_cu_adaos = round(pret_furn * (1.0 + adaos_client / 100.0), 2)
                        mon = str(r.get("Monedă") or "EUR").strip().upper()
                        if mon not in ("RON", "EUR"):
                            mon = "EUR"
                        den = str(r.get("Piesă") or "").strip()
                        cod = str(r.get("Cod Prod.") or "").strip()
                        inloc = str(r.get("Piese înlocuitoare") or "").strip()
                        furn_r = str(r.get("Furnizor") or "").strip()

                        desc_finala = f"{den} ({cod})" if cod and cod.lower() not in den.lower() else den
                        if inloc and inloc != "-":
                            desc_finala += f" | Echiv: {inloc}"
                        if contor_piese.get(den.lower(), 0) > 1 and furn_r:
                            desc_finala += f" [Varianta: {furn_r}]"

                        termen = str(r.get("Termen livrare") or "1").strip() or "1"

                        randuri_oferta.append({
                            "Ordine": idx_r,
                            "Descriere": desc_finala,
                            "UM": "buc",
                            "Cantitate": cant,
                            "Pret Unitar": pret_cu_adaos,
                            "Moneda": mon,
                            "Termen livrare": termen,
                        })

                    if randuri_oferta:
                        st.session_state["df_oferta_editor"] = pd.DataFrame(randuri_oferta)
                        st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1

                    draft = st.session_state.get("oferta_draft")
                    if isinstance(draft, dict):
                        if firma_nume:
                            draft["sel_firma"] = firma_nume
                            draft["ultima_firma_pers"] = firma_nume
                        masina_nume = str(cer_activa.get("masina_nume") or "").strip()
                        if masina_nume:
                            draft["sel_masina"] = masina_nume
                            draft["ultima_masina_selectata"] = masina_nume
                            draft["utilaj"] = masina_nume
                        draft["cerere_furnizor_id"] = cid_activa
                        draft["cod_cerere_furnizor"] = cer_activa.get("cod_cerere")
                        st.session_state["ofs_cnt"] = st.session_state.get("ofs_cnt", 0) + 1

                    st.session_state[f"df_rfq_linii_ver_{cid_activa}"] = ver_linii + 1
                    CereriOfertaRepository.update_status_cerere(cid_activa, "Ofertat la client")
                    _goleste_cache_piese_si_rfq()
                    _rerun_app(f"✅ {len(randuri_oferta)} poziții pregătite în Oferte pentru {firma_nume}.")

    # 4. SUBEXPANDER SEPARAT: ANALIZĂ COMPARATIVĂ ÎNTRE FURNIZORI
    comp_open = _sync_expander_state("df_rfq_comp_open", "exp_rfq_comp", False)
    with st.expander("📊 Analiză Comparativă între Furnizori", expanded=comp_open, key="exp_rfq_comp"):
        if cer_activa is None or df_lin_edit.empty:
            st.info("Selectează o cerere cu oferte în subexpanderul de preluare pentru a vedea comparația între furnizori.")
        else:
            df_analiza = df_lin_edit[df_lin_edit["Piesă"].fillna("").astype(str).str.strip() != ""].copy()
            if df_analiza.empty:
                st.info("Nu există repere completate pentru analiză.")
            else:
                df_analiza["Furnizor"] = df_analiza["Furnizor"].fillna("").astype(str).str.strip().replace("", "Fără furnizor")
                df_analiza["Cant."] = df_analiza["Cant."].apply(lambda v: _to_float_safe(v, 0.0))
                df_analiza["Preț Unitar"] = df_analiza["Preț Unitar"].apply(lambda v: _to_float_safe(v, 0.0))
                df_analiza["Total Linie"] = (df_analiza["Cant."] * df_analiza["Preț Unitar"]).round(2)

                st.caption(f"Cerere analizată: **{cer_activa.get('cod_cerere')}** • Client: **{cer_activa.get('firma_nume')}**")

                nr_fara_pret = int((df_analiza["Preț Unitar"] <= 0).sum())
                if nr_fara_pret > 0:
                    st.warning(f"⚠️ {nr_fara_pret} poziții au preț 0.00 (necompletat) și apar la final în comparația pe piesă.")

                rezumat_furn = (
                    df_analiza.groupby(["Furnizor", "Monedă"], as_index=False)
                    .agg(
                        Pozitii=("Piesă", "count"),
                        Pozitii_Cotate=("Preț Unitar", lambda s: int((s > 0).sum())),
                        Total_Oferta=("Total Linie", "sum"),
                    )
                    .sort_values(by=["Monedă", "Total_Oferta"], ascending=[True, True])
                )
                rezumat_furn = rezumat_furn.rename(
                    columns={"Pozitii": "Nr. Poziții", "Pozitii_Cotate": "Cotate (>0)", "Total_Oferta": "Total Ofertă"}
                )
                st.markdown("**1. Total pe Furnizor & Monedă**")
                st.dataframe(rezumat_furn, hide_index=True, use_container_width=True)

                df_analiza["_fara_pret"] = df_analiza["Preț Unitar"] <= 0
                comp_pe_piesa = (
                    df_analiza.sort_values(
                        by=["Piesă", "Monedă", "_fara_pret", "Preț Unitar"],
                        ascending=[True, True, True, True],
                    )[
                        ["Piesă", "Cod Prod.", "Furnizor", "Piese înlocuitoare", "Cant.", "Preț Unitar", "Monedă", "Total Linie", "Termen livrare", "Selectat Client"]
                    ]
                )
                st.markdown("**2. Comparație detaliată pe fiecare Piesă (ordonată după cel mai mic preț cotat)**")
                st.dataframe(comp_pe_piesa, hide_index=True, use_container_width=True)


def render_cereri_oferta_furnizori_de_facut():
    if not _HAS_CERERI_REPO or CereriOfertaRepository is None:
        return

    st.session_state.setdefault("df_rfq_main_open", False)
    st.session_state.setdefault("df_rfq_sub1_open", False)
    st.session_state.setdefault("df_rfq_tbl_open", False)
    st.session_state.setdefault("df_rfq_preluare_open", False)
    st.session_state.setdefault("df_rfq_comp_open", False)

    main_open = _sync_expander_state("df_rfq_main_open", "exp_rfq_main", False)

    with st.expander(
        "📨 Cereri Ofertă Furnizori (RFQ) • Analiză Prețuri & Legătură Client / Mașină",
        expanded=main_open,
        key="exp_rfq_main",
    ):
        _fragment_cereri_oferta_furnizori()


# ---------------------------------------------------------
# SECȚIUNEA 6: ÎNTREȚINERI SCADENTE (FRAGMENT)
# ---------------------------------------------------------

@_fragment
def _fragment_memento_intretinere():
    col_z, col_info = st.columns([1.4, 3.6], vertical_alignment="bottom")
    with col_z:
        zile_avans = st.selectbox(
            "Anunță-mă cu cel puțin:",
            options=[3, 7, 14, 21, 30, 60],
            index=2,
            format_func=lambda x: f"{x} zile înainte",
            key="df_memento_intretinere_zile",
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


def render_memento_intretinere_de_facut():
    st.subheader("📅 Întrețineri Scadente")
    _fragment_memento_intretinere()


# ---------------------------------------------------------
# ENTRYPOINT PAGINĂ
# ---------------------------------------------------------

def render_de_facut():
    t0 = time.perf_counter()

    if st.session_state.get("df_toast_msg"):
        st.toast(st.session_state.pop("df_toast_msg"))

    col_title, col_refresh, col_perf = st.columns([4.4, 1.0, 0.8], vertical_alignment="center")
    with col_title:
        st.title("✅ De făcut & Activități Teren")
    with col_refresh:
        if st.button("🔄 Actualizează", use_container_width=True, key="btn_df_refresh_unic"):
            _goleste_cache_de_facut()
            _rerun_app("🔄 Datele au fost reîncărcate.")
    with col_perf:
        arat_timpi = st.checkbox("⏱️ Timpi", value=False, key="df_show_timings")

    ts_a = time.perf_counter()
    link_gdrive_global = _obtine_link_gdrive_setari()
    taskuri = _obtine_taskuri_cached()
    piese_rows = _colecteaza_piese_necesare(link_gdrive_global)
    ts_b = time.perf_counter()

    render_privire_ansamblu_de_facut(piese_rows, taskuri)
    ts_c = time.perf_counter()

    st.markdown("---")
    render_notite_vizita_de_facut(taskuri)
    render_notare_rapida_teren()
    render_tabel_piese_de_comandat(piese_rows)
    render_cereri_oferta_furnizori_de_facut()
    ts_d = time.perf_counter()

    st.markdown("---")
    render_memento_intretinere_de_facut()
    ts_e = time.perf_counter()

    if arat_timpi:
        st.caption(
            f"⏱️ Date/Cache: {(ts_b - ts_a):.2f}s | "
            f"Ansamblu: {(ts_c - ts_b):.2f}s | "
            f"Secțiuni/Formulare: {(ts_d - ts_c):.2f}s | "
            f"Întrețineri: {(ts_e - ts_d):.2f}s | "
            f"Total: {(ts_e - t0):.2f}s"
        )