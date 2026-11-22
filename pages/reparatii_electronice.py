#------------------------------------------
#-------reparatii_electronice.py-----------
#------------------------------------------

import json
import streamlit as st
import pandas as pd
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.reparatii_electronice_repository import ReparatiiElectroniceRepository
from repositories.setari_repository import SetariRepository
from repositories.documentatie_repository import DocumentatieRepository
from services.pdf_service import genereaza_pdf_electronic

OPT_STARI_FINALE = ["În lucru / Diagnosticare", "Funcțional", "Nefuncțional", "Înlocuit complet"]
OPT_STARI_COMP = ["Inlocuita", "Necesara", "Reparata","Masurata/OK"]
COL_COMP_DEN = "Componenta / Cod / Parametri"
COL_COMP_CANT = "Cantitate"
COL_COMP_STARE = "Stare"
COLS_COMP_EDITOR = [COL_COMP_DEN, COL_COMP_CANT, COL_COMP_STARE]
MAX_LEN_DREAPTA = 30


def _limita_30(val) -> str:
    return str(val or "")[:MAX_LEN_DREAPTA]


def _cauta_docs_electronice(termen: str, masina_id=None) -> list[dict]:
    """Caută în indexul de documentație după subansamblu, cod, componente sau utilaj."""
    q = str(termen or "").strip().lower()
    try:
        toate_doc = DocumentatieRepository.get_all() or []
    except Exception:
        return []

    rezultate = []
    for d in toate_doc:
        d_mid = d.get("masina_id")
        if masina_id is not None and d_mid not in (None, masina_id):
            continue
        blob = " ".join([
            str(d.get("tag_sectiune") or ""),
            str(d.get("categorie") or ""),
            str(d.get("titlu") or ""),
            str(d.get("tip_sistem") or ""),
            str(d.get("coduri_eroare_hmi") or ""),
            str(d.get("coduri_eroare_driver") or ""),
            str(d.get("interval_pagini") or ""),
            str(d.get("piese_necesare") or ""),
            str(d.get("text_indexat") or ""),
        ]).lower()
        if not q or q in blob:
            rezultate.append(d)
    return rezultate[:6]


def _normalizeaza_cantitate(val, implicit: float = 1.0) -> float:
    try:
        cant = float(val)
        return cant if cant > 0 else implicit
    except (TypeError, ValueError):
        return implicit


def _formateaza_componente_index(comp_lista: list[dict]) -> str:
    """Formatează componentele din fișa electronică pentru indexare."""
    if not comp_lista:
        return ""
    parti = []
    for c in comp_lista:
        if not isinstance(c, dict):
            continue
        den = str(c.get(COL_COMP_DEN) or "").strip()
        if not den:
            continue
        cant = _normalizeaza_cantitate(c.get(COL_COMP_CANT), 1.0)
        cant_txt = f" x{cant:g}" if cant != 1.0 else ""
        stare_c = str(c.get(COL_COMP_STARE) or "").strip()
        detalii = f"{cant_txt} ({stare_c})" if stare_c else cant_txt
        parti.append(f"{den}{detalii}")
    return ", ".join(parti)


def _parseaza_componente_json(raw_comp) -> list[dict]:
    if isinstance(raw_comp, list):
        raw_list = [r for r in raw_comp if isinstance(r, dict)]
    elif isinstance(raw_comp, str) and raw_comp.strip():
        try:
            parsed = json.loads(raw_comp)
            raw_list = [r for r in parsed if isinstance(r, dict)] if isinstance(parsed, list) else []
        except Exception:
            raw_list = []
    else:
        raw_list = []

    normalizate = []
    for r in raw_list:
        den = str(r.get(COL_COMP_DEN) or "").strip()
        if not den:
            continue
        stare = str(r.get(COL_COMP_STARE) or OPT_STARI_COMP[0]).strip()
        if stare not in OPT_STARI_COMP:
            stare = OPT_STARI_COMP[0]
        normalizate.append({
            COL_COMP_DEN: den,
            COL_COMP_CANT: _normalizeaza_cantitate(r.get(COL_COMP_CANT), 1.0),
            COL_COMP_STARE: stare,
        })
    return normalizate


