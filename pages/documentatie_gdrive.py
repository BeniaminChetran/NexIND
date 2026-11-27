# ----------------------------------------------
# --- pages/documentatie_gdrive.py -------------
# ----------------------------------------------

import html
import pandas as pd
import streamlit as st

from repositories.documentatie_repository import (
    DocumentatieRepository,
    TAGURI_DOCUMENTATIE,
    CATEGORII_DOCUMENTATIE,
)
from services.gdrive_service import (
    extrage_drive_id,
    listeaza_fisiere_folder,
    extrage_text_pdf_drive,
)

OPT_TIP_FISIER = ["pdf", "img", "folder", "doc"]

# Cheile widget-urilor din formularul de adăugare
FORM_KEYS = {
    "titlu": "doc_form_titlu",
    "categorie": "doc_form_categorie",
    "tip_sistem": "doc_form_tip_sistem",
    "masina": "doc_form_masina",
    "tag": "doc_form_tag",
    "pagini": "doc_form_pagini",
    "tip_fisier": "doc_form_tip_fisier",
    "url": "doc_form_url",
    "drive_id": "doc_form_drive_id",
    "cod_hmi": "doc_form_cod_hmi",
    "cod_driver": "doc_form_cod_driver",
    "text": "doc_form_text",
}


# =========================================================
# 1. CACHING PENTRU CITIRI RAPIDE DIN BAZA DE DATE
# =========================================================

@st.cache_data(ttl=300, show_spinner=False)
def _incarca_lista_masini_scurta() -> dict[int, str]:
    """Returnează {id_masina: denumire} cu cache de 5 minute."""
    try:
        from repositories.masini_repository import MasiniRepository

        masini = MasiniRepository.get_all() or []
        return {
            int(m["id"]): str(m.get("denumire") or f"Mașina #{m['id']}")
            for m in masini
            if m.get("id") is not None
        }
    except Exception:
        return {}


@st.cache_data(ttl=120, show_spinner=False)
def _incarca_documentatie_indexata() -> list[dict]:
    """Încarcă documentele și pre-calculează câmpul normalizat de căutare."""
    raw_docs = DocumentatieRepository.get_all() or []
    rezultat = []
    for d in raw_docs:
        item = dict(d)
        item["_search_blob"] = " ".join(
            [
                str(item.get("titlu") or ""),
                str(item.get("tip_sistem") or ""),
                str(item.get("interval_pagini") or ""),
                str(item.get("coduri_eroare_hmi") or ""),
                str(item.get("coduri_eroare_driver") or ""),
                str(item.get("text_indexat") or ""),
            ]
        ).lower()
        rezultat.append(item)
    return rezultat


def _invalideaza_cache_documentatie() -> None:
    _incarca_documentatie_indexata.clear()


# =========================================================
# 2. GESTIONARE STARE FORMULAR FARA st.rerun()
# =========================================================

