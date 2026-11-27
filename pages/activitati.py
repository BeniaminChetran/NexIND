# ----------------------------------
# -------pages/activitati.py--------
# ----------------------------------

import logging
import threading
from datetime import datetime
import pandas as pd
import streamlit as st
from repositories.documentatie_repository import DocumentatieRepository
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.reparatii_repository import ReparatiiRepository
from repositories.setari_repository import SetariRepository
from services.email_service import trimite_email_raport
from services.pdf_service import genereaza_pdf
from services.sync_service import background_sync_task
from utils.context_selectie import aplica_context_la_tab, seteaza_context_selectie
from utils.draft_state import init_draft, lega_camp, reset_draft, sync_camp, widget_key

logger = logging.getLogger(__name__)

OPT_FIRMA_IMPLICIT = "-- Alege firma --"
OPT_MASINA_IMPLICIT = "Nicio mașină"
OPT_SUB_IMPLICIT = "General"
OPT_EROARE_IMPLICIT = "Niciunul"

_fragment = getattr(st, "fragment", lambda fn: fn)


# ----------------------------------
# --------- CACHE CITIRI DB --------
# ----------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def _get_setari_cached() -> dict:
    return SetariRepository.get_setari() or {}


@st.cache_data(ttl=30, show_spinner=False)
def _get_firme_cached() -> list[dict]:
    return FirmeRepository.get_all() or []


@st.cache_data(ttl=30, show_spinner=False)
def _get_masini_by_firma_cached(firma_id) -> list[dict]:
    if firma_id is None:
        return []
    return MasiniRepository.get_by_firma(firma_id) or []


@st.cache_data(ttl=30, show_spinner=False)
def _get_piese_catalog_cached() -> list[str]:
    piese = PieseRepository.get_all() or []
    return [p["denumire"] for p in piese if isinstance(p, dict) and p.get("denumire")]


@st.cache_data(ttl=30, show_spinner=False)
def _get_documentatie_cached() -> list[dict]:
    try:
        return DocumentatieRepository.get_all() or []
    except Exception as exc:
        logger.warning("Eroare la citirea documentației din cache: %s", exc)
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _get_oferte_cached() -> list[dict]:
    for mod_path, cls_name in [
        ("repositories.oferte_repository", "OferteRepository"),
        ("repositories.oferte_pret_repository", "OfertePretRepository"),
        ("repositories.comercial_repository", "OferteRepository"),
    ]:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            repo = getattr(mod, cls_name, None)
            if repo and hasattr(repo, "get_all"):
                res = repo.get_all()
                if isinstance(res, list):
                    return res
        except Exception as exc:
            logger.debug("Repository oferte indisponibil (%s.%s): %s", mod_path, cls_name, exc)
            continue
    return []


# ----------------------------------
# -------- HELPERS & STATE ---------
# ----------------------------------

def _extrage_email_client(firma_obj: dict) -> str:
    if not firma_obj:
        return ""
    for k in ("email_client", "email", "mail", "adresa_email"):
        val = str(firma_obj.get(k) or "").strip()
        if val:
            return val
    return ""


def _defaults_activitati(tehnician_def: str) -> dict:
    return {
        "sel_firma": OPT_FIRMA_IMPLICIT,
        "sel_masina": OPT_MASINA_IMPLICIT,
        "sel_sub": OPT_SUB_IMPLICIT,
        "titlu_lucrare": "Intervenție tehnică",
        "simptom": "",
        "defect": "",
        "cod_eroare": OPT_EROARE_IMPLICIT,
        "solutie": "",
        "durata_min": 60,
        "tip_interventie": "reparatie",
        "stare_fin": "Funcțională",
        "tehnician": tehnician_def,
        "verificator": "Client",
        "optimizari": "",
        "ultima_firma": OPT_FIRMA_IMPLICIT,
    }


