#----------------------------------------------
#--- TAB NOU IN ARHIVA&DOCS: INDEX GDRIVE -----
#----------------------------------------------

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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


def _incarca_lista_masini_scurta() -> dict[int, str]:
    """Returnează un dicționar {id_masina: denumire} fără să crape dacă repository-ul nu e importat."""
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


def render_documentatie_gdrive():
    st.markdown("### 📚 Index Documentație Tehnică (Cont Google Drive)")
    st.caption(
        "Indexează secțiuni de manuale ([ERR], [SCH], [PRM], [TST], [MEC], [SOL]), intervale de pagini, "
        "coduri de eroare HMI / Driver-VFD și notițe (inclusiv pentru poze și PDF-uri scanate)."
    )

    masini_map = _incarca_lista_masini_scurta()
    opt_masini = ["", *masini_map.keys()]

    # --- 1. LISTARE RAPIDA DIN FOLDER GOOGLE DRIVE (CAND E CONFIGURAT SERVICE ACCOUNT) ---
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
            fisiere, status_msg = listeaza_fisiere_folder(folder_input)
            st.session_state["arhiva_gdrive_files_cache"] = fisiere
            st.session_state["arhiva_gdrive_status_msg"] = status_msg

        if st.session_state.get("arhiva_gdrive_status_msg"):
            st.info(st.session_state["arhiva_gdrive_status_msg"])

        fisiere_cache = st.session_state.get("arhiva_gdrive_files_cache") or []
        if fisiere_cache:
            etichete_fisiere = [
                f"[{f['tip_fisier'].upper()} | {f['tag_sugerat']}] {f['name']}"
                for f in fisiere_cache
            ]
            idx_sel = st.selectbox(
                "Alege un fișier / folder din listă pentru a precompleta formularul:",
                options=range(len(etichete_fisiere)),
                format_func=lambda i: etichete_fisiere[i],
                key="arhiva_gdrive_select_file",
            )
            col_pre1, col_pre2 = st.columns([1, 1])
            with col_pre1:
                if st.button("⬇️ Precompletează în formular", key="arhiva_btn_preia_fisier"):
                    f_sel = fisiere_cache[idx_sel]
                    st.session_state["doc_prefill_titlu"] = f_sel["name"]
                    st.session_state["doc_prefill_url"] = f_sel["webViewLink"]
                    st.session_state["doc_prefill_id"] = f_sel["id"]
                    st.session_state["doc_prefill_tip"] = f_sel["tip_fisier"]
                    st.session_state["doc_prefill_tag"] = f_sel["tag_sugerat"]
                    st.rerun()
            with col_pre2:
                if st.button("📄 Extrage text PDF (dacă are strat text)", key="arhiva_btn_extract_pdf"):
                    f_sel = fisiere_cache[idx_sel]
                    if f_sel["tip_fisier"] == "pdf":
                        txt_pdf = extrage_text_pdf_drive(f_sel["id"])
                        if txt_pdf:
                            st.session_state["doc_prefill_text"] = txt_pdf
                            st.success("Text extras din PDF și pus în câmpul de notițe/text indexat.")
                            st.rerun()
                        else:
                            st.warning("PDF-ul nu are strat text extras (posibil scanat/imagine) — adaugă notițele manual.")
                    else:
                        st.info("Extragerea automată de text este disponibilă doar pentru fișiere PDF.")

    # --- 2. FORMULAR ADAUGARE IN INDEX ---
    st.markdown("#### ➕ Adaugă înregistrare în index")
    with st.form("form_adauga_doc_gdrive", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1.5, 1.5])
        with c1:
            titlu = st.text_input(
                "Titlu document / secțiune / poză *",
                value=st.session_state.pop("doc_prefill_titlu", ""),
                placeholder="ex: Fanuc 0i-MF Plus - Alarms [ERR] pag. 1101-1450",
            )
        with c2:
            categorie = st.selectbox(
                "Categorie",
                options=list(CATEGORII_DOCUMENTATIE),
                index=0,
            )
        with c3:
            tip_sistem = st.text_input(
                "Tip sistem / Comandă / VFD",
                placeholder="ex: Fanuc, Siemens Sinamics, Mitsubishi",
            )

        c4, c5, c6, c7 = st.columns([1.8, 1.2, 1.2, 1.3])
        with c4:
            masina_sel = st.selectbox(
                "Utilaj asociat (opțional)",
                options=opt_masini,
                format_func=lambda x: "— General (toate utilajele) —" if x == "" else masini_map.get(x, f"#{x}"),
            )
        with c5:
            tag_pref = st.session_state.pop("doc_prefill_tag", "[ERR]")
            tag_idx = list(TAGURI_DOCUMENTATIE).index(tag_pref) if tag_pref in TAGURI_DOCUMENTATIE else 0
            tag_sectiune = st.selectbox("Tag secțiune", options=list(TAGURI_DOCUMENTATIE), index=tag_idx)
        with c6:
            interval_pagini = st.text_input("Interval / Pagină", placeholder="ex: p1101-p1450")
        with c7:
            tip_pref = st.session_state.pop("doc_prefill_tip", "pdf")
            opt_tip_fis = ["pdf", "img", "folder", "doc"]
            tip_idx = opt_tip_fis.index(tip_pref) if tip_pref in opt_tip_fis else 0
            tip_fisier = st.selectbox("Tip fișier", options=opt_tip_fis, index=tip_idx)

        c8, c9 = st.columns([3, 1.5])
        with c8:
            gdrive_url = st.text_input(
                "Link Google Drive (fișier, poză sau folder)",
                value=st.session_state.pop("doc_prefill_url", ""),
                placeholder="https://drive.google.com/file/d/... sau .../folders/...",
            )
        with c9:
            gdrive_id_manual = st.text_input(
                "Drive ID (auto-completat dacă lași gol)",
                value=st.session_state.pop("doc_prefill_id", ""),
            )

        c10, c11 = st.columns([1, 1])
        with c10:
            coduri_hmi = st.text_input("Coduri eroare HMI", placeholder="ex: ALM 414, 414, SV0414")
        with c11:
            coduri_driver = st.text_input("Coduri eroare Driver / VFD", placeholder="ex: AL.24, F30002, OC1")

        text_indexat = st.text_area(
            "Notițe / Rezumat / Text extras (important pentru poze și PDF-uri scanate)",
            value=st.session_state.pop("doc_prefill_text", ""),
            height=100,
            placeholder="Notează aici ce arată poza/schema, simptomele, măsurătorile sau pașii cheie...",
        )

        submitted = st.form_submit_button("💾 Salvează în index", type="primary")
        if submitted:
            try:
                final_id = gdrive_id_manual.strip() or extrage_drive_id(gdrive_url)
                DocumentatieRepository.insert({
                    "masina_id": None if masina_sel == "" else int(masina_sel),
                    "categorie": categorie,
                    "tip_sistem": tip_sistem,
                    "titlu": titlu,
                    "gdrive_file_id": final_id,
                    "gdrive_url": gdrive_url,
                    "tip_fisier": tip_fisier,
                    "tag_sectiune": tag_sectiune,
                    "interval_pagini": interval_pagini,
                    "coduri_eroare_hmi": coduri_hmi,
                    "coduri_eroare_driver": coduri_driver,
                    "text_indexat": text_indexat,
                })
                st.success("✅ Înregistrarea a fost adăugată în indexul de documentație.")
                st.rerun()
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
        toate_doc = DocumentatieRepository.get_all() or []
    except Exception as e:
        st.error(f"Nu s-a putut citi indexul de documentație: {e}")
        toate_doc = []

    q_low = str(cautare_q or "").strip().lower()
    filtrate = []
    for d in toate_doc:
        if filtru_tag != "Toate" and d.get("tag_sectiune") != filtru_tag:
            continue
        if filtru_cat != "Toate" and d.get("categorie") != filtru_cat:
            continue
        if filtru_masina != "Toate" and d.get("masina_id") != filtru_masina:
            continue
        if q_low:
            camp_comb = " ".join([
                str(d.get("titlu") or ""),
                str(d.get("tip_sistem") or ""),
                str(d.get("interval_pagini") or ""),
                str(d.get("coduri_eroare_hmi") or ""),
                str(d.get("coduri_eroare_driver") or ""),
                str(d.get("text_indexat") or ""),
            ]).lower()
            if q_low not in camp_comb:
                continue
        filtrate.append(d)

    st.caption(f"Rezultate afișate: **{len(filtrate)}** din {len(toate_doc)}")

    if filtrate:
        df_doc = pd.DataFrame([
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
        ])

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
            key="doc_page_data_editor",
            use_container_width=True,
        )

        if st.button("💾 Salvează modificările din tabel", key="doc_btn_save_table_edits", type="primary"):
            modificate = 0
            orig_map = {int(row["ID"]): row for _, row in df_doc.iterrows()}
            for _, new_row in edited_df.iterrows():
                rid = int(new_row["ID"])
                old_row = orig_map.get(rid)
                if old_row is None:
                    continue
                if any(
                    str(new_row[col] or "") != str(old_row[col] or "")
                    for col in ["Tag", "Categorie", "Sistem", "Titlu", "Pagini", "Coduri HMI", "Coduri Driver/VFD", "Link Drive", "Notițe / Text"]
                ):
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
                st.success(f"✅ S-au actualizat {modificate} înregistrări.")
                st.rerun()
            else:
                st.info("Nu ai făcut nicio modificare în tabel.")

        for item in filtrate[:10]:
            with st.expander(
                f"{item.get('tag_sectiune')} {item.get('titlu')} — [{item.get('tip_sistem') or item.get('categorie')}]"
            ):
                if item.get("coduri_eroare_hmi"):
                    st.markdown(f"**Coduri HMI:** `{item.get('coduri_eroare_hmi')}`")
                if item.get("coduri_eroare_driver"):
                    st.markdown(f"**Coduri Driver / VFD:** `{item.get('coduri_eroare_driver')}`")
                if item.get("interval_pagini"):
                    st.markdown(f"**Interval / Pagină:** `{item.get('interval_pagini')}`")
                if item.get("text_indexat"):
                    st.markdown(f"**Notițe / Text indexat:**\n\n{item.get('text_indexat')}")
                if item.get("gdrive_url"):
                    st.markdown(f"🔗 [Deschide în Google Drive]({item.get('gdrive_url')})")
                if st.button("🗑️ Șterge din index", key=f"del_doc_page_{item.get('id')}"):
                    DocumentatieRepository.delete(int(item["id"]))
                    st.rerun()
    else:
        st.info("Nu există încă înregistrări care să potrivească filtrele curente.")
        
def render_help_documentatie_gdrive():
    with st.expander("❓ Ajutor / Ghid rapid — Indexare & Căutare Documentație (Google Drive)", expanded=False):
        st.markdown("""
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
""")


def render_gview_iframe(pdf_url: str, pagina: str = ""):
    url_curat = str(pdf_url or "").strip()
    if not url_curat:
        return

    pag_num = "".join(ch for ch in str(pagina or "") if ch.isdigit())
    onload_attr = f" onload=\"this.contentWindow.location.hash=':0.page.{pag_num}';\"" if pag_num else ""

    target_pdf_url = "https://drive.google.com/uc?export=download&id=1_Vc6Cb6o1h2o3ldC1CHU_G5GhfEPfl7a"
    html_code = f"""
        <iframe
            id="iframe1"
            src="https://docs.google.com/gview?url={target_pdf_url}&embedded=true"
            style="width: 100%; height: 680px; border: 1px solid #444; border-radius: 6px;"
            onload="this.contentWindow.location.hash=':0.page.49';"
        ></iframe>
        """

    components.html(html_code, height=700)

