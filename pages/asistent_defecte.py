#----------------------------------------------
#--- pages/asistent_defecte.py ---------------
#----------------------------------------------

import re
import streamlit as st
from repositories.documentatie_repository import (
    DocumentatieRepository,
    TAGURI_DOCUMENTATIE,
    CATEGORII_DOCUMENTATIE,
)


def _incarca_lista_masini() -> dict[int, str]:
    """Încarcă utilajele din baza de date dacă este disponibil MasiniRepository."""
    try:
        from repositories.masini_repository import MasiniRepository

        masini = MasiniRepository.get_all() or []
        return {
            int(m["id"]): str(m.get("denumire") or m.get("nume") or f"Mașina #{m['id']}")
            for m in masini
            if m.get("id") is not None
        }
    except Exception:
        return {}


def _incarca_defecte_istoric() -> list[dict]:
    """Încarcă defectele/intervențiile dacă există repository-ul în proiect."""
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


def _salveaza_in_defecte_istoric(payload: dict) -> bool:
    """Încearcă salvarea în repository-ul de defecte/intervenții dacă există."""
    for mod_path, cls_name in [
        ("repositories.defecte_repository", "DefecteRepository"),
        ("repositories.interventii_repository", "InterventiiRepository"),
    ]:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            repo = getattr(mod, cls_name, None)
            if repo and hasattr(repo, "insert"):
                repo.insert(payload)
                return True
        except Exception:
            continue
    return False


def _tokenize_codes(raw_text: str) -> list[str]:
    """Extrage token-uri normalizate pentru potrivirea codurilor HMI și Driver/VFD."""
    if not raw_text:
        return []
    parts = re.split(r"[,;\n|/]+", str(raw_text).lower())
    tokens: list[str] = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip()
        if cleaned:
            tokens.append(cleaned)
            stripped_prefix = re.sub(
                r"^(alm|err|alarm|fault|code|al\.?|f|sv)\s*", "", cleaned
            ).strip()
            if stripped_prefix and stripped_prefix != cleaned:
                tokens.append(stripped_prefix)
    return list(dict.fromkeys(tokens))


def _split_coduri_lista(raw_text: str) -> list[str]:
    """Împarte un câmp cu coduri separate prin virgulă / punct și virgulă / linie nouă."""
    if not raw_text:
        return []
    items: list[str] = []
    for chunk in re.split(r"[,;\n|/]+", str(raw_text)):
        val = re.sub(r"\s+", " ", chunk).strip()
        if val and val not in items:
            items.append(val)
    return items


def cauta_si_coreleaza(
    query_cod: str,
    masina_id=None,
    tip_sistem: str = "",
    filtru_tag: str = "Toate",
) -> dict:
    """
    Corelează un cod HMI sau Driver/VFD (relație 1-la-mai-mulți) cu:
    - toate codurile Driver/VFD asociate,
    - toate codurile HMI asociate (dacă se caută după Driver/VFD),
    - secțiunile indexate din documentatie_tehnica,
    - istoricul de defecte/intervenții (dacă există).
    """
    q_norm = re.sub(r"\s+", " ", str(query_cod or "").strip().lower())
    q_tokens = _tokenize_codes(query_cod)
    sys_norm = str(tip_sistem or "").strip().lower()

    docs = DocumentatieRepository.get_all() or []
    defecte = _incarca_defecte_istoric()

    doc_potrivite: list[dict] = []
    drivere_asociate: list[str] = []
    hmi_asociate: list[str] = []

    for d in docs:
        if filtru_tag != "Toate" and d.get("tag_sectiune") != filtru_tag:
            continue
        if masina_id not in (None, "", "Toate"):
            if d.get("masina_id") not in (
                None,
                int(masina_id) if str(masina_id).isdigit() else masina_id,
            ):
                continue
        if sys_norm and sys_norm not in str(d.get("tip_sistem") or "").lower():
            continue

        hmi_raw = str(d.get("coduri_eroare_hmi") or "")
        drv_raw = str(d.get("coduri_eroare_driver") or "")
        titlu_raw = str(d.get("titlu") or "")
        txt_raw = str(d.get("text_indexat") or "")

        haystack_codes = f"{hmi_raw} {drv_raw}".lower()
        haystack_all = f"{hmi_raw} {drv_raw} {titlu_raw} {txt_raw}".lower()

        is_match = False
        if not q_norm:
            is_match = True
        elif q_norm in haystack_codes or any(tok in haystack_codes for tok in q_tokens):
            is_match = True
        elif q_norm in haystack_all or any(tok in haystack_all for tok in q_tokens):
            is_match = True

        if is_match:
            doc_potrivite.append(d)
            for drv_code in _split_coduri_lista(drv_raw):
                if drv_code not in drivere_asociate:
                    drivere_asociate.append(drv_code)
            for hmi_code in _split_coduri_lista(hmi_raw):
                if hmi_code not in hmi_asociate:
                    hmi_asociate.append(hmi_code)

    defecte_potrivite: list[dict] = []
    for df in defecte:
        blob = " ".join(str(v or "") for v in df.values()).lower()
        if not q_norm or q_norm in blob or any(tok in blob for tok in q_tokens):
            defecte_potrivite.append(df)
            drv_hist = df.get("cod_driver") or df.get("coduri_eroare_driver") or ""
            for drv_code in _split_coduri_lista(str(drv_hist)):
                if drv_code not in drivere_asociate:
                    drivere_asociate.append(drv_code)
            hmi_hist = df.get("cod_hmi") or df.get("coduri_eroare_hmi") or ""
            for hmi_code in _split_coduri_lista(str(hmi_hist)):
                if hmi_code not in hmi_asociate:
                    hmi_asociate.append(hmi_code)

    # Sortare: întâi [ERR] și [SOL], apoi restul tag-urilor
    prioritate_tag = {"[ERR]": 0, "[SOL]": 1, "[TST]": 2, "[PRM]": 3, "[SCH]": 4, "[MEC]": 5}
    doc_potrivite.sort(
        key=lambda x: (
            prioritate_tag.get(str(x.get("tag_sectiune") or "").upper(), 9),
            str(x.get("titlu") or "").lower(),
        )
    )

    return {
        "query": query_cod,
        "drivere_asociate": drivere_asociate,
        "hmi_asociate": hmi_asociate,
        "documentatie": doc_potrivite,
        "defecte": defecte_potrivite,
    }