def _reseteaza_stare_raport_salvat() -> None:
    st.session_state["raport_salvat"] = False
    st.session_state["ultimul_id_salvat"] = None
    st.session_state["ultimul_pdf_bytes"] = None
    st.session_state["ultim_email_client"] = ""
    st.session_state["ultim_firma_raport"] = ""
    st.session_state["ultim_masina_raport"] = ""
    st.session_state["ultim_titlu_raport"] = ""
    st.session_state["email_raport_trimis"] = False


def _init_sau_reseteaza_act_draft(tehnician_def: str) -> None:
    reset_draft("act_draft", _defaults_activitati(tehnician_def), "act_cnt")
    st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])
    st.session_state["act_editor_counter"] = st.session_state.get("act_editor_counter", 0) + 1
    st.session_state.pop("_act_ctx_aplicat", None)


def _cb_anulare_activitate(tehnician_def: str) -> None:
    _init_sau_reseteaza_act_draft(tehnician_def)
    st.session_state["_act_toast_msg"] = "🗑️ Datele activității au fost resetate."


def _cb_activitate_noua(tehnician_def: str) -> None:
    _reseteaza_stare_raport_salvat()
    _init_sau_reseteaza_act_draft(tehnician_def)


def _asigura_valoare_in_optiuni(
    draft: dict,
    key_widget: str,
    campo_draft: str,
    optiuni: list,
    valoare_implicita,
) -> None:
    val_curenta = st.session_state.get(key_widget, draft.get(campo_draft, valoare_implicita))
    if val_curenta not in optiuni:
        val_noua = valoare_implicita if valoare_implicita in optiuni else optiuni[0]
        st.session_state[key_widget] = val_noua
        draft[campo_draft] = val_noua


def _sincronizeaza_piese_activitate() -> pd.DataFrame:
    cnt = st.session_state.get("act_editor_counter", 0)
    w_key = f"act_editor_piese_{cnt}"
    base_df = st.session_state.get("df_piese_editor")
    if base_df is None or w_key not in st.session_state:
        return base_df
    delta = st.session_state[w_key]
    if not isinstance(delta, dict):
        return base_df

    df_work = base_df.copy().reset_index(drop=True)
    for r_idx_str, changes in delta.get("edited_rows", {}).items():
        r_idx = int(r_idx_str)
        if 0 <= r_idx < len(df_work):
            for col_k, val_v in changes.items():
                if col_k in df_work.columns:
                    df_work.at[r_idx, col_k] = val_v

    del_rows = sorted(
        [int(i) for i in delta.get("deleted_rows", []) if 0 <= int(i) < len(df_work)],
        reverse=True,
    )
    if del_rows:
        df_work = df_work.drop(index=del_rows).reset_index(drop=True)

    added_rows = delta.get("added_rows", [])
    if added_rows:
        df_work = pd.concat([df_work, pd.DataFrame(added_rows)], ignore_index=True)

    st.session_state["df_piese_editor"] = df_work
    return df_work


def _cauta_docs_rapide_interventie(termen: str, masina_id=None) -> list[dict]:
    q = str(termen or "").strip().lower()
    toate_doc = _get_documentatie_cached()

    rezultate = []
    for d in toate_doc:
        if not isinstance(d, dict):
            continue
        if masina_id is not None and d.get("masina_id") not in (None, masina_id):
            continue
        blob = " ".join([
            str(d.get("titlu") or ""),
            str(d.get("tip_sistem") or ""),
            str(d.get("coduri_eroare_hmi") or ""),
            str(d.get("coduri_eroare_driver") or ""),
            str(d.get("interval_pagini") or ""),
            str(d.get("text_indexat") or ""),
        ]).lower()
        if not q or q in blob:
            rezultate.append(d)
            if len(rezultate) >= 6:
                break
    return rezultate