def _init_sau_reseteaza_el_draft(tehnician_def: str):
    st.session_state["el_editing_id"] = None
    st.session_state["el_editing_meta"] = {}
    st.session_state["el_draft"] = {
        "sel_firma": "-- Alege firma --",
        "apartenenta_masina": False,
        "sel_masina": "General / Fără mașină",
        "piesa_subansamblu": "",
        "defect_reclamat": "",
        "stare_finala": _limita_30(OPT_STARI_FINALE[0]),
        "tehnician": _limita_30(tehnician_def),
        "verificator": _limita_30("Client"),
        "ultima_firma": "-- Alege firma --",
    }
    st.session_state["df_comp_editor"] = pd.DataFrame(columns=COLS_COMP_EDITOR)
    st.session_state["el_editor_counter"] = st.session_state.get("el_editor_counter", 0) + 1


def _incarca_fisa_in_editor(fisa: dict, tehnician_def: str):
    """Încarcă o fișă existentă din istoric în formular pentru editare/continuare pe mai multe zile."""
    comp_lista = _parseaza_componente_json(fisa.get("componente_json"))
    are_masina = bool(fisa.get("masina_id")) or (
        bool(fisa.get("masina_nume")) and str(fisa.get("masina_nume")).strip() != "General / Fără mașină"
    )
    stare_db = _limita_30(fisa.get("stare_finala") or OPT_STARI_FINALE[0]).strip()
    if stare_db and stare_db not in OPT_STARI_FINALE:
        OPT_STARI_FINALE.append(stare_db)

    st.session_state["el_editing_id"] = fisa.get("id")
    st.session_state["el_editing_meta"] = {
        "firma_id": fisa.get("firma_id"),
        "masina_id": fisa.get("masina_id"),
        "firma_nume": fisa.get("firma_nume") or "",
        "masina_nume": fisa.get("masina_nume") or "General / Fără mașină",
        "data_creare": fisa.get("data_creare") or datetime.now(),
    }
    st.session_state["el_draft"] = {
        "sel_firma": fisa.get("firma_nume") or "-- Alege firma --",
        "apartenenta_masina": are_masina,
        "sel_masina": fisa.get("masina_nume") or "General / Fără mașină",
        "piesa_subansamblu": str(fisa.get("piesa_subansamblu") or ""),
        "defect_reclamat": str(fisa.get("defect_reclamat") or ""),
        "stare_finala": stare_db or OPT_STARI_FINALE[0],
        "tehnician": _limita_30(fisa.get("tehnician") or tehnician_def),
        "verificator": _limita_30(fisa.get("verificator") or "Client"),
        "ultima_firma": fisa.get("firma_nume") or "-- Alege firma --",
    }
    if comp_lista:
        df_c = pd.DataFrame(comp_lista)
        if COL_COMP_CANT not in df_c.columns:
            df_c[COL_COMP_CANT] = 1.0
        st.session_state["df_comp_editor"] = df_c[COLS_COMP_EDITOR]
    else:
        st.session_state["df_comp_editor"] = pd.DataFrame(columns=COLS_COMP_EDITOR)
    st.session_state["el_editor_counter"] = st.session_state.get("el_editor_counter", 0) + 1
    st.session_state["electrice_salvat"] = False


