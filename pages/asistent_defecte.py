#----------------------------------------------
#--- pages/asistent_defecte.py ---------------
#----------------------------------------------

import logging
import re
import streamlit as st
from repositories.documentatie_repository import (
    DocumentatieRepository,
    TAGURI_DOCUMENTATIE,
    CATEGORII_DOCUMENTATIE,
)

# Importuri statice cu fallback controlat la nivel de modul
try:
    from repositories.firme_repository import FirmeRepository
except ImportError:
    FirmeRepository = None

try:
    from repositories.masini_repository import MasiniRepository
except ImportError:
    MasiniRepository = None

try:
    from repositories.piese_repository import PieseRepository
except ImportError:
    PieseRepository = None

try:
    from repositories.defecte_repository import DefecteRepository
except ImportError:
    DefecteRepository = None

try:
    from repositories.interventii_repository import InterventiiRepository
except ImportError:
    InterventiiRepository = None

logger = logging.getLogger(__name__)

OPT_ALEGE_FIRMA = "-- Alege firma --"
MAX_CARDURI_AFISATE = 20
MAX_DEFECTE_AFISATE = 10

PRIORITATE_TAG = {
    "[SOL]": 0,
    "[ALM]": 1,
    "[ERR]": 2,
    "[TST]": 3,
    "[PRM]": 4,
    "[SCH]": 5,
    "[MEC]": 6,
}

_PREFIX_CODE_RE = re.compile(r"^(alm|err|alarm|fault|code|al\.?|f|sv)\s*", flags=re.IGNORECASE)
_SPLIT_CODE_RE = re.compile(r"[,;\n|/]+")
_WHITESPACE_RE = re.compile(r"\s+")
_PIESE_LINE_RE = re.compile(r"^\s*piese\s*(necesare)?\s*:\s*(.+)$", flags=re.IGNORECASE)


def _normalizare_id(val):
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        s = str(val).strip()
        return s if s else None


def _extrage_nume_firma(firma: dict) -> str:
    for k in ("nume_firma", "denumire", "nume", "client"):
        val = str(firma.get(k) or "").strip()
        if val:
            return val
    fid = firma.get("id")
    return f"Firma #{fid}" if fid is not None else ""


def _extrage_firma_id_masina(masina: dict):
    for k in ("firma_id", "id_firma", "client_id"):
        nid = _normalizare_id(masina.get(k))
        if nid is not None:
            return nid
    return None


def _extrage_piese_din_item(item: dict) -> str:
    """Extrage lista de piese necesare dintr-un dicționar din documentație sau din notițe."""
    for k in ("piese_necesare", "piese", "piese_remediere"):
        val = str(item.get(k) or "").strip()
        if val:
            return val

    txt = str(item.get("text_indexat") or "")
    for line in txt.splitlines():
        m = _PIESE_LINE_RE.match(line)
        if m:
            return m.group(2).strip()
    return ""


def _tokenize_codes(raw_text: str) -> list[str]:
    """Extrage token-uri normalizate pentru potrivirea codurilor HMI și Driver/VFD."""
    if not raw_text:
        return []
    parts = _SPLIT_CODE_RE.split(str(raw_text).lower())
    tokens: list[str] = []
    for part in parts:
        cleaned = _WHITESPACE_RE.sub(" ", part).strip()
        if cleaned:
            tokens.append(cleaned)
            stripped_prefix = _PREFIX_CODE_RE.sub("", cleaned).strip()
            if stripped_prefix and stripped_prefix != cleaned:
                tokens.append(stripped_prefix)
    return list(dict.fromkeys(tokens))


def _split_coduri_lista(raw_text: str) -> list[str]:
    """Împarte un câmp cu coduri separate prin virgulă / punct și virgulă / linie nouă."""
    if not raw_text:
        return []
    items: list[str] = []
    for chunk in _SPLIT_CODE_RE.split(str(raw_text)):
        val = _WHITESPACE_RE.sub(" ", chunk).strip()
        if val and val not in items:
            items.append(val)
    return items


# =====================================================================
# 1. CACHE SEPARAT PE SURSE DE DATE + PREPROCESARE LA INCARCARE
# =====================================================================