def _render_card_documentatie(item: dict, idx: int, masini_map: dict[int, str]):
    """Randează o înregistrare din documentatie_tehnica cu codul HMI și pagina/intervalul evidențiate."""
    tag = str(item.get("tag_sectiune") or "[ERR]").strip()
    titlu = str(item.get("titlu") or "Fără titlu").strip()
    sistem = str(item.get("tip_sistem") or item.get("categorie") or "").strip()
    hmi_txt = str(item.get("coduri_eroare_hmi") or "").strip()
    pag_txt = str(item.get("interval_pagini") or "").strip()
    drv_txt = str(item.get("coduri_eroare_driver") or "").strip()
    txt_idx = str(item.get("text_indexat") or "").strip()
    url_drv = str(item.get("gdrive_url") or "").strip()
    m_id = item.get("masina_id")
    m_nume = masini_map.get(int(m_id), f"Mașina #{m_id}") if m_id is not None else "General"

    titlu_expander = f"{tag} {titlu} — [{sistem}] • {m_nume}"
    with st.expander(titlu_expander, expanded=(idx == 0)):
        if hmi_txt or pag_txt:
            st.markdown(
                f"""
                <div style="display:flex; gap:24px; flex-wrap:wrap; align-items:center; padding:6px 10px; border-radius:8px; background:rgba(128,128,128,0.12); margin-bottom:10px;">
                    {f'<div style="font-size:1.15rem; font-weight:700;">🚨 Cod HMI: <span style="font-size:1.35rem; color:#ff6b6b;">{hmi_txt}</span></div>' if hmi_txt else ''}
                    {f'<div style="font-size:1.15rem; font-weight:700;">📄 Pagina / Interval: <span style="font-size:1.35rem; color:#4dabf7;">{pag_txt}</span></div>' if pag_txt else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

        if drv_txt:
            st.markdown(f"**🔌 Coduri Driver / VFD:** `{drv_txt}`")
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
    masini_map: dict[int, str],
):
    """Permite salvarea rapidă a unui defect rezolvat / soluții direct în index (tag [SOL])."""
    with st.expander("💾 Salvează intervenție / soluție nouă (`[SOL]`) în index", expanded=False):
        opt_masini = ["", *masini_map.keys()]
        drv_default = ", ".join(drivere_sugerate)

        with st.form("form_salvare_solutie_asistent", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                titlu_sol = st.text_input(
                    "Titlu defect / soluție *",
                    placeholder="ex: Eroare 414 / AL.24 — Cablu encoder axa X întrerupt",
                )
            with c2:
                masina_sel = st.selectbox(
                    "Utilaj",
                    options=opt_masini,
                    format_func=lambda x: "— General —" if x == "" else masini_map.get(x, f"#{x}"),
                )

            c3, c4, c5 = st.columns([1.2, 1.4, 1.4])
            with c3:
                categorie_sol = st.selectbox("Categorie", options=list(CATEGORII_DOCUMENTATIE), index=0)
            with c4:
                sistem_sol = st.text_input("Sistem / Driver / VFD", placeholder="ex: Fanuc / Sinamics")
            with c5:
                pag_sol = st.text_input("Pagina / Interval de referință", placeholder="ex: pag. 118 sau p1101-p1450")

            c6, c7 = st.columns([1, 1])
            with c6:
                cod_hmi_sol = st.text_input("Cod eroare HMI", value=cod_initial or "")
            with c7:
                cod_drv_sol = st.text_input("Cod eroare Driver / VFD", value=drv_default)

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
                try:
                    DocumentatieRepository.insert({
                        "masina_id": None if masina_sel == "" else int(masina_sel),
                        "categorie": categorie_sol,
                        "tip_sistem": sistem_sol,
                        "titlu": titlu_sol,
                        "gdrive_file_id": "",
                        "gdrive_url": url_sol,
                        "tip_fisier": "doc",
                        "tag_sectiune": "[SOL]",
                        "interval_pagini": pag_sol,
                        "coduri_eroare_hmi": cod_hmi_sol,
                        "coduri_eroare_driver": cod_drv_sol,
                        "text_indexat": descriere_sol,
                    })
                    _salveaza_in_defecte_istoric({
                        "masina_id": None if masina_sel == "" else int(masina_sel),
                        "titlu": titlu_sol,
                        "cod_hmi": cod_hmi_sol,
                        "cod_driver": cod_drv_sol,
                        "solutie": descriere_sol,
                        "link_documentatie": url_sol,
                    })
                    st.success("✅ Soluția (`[SOL]`) a fost salvată în indexul de documentație.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Eroare la salvare: {e}")


def render_page():
    st.markdown("## 🛠️ Asistent Căutare & Corelare Defecte (HMI ↔ Driver/VFD)")
    st.caption(
        "Corelează o alarmă de pe HMI sau un cod de Driver / VFD cu toate codurile subordonate (1-la-mai-mulți), "
        "secțiunile indexate ([ERR], [SCH], [PRM], [TST], [MEC], [SOL]) și intervențiile anterioare."
    )

    masini_map = _incarca_lista_masini()

    # --- BARA DE CAUTARE PRINCIPALA ---
    c1, c2, c3, c4 = st.columns([2.4, 1.4, 1.4, 1.2])
    with c1:
        cod_cautat = st.text_input(
            "Cod eroare HMI sau Driver / VFD",
            placeholder="ex: 414, ALM 414, AL.24, F30002, OC1...",
            key="asistent_defecte_q",
        )
    with c2:
        filtru_masina = st.selectbox(
            "Utilaj",
            options=["Toate", *masini_map.keys()],
            format_func=lambda x: "Toate utilajele" if x == "Toate" else masini_map.get(x, f"#{x}"),
            key="asistent_defecte_masina",
        )
    with c3:
        filtru_sistem = st.text_input(
            "Sistem / VFD",
            placeholder="ex: Fanuc, Sinamics...",
            key="asistent_defecte_sistem",
        )
    with c4:
        filtru_tag = st.selectbox(
            "Filtru Tag",
            options=["Toate", *TAGURI_DOCUMENTATIE],
            key="asistent_defecte_tag",
        )

    rezultat = cauta_si_coreleaza(
        query_cod=cod_cautat,
        masina_id=filtru_masina,
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
        for idx, item in enumerate(docs[:20]):
            _render_card_documentatie(item, idx=idx, masini_map=masini_map)
    else:
        st.warning(
            "Nu s-au găsit înregistrări în `documentatie_tehnica` pentru această căutare. "
            "Poți verifica în pagina **Documentație GDrive** sau poți salva o soluție nouă mai jos."
        )

    # --- 3. ISTORIC DEFECTE / INTERVENTII (DACA EXISTA) ---
    if rezultat["defecte"]:
        st.markdown("---")
        st.markdown(f"### 🧾 Defecte / Intervenții anterioare ({len(rezultat['defecte'])})")
        for df in rezultat["defecte"][:10]:
            titlu_df = df.get("titlu") or df.get("cod_hmi") or df.get("cod_driver") or "Intervenție"
            detalii_df = df.get("solutie") or df.get("observatii") or df.get("descriere") or ""
            st.markdown(f"- **{titlu_df}** — {detalii_df}")

    # --- 4. SALVARE RAPIDA SOLUTIE ---
    st.markdown("---")
    _render_formular_salvare_solutie(
        cod_initial=cod_cautat,
        drivere_sugerate=rezultat["drivere_asociate"],
        masini_map=masini_map,
    )