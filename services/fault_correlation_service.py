
#----------------------------------------------------------
#-------services/fault_correlation_service.py--------------
#----------------------------------------------------------

import re
import streamlit as st
from repositories.documentatie_repository import DocumentatieRepository


def _tokenize_codes(raw_text: str) -> list[str]:
    """Extrage token-uri normalizate (ex: 'ALM 414, 414; SV0414' -> ['alm', '414', 'sv0414'])."""
    if not raw_text:
        return []
    parts = re.split(r"[,;\n|/]+", str(raw_text).lower())
    tokens: list[str] = []
    for p in parts:
        cleaned = re.sub(r"\s+", " ", p).strip()
        if cleaned:
            tokens.append(cleaned)
            # Adaugă și codul pur alfanumeric fără prefixe gen 'alm ' sau 'err '
            code_only = re.sub(r"^(alm|err|alarm|fault|code|al\.?|f)\s*", "", cleaned).strip()
            if code_only and code_only != cleaned:
                tokens.append(code_only)
    return list(dict.fromkeys(tokens))


def _incarca_defecte_sigure() -> list[dict]:
    """Încearcă să citească defectele/intervențiile dacă există repository-ul în proiect."""
    for mod_path, cls_name in [
        ("repositories.defecte_repository", "DefecteRepository"),
        ("repositories.interventii_repository", "InterventiiRepository"),
    ]:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            repo = getattr(mod, cls_name, None)
            if repo and hasattr(repo, "get_all"):
                res = repo.get_all()
                if isinstance(res, list):
                    return res
        except Exception:
            continue
    return []


def cauta_si_coreleaza_defect(query_cod: str, masina_id=None, tip_sistem: str = "") -> dict:
    """
    Corelează un cod HMI sau Driver/VFD cu:
    - toate codurile Driver/VFD asociate (1-la-mai-mulți),
    - documentația indexată (documentatie_tehnica),
    - istoricul de defecte/intervenții (dacă este disponibil).
    """
    q_norm = re.sub(r"\s+", " ", str(query_cod or "").strip().lower())
    q_tokens = _tokenize_codes(query_cod)
    sys_norm = str(tip_sistem or "").strip().lower()

    docs = DocumentatieRepository.get_all() or []
    defecte = _incarca_defecte_sigure()

    doc_potrivite = []
    drivere_asociate = []

    for d in docs:
        if masina_id not in (None, "", "Toate"):
            if d.get("masina_id") not in (None, int(masina_id) if str(masina_id).isdigit() else masina_id):
                continue
        if sys_norm and sys_norm not in str(d.get("tip_sistem") or "").lower():
            continue

        hmi_raw = str(d.get("coduri_eroare_hmi") or "")
        drv_raw = str(d.get("coduri_eroare_driver") or "")
        txt_raw = str(d.get("text_indexat") or "")
        titlu_raw = str(d.get("titlu") or "")

        haystack_codes = f"{hmi_raw} {drv_raw}".lower()
        haystack_all = f"{hmi_raw} {drv_raw} {titlu_raw} {txt_raw}".lower()

        match_cod = False
        if q_norm:
            if q_norm in haystack_codes or any(tok in haystack_codes for tok in q_tokens):
                match_cod = True
            elif q_norm in haystack_all or any(tok in haystack_all for tok in q_tokens):
                match_cod = True
        else:
            match_cod = True

        if match_cod:
            doc_potrivite.append(d)
            for drv_item in re.split(r"[,;\n|/]+", drv_raw):
                drv_clean = drv_item.strip()
                if drv_clean and drv_clean not in drivere_asociate:
                    drivere_asociate.append(drv_clean)

    defecte_potrivite = []
    for df in defecte:
        blob = " ".join(str(v or "") for v in df.values()).lower()
        if not q_norm or q_norm in blob or any(tok in blob for tok in q_tokens):
            defecte_potrivite.append(df)
            for drv_item in re.split(r"[,;\n|/]+", str(df.get("cod_driver") or df.get("coduri_eroare_driver") or "")):
                drv_clean = drv_item.strip()
                if drv_clean and drv_clean not in drivere_asociate:
                    drivere_asociate.append(drv_clean)

    return {
        "query": query_cod,
        "drivere_asociate": drivere_asociate,
        "documentatie": doc_potrivite,
        "defecte": defecte_potrivite,
    }