def _cauta_oferte_asociate(firma: str, masina: str = "", titlu: str = "") -> list[dict]:
    firma_low = str(firma or "").strip().lower()
    masina_low = str(masina or "").strip().lower()
    titlu_low = str(titlu or "").strip().lower()

    if not firma_low:
        return []

    toate_oferte = _get_oferte_cached()
    potriviri_firma: list[dict] = []
    for of in toate_oferte:
        if not isinstance(of, dict):
            continue
        f_of = " ".join(
            str(of.get(k) or "")
            for k in ("firma", "nume_firma", "client", "denumire_firma")
        ).lower()
        if firma_low in f_of:
            potriviri_firma.append(of)

    if not potriviri_firma:
        return []

    def _scor_oferta(of: dict) -> int:
        blob = " ".join(str(v or "") for v in of.values()).lower()
        scor = 0
        if masina_low and masina_low != OPT_MASINA_IMPLICIT.lower() and masina_low in blob:
            scor += 2
        if titlu_low and titlu_low != "intervenție tehnică" and titlu_low in blob:
            scor += 1
        return scor

    potriviri_firma.sort(key=_scor_oferta, reverse=True)
    return potriviri_firma


def _format_eticheta_oferta(of: dict, idx: int) -> str:
    cod = of.get("numar") or of.get("cod") or of.get("nr_oferta") or of.get("id") or (idx + 1)
    titlu = of.get("titlu") or of.get("denumire") or of.get("obiect") or "Ofertă"
    stare = of.get("status") or of.get("stare") or ""
    val = of.get("total") or of.get("valoare") or of.get("pret_total") or ""
    parti = [f"#{cod} — {titlu}"]
    if stare:
        parti.append(f"[{stare}]")
    if val not in ("", None):
        parti.append(f"({val})")
    return " ".join(parti)


def _ruleaza_sync_fundal(payload: dict) -> None:
    try:
        background_sync_task(payload)
    except Exception as exc:
        logger.exception("Eroare la sincronizarea în fundal pentru raportul #%s: %s", payload.get("id"), exc)


# ----------------------------------
# -------- FRAGMENTE & ECRANE ------
# ----------------------------------

@_fragment
def _render_consultare_rapida_docs(cod_eroare_curent: str, masina_id_sel) -> None:
    with st.expander("📚 Consultare rapidă Index GDrive (cod eroare / utilaj / simptom)", expanded=False):
        cod_sugerat = "" if cod_eroare_curent == OPT_EROARE_IMPLICIT else cod_eroare_curent
        q_doc = st.text_input(
            "Filtru rapid în documentația indexată",
            value=cod_sugerat,
            placeholder="ex: 414, AL.24, encoder, invertor...",
            key="act_quick_doc_search",
        )
        docs_rapide = _cauta_docs_rapide_interventie(q_doc, masina_id=masina_id_sel)
        if docs_rapide:
            for d in docs_rapide:
                hmi_d = str(d.get("coduri_eroare_hmi") or "").strip()
                drv_d = str(d.get("coduri_eroare_driver") or "").strip()
                pag_d = str(d.get("interval_pagini") or "").strip()
                st.markdown(
                    f"- **{d.get('tag_sectiune') or '[ERR]'} {d.get('titlu')}**"
                    + (f" — Cod HMI: `{hmi_d}`" if hmi_d else "")
                    + (f" — Driver/VFD: `{drv_d}`" if drv_d else "")
                    + (f" — Pagini: `{pag_d}`" if pag_d else "")
                    + (f" — [Google Drive]({d.get('gdrive_url')})" if d.get("gdrive_url") else "")
                )
        else:
            st.caption("Nu s-au găsit înregistrări în index pentru filtrul curent.")