@st.cache_data(ttl=300, show_spinner=False)
def _incarca_nomenclatoare_cached() -> tuple[dict, list[dict], list[str], list[str]]:
    """
    Încarcă și cache-uiește nomenclatoarele rare (firme, mașini, piese).
    Returnează: (firme_map, masini_lista, catalog_piese, avertismente)
    """
    avertismente: list[str] = []
    firme_map: dict = {}

    if FirmeRepository is not None and hasattr(FirmeRepository, "get_all"):
        try:
            firme_raw = FirmeRepository.get_all()
            if isinstance(firme_raw, list):
                for f in firme_raw:
                    if not isinstance(f, dict):
                        continue
                    fid = _normalizare_id(f.get("id"))
                    if fid is not None:
                        firme_map[fid] = _extrage_nume_firma(f)
        except Exception as exc:
            logger.exception("Eroare la încărcarea firmelor")
            avertismente.append(f"Nu s-au putut încărca firmele: {exc}")

    masini_lista: list[dict] = []
    if MasiniRepository is not None and hasattr(MasiniRepository, "get_all"):
        try:
            masini_raw = MasiniRepository.get_all()
            if isinstance(masini_raw, list):
                for m in masini_raw:
                    if not isinstance(m, dict):
                        continue
                    mid = _normalizare_id(m.get("id"))
                    if mid is not None:
                        den = str(m.get("denumire") or m.get("nume") or f"Mașina #{mid}").strip()
                        masini_lista.append(
                            {
                                "id": mid,
                                "denumire": den,
                                "firma_id": _extrage_firma_id_masina(m),
                            }
                        )
        except Exception as exc:
            logger.exception("Eroare la încărcarea mașinilor")
            avertismente.append(f"Nu s-au putut încărca mașinile: {exc}")

    catalog_piese: list[str] = []
    if PieseRepository is not None and hasattr(PieseRepository, "get_all"):
        try:
            piese_raw = PieseRepository.get_all()
            if isinstance(piese_raw, list):
                seen_piese: set[str] = set()
                for p in piese_raw:
                    if not isinstance(p, dict):
                        continue
                    den = str(p.get("denumire") or p.get("nume") or "").strip()
                    if den and den not in seen_piese:
                        seen_piese.add(den)
                        catalog_piese.append(den)
        except Exception as exc:
            logger.exception("Eroare la încărcarea catalogului de piese")
            avertismente.append(f"Nu s-a putut încărca catalogul de piese: {exc}")

    return firme_map, masini_lista, catalog_piese, avertismente


@st.cache_data(ttl=120, show_spinner=False)
def _incarca_documentatie_indexata_cached() -> tuple[list[dict], list[str]]:
    """
    Încarcă documentația tehnică și precalculează câmpurile normalizate o singură dată,
    evitând regex și .lower() repetat la fiecare tastare.
    """
    avertismente: list[str] = []
    rezultat: list[dict] = []

    try:
        docs_raw = DocumentatieRepository.get_all()
        if not isinstance(docs_raw, list):
            return [], avertismente
    except Exception as exc:
        logger.exception("Eroare la încărcarea documentatie_tehnica")
        return [], [f"Eroare la citirea documentației tehnice: {exc}"]

    for d in docs_raw:
        if not isinstance(d, dict):
            continue

        hmi_raw = str(d.get("coduri_eroare_hmi") or "")
        drv_raw = str(d.get("coduri_eroare_driver") or "")
        titlu_raw = str(d.get("titlu") or "")
        txt_raw = str(d.get("text_indexat") or "")
        piese_raw = _extrage_piese_din_item(d)
        tag_norm = str(d.get("tag_sectiune") or "").strip()

        item_indexat = {
            "raw": d,
            "firma_id": _normalizare_id(d.get("firma_id")),
            "masina_id": _normalizare_id(d.get("masina_id")),
            "tag_sectiune": tag_norm,
            "tip_sistem_low": str(d.get("tip_sistem") or "").lower(),
            "piese_extrase": piese_raw,
            "drv_list": _split_coduri_lista(drv_raw),
            "hmi_list": _split_coduri_lista(hmi_raw),
            "haystack_codes": f"{hmi_raw} {drv_raw}".lower(),
            "haystack_text": f"{titlu_raw} {txt_raw} {piese_raw}".lower(),
            "sort_key": (
                PRIORITATE_TAG.get(tag_norm.upper(), 9),
                titlu_raw.lower(),
            ),
        }
        rezultat.append(item_indexat)

    rezultat.sort(key=lambda x: x["sort_key"])
    return rezultat, avertismente