def _init_form_state() -> None:
    defaults = {
        FORM_KEYS["titlu"]: "",
        FORM_KEYS["categorie"]: list(CATEGORII_DOCUMENTATIE)[0] if CATEGORII_DOCUMENTATIE else "CNC",
        FORM_KEYS["tip_sistem"]: "",
        FORM_KEYS["masina"]: "",
        FORM_KEYS["tag"]: "[ERR]" if "[ERR]" in TAGURI_DOCUMENTATIE else list(TAGURI_DOCUMENTATIE)[0],
        FORM_KEYS["pagini"]: "",
        FORM_KEYS["tip_fisier"]: "pdf",
        FORM_KEYS["url"]: "",
        FORM_KEYS["drive_id"]: "",
        FORM_KEYS["cod_hmi"]: "",
        FORM_KEYS["cod_driver"]: "",
        FORM_KEYS["text"]: "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset_form_state() -> None:
    st.session_state[FORM_KEYS["titlu"]] = ""
    st.session_state[FORM_KEYS["tip_sistem"]] = ""
    st.session_state[FORM_KEYS["pagini"]] = ""
    st.session_state[FORM_KEYS["url"]] = ""
    st.session_state[FORM_KEYS["drive_id"]] = ""
    st.session_state[FORM_KEYS["cod_hmi"]] = ""
    st.session_state[FORM_KEYS["cod_driver"]] = ""
    st.session_state[FORM_KEYS["text"]] = ""


def _cb_precompleteaza_din_drive() -> None:
    """Callback executat înainte de randare — elimină nevoia de st.rerun()."""
    fisiere_cache = st.session_state.get("arhiva_gdrive_files_cache") or []
    idx_sel = st.session_state.get("arhiva_gdrive_select_file")
    if idx_sel is None or not (0 <= idx_sel < len(fisiere_cache)):
        return

    f_sel = fisiere_cache[idx_sel]
    st.session_state[FORM_KEYS["titlu"]] = f_sel.get("name", "")
    st.session_state[FORM_KEYS["url"]] = f_sel.get("webViewLink", "")
    st.session_state[FORM_KEYS["drive_id"]] = f_sel.get("id", "")

    tip_sug = f_sel.get("tip_fisier", "pdf")
    if tip_sug in OPT_TIP_FISIER:
        st.session_state[FORM_KEYS["tip_fisier"]] = tip_sug

    tag_sug = f_sel.get("tag_sugerat", "[ERR]")
    if tag_sug in TAGURI_DOCUMENTATIE:
        st.session_state[FORM_KEYS["tag"]] = tag_sug

    st.session_state["arhiva_gdrive_feedback"] = ("success", "Câmpurile formularului au fost precompletate.")


def _cb_extrage_text_pdf() -> None:
    """Callback pentru extragerea textului PDF direct în câmpul de notițe, fără st.rerun()."""
    fisiere_cache = st.session_state.get("arhiva_gdrive_files_cache") or []
    idx_sel = st.session_state.get("arhiva_gdrive_select_file")
    if idx_sel is None or not (0 <= idx_sel < len(fisiere_cache)):
        return

    f_sel = fisiere_cache[idx_sel]
    if f_sel.get("tip_fisier") != "pdf":
        st.session_state["arhiva_gdrive_feedback"] = (
            "info",
            "Extragerea automată de text este disponibilă doar pentru fișiere PDF.",
        )
        return

    try:
        txt_pdf = extrage_text_pdf_drive(f_sel["id"])
        if txt_pdf:
            st.session_state[FORM_KEYS["text"]] = txt_pdf
            st.session_state["arhiva_gdrive_feedback"] = (
                "success",
                "Text extras din PDF și pus în câmpul de notițe/text indexat.",
            )
        else:
            st.session_state["arhiva_gdrive_feedback"] = (
                "warning",
                "PDF-ul nu are strat text extras (posibil scanat/imagine) — adaugă notițele manual.",
            )
    except Exception as e:
        st.session_state["arhiva_gdrive_feedback"] = ("error", f"Eroare la extragerea PDF: {e}")


# =========================================================
# 3. RANDARE PAGINA PRINCIPALA
# =========================================================

def render_documentatie_gdrive():
    _init_form_state()

    st.markdown("### 📚 Index Documentație Tehnică (Cont Google Drive)")
    st.caption(
        "Indexează secțiuni de manuale ([ERR], [SCH], [PRM], [TST], [MEC], [SOL]), intervale de pagini, "
        "coduri de eroare HMI / Driver-VFD și notițe (inclusiv pentru poze și PDF-uri scanate)."
    )

    masini_map = _incarca_lista_masini_scurta()
    opt_masini = ["", *masini_map.keys()]

    # --- 1. LISTARE RAPIDA DIN FOLDER GOOGLE DRIVE ---
    with st.expander("☁️ Explorare Folder din Noul Cont Google Drive (opțional)", expanded=False):
        c_f1, c_f2 = st.columns([3, 1], vertical_alignment="bottom")
        with c_f1:
            folder_input = st.text_input(
                "Link sau ID folder Google Drive",
                placeholder="https://drive.google.com/drive/folders/...",
                key="arhiva_gdrive_folder_input",
            )
        with c_f2:
            btn_list = st.button("📂 Listează folder", key="arhiva_btn_listeaza_gdrive", use_container_width=True)

        if btn_list:
            try:
                fisiere, status_msg = listeaza_fisiere_folder(folder_input)
                st.session_state["arhiva_gdrive_files_cache"] = fisiere
                st.session_state["arhiva_gdrive_status_msg"] = status_msg
                st.session_state.pop("arhiva_gdrive_feedback", None)
            except Exception as e:
                st.session_state["arhiva_gdrive_files_cache"] = []
                st.session_state["arhiva_gdrive_status_msg"] = f"Eroare la listarea folderului: {e}"

        if st.session_state.get("arhiva_gdrive_status_msg"):
            st.info(st.session_state["arhiva_gdrive_status_msg"])

        fisiere_cache = st.session_state.get("arhiva_gdrive_files_cache") or []
        if fisiere_cache:
            etichete_fisiere = [
                f"[{f['tip_fisier'].upper()} | {f['tag_sugerat']}] {f['name']}"
                for f in fisiere_cache
            ]
            st.selectbox(
                "Alege un fișier / folder din listă pentru a precompleta formularul:",
                options=range(len(etichete_fisiere)),
                format_func=lambda i: etichete_fisiere[i],
                key="arhiva_gdrive_select_file",
            )
            col_pre1, col_pre2 = st.columns([1, 1])
            with col_pre1:
                st.button(
                    "⬇️ Precompletează în formular",
                    key="arhiva_btn_preia_fisier",
                    on_click=_cb_precompleteaza_din_drive,
                    use_container_width=True,
                )
            with col_pre2:
                st.button(
                    "📄 Extrage text PDF (dacă are strat text)",
                    key="arhiva_btn_extract_pdf",
                    on_click=_cb_extrage_text_pdf,
                    use_container_width=True,
                )

        feedback = st.session_state.pop("arhiva_gdrive_feedback", None)
        if feedback:
            tip_msg, text_msg = feedback
            getattr(st, tip_msg, st.info)(text_msg)

    # --- 2. FORMULAR ADAUGARE IN INDEX ---
    st.markdown("#### ➕ Adaugă înregistrare în index")
    with st.form("form_adauga_doc_gdrive", clear_on_submit=False):
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            titlu = st.text_input(
                "Titlu document / secțiune / poză *",
                key=FORM_KEYS["titlu"],
                placeholder="ex: Fanuc 0i-MF Plus - Alarms [ERR] pag. 1101-1450",
            )
        with c2:
            categorie = st.selectbox(
                "Categorie",
                options=list(CATEGORII_DOCUMENTATIE),
                key=FORM_KEYS["categorie"],
            )
        with c3:
            tip_sistem = st.text_input(
                "Tip sistem / Comandă / VFD",
                key=FORM_KEYS["tip_sistem"],
                placeholder="ex: Fanuc, Siemens Sinamics, Mitsubishi",
            )

        c4, c5, c6, c7 = st.columns([1.8, 1.2, 1.2, 1.3])
        with c4:
            masina_sel = st.selectbox(
                "Utilaj asociat (opțional)",
                options=opt_masini,
                key=FORM_KEYS["masina"],
                format_func=lambda x: "— General (toate utilajele) —" if x == "" else masini_map.get(x, f"#{x}"),
            )
        with c5:
            tag_sectiune = st.selectbox(
                "Tag secțiune",
                options=list(TAGURI_DOCUMENTATIE),
                key=FORM_KEYS["tag"],
            )
        with c6:
            interval_pagini = st.text_input(
                "Interval / Pagină",
                key=FORM_KEYS["pagini"],
                placeholder="ex: p1101-p1450",
            )
        with c7:
            tip_fisier = st.selectbox(
                "Tip fișier",
                options=OPT_TIP_FISIER,
                key=FORM_KEYS["tip_fisier"],
            )

        c8, c9 = st.columns([3, 1.5])
        with c8:
            gdrive_url = st.text_input(
                "Link Google Drive (fișier, poză sau folder)",
                key=FORM_KEYS["url"],
                placeholder="https://drive.google.com/file/d/... sau .../folders/...",
            )
        with c9:
            gdrive_id_manual = st.text_input(
                "Drive ID (auto-completat dacă lași gol)",
                key=FORM_KEYS["drive_id"],
            )

        c10, c11 = st.columns([1, 1])
        with c10:
            coduri_hmi = st.text_input(
                "Coduri eroare HMI",
                key=FORM_KEYS["cod_hmi"],
                placeholder="ex: ALM 414, 414, SV0414",
            )
        with c11:
            coduri_driver = st.text_input(
                "Coduri eroare Driver / VFD",
                key=FORM_KEYS["cod_driver"],
                placeholder="ex: AL.24, F30002, OC1",
            )

        text_indexat = st.text_area(
            "Notițe / Rezumat / Text extras (important pentru poze și PDF-uri scanate)",
            key=FORM_KEYS["text"],
            height=100,
            placeholder="Notează aici ce arată poza/schema, simptomele, măsurătorile sau pașii cheie...",
        )

        submitted = st.form_submit_button("💾 Salvează în index", type="primary")
        if submitted:
            if not titlu.strip():
                st.warning("Completează titlul documentului înainte de salvare.")
            else:
                try:
                    final_id = gdrive_id_manual.strip() or extrage_drive_id(gdrive_url)
                    DocumentatieRepository.insert(
                        {
                            "masina_id": None if masina_sel == "" else int(masina_sel),
                            "categorie": categorie,
                            "tip_sistem": tip_sistem.strip(),
                            "titlu": titlu.strip(),
                            "gdrive_file_id": final_id,
                            "gdrive_url": gdrive_url.strip(),
                            "tip_fisier": tip_fisier,
                            "tag_sectiune": tag_sectiune,
                            "interval_pagini": interval_pagini.strip(),
                            "coduri_eroare_hmi": coduri_hmi.strip(),
                            "coduri_eroare_driver": coduri_driver.strip(),
                            "text_indexat": text_indexat.strip(),
                        }
                    )
                    _invalideaza_cache_documentatie()
                    _reset_form_state()
                    st.success("✅ Înregistrarea a fost adăugată în indexul de documentație.")
                except Exception as e:
                    st.error(f"Eroare la salvare: {e}")

    # --- 3. CAUTARE SI LISTARE INREGISTRARI INDEXATE ---
    st.markdown("---")
    st.markdown("#### 🔎 Căutare în documentația indexată")

    f1, f2, f3, f4 = st.columns([2.2, 1.2, 1.2, 1.4])
    with f1:
        cautare_q = st.text_input(
            "Caută după cod eroare, titlu, sistem sau notițe",
            placeholder="ex: 414, AL.24, Sinamics, encoder...",
            key="arhiva_search_q",
        )
    with f2:
        filtru_tag = st.selectbox(
            "Tag",
            options=["Toate", *TAGURI_DOCUMENTATIE],
            key="arhiva_filter_tag",
        )
    with f3:
        filtru_cat = st.selectbox(
            "Categorie",
            options=["Toate", *CATEGORII_DOCUMENTATIE],
            key="arhiva_filter_cat",
        )
    with f4:
        filtru_masina = st.selectbox(
            "Utilaj",
            options=["Toate", *masini_map.keys()],
            format_func=lambda x: "Toate utilajele" if x == "Toate" else masini_map.get(x, f"#{x}"),
            key="arhiva_filter_masina",
        )

    try:
        toate_doc = _incarca_documentatie_indexata()
    except Exception as e:
        st.error(f"Nu s-a putut citi indexul de documentație: {e}")
        toate_doc = []

    q_low = str(cautare_q or "").strip().lower()
    filtrate = [
        d
        for d in toate_doc
        if (filtru_tag == "Toate" or d.get("tag_sectiune") == filtru_tag)
        and (filtru_cat == "Toate" or d.get("categorie") == filtru_cat)
        and (filtru_masina == "Toate" or d.get("masina_id") == filtru_masina)
        and (not q_low or q_low in d.get("_search_blob", ""))
    ]

    st.caption(f"Rezultate afișate: **{len(filtrate)}** din {len(toate_doc)}")

    if filtrate:
        df_doc = pd.DataFrame(
            [
                {
                    "ID": int(r.get("id")),
                    "Tag": r.get("tag_sectiune") or "[ERR]",
                    "Categorie": r.get("categorie") or "CNC",
                    "Sistem": r.get("tip_sistem") or "",
                    "Titlu": r.get("titlu") or "",
                    "Pagini": r.get("interval_pagini") or "",
                    "Coduri HMI": r.get("coduri_eroare_hmi") or "",
                    "Coduri Driver/VFD": r.get("coduri_eroare_driver") or "",
                    "Link Drive": r.get("gdrive_url") or "",
                    "Notițe / Text": r.get("text_indexat") or "",
                }
                for r in filtrate
            ]
        )

        # Cheie legată de filtre pentru a evita suprapunerea stării editorului când se schimbă setul de rânduri
        editor_key = f"doc_editor_{filtru_tag}_{filtru_cat}_{filtru_masina}_{hash(q_low)}"

        edited_df = st.data_editor(
            df_doc,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "Tag": st.column_config.SelectboxColumn(
                    "Tag",
                    options=list(TAGURI_DOCUMENTATIE),
                    required=True,
                    width="small",
                ),
                "Categorie": st.column_config.SelectboxColumn(
                    "Categorie",
                    options=list(CATEGORII_DOCUMENTATIE),
                    required=True,
                    width="small",
                ),
                "Sistem": st.column_config.TextColumn("Sistem", width="medium"),
                "Titlu": st.column_config.TextColumn("Titlu", required=True, width="large"),
                "Pagini": st.column_config.TextColumn("Pagini", width="small"),
                "Coduri HMI": st.column_config.TextColumn("Coduri HMI", width="medium"),
                "Coduri Driver/VFD": st.column_config.TextColumn("Coduri Driver/VFD", width="medium"),
                "Link Drive": st.column_config.TextColumn("Link Drive", width="medium"),
                "Notițe / Text": st.column_config.TextColumn("Notițe / Text", width="large"),
            },
            key=editor_key,
            use_container_width=True,
        )

        if st.button("💾 Salvează modificările din tabel", key="doc_btn_save_table_edits", type="primary"):
            modificate = 0
            orig_map = {int(row["ID"]): row for _, row in df_doc.iterrows()}
            coloane_editabile = [
                "Tag",
                "Categorie",
                "Sistem",
                "Titlu",
                "Pagini",
                "Coduri HMI",
                "Coduri Driver/VFD",
                "Link Drive",
                "Notițe / Text",
            ]
            try:
                for _, new_row in edited_df.iterrows():
                    rid = int(new_row["ID"])
                    old_row = orig_map.get(rid)
                    if old_row is None:
                        continue
                    if any(str(new_row[col] or "") != str(old_row[col] or "") for col in coloane_editabile):
                        DocumentatieRepository.update(
                            rid,
                            {
                                "tag_sectiune": new_row["Tag"],
                                "categorie": new_row["Categorie"],
                                "tip_sistem": new_row["Sistem"],
                                "titlu": new_row["Titlu"],
                                "interval_pagini": new_row["Pagini"],
                                "coduri_eroare_hmi": new_row["Coduri HMI"],
                                "coduri_eroare_driver": new_row["Coduri Driver/VFD"],
                                "gdrive_url": new_row["Link Drive"],
                                "text_indexat": new_row["Notițe / Text"],
                            },
                        )
                        modificate += 1

                if modificate > 0:
                    _invalideaza_cache_documentatie()
                    st.success(f"✅ S-au actualizat {modificate} înregistrări.")
                else:
                    st.info("Nu ai făcut nicio modificare în tabel.")
            except Exception as e:
                st.error(f"Eroare la actualizarea înregistrărilor: {e}")

        # Afișăm maxim 5 fișe detaliate pentru a menține randarea rapidă
        for item in filtrate[:5]:
            rid = item.get("id")
            with st.expander(
                f"{item.get('tag_sectiune')} {item.get('titlu')} — [{item.get('tip_sistem') or item.get('categorie')}]"
            ):
                hmi_txt = html.escape(str(item.get("coduri_eroare_hmi") or "").strip())
                pag_txt = html.escape(str(item.get("interval_pagini") or "").strip())

                if hmi_txt or pag_txt:
                    st.markdown(
                        f"""
                        <div style="display:flex; gap:18px; flex-wrap:wrap; align-items:center; margin:4px 0 10px 0;">
                            {f'<div style="font-size:1.15rem; font-weight:700;">🚨 Cod HMI: <span style="font-size:1.25rem; color:#ff6b6b;">{hmi_txt}</span></div>' if hmi_txt else ''}
                            {f'<div style="font-size:1.15rem; font-weight:700;">📄 Pagina / Interval: <span style="font-size:1.25rem; color:#4dabf7;">{pag_txt}</span></div>' if pag_txt else ''}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                if item.get("coduri_eroare_driver"):
                    st.markdown(f"**Coduri Driver / VFD:** `{item.get('coduri_eroare_driver')}`")
                if item.get("text_indexat"):
                    st.markdown(f"**Notițe / Text indexat:**\n\n{item.get('text_indexat')}")
                if item.get("gdrive_url"):
                    st.markdown(f"🔗 [Deschide în Google Drive]({item.get('gdrive_url')})")
                if rid is not None and st.button("🗑️ Șterge din index", key=f"del_doc_page_{rid}"):
                    try:
                        DocumentatieRepository.delete(int(rid))
                        _invalideaza_cache_documentatie()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Eroare la ștergere: {e}")
    else:
        st.info("Nu există încă înregistrări care să potrivească filtrele curente.")


def render_help_documentatie_gdrive():
    with st.expander("❓ Ajutor / Ghid rapid — Indexare & Căutare Documentație (Google Drive)", expanded=False):
        st.markdown(
            """
Această pagină este **indexul tău rapid** pentru manualele, schemele, parametrii și pozele din contul Google Drive dedicat documentației. Nu încarcă manuale întregi în aplicație — păstrează **reperele esențiale** ca să găsești rapid ce îți trebuie la un defect.

### 1. Cum etichetezi secțiunile (`Tag`)
* **`[ERR]`** — alarme, coduri de eroare și diagnoză defecte.
* **`[SCH]`** — scheme electrice, conexiuni, pinout și trasee de semnal/putere.
* **`[PRM]`** — parametri CNC, PLC, servo-driver sau variator (VFD).
* **`[TST]`** — proceduri de test, verificări, măsurători și reglaje.
* **`[MEC]`** — componente mecanice, axe, rulmenți, cuplaje, frâne, gresare.
* **`[SOL]`** — soluții verificate, remedieri aplicate și piese înlocuite.

### 2. Cum indexezi manuale mari, PDF-uri scanate și poze
* **Manuale mari (ex. 1.000–2.500 pagini):** fă câte o înregistrare pe calupuri/secțiuni relevante (de ex. `p1101-p1450`), ca să știi exact unde să sari.
* **Poze / capturi de ecran / PDF-uri scanate:** pune linkul din Google Drive și scrie în **Notițe / Text** ce se vede în poză, ce ai măsurat sau ce coduri apar — altfel căutarea după text nu le va găsi.
* **Coduri HMI și Driver / VFD:** completează atât alarma de pe **HMI**, cât și codurile specifice de pe **driver sau VFD** (o alarmă pe HMI poate corespunde mai multor coduri de driver/VFD).

### 3. Editare directă din tabel și explorare Google Drive
* **Modificare rapidă:** poți da dublu-click direct în tabelul de rezultate (de ex. pe `Pagini` când adaugi un nou calup de pagini, pe `Coduri HMI` / `Coduri Driver/VFD` sau pe `Notițe / Text`), apoi apeși **Salvează modificările din tabel**.
* **Explorare folder Drive:** dacă este configurat contul de serviciu (Service Account) și folderul din noul cont Google Drive este partajat cu el, poți lista fișierele direct din **Explorare Folder din Noul Cont Google Drive** și le poți precompleta în formular.
"""
        )