

# -------------------------------------------------------------
# -------utils/sectiune_masina_cmms.py--------------
# -------------------------------------------------------------




from datetime import datetime
import io
import pandas as pd
import streamlit as st

from repositories.parametri_masina_repository import (
    ParametriMasinaRepository,
    parseaza_parametri_din_text,
)
from repositories.parole_masini_repository import ParoleMasiniRepository

try:
    from PIL import Image
    import pytesseract

    _OCR_DISPONIBIL = True
except Exception:
    Image = None
    pytesseract = None
    _OCR_DISPONIBIL = False


def _extrage_text_ocr(uploaded_img) -> tuple[str, str | None]:
    if not uploaded_img:
        return "", None
    if not _OCR_DISPONIBIL or Image is None or pytesseract is None:
        return (
            "",
            "Recunoașterea automată OCR nu este disponibilă în acest mediu. "
            "Poți lipi sau scrie textul direct în zona de mai jos.",
        )
    try:
        img = Image.open(io.BytesIO(uploaded_img.getvalue()))
        txt = pytesseract.image_to_string(img) or ""
        if not txt.strip():
            return "", "Nu s-a putut detecta text clar în imagine. Verifică claritatea sau introdu textul manual."
        return txt.strip(), None
    except Exception as exc:
        return "", f"OCR indisponibil sau eroare la citirea imaginii ({exc}). Poți introduce textul manual."


def _format_eticheta_set(s: dict) -> str:
    dt_str = str(s.get("data_inregistrare") or "")[:19]
    ref_tag = " [REFERINȚĂ OK]" if s.get("este_referinta") else ""
    sub_tag = f" • {s['subansamblu']}" if s.get("subansamblu") else ""
    piesa_tag = f" • Piesă: {s['model_piesa']}" if s.get("model_piesa") else ""
    nr_p = s.get("nr_parametri", 0)
    return f"#{s['id']} ({dt_str}){ref_tag}{sub_tag}{piesa_tag} — {nr_p} param."