@st.cache_data(ttl=120, show_spinner=False)
def _incarca_defecte_indexate_cached() -> tuple[list[dict], list[str]]:
    """Încarcă și preprocesează istoricul de defecte/intervenții din primul repository disponibil."""
    avertismente: list[str] = []
    repo_activ = None

    for repo in (DefecteRepository, InterventiiRepository):
        if repo is not None and hasattr(repo, "get_all") and callable(repo.get_all):
            repo_activ = repo
            break

    if repo_activ is None:
        return [], avertismente

    try:
        raw_list = repo_activ.get_all()
        if not isinstance(raw_list, list):
            return [], avertismente
    except Exception as exc:
        logger.exception("Eroare la încărcarea istoricului de defecte")
        return [], [f"Nu s-a putut încărca istoricul de intervenții: {exc}"]

    rezultat: list[dict] = []
    for df in raw_list:
        if not isinstance(df, dict):
            continue

        drv_hist = str(df.get("cod_driver") or df.get("coduri_eroare_driver") or "")
        hmi_hist = str(df.get("cod_hmi") or df.get("coduri_eroare_hmi") or "")
        piese_df = _extrage_piese_din_item(df)
        blob = " ".join(str(v or "") for v in df.values()).lower()

        rezultat.append(
            {
                "raw": df,
                "firma_id": _normalizare_id(df.get("firma_id")),
                "masina_id": _normalizare_id(df.get("masina_id")),
                "firma_low": str(df.get("firma") or "").strip().lower(),
                "piese_extrase": piese_df,
                "drv_list": _split_coduri_lista(drv_hist),
                "hmi_list": _split_coduri_lista(hmi_hist),
                "haystack_codes": f"{hmi_hist} {drv_hist}".lower(),
                "haystack_all": blob,
            }
        )

    return rezultat, avertismente


def _invalideaza_cache_date_operationale():
    """Curăță cache-ul pentru documentație și defecte după o salvare nouă."""
    _incarca_documentatie_indexata_cached.clear()
    _incarca_defecte_indexate_cached.clear()


def _salveaza_in_defecte_istoric(payload: dict) -> tuple[bool, str | None]:
    """
    Încearcă salvarea în repository-ul de defecte/intervenții dacă există.
    Returnează (salvat_cu_succes, mesaj_eroare_optional).
    """
    repo_activ = None
    for repo in (DefecteRepository, InterventiiRepository):
        if repo is not None and hasattr(repo, "insert") and callable(repo.insert):
            repo_activ = repo
            break

    if repo_activ is None:
        return False, None  # Repository-ul opțional nu este configurat în proiect

    try:
        repo_activ.insert(payload)
        return True, None
    except Exception as exc:
        logger.exception("Eroare la salvarea în istoricul de defecte")
        return False, str(exc)


# =====================================================================
# 2. CAUTARE SI FILTRARE UNIFICATA SI RAPIDA
# =====================================================================

def _potriveste_context_echipament(
    item_fid,
    item_mid,
    fid_norm,
    mid_norm,
    masini_firma_ids: set | None,
    item_firma_low: str = "",
    firma_low: str = "",
) -> bool:
    """
    Regulă unică de filtrare după mașină și firmă pentru documentație și defecte:
    - Dacă e selectată o mașină: acceptă înregistrările acelei mașini sau generale (masina_id None).
    - Dacă e selectată o firmă: verifică firma_id, numele firmei (dacă există) sau apartenența mașinii la firmă.
    """
    if mid_norm is not None:
        return item_mid in (None, mid_norm)

    if fid_norm is not None:
        if item_fid is not None:
            return item_fid == fid_norm
        if item_firma_low and firma_low:
            return firma_low in item_firma_low
        if item_mid is not None and masini_firma_ids is not None:
            return item_mid in masini_firma_ids
        # Înregistrare generală (fără firmă și fără mașină asociată)
        return True

    return True


def _potriveste_query(q_norm: str, q_tokens: list[str], haystack_codes: str, haystack_text: str) -> tuple[bool, int]:
    """
    Separă potrivirea pe coduri (prioritate 0) de potrivirea în textul lung (prioritate 1).
    Returnează (este_potrivire, scor_relevanta).
    """
    if not q_norm:
        return True, 0

    if q_norm in haystack_codes or any(tok in haystack_codes for tok in q_tokens):
        return True, 0

    if q_norm in haystack_text or any(tok in haystack_text for tok in q_tokens):
        return True, 1

    return False, 99