def _render_ecran_raport_salvat(tehnician_def: str) -> None:
    rid_s = st.session_state["ultimul_id_salvat"]
    st.success(f"✅ Raportul #{rid_s} a fost salvat în baza de date! Verifică raportul, apoi confirmă trimiterea pe email.")

    oferte_gasite = _cauta_oferte_asociate(
        firma=st.session_state.get("ultim_firma_raport", ""),
        masina=st.session_state.get("ultim_masina_raport", ""),
        titlu=st.session_state.get("ultim_titlu_raport", ""),
    )

    oferta_selectata = None
    include_oferta_in_mail = False

    if oferte_gasite:
        st.success(f"💼 Am găsit **{len(oferte_gasite)}** ofertă/oferte asociată/asociate acestei firme/lucrări.")
        opt_of = list(range(len(oferte_gasite)))
        idx_of = st.selectbox(
            "Selectează oferta asociată",
            options=opt_of,
            format_func=lambda i: _format_eticheta_oferta(oferte_gasite[i], i),
            key="act_sel_oferta_asociata",
        )
        oferta_selectata = oferte_gasite[idx_of]
        include_oferta_in_mail = st.checkbox(
            "📎 Include detaliile ofertei selectate în emailul către client",
            value=True,
            key="act_include_oferta_mail",
        )
    else:
        st.caption("ℹ️ Nu s-a găsit nicio ofertă asociată momentan pentru această firmă/lucrare. Se va trimite doar raportul PDF.")

    if st.session_state.pop("solutie_indexata_flash", False):
        st.info("📚 Soluția (`[SOL]`) a fost adăugată și în indexul de documentație.")

    if st.session_state.pop("solutie_indexata_eroare", False):
        st.warning("⚠️ Raportul a fost salvat, dar soluția nu a putut fi adăugată în indexul de documentație.")

    col_act1, col_act2, col_act3 = st.columns([1.4, 1.8, 1.3])
    with col_act1:
        if st.session_state["ultimul_pdf_bytes"]:
            st.download_button(
                label="📥 Descarcă Raport PDF",
                data=st.session_state["ultimul_pdf_bytes"],
                file_name=f"Raport_{rid_s}.pdf",
                mime="application/pdf",
                type="secondary",
                use_container_width=True,
            )
    with col_act2:
        if not st.session_state["email_raport_trimis"]:
            if st.button("✅ Confirmă Verificarea & Trimite Raportul pe Email", type="primary", use_container_width=True):
                corp_mail = f"Vă atașăm raportul de intervenție #{rid_s}."

                if include_oferta_in_mail and oferta_selectata:
                    det_of = _format_eticheta_oferta(oferta_selectata, 0)
                    obs_of = str(
                        oferta_selectata.get("observatii")
                        or oferta_selectata.get("descriere")
                        or oferta_selectata.get("detalii")
                        or ""
                    ).strip()
                    corp_mail += f"\n\nOfertă asociată: {det_of}"
                    if obs_of:
                        corp_mail += f"\nDetalii ofertă: {obs_of}"

                ok_mail, info_mail = trimite_email_raport(
                    destinatar_client=st.session_state.get("ultim_email_client", ""),
                    subiect=f"Raport #{rid_s} - {st.session_state.get('ultim_firma_raport', '')}",
                    corp_mesaj=corp_mail,
                    pdf_bytes=st.session_state["ultimul_pdf_bytes"],
                    nume_fisier=f"Raport_{rid_s}.pdf",
                )
                if ok_mail:
                    st.session_state["email_raport_trimis"] = True
                    st.session_state["_email_trimis_info"] = info_mail
                else:
                    st.error(f"⚠️ Eroare la trimiterea emailului: {info_mail}")

        if st.session_state["email_raport_trimis"]:
            info_ok = st.session_state.get("_email_trimis_info", "")
            msg_ok = f"✉️ Raportul a fost confirmat și trimis pe email. ({info_ok})" if info_ok else "✉️ Raportul a fost confirmat și trimis pe email."
            st.info(msg_ok)

    with col_act3:
        st.button(
            "➕ Activitate nouă",
            use_container_width=True,
            on_click=_cb_activitate_noua,
            args=(tehnician_def,),
        )


