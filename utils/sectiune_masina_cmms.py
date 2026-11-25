

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


def _stil_expander_mic(m_id: int) -> None:
    st.markdown(
        f"""
        <style>
        .cmms-exp-compact-{m_id} [data-testid="stExpander"] summary p {{
            font-size: 0.92rem !important;
            font-weight: 600 !important;
        }}
        </style>
        <div class="cmms-exp-compact-{m_id}"></div>
        """,
        unsafe_allow_html=True,
    )


def render_sectiune_cmms_masina(firma_id: int, masina_obj: dict) -> None:
    """
    Randează secțiunile CMMS pentru mașina selectată:
    Parole -> Param -> Comparare.
    """
    if not masina_obj or "id" not in masina_obj:
        return

    m_id = int(masina_obj["id"])
    _stil_expander_mic(m_id)

    # ---------------------------------------------------------
    # PAROLE
    # ---------------------------------------------------------
    with st.expander("Parole", expanded=False):
        with st.form(f"form_parola_masina_{m_id}", clear_on_submit=True):
            p_col1, p_col2, p_col3 = st.columns([1.2, 1.2, 1.4])
            with p_col1:
                unde_se_aplica = st.text_input(
                    "Unde se aplică *",
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

            if st.form_submit_button("💾 Salvează parola", type="primary"):
                if not unde_se_aplica.strip() or not parola_val.strip():
                    st.error("Completează 'Unde se aplică' și 'Parola'.")
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
        for p in parole_db:
            pid = int(p["id"])
            obs_preview = f" — {p['observatii']}" if p.get("observatii") else ""
            with st.container(border=True):
                c1, c2 = st.columns([1.4, 1.6])
                with c1:
                    st.markdown(f"**Unde se aplică:** `{p['unde_se_aplica']}`")
                with c2:
                    st.markdown(f"**Parola:** `{p['parola']}`{obs_preview}")

                with st.expander("Modifică / Șterge", expanded=False):
                    with st.form(f"form_edit_parola_{pid}"):
                        ep1, ep2, ep3 = st.columns([1.2, 1.2, 1.4])
                        with ep1:
                            edit_unde = st.text_input("Unde se aplică *", value=str(p.get("unde_se_aplica") or ""))
                        with ep2:
                            edit_parola = st.text_input("Parola *", value=str(p.get("parola") or ""))
                        with ep3:
                            edit_obs = st.text_input("Observații", value=str(p.get("observatii") or ""))

                        b_up, b_del = st.columns([2, 1])
                        if b_up.form_submit_button("💾 Salvează", type="primary"):
                            if not edit_unde.strip() or not edit_parola.strip():
                                st.error("Completează 'Unde se aplică' și 'Parola'.")
                            else:
                                ParoleMasiniRepository.update(pid, edit_parola, edit_unde, edit_obs)
                                st.success("Parola a fost actualizată.")
                                st.rerun()
                        if b_del.form_submit_button("🗑️ Șterge"):
                            ParoleMasiniRepository.delete(pid)
                            st.warning("Parola a fost ștearsă.")
                            st.rerun()

    # ---------------------------------------------------------
    # PARAM
    # ---------------------------------------------------------
    with st.expander("Param", expanded=False):
        draft_key = f"_cmms_text_draft_{m_id}"
        sursa_key = f"_cmms_sursa_draft_{m_id}"
        last_ocr_key = f"_cmms_last_ocr_id_{m_id}"
        last_file_key = f"_cmms_last_file_id_{m_id}"

        st.session_state.setdefault(draft_key, "")
        st.session_state.setdefault(sursa_key, "text_lipit")

        imp_col1, imp_col2 = st.columns(2)
        with imp_col1:
            uploaded_txt = st.file_uploader(
                "Fișier text (.txt, .csv, .log, .json)",
                type=["txt", "csv", "log", "json"],
                key=f"up_param_txt_{m_id}",
            )
            if uploaded_txt is not None:
                file_token = f"{uploaded_txt.name}_{uploaded_txt.size}"
                if st.session_state.get(last_file_key) != file_token:
                    st.session_state[last_file_key] = file_token
                    st.session_state[draft_key] = uploaded_txt.getvalue().decode("utf-8", errors="replace")
                    st.session_state[sursa_key] = "fisier_text"

        with imp_col2:
            uploaded_img = st.file_uploader(
                "Poză parametri (OCR)",
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

        text_parametri = st.text_area(
            "Parametri (cod_param;valoare;descriere;documentatie_link)",
            height=150,
            key=draft_key,
            placeholder="P001;24.50;Tensiune alimentare;https://...\nP002;1500;Turatie nominala;",
        )

        meta_col1, meta_col2, meta_col3 = st.columns(3)
        with meta_col1:
            model_piesa = st.text_input("Model piesă", key=f"cmms_model_piesa_{m_id}")
        with meta_col2:
            subansamblu_param = st.text_input("Subansamblu", key=f"cmms_subansamblu_{m_id}")
        with meta_col3:
            obs_set = st.text_input("Observații set", key=f"cmms_obs_set_{m_id}")

        este_referinta_ok = st.checkbox(
            "Set de referință (OK)",
            value=False,
            key=f"cmms_este_ref_{m_id}",
        )

        parametri_parsati = parseaza_parametri_din_text(text_parametri)
        if parametri_parsati:
            st.dataframe(pd.DataFrame(parametri_parsati), use_container_width=True, hide_index=True)

        if st.button("💾 Salvează setul", type="primary", key=f"btn_salveaza_set_{m_id}"):
            if not parametri_parsati:
                st.warning("Nu am găsit parametri valizi.")
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
                st.success(f"Setul #{set_nou_id} a fost salvat.")
                st.rerun()

        st.markdown("---")
        for s in ParametriMasinaRepository.get_seturi_by_masina(m_id):
            sid = int(s["id"])
            with st.expander(_format_eticheta_set(s), expanded=False):
                valori_set = ParametriMasinaRepository.get_valori_by_set(sid)
                df_initial = pd.DataFrame(
                    [
                        {
                            "cod_param": v.get("cod_param") or "",
                            "valoare": v.get("valoare_text") or "",
                            "descriere": v.get("descriere") or "",
                            "documentatie_link": v.get("documentatie_link") or "",
                        }
                        for v in valori_set
                    ]
                    if valori_set
                    else [{"cod_param": "", "valoare": "", "descriere": "", "documentatie_link": ""}]
                )

                em1, em2, em3 = st.columns(3)
                with em1:
                    edit_piesa = st.text_input("Model piesă", value=str(s.get("model_piesa") or ""), key=f"edit_set_piesa_{sid}")
                with em2:
                    edit_sub = st.text_input("Subansamblu", value=str(s.get("subansamblu") or ""), key=f"edit_set_sub_{sid}")
                with em3:
                    edit_obs = st.text_input("Observații", value=str(s.get("observatii") or ""), key=f"edit_set_obs_{sid}")

                edit_ref = st.checkbox(
                    "Referință (OK)",
                    value=bool(s.get("este_referinta", False)),
                    key=f"edit_set_ref_{sid}",
                )

                df_editat = st.data_editor(
                    df_initial,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key=f"editor_parametri_set_{sid}",
                )

                bs1, bs2 = st.columns([2, 1])
                if bs1.button("💾 Salvează modificările", type="primary", key=f"btn_save_edit_set_{sid}", use_container_width=True):
                    randuri_valide = [
                        r for r in df_editat.fillna("").to_dict(orient="records")
                        if str(r.get("cod_param") or "").strip()
                    ]
                    if not randuri_valide:
                        st.error("Adaugă cel puțin un parametru cu cod.")
                    else:
                        ParametriMasinaRepository.actualizeaza_set_parametri(
                            set_id=sid,
                            parametri=randuri_valide,
                            model_piesa=edit_piesa,
                            subansamblu=edit_sub,
                            este_referinta=edit_ref,
                            observatii=edit_obs,
                        )
                        st.success(f"Setul #{sid} a fost actualizat.")
                        st.rerun()
                if bs2.button("🗑️ Șterge setul", key=f"btn_del_set_{sid}", use_container_width=True):
                    ParametriMasinaRepository.delete_set(sid)
                    st.warning(f"Setul #{sid} a fost șters.")
                    st.rerun()

    # ---------------------------------------------------------
    # COMPARARE
    # ---------------------------------------------------------
    with st.expander("Comparare", expanded=False):
        seturi_comp = ParametriMasinaRepository.get_seturi_by_masina(m_id)
        if len(seturi_comp) < 2:
            st.info("Ai nevoie de cel puțin 2 seturi salvate pentru a compara.")
            return

        etichete_map = {_format_eticheta_set(s): int(s["id"]) for s in seturi_comp}
        etichete_lista = list(etichete_map.keys())
        default_ref_idx = next((i for i, s in enumerate(seturi_comp) if s.get("este_referinta")), 0)
        default_nou_idx = 1 if default_ref_idx == 0 else 0

        c_comp1, c_comp2, c_comp3 = st.columns([2.0, 2.0, 1.4])
        with c_comp1:
            ref_lbl = st.selectbox("Referință (OK)", options=etichete_lista, index=default_ref_idx, key=f"comp_ref_{m_id}")
        with c_comp2:
            nou_lbl = st.selectbox("Set nou", options=etichete_lista, index=default_nou_idx, key=f"comp_nou_{m_id}")
        with c_comp3:
            filtru_status = st.selectbox(
                "Filtru",
                options=["Toate", "Doar diferențe", "Modificat", "Parametru nou", "Lipsă în setul nou", "Identic (OK)"],
                key=f"comp_filtru_{m_id}",
            )

        ref_id = etichete_map[ref_lbl]
        nou_id = etichete_map[nou_lbl]
        if ref_id == nou_id:
            st.warning("Alege două seturi diferite.")
            return

        rezultate = ParametriMasinaRepository.compara_seturi(ref_id, nou_id)
        if not rezultate:
            st.info("Nu există parametri de comparat.")
            return

        df_comp = pd.DataFrame(rezultate)
        if filtru_status == "Doar diferențe":
            df_comp = df_comp[df_comp["status"] != "Identic (OK)"]
        elif filtru_status != "Toate":
            df_comp = df_comp[df_comp["status"] == filtru_status]

        if df_comp.empty:
            st.info("Nicio înregistrare pentru filtrul selectat.")
            return

        df_afis = df_comp[
            ["cod_param", "descriere", "valoare_referinta", "valoare_noua", "diferenta_num", "status", "documentatie_link"]
        ].copy()
        df_afis.columns = ["Cod Parametru", "Descriere", "Referință (OK)", "Valoare Nouă", "Diferență", "Status", "Documentație"]
        st.dataframe(df_afis, use_container_width=True, hide_index=True)