def cauta_si_coreleaza(
    docs_indexate: list[dict],
    defecte_indexate: list[dict],
    query_cod: str,
    firma_id=None,
    nume_firma: str = "",
    masina_id=None,
    masini_firma_ids: set | None = None,
    tip_sistem: str = "",
    filtru_tag: str = "Toate",
) -> dict:
    """
    Corelează un cod HMI sau Driver/VFD (relație 1-la-mai-mulți) pe structurile preindexate.
    Nu mută listele primite din cache.
    """
    q_norm = _WHITESPACE_RE.sub(" ", str(query_cod or "").strip().lower())
    q_tokens = _tokenize_codes(query_cod)
    sys_norm = str(tip_sistem or "").strip().lower()
    fid_norm = _normalizare_id(firma_id)
    mid_norm = _normalizare_id(masina_id)
    firma_low = str(nume_firma or "").strip().lower()

    doc_candidate: list[tuple[int, dict]] = []
    drivere_seen: set[str] = set()
    drivere_asociate: list[str] = []
    hmi_seen: set[str] = set()
    hmi_asociate: list[str] = []

    for entry in docs_indexate:
        if filtru_tag != "Toate" and entry["tag_sectiune"] != filtru_tag:
            continue

        if not _potriveste_context_echipament(
            item_fid=entry["firma_id"],
            item_mid=entry["masina_id"],
            fid_norm=fid_norm,
            mid_norm=mid_norm,
            masini_firma_ids=masini_firma_ids,
        ):
            continue

        if sys_norm and sys_norm not in entry["tip_sistem_low"]:
            continue

        is_match, match_rank = _potriveste_query(
            q_norm=q_norm,
            q_tokens=q_tokens,
            haystack_codes=entry["haystack_codes"],
            haystack_text=entry["haystack_text"],
        )

        if is_match:
            doc_candidate.append((match_rank, entry))
            for drv_code in entry["drv_list"]:
                if drv_code not in drivere_seen:
                    drivere_seen.add(drv_code)
                    drivere_asociate.append(drv_code)
            for hmi_code in entry["hmi_list"]:
                if hmi_code not in hmi_seen:
                    hmi_seen.add(hmi_code)
                    hmi_asociate.append(hmi_code)

    # Sortare pe copie nouă: mai întâi potrivire exactă pe coduri (rank 0), apoi prioritatea tag-ului
    doc_candidate.sort(key=lambda pair: (pair[0], pair[1]["sort_key"]))
    doc_potrivite = [pair[1] for pair in doc_candidate]

    defecte_potrivite: list[dict] = []
    for df_entry in defecte_indexate:
        if not _potriveste_context_echipament(
            item_fid=df_entry["firma_id"],
            item_mid=df_entry["masina_id"],
            fid_norm=fid_norm,
            mid_norm=mid_norm,
            masini_firma_ids=masini_firma_ids,
            item_firma_low=df_entry["firma_low"],
            firma_low=firma_low,
        ):
            continue

        is_match, _ = _potriveste_query(
            q_norm=q_norm,
            q_tokens=q_tokens,
            haystack_codes=df_entry["haystack_codes"],
            haystack_text=df_entry["haystack_all"],
        )

        if is_match:
            defecte_potrivite.append(df_entry)
            for drv_code in df_entry["drv_list"]:
                if drv_code not in drivere_seen:
                    drivere_seen.add(drv_code)
                    drivere_asociate.append(drv_code)
            for hmi_code in df_entry["hmi_list"]:
                if hmi_code not in hmi_seen:
                    hmi_seen.add(hmi_code)
                    hmi_asociate.append(hmi_code)

    return {
        "query": query_cod,
        "drivere_asociate": drivere_asociate,
        "hmi_asociate": hmi_asociate,
        "documentatie": doc_potrivite,
        "defecte": defecte_potrivite,
    }


# =====================================================================
# 3. RANDARE UI USOARA SI STABILA
# =====================================================================