def render_reparatii_electronice():
    st.subheader("⚡ Gestiune Reparații Electronice & Mecatronice")

    setari_el = SetariRepository.get_setari() or {}
    tehnician_def_el = _limita_30(setari_el.get("tehnician_implicit") or "Tehnician Nexus")

    if "el_draft" not in st.session_state:
        _init_sau_reseteaza_el_draft(tehnician_def_el)
    if "electrice_salvat" not in st.session_state:
        st.session_state["electrice_salvat"] = False
    if "electrice_pdf" not in st.session_state:
        st.session_state["electrice_pdf"] = None
    if "electrice_id" not in st.session_state:
        st.session_state["electrice_id"] = None
    if "el_editing_id" not in st.session_state:
        st.session_state["el_editing_id"] = None
    if "el_editing_meta" not in st.session_state:
        st.session_state["el_editing_meta"] = {}

    draft = st.session_state["el_draft"]
    editing_id = st.session_state.get("el_editing_id")

    firme_db = FirmeRepository.get_all()
    firme_dict = {f["nume_firma"]: f for f in firme_db}

    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă.")
        return

    if st.session_state["electrice_salvat"]:
        actiune_msg = "actualizată" if st.session_state.get("el_a_fost_editare") else "salvată"
        st.success(f"✅ Fișa de reparație electronică #{st.session_state['electrice_id']} a fost {actiune_msg} cu succes!")
        if st.session_state.pop("el_solutie_indexata_flash", False):
            st.info("📚 Reparația / componentele au fost salvate și în indexul de documentație (`[SOL]`).")
        if st.session_state["electrice_pdf"]:
            st.download_button(
                label="📥 Descarcă Raport PDF Reparație Electronică",
                data=st.session_state["electrice_pdf"],
                file_name=f"Raport_Electronic_{st.session_state['electrice_id']}.pdf",
                mime="application/pdf",
                type="primary",
            )
        if st.button("➕ Adaugă altă reparație electronică"):
            st.session_state["electrice_salvat"] = False
            st.session_state["el_a_fost_editare"] = False
            st.session_state["electrice_pdf"] = None
            st.session_state["electrice_id"] = None
            _init_sau_reseteaza_el_draft(tehnician_def_el)
            st.rerun()
        return

    if editing_id is not None:
        st.warning(f"✏️ **Mod editare activ pentru Fișa #{editing_id}** — poți adăuga etape, componente sau schimba starea finală pe parcursul mai multor zile.")

    top_e1, top_e2 = st.columns([4, 1], vertical_alignment="center")
    with top_e1:
        st.caption("💾 Datele fișei electronice se păstrează automat la schimbarea tab-ului.")
    with top_e2:
        if st.button("❌ Anulare Fișă", key="btn_anulare_el_top", use_container_width=True):
            _init_sau_reseteaza_el_draft(tehnician_def_el)
            st.toast("🗑️ Datele fișei electronice au fost resetate.")
            st.rerun()

    optiuni_firme = ["-- Alege firma --"] + list(firme_dict.keys())
    idx_f = optiuni_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in optiuni_firme else 0
    sel_firma = st.selectbox("1. Alege Firma", options=optiuni_firme, index=idx_f)
    draft["sel_firma"] = sel_firma

    if sel_firma != "-- Alege firma --":
        firma_obj = firme_dict[sel_firma]
        if draft.get("ultima_firma") != sel_firma:
            draft["ultima_firma"] = sel_firma
            if editing_id is None:
                draft["verificator"] = _limita_30(
                    firma_obj.get("nume_persoana") or firma_obj.get("persoana_contact") or "Client"
                )

        masini_db = MasiniRepository.get_by_firma(firma_obj["id"])
        masini_nume = [m["denumire"] for m in masini_db]

        apartenenta_masina = st.checkbox(
            "Echipamentul / Piesa aparține unei mașini înregistrate?",
            value=bool(draft.get("apartenenta_masina", False)),
        )
        draft["apartenenta_masina"] = apartenenta_masina

        sel_masina = "General / Fără mașină"
        masina_obj_id = None

        if apartenenta_masina and masini_nume:
            idx_m = masini_nume.index(draft["sel_masina"]) if draft.get("sel_masina") in masini_nume else 0
            sel_masina = st.selectbox("Alege Mașina", options=masini_nume, index=idx_m)
            draft["sel_masina"] = sel_masina
            m_match = next((m for m in masini_db if m["denumire"] == sel_masina), None)
            if m_match:
                masina_obj_id = m_match["id"]
        else:
            draft["sel_masina"] = "General / Fără mașină"

        st.markdown(
            """
            <style>
                div[data-testid="stVerticalBlock"]:has(> div > div[data-testid="stMarkdownContainer"] .el-col-dreapta-30)
                [data-testid="stTextInput"],
                div[data-testid="stVerticalBlock"]:has(> div > div[data-testid="stMarkdownContainer"] .el-col-dreapta-30)
                [data-testid="stSelectboxF"] {
                    max-width: 22ch !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns([2.35, 1.0])
        with c1:
            piesa_subansamblu = st.text_input(
                "Piesă sau Subansamblu (ex: Placă de bază CNC, Invertor, Unitate comandă)",
                value=str(draft.get("piesa_subansamblu", "")),
            )
            draft["piesa_subansamblu"] = piesa_subansamblu

            defect_reclamat = st.text_area(
                "Defect Reclamat & Jurnal Intervenție / Etape (poți completa pe mai multe zile)",
                value=str(draft.get("defect_reclamat", "")),
                height=360,
            )
            draft["defect_reclamat"] = defect_reclamat
        with c2:
            st.markdown('<span class="el-col-dreapta-30" style="display:none;"></span>', unsafe_allow_html=True)

            stare_draft = _limita_30(draft.get("stare_finala", OPT_STARI_FINALE[0]))
            if stare_draft and stare_draft not in OPT_STARI_FINALE:
                OPT_STARI_FINALE.append(stare_draft)
            idx_st = OPT_STARI_FINALE.index(stare_draft) if stare_draft in OPT_STARI_FINALE else 0
            stare_finala = _limita_30(
                st.selectbox("Stare Reparație (max 30 caractere)", options=OPT_STARI_FINALE, index=idx_st)
            )
            draft["stare_finala"] = stare_finala

            tehnician = _limita_30(
                st.text_input(
                    "Tehnician Electronică (max 30 caractere)",
                    value=_limita_30(draft.get("tehnician", tehnician_def_el)),
                    max_chars=MAX_LEN_DREAPTA,
                )
            )
            draft["tehnician"] = tehnician

            verificator = _limita_30(
                st.text_input(
                    "Verificat de (max 30 caractere)",
                    value=_limita_30(draft.get("verificator", "Client")),
                    max_chars=MAX_LEN_DREAPTA,
                )
            )
            draft["verificator"] = verificator

        st.markdown("#### 🔌 Componente Electronice / Elemente Defecte sau Înlocuite")
        st.info("Adăugați componente electronice (cu cod piesă/parametri), cantitatea utilizată/necesară și starea fiecărei piese.")

        if "df_comp_editor" not in st.session_state:
            st.session_state["df_comp_editor"] = pd.DataFrame(columns=COLS_COMP_EDITOR)
        elif COL_COMP_CANT not in st.session_state["df_comp_editor"].columns:
            st.session_state["df_comp_editor"][COL_COMP_CANT] = 1.0
            st.session_state["df_comp_editor"] = st.session_state["df_comp_editor"][COLS_COMP_EDITOR]

        edited_comp_df = st.data_editor(
            st.session_state["df_comp_editor"],
            num_rows="dynamic",
            column_config={
                COL_COMP_DEN: st.column_config.TextColumn(
                    "Componentă / Cod / Parametri (ex: C 100uF 50V, Rotiță dințată z=15)",
                    required=True,
                ),
                COL_COMP_CANT: st.column_config.NumberColumn(
                    "Cantitate",
                    min_value=0.01,
                    step=1.0,
                    format="%.2f",
                    default=1.0,
                    required=True,
                ),
                COL_COMP_STARE: st.column_config.SelectboxColumn(
                    "Stare Componentă",
                    options=OPT_STARI_COMP,
                    default=OPT_STARI_COMP[0],
                    required=True,
                ),
            },
            key=f"el_comp_editor_{st.session_state.get('el_editor_counter', 0)}",
            use_container_width=True,
        )
        st.session_state["df_comp_editor"] = edited_comp_df

        # --- CONSULTARE RAPIDA IN INDEXUL DE DOCUMENTATIE ---
        with st.expander("📚 Consultare rapidă Index GDrive (scheme [SCH], parametri [PRM], coduri [ERR]/[ALM])", expanded=False):
            termen_sugerat = str(piesa_subansamblu or defect_reclamat or "").strip()
            q_el_doc = st.text_input(
                "Filtru rapid în indexul de documentație",
                value=termen_sugerat,
                placeholder="ex: invertor, IGBT, AL.24, 414, pinout...",
                key="el_quick_doc_search",
            )
            docs_el = _cauta_docs_electronice(q_el_doc, masina_id=masina_obj_id)
            if docs_el:
                for d in docs_el:
                    hmi_d = str(d.get("coduri_eroare_hmi") or "").strip()
                    drv_d = str(d.get("coduri_eroare_driver") or "").strip()
                    pag_d = str(d.get("interval_pagini") or "").strip()
                    st.markdown(
                        f"- **{d.get('tag_sectiune') or '[ERR]'} {d.get('titlu')}**"
                        + (f" — HMI: `{hmi_d}`" if hmi_d else "")
                        + (f" — Driver/VFD: `{drv_d}`" if drv_d else "")
                        + (f" — Pagini: `{pag_d}`" if pag_d else "")
                        + (f" — [Google Drive]({d.get('gdrive_url')})" if d.get("gdrive_url") else "")
                    )
            else:
                st.caption("Nu s-au găsit înregistrări în index pentru filtrul curent.")

        salveaza_in_index_el = st.checkbox(
            "💾 Salvează reparația și componentele în Indexul de Documentație (`[SOL]`) la finalizare",
            value=False,
            key="el_save_to_doc_sol",
        )

        label_btn_save = (
            f"💾 Actualizează Fișa Electronică #{editing_id}"
            if editing_id is not None
            else "💾 Salvează Fișa Electronică"
        )
        be1, be2 = st.columns([2, 1])
        with be1:
            salveaza_el = st.button(label_btn_save, type="primary", use_container_width=True)
        with be2:
            if st.button("❌ Anulare Fișă", key="btn_anulare_el_jos", use_container_width=True):
                _init_sau_reseteaza_el_draft(tehnician_def_el)
                st.rerun()

        if salveaza_el:
            if not piesa_subansamblu.strip():
                st.error("Completați denumirea piesei sau subansamblului.")
            else:
                df_comp_cur = edited_comp_df.dropna(subset=[COL_COMP_DEN]).copy()
                componente_valide = []
                for _, r_c in df_comp_cur.iterrows():
                    den_c = str(r_c.get(COL_COMP_DEN) or "").strip()
                    if not den_c:
                        continue
                    stare_c = str(r_c.get(COL_COMP_STARE) or OPT_STARI_COMP[0]).strip()
                    if stare_c not in OPT_STARI_COMP:
                        stare_c = OPT_STARI_COMP[0]
                    componente_valide.append({
                        COL_COMP_DEN: den_c,
                        COL_COMP_CANT: _normalizeaza_cantitate(r_c.get(COL_COMP_CANT), 1.0),
                        COL_COMP_STARE: stare_c,
                    })

                stare_finala_cur = _limita_30(stare_finala)
                tehnician_cur = _limita_30(tehnician)
                verificator_cur = _limita_30(verificator)

                payload = {
                    "firma_id": firma_obj["id"],
                    "masina_id": masina_obj_id,
                    "firma_nume": sel_firma,
                    "masina_nume": sel_masina,
                    "piesa_subansamblu": piesa_subansamblu.strip(),
                    "defect_reclamat": defect_reclamat,
                    "componente_json": componente_valide,
                    "stare_finala": stare_finala_cur,
                    "tehnician": tehnician_cur,
                    "verificator": verificator_cur,
                }

                if editing_id is not None:
                    ReparatiiElectroniceRepository.update(editing_id, payload)
                    rid = editing_id
                    st.session_state["el_a_fost_editare"] = True
                else:
                    rid = ReparatiiElectroniceRepository.insert(payload)
                    st.session_state["el_a_fost_editare"] = False

                if rid:
                    if salveaza_in_index_el:
                        try:
                            comp_txt = _formateaza_componente_index(componente_valide)
                            parti_doc = []
                            if str(defect_reclamat or "").strip():
                                parti_doc.append(f"Defect reclamat: {str(defect_reclamat).strip()}")
                            parti_doc.append(f"Stare finală: {stare_finala_cur}")
                            if comp_txt:
                                parti_doc.append(f"Piese necesare: {comp_txt}")

                            DocumentatieRepository.insert({
                                "firma_id": firma_obj["id"],
                                "masina_id": masina_obj_id,
                                "categorie": "CNC",
                                "tip_sistem": piesa_subansamblu.strip(),
                                "titlu": f"{piesa_subansamblu.strip()} ({sel_masina}) — {stare_finala_cur}",
                                "gdrive_file_id": "",
                                "gdrive_url": "",
                                "tip_fisier": "doc",
                                "tag_sectiune": "[SOL]",
                                "interval_pagini": "",
                                "coduri_eroare_hmi": "",
                                "coduri_eroare_driver": "",
                                "piese_necesare": comp_txt,
                                "text_indexat": "\n".join(parti_doc),
                            })
                            st.session_state["el_solutie_indexata_flash"] = True
                        except Exception:
                            pass

                    pdf_bytes = genereaza_pdf_electronic({
                        "id": rid,
                        "client": sel_firma,
                        "masina": sel_masina,
                        "piesa_subansamblu": piesa_subansamblu.strip(),
                        "defect_reclamat": defect_reclamat,
                        "componente_json": componente_valide,
                        "stare_finala": stare_finala_cur,
                        "tehnician": tehnician_cur,
                        "verificator": verificator_cur,
                        "data": datetime.now(),
                    })

                    st.session_state["electrice_id"] = rid
                    st.session_state["electrice_pdf"] = pdf_bytes
                    _init_sau_reseteaza_el_draft(tehnician_def_el)
                    st.session_state["electrice_salvat"] = True
                    st.rerun()

    # ------------------------------------------------------------------
    # SECȚIUNE ISTORIC & CONTINUARE / EDITARE FIȘE EXISTENTE
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📂 Istoric Fișe Reparații Electronice (Continuare & Editare)")

    fh1, fh2 = st.columns([2, 3], vertical_alignment="bottom")
    with fh1:
        filtru_firma_el = st.selectbox(
            "Filtrează istoric după firmă",
            options=["Toate firmele"] + list(firme_dict.keys()),
            key="el_hist_filtru_firma",
        )
    with fh2:
        filtru_txt_el = st.text_input(
            "Caută după subansamblu, defect sau tehnician",
            placeholder="ex: invertor, PLC, IGBT...",
            key="el_hist_filtru_txt",
        ).strip().lower()

    fise_istoric = ReparatiiElectroniceRepository.get_all() or []
    fise_filtrate = []
    for f_row in fise_istoric:
        ok_firma = (filtru_firma_el == "Toate firmele") or (f_row.get("firma_nume") == filtru_firma_el)
        blob_f = " ".join([
            str(f_row.get("id") or ""),
            str(f_row.get("firma_nume") or ""),
            str(f_row.get("masina_nume") or ""),
            str(f_row.get("piesa_subansamblu") or ""),
            str(f_row.get("defect_reclamat") or ""),
            str(f_row.get("tehnician") or ""),
            str(f_row.get("stare_finala") or ""),
        ]).lower()
        ok_txt = (not filtru_txt_el) or (filtru_txt_el in blob_f)
        if ok_firma and ok_txt:
            fise_filtrate.append(f_row)

    if not fise_filtrate:
        st.info("Nu există fișe electronice salvate care să corespundă filtrelor.")
        return

    for f_row in fise_filtrate[:50]:
        fid = f_row.get("id")
        data_str = str(f_row.get("data_creare") or "")[:16]
        stare_f = _limita_30(f_row.get("stare_finala") or "Nespecificat")
        titlu_exp = (
            f"⚡ Fișa #{fid} | {f_row.get('firma_nume') or '-'} | "
            f"{f_row.get('piesa_subansamblu') or '-'} — {stare_f} ({data_str})"
        )
        with st.expander(titlu_exp, expanded=False):
            st.write(f"**Mașină:** {f_row.get('masina_nume') or 'General / Fără mașină'}")
            st.write(f"**Tehnician:** {_limita_30(f_row.get('tehnician') or '-')} | **Verificat de:** {_limita_30(f_row.get('verificator') or '-')}")
            st.write(f"**Defect / Note / Etape:**\n{f_row.get('defect_reclamat') or '-'}")

            comp_f = _parseaza_componente_json(f_row.get("componente_json"))
            if comp_f:
                st.dataframe(pd.DataFrame(comp_f)[COLS_COMP_EDITOR], use_container_width=True, hide_index=True)
            else:
                st.caption("Fără componente înregistrate.")

            ce_btn1, ce_btn2 = st.columns([2, 1])
            with ce_btn1:
                if st.button("✏️ Editează / Continuă Fișa", key=f"edit_fisa_el_{fid}", type="primary", use_container_width=True):
                    _incarca_fisa_in_editor(f_row, tehnician_def_el)
                    st.rerun()
            with ce_btn2:
                if st.button("📥 PDF", key=f"pdf_fisa_el_{fid}", use_container_width=True):
                    pdf_f = genereaza_pdf_electronic({
                        "id": fid,
                        "client": f_row.get("firma_nume") or "",
                        "masina": f_row.get("masina_nume") or "General / Fără mașină",
                        "piesa_subansamblu": f_row.get("piesa_subansamblu") or "",
                        "defect_reclamat": f_row.get("defect_reclamat") or "",
                        "componente_json": comp_f,
                        "stare_finala": stare_f,
                        "tehnician": _limita_30(f_row.get("tehnician") or tehnician_def_el),
                        "verificator": _limita_30(f_row.get("verificator") or "Client"),
                        "data": f_row.get("data_creare") or datetime.now(),
                    })
                    st.download_button(
                        label=f"⬇️ Descarcă PDF #{fid}",
                        data=pdf_f,
                        file_name=f"Raport_Electronic_{fid}.pdf",
                        mime="application/pdf",
                        key=f"dl_fisa_el_{fid}",
                    )