def render_activitati() -> None:
    st.subheader("📝 Activități Zilnice & Raport Intervenție Tehnică")

    toast_msg = st.session_state.pop("_act_toast_msg", None)
    if toast_msg:
        st.toast(toast_msg)

    setari_act = _get_setari_cached()
    tehnician_def = setari_act.get("tehnician_implicit") or "Tehnician Nexus"

    init_draft("act_draft", _defaults_activitati(tehnician_def), "act_cnt")

    for k_def, v_def in {
        "raport_salvat": False,
        "ultimul_id_salvat": None,
        "ultimul_pdf_bytes": None,
        "ultim_email_client": "",
        "ultim_firma_raport": "",
        "ultim_masina_raport": "",
        "ultim_titlu_raport": "",
        "email_raport_trimis": False,
    }.items():
        if k_def not in st.session_state:
            st.session_state[k_def] = v_def

    if st.session_state["raport_salvat"]:
        _render_ecran_raport_salvat(tehnician_def)
        return

    draft = st.session_state["act_draft"]

    firme_db = _get_firme_cached()
    if not firme_db:
        st.warning("⚠️ Adăugați cel puțin o firmă în tabul de Firme.")
        return

    firme_dict = {f["nume_firma"]: f for f in firme_db if isinstance(f, dict) and f.get("nume_firma")}
    optiuni_firme = [OPT_FIRMA_IMPLICIT] + list(firme_dict.keys())

    top_a1, top_a2 = st.columns([4, 1], vertical_alignment="center")
    with top_a1:
        st.caption("💾 Datele activității în lucru se păstrează automat la schimbarea tab-ului.")
    with top_a2:
        st.button(
            "❌ Anulare Activitate",
            key="btn_anulare_act",
            use_container_width=True,
            on_click=_cb_anulare_activitate,
            args=(tehnician_def,),
        )

    k_firma = widget_key("act", "sel_firma", "act_cnt")
    k_masina = widget_key("act", "sel_masina", "act_cnt")
    aplica_context_la_tab(
        tab_prefix="act",
        optiuni_firme=optiuni_firme,
        default_firma=OPT_FIRMA_IMPLICIT,
        key_firma=k_firma,
        draft=draft,
        campo_firma="sel_firma",
        campo_masina="sel_masina",
    )

    k_firma, _ = lega_camp("act_draft", "sel_firma", OPT_FIRMA_IMPLICIT, "act", "act_cnt")
    _asigura_valoare_in_optiuni(draft, k_firma, "sel_firma", optiuni_firme, OPT_FIRMA_IMPLICIT)

    c_sel1, c_sel2, c_sel3 = st.columns(3)
    with c_sel1:
        sel_firma = st.selectbox(
            "1. Alege Firma",
            options=optiuni_firme,
            key=k_firma,
            on_change=sync_camp,
            args=("act_draft", k_firma, "sel_firma"),
        )

    if sel_firma == OPT_FIRMA_IMPLICIT:
        seteaza_context_selectie(firma=None, masina=None)
        st.info("ℹ️ Vă rugăm să selectați o firmă din listă pentru a continua.")
        return

    firma_obj = firme_dict[sel_firma]
    persoana_contact_firma = firma_obj.get("nume_persoana") or firma_obj.get("persoana_contact") or "Client"
    email_client_sel = _extrage_email_client(firma_obj)

    if draft.get("ultima_firma") != sel_firma:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = persoana_contact_firma
        k_verif_reset = widget_key("act", "verificator", "act_cnt")
        st.session_state[k_verif_reset] = persoana_contact_firma

    masini_db = _get_masini_by_firma_cached(firma_obj.get("id"))
    masini_nume = [m["denumire"] for m in masini_db if isinstance(m, dict) and m.get("denumire")] or [OPT_MASINA_IMPLICIT]

    aplica_context_la_tab(
        tab_prefix="act_mas",
        optiuni_firme=optiuni_firme,
        default_firma=sel_firma,
        key_firma=k_firma,
        optiuni_masini=masini_nume,
        default_masina=masini_nume[0],
        key_masina=k_masina,
        draft=draft,
        campo_firma="sel_firma",
        campo_masina="sel_masina",
    )

    k_masina, _ = lega_camp("act_draft", "sel_masina", OPT_MASINA_IMPLICIT, "act", "act_cnt")
    _asigura_valoare_in_optiuni(draft, k_masina, "sel_masina", masini_nume, masini_nume[0])

    with c_sel2:
        sel_masina = st.selectbox(
            "2. Alege Mașina",
            options=masini_nume,
            key=k_masina,
            on_change=sync_camp,
            args=("act_draft", k_masina, "sel_masina"),
        )

    seteaza_context_selectie(firma=sel_firma, masina=sel_masina)

    subansambluri, erori = [], []
    masina_id_sel = None
    if masini_db and sel_masina != OPT_MASINA_IMPLICIT:
        m_match = next((m for m in masini_db if m.get("denumire") == sel_masina), None)
        if m_match:
            masina_id_sel = m_match.get("id")
            if m_match.get("subansambluri"):
                subansambluri = [s.strip() for s in str(m_match["subansambluri"]).split(",") if s.strip()]
            if m_match.get("erori"):
                erori = [e.strip() for e in str(m_match["erori"]).split(",") if e.strip()]

    opt_sub = subansambluri if subansambluri else [OPT_SUB_IMPLICIT]
    k_sub, _ = lega_camp("act_draft", "sel_sub", OPT_SUB_IMPLICIT, "act", "act_cnt")
    _asigura_valoare_in_optiuni(draft, k_sub, "sel_sub", opt_sub, opt_sub[0])

    with c_sel3:
        sel_subansamblu = st.selectbox(
            "3. Subansamblu",
            options=opt_sub,
            key=k_sub,
            on_change=sync_camp,
            args=("act_draft", k_sub, "sel_sub"),
        )

    st.markdown("---")

    piese_catalog = _get_piese_catalog_cached()
    if "df_piese_editor" not in st.session_state:
        st.session_state["df_piese_editor"] = pd.DataFrame(columns=["Piesa", "Cantitate", "Tip"])

    _sincronizeaza_piese_activitate()

    st.markdown("##### 🔩 Piese Utilizate / Necesare")
    edited_df = st.data_editor(
        st.session_state["df_piese_editor"],
        num_rows="dynamic",
        column_config={
            "Piesa": st.column_config.SelectboxColumn("Piesă", options=piese_catalog, required=True),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=1, default=1),
            "Tip": st.column_config.SelectboxColumn("Tip", options=["Utilizata", "Inlocuita", "Necesara", "De Comandat"], required=True),
        },
        key=f"act_editor_piese_{st.session_state.get('act_editor_counter', 0)}",
        use_container_width=True,
    )
    st.session_state["df_piese_editor"] = edited_df

    st.markdown("##### 📋 Detalii Intervenție Tehnică")
    c1, c2 = st.columns(2)
    with c1:
        k_titlu, _ = lega_camp("act_draft", "titlu_lucrare", "Intervenție tehnică", "act", "act_cnt")
        titlu_lucrare = st.text_input(
            "Titlu",
            key=k_titlu,
            on_change=sync_camp,
            args=("act_draft", k_titlu, "titlu_lucrare"),
        )

        k_simptom, _ = lega_camp("act_draft", "simptom", "", "act", "act_cnt")
        simptom = st.text_area(
            "Simptom",
            key=k_simptom,
            on_change=sync_camp,
            args=("act_draft", k_simptom, "simptom"),
        )

        k_defect, _ = lega_camp("act_draft", "defect", "", "act", "act_cnt")
        defect = st.text_area(
            "Defect",
            key=k_defect,
            on_change=sync_camp,
            args=("act_draft", k_defect, "defect"),
        )

        opt_erori = [OPT_EROARE_IMPLICIT] + erori
        k_err, _ = lega_camp("act_draft", "cod_eroare", OPT_EROARE_IMPLICIT, "act", "act_cnt")
        _asigura_valoare_in_optiuni(draft, k_err, "cod_eroare", opt_erori, OPT_EROARE_IMPLICIT)

        cod_eroare = st.selectbox(
            "Cod Eroare",
            options=opt_erori,
            key=k_err,
            on_change=sync_camp,
            args=("act_draft", k_err, "cod_eroare"),
        )

    with c2:
        k_sol, _ = lega_camp("act_draft", "solutie", "", "act", "act_cnt")
        solutie = st.text_area(
            "Soluție",
            key=k_sol,
            on_change=sync_camp,
            args=("act_draft", k_sol, "solutie"),
        )

        k_dur, _ = lega_camp("act_draft", "durata_min", 60, "act", "act_cnt", transform=lambda x: int(x or 60))
        durata_min = st.number_input(
            "Durată (min)",
            step=15,
            key=k_dur,
            on_change=sync_camp,
            args=("act_draft", k_dur, "durata_min"),
        )

        opt_tip = ["reparatie", "diagnostic", "consultanta"]
        k_tip, _ = lega_camp("act_draft", "tip_interventie", "reparatie", "act", "act_cnt")
        _asigura_valoare_in_optiuni(draft, k_tip, "tip_interventie", opt_tip, "reparatie")

        tip_interventie = st.selectbox(
            "Tip",
            options=opt_tip,
            key=k_tip,
            on_change=sync_camp,
            args=("act_draft", k_tip, "tip_interventie"),
        )

        opt_stare = ["Funcțională", "În testare", "Oprită / Necesar piese"]
        k_stare, _ = lega_camp("act_draft", "stare_fin", "Funcțională", "act", "act_cnt")
        _asigura_valoare_in_optiuni(draft, k_stare, "stare_fin", opt_stare, "Funcțională")

        stare_fin = st.selectbox(
            "Stare Finală",
            options=opt_stare,
            key=k_stare,
            on_change=sync_camp,
            args=("act_draft", k_stare, "stare_fin"),
        )

    c_t1, c_t2 = st.columns(2)
    k_tehn, _ = lega_camp("act_draft", "tehnician", tehnician_def, "act", "act_cnt")
    tehnician = c_t1.text_input(
        "Tehnician",
        key=k_tehn,
        on_change=sync_camp,
        args=("act_draft", k_tehn, "tehnician"),
    )

    opt_verif = list(dict.fromkeys([persoana_contact_firma, "Client"]))
    k_verif, _ = lega_camp("act_draft", "verificator", opt_verif[0], "act", "act_cnt")
    _asigura_valoare_in_optiuni(draft, k_verif, "verificator", opt_verif, opt_verif[0])

    verificator = c_t2.selectbox(
        "Verificat de",
        options=opt_verif,
        key=k_verif,
        on_change=sync_camp,
        args=("act_draft", k_verif, "verificator"),
    )

    k_opt, _ = lega_camp("act_draft", "optimizari", "", "act", "act_cnt")
    optimizari = st.text_area(
        "Recomandări",
        key=k_opt,
        on_change=sync_camp,
        args=("act_draft", k_opt, "optimizari"),
    )

    _render_consultare_rapida_docs(cod_eroare, masina_id_sel)

    salveaza_in_index_sol = st.checkbox(
        "💾 Salvează soluția și în Indexul de Documentație (`[SOL]`) la finalizare",
        value=False,
        key="act_save_to_doc_sol",
    )

    submitted = st.button("💾 Salvează Activitatea", type="primary", use_container_width=True)

    if submitted:
        if isinstance(edited_df, pd.DataFrame) and "Piesa" in edited_df.columns:
            df_curat = edited_df.dropna(subset=["Piesa"]).copy()
            df_curat = df_curat[df_curat["Piesa"].astype(str).str.strip() != ""]
            piese_valide = df_curat.to_dict(orient="records")
        else:
            piese_valide = []

        data_rep = {
            "firma": sel_firma,
            "masina": sel_masina,
            "subansamblu": sel_subansamblu,
            "defect": defect,
            "cod_eroare": cod_eroare,
            "piese_valide": piese_valide,
            "titlu_lucrare": titlu_lucrare,
            "simptom": simptom,
            "solutie": solutie,
            "stare_fin": stare_fin,
            "durata_min": durata_min,
            "optimizari": optimizari,
            "tehnician_nume": tehnician,
            "verificator_nume": verificator,
            "tip_interventie": tip_interventie,
        }
        rid = ReparatiiRepository.insert(data_rep)
        if not rid:
            st.error("⚠️ Nu s-a putut salva raportul în baza de date. Verifică conexiunea și încearcă din nou.")
            return

        if salveaza_in_index_sol and (str(solutie or "").strip() or str(defect or "").strip()):
            try:
                cod_curat = "" if cod_eroare == OPT_EROARE_IMPLICIT else str(cod_eroare).strip()
                text_sol_parti = []
                if str(simptom or "").strip():
                    text_sol_parti.append(f"Simptom: {str(simptom).strip()}")
                if str(defect or "").strip():
                    text_sol_parti.append(f"Defect: {str(defect).strip()}")
                if str(solutie or "").strip():
                    text_sol_parti.append(f"Soluție: {str(solutie).strip()}")
                if str(optimizari or "").strip():
                    text_sol_parti.append(f"Recomandări: {str(optimizari).strip()}")

                DocumentatieRepository.insert({
                    "masina_id": int(masina_id_sel) if masina_id_sel is not None else None,
                    "categorie": "CNC",
                    "tip_sistem": str(sel_subansamblu or "").strip(),
                    "titlu": f"{titlu_lucrare} ({sel_masina})" if sel_masina != OPT_MASINA_IMPLICIT else titlu_lucrare,
                    "gdrive_file_id": "",
                    "gdrive_url": "",
                    "tip_fisier": "doc",
                    "tag_sectiune": "[SOL]",
                    "interval_pagini": "",
                    "coduri_eroare_hmi": cod_curat,
                    "coduri_eroare_driver": "",
                    "text_indexat": "\n".join(text_sol_parti),
                })
                _get_documentatie_cached.clear()
                st.session_state["solutie_indexata_flash"] = True
            except Exception as exc:
                logger.warning("Nu s-a putut salva soluția în indexul de documentație: %s", exc)
                st.session_state["solutie_indexata_eroare"] = True

        pdf_bytes = genereaza_pdf({
            "id": rid,
            "client": sel_firma,
            "masina": sel_masina,
            "durata": durata_min,
            "stare_finala": stare_fin,
            "piese_json": [{"piesa": p.get("Piesa"), "cantitate": p.get("Cantitate"), "tip": p.get("Tip")} for p in piese_valide],
            "titlu": titlu_lucrare,
            "simptom": simptom,
            "defect": defect,
            "solutie": solutie,
            "optimizari": optimizari,
            "tehnician": tehnician,
            "verificator": verificator,
            "data": datetime.now(),
            "tip_interventie": tip_interventie,
        })

        st.session_state["ultimul_id_salvat"] = rid
        st.session_state["ultimul_pdf_bytes"] = pdf_bytes
        st.session_state["ultim_email_client"] = email_client_sel
        st.session_state["ultim_firma_raport"] = sel_firma
        st.session_state["ultim_masina_raport"] = sel_masina
        st.session_state["ultim_titlu_raport"] = titlu_lucrare
        st.session_state["email_raport_trimis"] = False

        threading.Thread(
            target=_ruleaza_sync_fundal,
            args=({
                "status": "nefacturat",
                "id": str(rid),
                "data": datetime.now().strftime("%Y-%m-%d"),
                "tip_interventie": tip_interventie,
                "ora": f"{durata_min} min",
                "firma": sel_firma,
                "masina": sel_masina,
                "tehnician": tehnician,
                "verificator": verificator,
            },),
            daemon=True,
        ).start()

        _init_sau_reseteaza_act_draft(tehnician_def)
        st.session_state["raport_salvat"] = True
        st.rerun()