def _render_card_documentatie(entry: dict, idx: int, masini_map: dict):
    """Randează o înregistrare folosind componente native rapide (fără HTML inline greu)."""
    item = entry["raw"]
    tag = entry["tag_sectiune"] or "[ERR]"
    titlu = str(item.get("titlu") or "Fără titlu").strip()
    sistem = str(item.get("tip_sistem") or item.get("categorie") or "").strip()
    hmi_txt = str(item.get("coduri_eroare_hmi") or "").strip()
    pag_txt = str(item.get("interval_pagini") or "").strip()
    drv_txt = str(item.get("coduri_eroare_driver") or "").strip()
    piese_txt = entry["piese_extrase"]
    txt_idx = str(item.get("text_indexat") or "").strip()
    url_drv = str(item.get("gdrive_url") or "").strip()
    m_id = entry["masina_id"]
    m_nume = masini_map.get(m_id, f"Mașina #{m_id}") if m_id is not None else "General"

    titlu_expander = f"{tag} {titlu} — [{sistem}] • {m_nume}" if sistem else f"{tag} {titlu} • {m_nume}"
    with st.expander(titlu_expander, expanded=(idx == 0)):
        if hmi_txt or pag_txt:
            col_hmi, col_pag = st.columns(2)
            with col_hmi:
                if hmi_txt:
                    st.markdown(f"🚨 **Cod HMI:** `{hmi_txt}`")
            with col_pag:
                if pag_txt:
                    st.markdown(f"📄 **Pagina / Interval:** `{pag_txt}`")

        if drv_txt:
            st.markdown(f"**🔌 Coduri Driver / VFD:** `{drv_txt}`")
        if piese_txt:
            st.markdown(f"**🔩 Piese necesare remediere:** {piese_txt}")
        if txt_idx:
            st.markdown(f"**📝 Notițe / Text indexat:**\n\n{txt_idx}")
        if url_drv:
            if pag_txt:
                st.markdown(f"🔗 [Deschide fișierul în Google Drive]({url_drv}) — **Mergi la: `{pag_txt}`**")
            else:
                st.markdown(f"🔗 [Deschide fișierul în Google Drive]({url_drv})")
        else:
            st.caption("Nu este setat link Google Drive pentru această înregistrare.")