def render_sectiune_cmms_masina(firma_id: int, masina_obj: dict) -> None:
    """
    Se apelează din pagina de Mașini după selectarea / încărcarea mașinii curente.
    """
    if not masina_obj or "id" not in masina_obj:
        return

    m_id = int(masina_obj["id"])
    m_nume = str(masina_obj.get("denumire") or f"Mașina #{m_id}")

    st.markdown("---")
    st.subheader(f"🔐 Parole, Parametri & Comparație — {m_nume}")

    tab_parole, tab_import, tab_comparare = st.tabs(
        [
            "🔑 Parole Mașină",
            "📥 Import Parametri (Fișier / Text / OCR)",
            "⚖️ Comparare Parametri (OK vs. Noi)",
        ]
    )

    # ---------------------------------------------------------
    # TAB 1: PAROLE MAȘINI
    # ---------------------------------------------------------
    with tab_parole:
        st.markdown("#### Adaugă parolă nouă pentru această mașină")
        with st.form(f"form_parola_masina_{m_id}", clear_on_submit=True):
            p_col1, p_col2, p_col3 = st.columns([1.2, 1.2, 1.4])
            with p_col1:
                unde_se_aplica = st.text_input(
                    "Unde se aplică parola *",
                    placeholder="ex: PLC Siemens, HMI, CNC, Service",
                )
            with p_col2:
                parola_val = st.text_input(
                    "Parola *",
                    placeholder="Introdu parola",
                )
            with p_col3:
                obs_parola = st.text_input(
                    "Observații",
                    placeholder="ex: Nivel acces operator / mentenanță",
                )

            btn_add_parola = st.form_submit_button("💾 Salvează parola", type="primary")
            if btn_add_parola:
                if not unde_se_aplica.strip() or not parola_val.strip():
                    st.error("Completează câmpurile obligatorii: 'Unde se aplică parola' și 'Parola'.")
                else:
                    ParoleMasiniRepository.insert(
                        firma_id=firma_id,
                        masina_id=m_id,
                        parola=parola_val,
                        unde_se_aplica=unde_se_aplica,
                        observatii=obs_parola,
                    )
                    st.success("Parola a fost salvată.")
                    st.rerun()

        parole_db = ParoleMasiniRepository.get_by_masina(m_id)
        if not parole_db:
            st.info("Nu există parole înregistrate pentru această mașină.")
        else:
            st.markdown("#### Parole salvate")
            df_parole = pd.DataFrame(parole_db)[
                ["id", "unde_se_aplica", "parola", "observatii", "creat_la"]
            ].copy()
            df_parole.columns = ["ID", "Unde se aplică", "Parolă", "Observații", "Creat la"]
            st.dataframe(df_parole, use_container_width=True, hide_index=True)

            opt_del = {
                f"#{p['id']} — {p['unde_se_aplica']}": int(p["id"]) for p in parole_db
            }
            del_col1, del_col2 = st.columns([3.0, 1.0], vertical_alignment="bottom")
            with del_col1:
                sel_del_lbl = st.selectbox(
                    "Selectează parola de șters",
                    options=list(opt_del.keys()),
                    key=f"sel_del_parola_{m_id}",
                )
            with del_col2:
                if st.button("🗑️ Șterge", key=f"btn_del_parola_{m_id}", use_container_width=True):
                    ParoleMasiniRepository.delete(opt_del[sel_del_lbl])
                    st.success("Parola a fost ștearsă.")
                    st.rerun()

    # ---------------------------------------------------------
    # TAB 2: IMPORT PARAMETRI (FIȘIER TEXT / TEXT LIPIT / OCR)
    # ---------------------------------------------------------
    with tab_import:
        draft_key = f"_cmms_text_draft_{m_id}"
        sursa_key = f"_cmms_sursa_draft_{m_id}"
        last_ocr_key = f"_cmms_last_ocr_id_{m_id}"
        last_file_key = f"_cmms_last_file_id_{m_id}"

        st.session_state.setdefault(draft_key, "")
        st.session_state.setdefault(sursa_key, "text_lipit")

        imp_col1, imp_col2 = st.columns(2)
        with imp_col1:
            uploaded_txt = st.file_uploader(
                "1a. Încarcă fișier text cu parametri (.txt, .csv, .log, .json)",
                type=["txt", "csv", "log", "json"],
                key=f"up_param_txt_{m_id}",
            )
            if uploaded_txt is not None:
                file_token = f"{uploaded_txt.name}_{uploaded_txt.size}"
                if st.session_state.get(last_file_key) != file_token:
                    st.session_state[last_file_key] = file_token
                    try:
                        continut_fisier = uploaded_txt.getvalue().decode("utf-8", errors="replace")
                        st.session_state[draft_key] = continut_fisier
                        st.session_state[sursa_key] = "fisier_text"
                    except Exception as exc:
                        st.error(f"Nu am putut citi fișierul: {exc}")

        with imp_col2:
            uploaded_img = st.file_uploader(
                "1b. Sau încarcă poză cu parametri (OCR)",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"up_param_img_{m_id}",
            )
            if uploaded_img is not None:
                img_token = f"{uploaded_img.name}_{uploaded_img.size}"
                if st.session_state.get(last_ocr_key) != img_token:
                    st.session_state[last_ocr_key] = img_token
                    text_ocr, err_ocr = _extrage_text_ocr(uploaded_img)
                    if err_ocr:
                        st.warning(err_ocr)
                    if text_ocr:
                        st.session_state[draft_key] = text_ocr
                        st.session_state[sursa_key] = "ocr_poza"
                        st.info("Text extras prin OCR. Verifică-l în câmpul de mai jos înainte de salvare.")

        st.caption(
            "Formate acceptate per linie: `cod_param;valoare;descriere;documentatie_link`, "
            "`cod_param = valoare`, `cod_param : valoare` sau JSON `[{\"cod_param\": ..., \"valoare\": ..., \"descriere\": ..., \"documentatie_link\": ...}]`."
        )

        text_parametri = st.text_area(
            "Text parametri (poți lipi, edita sau încărca din fișier / poză)",
            height=180,
            key=draft_key,
            placeholder="P001;24.50;Tensiune alimentare;https://...\nP002;1500;Turatie nominala;",
        )

        meta_col1, meta_col2, meta_col3 = st.columns(3)
        with meta_col1:
            model_piesa = st.text_input(
                "Model piesă",
                placeholder="ex: Piesă Tip A-12",
                key=f"cmms_model_piesa_{m_id}",
            )
        with meta_col2:
            subansamblu_param = st.text_input(
                "Subansamblu",
                placeholder="ex: Axă X / Grup hidraulic",
                key=f"cmms_subansamblu_{m_id}",
            )
        with meta_col3:
            obs_set = st.text_input(
                "Observații set",
                placeholder="ex: Configurație validată în producție",
                key=f"cmms_obs_set_{m_id}",
            )

        este_referinta_ok = st.checkbox(
            "Marchează acest set ca REFERINȚĂ (OK — când mașina merge bine)",
            value=False,
            key=f"cmms_este_ref_{m_id}",
        )

        parametri_parsati = parseaza_parametri_din_text(text_parametri)
        if parametri_parsati:
            st.markdown(f"#### Previzualizare ({len(parametri_parsati)} parametri detectați)")
            st.dataframe(
                pd.DataFrame(parametri_parsati),
                use_container_width=True,
                hide_index=True,
            )

        if st.button("💾 Salvează setul de parametri", type="primary", key=f"btn_salveaza_set_{m_id}"):
            if not parametri_parsati:
                st.warning("Nu am găsit parametri valizi (cu `cod_param`) în textul introdus.")
            else:
                sursa_finala = (
                    "text_lipit"
                    if st.session_state.get(sursa_key) == "text_lipit" and not uploaded_txt and not uploaded_img
                    else st.session_state.get(sursa_key, "text_lipit")
                )
                set_nou_id = ParametriMasinaRepository.salveaza_set_parametri(
                    firma_id=firma_id,
                    masina_id=m_id,
                    parametri=parametri_parsati,
                    model_piesa=model_piesa,
                    subansamblu=subansamblu_param,
                    sursa_import=sursa_finala,
                    este_referinta=este_referinta_ok,
                    observatii=obs_set,
                    data_inregistrare=datetime.now(),
                )
                st.success(f"Setul #{set_nou_id} ({len(parametri_parsati)} parametri) a fost salvat.")
                st.rerun()

        st.markdown("---")
        st.markdown("#### Seturi de parametri salvate pe această mașină")
        seturi_db = ParametriMasinaRepository.get_seturi_by_masina(m_id)
        if not seturi_db:
            st.info("Nu există încă seturi de parametri salvate pentru această mașină.")
        else:
            df_seturi = pd.DataFrame(
                [
                    {
                        "ID Set": s["id"],
                        "Data": str(s["data_inregistrare"])[:19],
                        "Referință OK": "✅ DA" if s.get("este_referinta") else "Nu",
                        "Model piesă": s.get("model_piesa") or "—",
                        "Subansamblu": s.get("subansamblu") or "—",
                        "Sursă": s.get("sursa_import") or "—",
                        "Nr. parametri": s.get("nr_parametri", 0),
                        "Observații": s.get("observatii") or "—",
                    }
                    for s in seturi_db
                ]
            )
            st.dataframe(df_seturi, use_container_width=True, hide_index=True)

            opt_seturi_ref = {_format_eticheta_set(s): int(s["id"]) for s in seturi_db}
            ref_c1, ref_c2, ref_c3 = st.columns([2.6, 1.0, 1.0], vertical_alignment="bottom")
            with ref_c1:
                sel_set_ref_flag = st.selectbox(
                    "Selectează set pentru status Referință (OK)",
                    options=list(opt_seturi_ref.keys()),
                    key=f"sel_set_flag_ref_{m_id}",
                )
            with ref_c2:
                if st.button("⭐ Marchează OK", key=f"btn_set_ok_{m_id}", use_container_width=True):
                    ParametriMasinaRepository.seteaza_referinta(opt_seturi_ref[sel_set_ref_flag], True)
                    st.rerun()
            with ref_c3:
                if st.button("↩️ Scoate OK", key=f"btn_unset_ok_{m_id}", use_container_width=True):
                    ParametriMasinaRepository.seteaza_referinta(opt_seturi_ref[sel_set_ref_flag], False)
                    st.rerun()

    # ---------------------------------------------------------
    # TAB 3: COMPARARE PARAMETRI (REFERINȚĂ OK VS. NOI)
    # ---------------------------------------------------------
    with tab_comparare:
        seturi_comp = ParametriMasinaRepository.get_seturi_by_masina(m_id)
        if len(seturi_comp) < 2:
            st.info(
                "Ai nevoie de cel puțin **2 seturi de parametri** salvate pe această mașină "
                "(de ex. un set de referință când mașina mergea OK și un set nou) pentru a face comparația."
            )
            return

        etichete_map = {_format_eticheta_set(s): int(s["id"]) for s in seturi_comp}
        etichete_lista = list(etichete_map.keys())

        # Alegem implicit un set marcat ca referință OK dacă există
        default_ref_idx = 0
        for idx, s in enumerate(seturi_comp):
            if s.get("este_referinta"):
                default_ref_idx = idx
                break

        c_comp1, c_comp2, c_comp3 = st.columns([2.0, 2.0, 1.4])
        with c_comp1:
            ref_lbl = st.selectbox(
                "Set de referință (vechi / mașină OK)",
                options=etichete_lista,
                index=default_ref_idx,
                key=f"comp_ref_{m_id}",
            )
        with c_comp2:
            default_nou_idx = 1 if default_ref_idx == 0 else 0
            nou_lbl = st.selectbox(
                "Set nou de comparat",
                options=etichete_lista,
                index=default_nou_idx,
                key=f"comp_nou_{m_id}",
            )
        with c_comp3:
            filtru_status = st.selectbox(
                "Filtru status",
                options=[
                    "Toate",
                    "Doar diferențe",
                    "Modificat",
                    "Parametru nou",
                    "Lipsă în setul nou",
                    "Identic (OK)",
                ],
                key=f"comp_filtru_{m_id}",
            )

        ref_id = etichete_map[ref_lbl]
        nou_id = etichete_map[nou_lbl]

        if ref_id == nou_id:
            st.warning("Alege două seturi diferite pentru a compara.")
            return

        rezultate = ParametriMasinaRepository.compara_seturi(ref_id, nou_id)
        if not rezultate:
            st.info("Nu există parametri de comparat în seturile selectate.")
            return

        df_comp = pd.DataFrame(rezultate)

        if filtru_status == "Doar diferențe":
            df_comp = df_comp[df_comp["status"] != "Identic (OK)"]
        elif filtru_status != "Toate":
            df_comp = df_comp[df_comp["status"] == filtru_status]

        if df_comp.empty:
            st.success("Nu există înregistrări care să corespundă filtrului selectat.")
            return

        df_afis = df_comp[
            [
                "cod_param",
                "descriere",
                "valoare_referinta",
                "valoare_noua",
                "diferenta_num",
                "status",
                "documentatie_link",
            ]
        ].copy()
        df_afis.columns = [
            "Cod Parametru",
            "Descriere",
            "Valoare Referință (OK)",
            "Valoare Nouă",
            "Diferență (Num.)",
            "Status",
            "Documentație Link",
        ]

        st.dataframe(df_afis, use_container_width=True, hide_index=True)