def _render_formular_salvare_solutie(
    cod_initial: str,
    drivere_sugerate: list[str],
    firme_map: dict,
    masini_disponibile: list[dict],
    catalog_piese: list[str],
    firma_selectata=None,
    masina_selectata=None,
) -> bool:
    """
    Salvează soluția fără st.rerun().
    Returnează True dacă s-a salvat o înregistrare nouă în acest ciclu de rulare,
    astfel încât pagina să reîncarce datele proaspete imediat în același run.
    """
    salvat_acum = False

    with st.expander("💾 Salvează intervenție / soluție nouă (`[SOL]`) în index", expanded=False):
        masini_map_loc = {m["id"]: m["denumire"] for m in masini_disponibile}
        opt_masini = ["", *masini_map_loc.keys()]
        idx_m_def = opt_masini.index(masina_selectata) if masina_selectata in opt_masini else 0

        opt_firme = ["", *firme_map.keys()]
        idx_f_def = opt_firme.index(firma_selectata) if firma_selectata in opt_firme else 0

        drv_default = ", ".join(drivere_sugerate)

        with st.form("form_salvare_solutie_asistent", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                titlu_sol = st.text_input(
                    "Titlu defect / soluție *",
                    placeholder="ex: Eroare 414 / AL.24 — Cablu encoder axa X întrerupt",
                )
            with c2:
                firma_sol = st.selectbox(
                    "Firmă",
                    options=opt_firme,
                    index=idx_f_def,
                    format_func=lambda x: "— General —" if x == "" else firme_map.get(x, f"#{x}"),
                )

            c2b, c3, c4 = st.columns([1.4, 1.2, 1.4])
            with c2b:
                masina_sel = st.selectbox(
                    "Utilaj",
                    options=opt_masini,
                    index=idx_m_def,
                    format_func=lambda x: "— General —" if x == "" else masini_map_loc.get(x, f"#{x}"),
                )
            with c3:
                categorie_sol = st.selectbox("Categorie", options=list(CATEGORII_DOCUMENTATIE), index=0)
            with c4:
                sistem_sol = st.text_input("Sistem / Driver / VFD", placeholder="ex: Fanuc / Sinamics")

            c5, c6, c7 = st.columns([1.2, 1, 1])
            with c5:
                pag_sol = st.text_input("Pagina / Interval de referință", placeholder="ex: pag. 118 sau p1101-p1450")
            with c6:
                cod_hmi_sol = st.text_input("Cod eroare HMI", value=cod_initial or "")
            with c7:
                cod_drv_sol = st.text_input("Cod eroare Driver / VFD", value=drv_default)

            p_col1, p_col2 = st.columns([1.4, 1.6])
            with p_col1:
                piese_catalog_sel = st.multiselect(
                    "Piese din nomenclator (opțional)",
                    options=catalog_piese,
                    placeholder="Alege piese existente...",
                )
            with p_col2:
                piese_text_extra = st.text_input(
                    "Alte piese necesare / cantități (text liber)",
                    placeholder="ex: Cablu encoder 5m (1 buc), Siguranță 10A (2 buc)",
                )

            url_sol = st.text_input(
                "Link Google Drive (manual / schemă / poză)",
                placeholder="https://drive.google.com/file/d/.../view",
            )
            descriere_sol = st.text_area(
                "Cauză găsită, măsurători și remediere aplicată *",
                height=110,
                placeholder="Notează ce ai măsurat, ce cod sub-eroare a dat driverul/VFD-ul și cum s-a rezolvat...",
            )

            if st.form_submit_button("💾 Salvează soluția în index", type="primary"):
                titlu_clean = str(titlu_sol or "").strip()
                descriere_clean = str(descriere_sol or "").strip()

                # Validare câmpuri obligatorii înainte de scriere
                if not titlu_clean or not descriere_clean:
                    st.warning("⚠️ Completează câmpurile obligatorii: **Titlu defect / soluție** și **Cauză / remediere**.")
                else:
                    fid_val = None if firma_sol == "" else _normalizare_id(firma_sol)
                    mid_val = None if masina_sel == "" else _normalizare_id(masina_sel)

                    parti_piese = list(piese_catalog_sel)
                    if str(piese_text_extra or "").strip():
                        parti_piese.append(str(piese_text_extra).strip())
                    piese_finale_txt = ", ".join(dict.fromkeys(parti_piese))

                    text_complet = descriere_clean
                    if piese_finale_txt and "piese necesare:" not in text_complet.lower():
                        text_complet = f"{text_complet}\n\nPiese necesare: {piese_finale_txt}".strip()

                    # 1. Salvare principală în DocumentatieRepository
                    try:
                        DocumentatieRepository.insert(
                            {
                                "firma_id": fid_val,
                                "masina_id": mid_val,
                                "categorie": categorie_sol,
                                "tip_sistem": str(sistem_sol or "").strip(),
                                "titlu": titlu_clean,
                                "gdrive_file_id": "",
                                "gdrive_url": str(url_sol or "").strip(),
                                "tip_fisier": "doc",
                                "tag_sectiune": "[SOL]",
                                "interval_pagini": str(pag_sol or "").strip(),
                                "coduri_eroare_hmi": str(cod_hmi_sol or "").strip(),
                                "coduri_eroare_driver": str(cod_drv_sol or "").strip(),
                                "piese_necesare": piese_finale_txt,
                                "text_indexat": text_complet,
                            }
                        )
                    except Exception as exc:
                        logger.exception("Eroare la inserarea în DocumentatieRepository")
                        st.error(f"Eroare la salvarea în indexul de documentație: {exc}")
                        return False

                    # 2. Salvare secundară separată în istoricul de defecte
                    ist_ok, ist_err = _salveaza_in_defecte_istoric(
                        {
                            "firma_id": fid_val,
                            "firma": firme_map.get(fid_val, "") if fid_val is not None else "",
                            "masina_id": mid_val,
                            "titlu": titlu_clean,
                            "cod_hmi": str(cod_hmi_sol or "").strip(),
                            "cod_driver": str(cod_drv_sol or "").strip(),
                            "piese_necesare": piese_finale_txt,
                            "solutie": descriere_clean,
                            "link_documentatie": str(url_sol or "").strip(),
                        }
                    )

                    # 3. Invalidare cache + mesaj în session_state (fără st.rerun)
                    _invalideaza_cache_date_operationale()
                    salvat_acum = True

                    if ist_err:
                        st.session_state["asistent_defecte_flash"] = (
                            "warning",
                            f"✅ Soluția a fost salvată în indexul principal, dar istoricul secundar nu a putut fi actualizat: {ist_err}",
                        )
                    else:
                        msg_extra = " și în istoricul de intervenții" if ist_ok else ""
                        st.session_state["asistent_defecte_flash"] = (
                            "success",
                            f"✅ Soluția (`[SOL]`) și piesele necesare au fost salvate în index{msg_extra}.",
                        )

    return salvat_acum


def render_page():
    st.markdown("## 🛠️ Asistent Căutare & Corelare Defecte (HMI ↔ Driver/VFD)")
    st.caption(
        "Corelează o alarmă de pe HMI sau un cod de Driver / VFD cu toate codurile subordonate (1-la-mai-mulți), "
        "piesele necesare pentru remediere, secțiunile indexate ([ERR], [ALM], [SOL], [SCH], [PRM], [TST], [MEC]) "
        "și intervențiile anterioare."
    )

    # Afișează eventualul mesaj de confirmare din ciclul anterior și curăță-l
    flash = st.session_state.pop("asistent_defecte_flash", None)
    if flash:
        nivel, mesaj = flash
        if nivel == "warning":
            st.warning(mesaj)
        else:
            st.success(mesaj)

    # Încărcare din cache separat
    firme_map, toate_masini, catalog_piese, warn_nom = _incarca_nomenclatoare_cached()
    docs_indexate, warn_docs = _incarca_documentatie_indexata_cached()
    defecte_indexate, warn_def = _incarca_defecte_indexate_cached()

    for w in (*warn_nom, *warn_docs, *warn_def):
        st.warning(w)

    masini_map_toate = {m["id"]: m["denumire"] for m in toate_masini}

    # --- BARA DE CAUTARE PRINCIPALA ---
    c1, c2, c3, c4, c5 = st.columns([2.2, 1.3, 1.3, 1.2, 1.1])
    with c1:
        cod_cautat = st.text_input(
            "Cod eroare HMI sau Driver / VFD",
            placeholder="ex: 414, ALM 414, AL.24, F30002, OC1...",
            key="asistent_defecte_q",
        )
    with c2:
        opt_firme_bar = [OPT_ALEGE_FIRMA, *firme_map.keys()]
        if st.session_state.get("asistent_defecte_firma") not in opt_firme_bar:
            st.session_state["asistent_defecte_firma"] = OPT_ALEGE_FIRMA
        firma_sel = st.selectbox(
            "Firmă",
            options=opt_firme_bar,
            format_func=lambda x: OPT_ALEGE_FIRMA if x == OPT_ALEGE_FIRMA else firme_map.get(x, f"#{x}"),
            key="asistent_defecte_firma",
        )

    firma_activa_id = None if firma_sel == OPT_ALEGE_FIRMA else _normalizare_id(firma_sel)
    nume_firma_activa = firme_map.get(firma_activa_id, "") if firma_activa_id is not None else ""

    if firma_activa_id is not None:
        masini_filtrate = [m for m in toate_masini if m.get("firma_id") == firma_activa_id]
    else:
        masini_filtrate = toate_masini

    masini_firma_ids = {m["id"] for m in masini_filtrate}
    masini_filtrate_map = {m["id"]: m["denumire"] for m in masini_filtrate}
    opt_masini_bar = ["Toate", *masini_filtrate_map.keys()]

    # Sincronizare stare mașină înainte de randarea selectbox-ului (fără rerun)
    if st.session_state.get("asistent_defecte_masina") not in opt_masini_bar:
        st.session_state["asistent_defecte_masina"] = "Toate"

    with c3:
        filtru_masina = st.selectbox(
            "Mașină",
            options=opt_masini_bar,
            format_func=lambda x: "Toate mașinile" if x == "Toate" else masini_filtrate_map.get(x, f"#{x}"),
            key="asistent_defecte_masina",
        )
    with c4:
        filtru_sistem = st.text_input(
            "Sistem / VFD",
            placeholder="ex: Fanuc, Sinamics...",
            key="asistent_defecte_sistem",
        )
    with c5:
        filtru_tag = st.selectbox(
            "Tag",
            options=["Toate", *TAGURI_DOCUMENTATIE],
            key="asistent_defecte_tag",
        )

    # --- 4. FORMULAR SALVARE (evaluat înaintea afișării rezultatelor ca să reflecte imediat o salvare nouă fără st.rerun) ---
    # Pregătim sugerarea driverelor din starea curentă înainte de randarea formularului
    rezultat = cauta_si_coreleaza(
        docs_indexate=docs_indexate,
        defecte_indexate=defecte_indexate,
        query_cod=cod_cautat,
        firma_id=firma_activa_id,
        nume_firma=nume_firma_activa,
        masina_id=None if filtru_masina == "Toate" else filtru_masina,
        masini_firma_ids=masini_firma_ids if firma_activa_id is not None else None,
        tip_sistem=filtru_sistem,
        filtru_tag=filtru_tag,
    )

    st.markdown("---")
    salvat_nou = _render_formular_salvare_solutie(
        cod_initial=cod_cautat,
        drivere_sugerate=rezultat["drivere_asociate"],
        firme_map=firme_map,
        masini_disponibile=masini_filtrate,
        catalog_piese=catalog_piese,
        firma_selectata=firma_activa_id,
        masina_selectata=None if filtru_masina == "Toate" else _normalizare_id(filtru_masina),
    )

    # Dacă tocmai s-a salvat o soluție în acest run, reîncărcăm doar datele proaspete (cache-ul a fost invalidat)
    if salvat_nou:
        flash_now = st.session_state.pop("asistent_defecte_flash", None)
        if flash_now:
            nivel, mesaj = flash_now
            st.warning(mesaj) if nivel == "warning" else st.success(mesaj)

        docs_indexate, _ = _incarca_documentatie_indexata_cached()
        defecte_indexate, _ = _incarca_defecte_indexate_cached()
        rezultat = cauta_si_coreleaza(
            docs_indexate=docs_indexate,
            defecte_indexate=defecte_indexate,
            query_cod=cod_cautat,
            firma_id=firma_activa_id,
            nume_firma=nume_firma_activa,
            masina_id=None if filtru_masina == "Toate" else filtru_masina,
            masini_firma_ids=masini_firma_ids if firma_activa_id is not None else None,
            tip_sistem=filtru_sistem,
            filtru_tag=filtru_tag,
        )

    st.markdown("---")

    # --- 1. CORELARE 1-LA-MAI-MULTI: CODURI DRIVER / VFD SI HMI ASOCIATE ---
    col_map1, col_map2 = st.columns([1.4, 1])
    with col_map1:
        st.markdown("### 🔌 Coduri Driver / VFD corelate (1-la-mai-mulți)")
        drivere = rezultat["drivere_asociate"]
        if drivere:
            cols_drv = st.columns(min(3, len(drivere)))
            for idx, drv in enumerate(drivere):
                with cols_drv[idx % len(cols_drv)]:
                    st.info(f"**Driver / VFD:** `{drv}`")
        else:
            st.caption("Niciun cod Driver / VFD distinct găsit pentru criteriile actuale.")

    with col_map2:
        st.markdown("### 🚨 Coduri HMI asociate")
        hmi_list = rezultat["hmi_asociate"]
        if hmi_list:
            st.write(" • ".join(f"`{h}`" for h in hmi_list[:12]))
        else:
            st.caption("Niciun cod HMI găsit.")

    st.markdown("---")

    # --- 2. DOCUMENTATIE TEHNICA RELEVANTA ---
    docs = rezultat["documentatie"]
    st.markdown(f"### 📚 Documentație tehnică găsită ({len(docs)})")

    if docs:
        for idx, entry in enumerate(docs[:MAX_CARDURI_AFISATE]):
            _render_card_documentatie(entry, idx=idx, masini_map=masini_map_toate)
        if len(docs) > MAX_CARDURI_AFISATE:
            st.caption(f"Se afișează primele {MAX_CARDURI_AFISATE} rezultate din {len(docs)}. Restrânge căutarea pentru mai multă precizie.")
    else:
        st.warning(
            "Nu s-au găsit înregistrări în `documentatie_tehnica` pentru această căutare. "
            "Poți verifica în pagina **Index & Căutare Docs (GDrive)** sau poți salva o soluție nouă mai sus."
        )

    # --- 3. ISTORIC DEFECTE / INTERVENTII (DACA EXISTA) ---
    if rezultat["defecte"]:
        st.markdown("---")
        st.markdown(f"### 🧾 Defecte / Intervenții anterioare ({len(rezultat['defecte'])})")
        for df_entry in rezultat["defecte"][:MAX_DEFECTE_AFISATE]:
            df = df_entry["raw"]
            titlu_df = df.get("titlu") or df.get("cod_hmi") or df.get("cod_driver") or "Intervenție"
            detalii_df = df.get("solutie") or df.get("observatii") or df.get("descriere") or ""
            piese_df = df_entry["piese_extrase"]
            linie = f"- **{titlu_df}** — {detalii_df}"
            if piese_df:
                linie += f" *(🔩 Piese: {piese_df})*"
            st.markdown(linie)