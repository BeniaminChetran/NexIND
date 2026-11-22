# ------------------------------------------
# -------pages/mentenanta.py----------------
# ------------------------------------------

import json
import re
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.mentenanta_repository import MentenantaRepository, INTERVALE_ZILE
from repositories.setari_repository import SetariRepository
from services.pdf_service import genereaza_pdf_mentenanta
from pages.fise_mentenanta import (
    FRECVENTE_MENTENANTA,
    adauga_operatiune_in_catalog_db,
    construieste_nume_fisa,
    incarca_catalog_operatiuni_db,
    obtine_fisa_pentru_utilaj,
)


def _frecventa_in_titlu(frecventa: str) -> str:
    f = str(frecventa or "lunare").strip().lower()
    mapa = {
        "zilnică": "zilnice",
        "zilnica": "zilnice",
        "săptămânală": "saptamanale",
        "saptamanala": "saptamanale",
        "lunară": "lunare",
        "lunara": "lunare",
        "trimestrială": "trimestriale",
        "trimestriala": "trimestriale",
        "anuală": "anuale",
        "anuala": "anuale",
    }
    return mapa.get(f, f or "lunare")


def construieste_titlu_operatiuni_pdf(
    frecventa: str,
    masina: str,
    tip_masina: str,
    data_str: str,
    firma: str,
) -> str:
    frec_txt = _frecventa_in_titlu(frecventa)
    m_txt = str(masina or "-").strip()
    t_txt = str(tip_masina or "-").strip()
    d_txt = str(data_str or "").strip()[:10]
    f_txt = str(firma or "-").strip()
    return f"Operatiuni de intretinere {frec_txt} la masina {m_txt} tip {t_txt} {d_txt} {f_txt}".strip()


def construieste_nume_fisier_pdf(titlu_pdf: str, fid: int | str | None = None) -> str:
    baza = re.sub(r'[\\/:*?"<>|]+', "", str(titlu_pdf or "Operatiuni de intretinere")).strip()
    baza = re.sub(r"\s+", "_", baza)
    if fid is not None and str(fid).strip():
        return f"{baza}_{fid}.pdf"
    return f"{baza}.pdf"


def _normalizare_link_drive(val: str) -> str | None:
    s = str(val or "").strip()
    if not s or s.lower() == "none":
        return None
    if s.startswith(("http://", "https://")):
        return s
    return f"https://{s}"


def _salveaza_doc_local_ment(uploaded_file, prefix_key: str) -> str:
    folder = Path("uploads/documentatie_mentenanta")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    dest = folder / f"{prefix_key}_{safe_name}"
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def _asigura_coloane_intretinere_ment():
    if st.session_state.get("_ment_coloane_verificate"):
        return
    try:
        with db_cursor() as c:
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS fara_intretinere BOOLEAN DEFAULT FALSE")
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS interval_intretinere_zile INTEGER DEFAULT 0")
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS ultima_intretinere DATE")
        st.session_state["_ment_coloane_verificate"] = True
    except Exception:
        pass


def _scoate_masina_din_intretinere_ment(masina_id: int):
    _asigura_coloane_intretinere_ment()
    with db_cursor() as c:
        c.execute(
            "UPDATE masini SET fara_intretinere = TRUE, data_intretinere = NULL WHERE id = %s",
            (int(masina_id),),
        )
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()


def _programeaza_masina_intretinere_ment(masina_id: int, data_prog: date, interval_zile: int, ultima_d: date | None = None):
    _asigura_coloane_intretinere_ment()
    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET fara_intretinere = FALSE,
                data_intretinere = %s,
                interval_intretinere_zile = %s,
                ultima_intretinere = COALESCE(%s, ultima_intretinere)
            WHERE id = %s
            """,
            (data_prog, max(0, int(interval_zile or 0)), ultima_d, int(masina_id)),
        )
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()


def _replanifica_dupa_pasi_ment(masina_id: int, data_efectuare: date, urmatoarea_data: date, interval_zile: int):
    _asigura_coloane_intretinere_ment()
    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET fara_intretinere = FALSE,
                ultima_intretinere = %s,
                data_intretinere = %s,
                interval_intretinere_zile = CASE
                    WHEN %s > 0 THEN %s
                    ELSE COALESCE(interval_intretinere_zile, 0)
                END
            WHERE id = %s
            """,
            (data_efectuare, urmatoarea_data, int(interval_zile or 0), int(interval_zile or 0), int(masina_id)),
        )
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()


def _normalizare_randuri_operatiuni(rows_in: list[dict]) -> list[dict]:
    rez = []
    for idx, r in enumerate(rows_in or [], start=1):
        if not isinstance(r, dict):
            continue
        op_txt = str(r.get("Operațiune / Verificare") or r.get("operatiune") or r.get("pas") or "").strip()
        prm_txt = str(
            r.get("Denumire parametru")
            or r.get("Piese / Parametri Măsurați")
            or r.get("Parametru")
            or r.get("parametru")
            or ""
        ).strip()
        val_txt = str(
            r.get("Valoare")
            or r.get("Valori / Observații")
            or r.get("valoare")
            or ""
        ).strip()
        um_txt = str(r.get("UM") or r.get("um") or "").strip()
        doc_txt = str(
            r.get("Documentație")
            or r.get("Documentație Drive")
            or r.get("Documentatie Drive")
            or r.get("documentatie_drive")
            or r.get("drive_url")
            or ""
        ).strip()
        if not op_txt and not prm_txt and not val_txt and not um_txt and not doc_txt:
            continue
        ef_raw = r.get("Efectuat", True)
        if isinstance(ef_raw, str):
            ef_val = ef_raw.strip().lower() not in ("false", "0", "nu", "no")
        else:
            ef_val = bool(ef_raw)
        rez.append({
            "Ordine": int(r.get("Ordine") or r.get("ordine") or idx),
            "Operațiune / Verificare": op_txt,
            "Denumire parametru": prm_txt,
            "Valoare": val_txt,
            "UM": um_txt,
            "Documentație": doc_txt,
            "Efectuat": ef_val,
        })
    return rez


def _init_sau_reseteaza_ment_draft(tehnician_def: str):
    st.session_state["ment_draft"] = {
        "sel_firma": "-- Alege firma --",
        "sel_masina": "-- Alege mașina --",
        "data_interventie": date.today(),
        "punct_lucru": "",
        "producator_model": "",
        "serie_fabricatie": "",
        "nr_inventar": "",
        "ore_functionare": "",
        "ore_cumulate": "",
        "nivel_grila": "Nivel A – Multimarcă (<20h)",
        "stare_initiala": "Funcțional",
        "stare_finala": "Funcțional (parametri nominali)",
        "recomandari_iiot": "",
        "tehnician": tehnician_def,
        "verificator": "Client",
        "functie_verificator": "",
        "ultima_firma": "-- Alege firma --",
        "ultima_masina": "-- Alege mașina --",
        "edit_fisa_id": None,
        "operatiuni_rows": [],
    }
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _incarca_fisa_din_istoric_pentru_editare(fisa: dict, firme_dict: dict):
    chk = fisa.get("checklist_json") or {}
    if isinstance(chk, str):
        try:
            chk = json.loads(chk)
        except Exception:
            chk = {}

    fisa_spec = chk.get("fisa_specifica_utilaj") if isinstance(chk, dict) else {}
    rows_salvate = _normalizare_randuri_operatiuni((fisa_spec.get("randuri") if isinstance(fisa_spec, dict) else []) or [])

    firma_nume = str(fisa.get("firma_nume") or "-- Alege firma --")
    if firma_nume not in firme_dict:
        firma_nume = "-- Alege firma --"

    data_raw = str(fisa.get("data_interventie") or "")[:10]
    try:
        data_int = date.fromisoformat(data_raw) if data_raw else date.today()
    except Exception:
        data_int = date.today()

    st.session_state["ment_draft"] = {
        "sel_firma": firma_nume,
        "sel_masina": str(fisa.get("masina_nume") or "-- Alege mașina --"),
        "data_interventie": data_int,
        "punct_lucru": str(fisa.get("punct_lucru") or ""),
        "producator_model": str(fisa.get("producator_model") or ""),
        "serie_fabricatie": str(fisa.get("serie_fabricatie") or ""),
        "nr_inventar": str(fisa.get("nr_inventar") or ""),
        "ore_functionare": str(fisa.get("ore_functionare") or ""),
        "ore_cumulate": str(fisa.get("ore_cumulate") or ""),
        "nivel_grila": str(fisa.get("nivel_grila") or "Nivel A – Multimarcă (<20h)"),
        "stare_initiala": str(fisa.get("stare_initiala") or "Funcțional"),
        "stare_finala": str(fisa.get("stare_finala") or "Funcțional (parametri nominali)"),
        "recomandari_iiot": str(fisa.get("recomandari_iiot") or ""),
        "tehnician": str(fisa.get("tehnician") or "Tehnician Nexus"),
        "verificator": str(fisa.get("verificator") or "Client"),
        "functie_verificator": str(fisa.get("functie_verificator") or ""),
        "ultima_firma": firma_nume,
        "ultima_masina": str(fisa.get("masina_nume") or "-- Alege mașina --"),
        "edit_fisa_id": fisa.get("id"),
        "operatiuni_rows": rows_salvate,
    }
    if isinstance(fisa_spec, dict) and fisa_spec.get("frecventa"):
        st.session_state["ment_frec_selectata"] = str(fisa_spec["frecventa"])
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _render_sectiune_operatiuni(
    masina_obj: dict,
    firma_nume: str,
    data_interv: date,
    is_unlocked: bool,
    frecventa_init: str,
):
    den_masina = str(masina_obj.get("denumire") or "").strip()
    tip_masina = str(masina_obj.get("tip_masina") or "").strip()

    frec_curr = st.session_state.get("ment_frec_selectata")
    if frec_curr not in FRECVENTE_MENTENANTA:
        frec_curr = frecventa_init if frecventa_init in FRECVENTE_MENTENANTA else "Lunară"

    frec_sel = st.selectbox(
        "Tip întreținere / Frecvență",
        options=FRECVENTE_MENTENANTA,
        index=FRECVENTE_MENTENANTA.index(frec_curr),
        key=f"ment_frec_fisa_{masina_obj['id']}",
    )
    st.session_state["ment_frec_selectata"] = frec_sel

    fisa_cfg = obtine_fisa_pentru_utilaj(den_masina, tip_masina, frec_sel)
    nume_fisa = fisa_cfg.get("nume_fisa") or construieste_nume_fisa(den_masina, tip_masina, frec_sel, False)
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=frec_sel,
        masina=den_masina,
        tip_masina=tip_masina,
        data_str=str(data_interv),
        firma=firma_nume,
    )
    st.caption(f"Fișă: **{nume_fisa}** | Titlu PDF: **{titlu_pdf}**")

    draft = st.session_state["ment_draft"]
    rows_key = f"ment_ops_rows_{masina_obj['id']}"
    if rows_key not in st.session_state:
        if draft.get("edit_fisa_id") is not None:
            st.session_state[rows_key] = _normalizare_randuri_operatiuni(draft.get("operatiuni_rows") or [])
        else:
            st.session_state[rows_key] = []

    rows_curente = list(st.session_state[rows_key] or [])
    catalog_db = incarca_catalog_operatiuni_db()

    if is_unlocked:
        st.markdown("#### 📎 Încarcă / Setează operațiune, denumire parametru, valoare, UM și documentație")
        opt_cat = {"-- Introdu manual / copy-paste --": None}
        for it in catalog_db:
            opt_cat[f"[{it['sistem']}] {it['operatiune']}"] = it

        sel_cat_label = st.selectbox(
            "Alege operațiunea din DB (sau lasă manual / copy-paste)",
            options=list(opt_cat.keys()),
            key=f"ment_sel_cat_{masina_obj['id']}",
        )
        item_cat = opt_cat.get(sel_cat_label)

        c_op, c_prm, c_val, c_um = st.columns([2.2, 1.2, 0.9, 0.7])
        with c_op:
            op_noua = st.text_input(
                "Operațiune / Verificare (manual sau copy-paste)",
                value=(item_cat["operatiune"] if item_cat else ""),
                key=f"ment_inp_op_{masina_obj['id']}_{sel_cat_label[:25]}",
            ).strip()
        with c_prm:
            prm_nou = st.text_input(
                "Denumire parametru",
                value=(item_cat.get("parametru") or "" if item_cat else ""),
                placeholder="ex: Tensiune / Presiune",
                key=f"ment_inp_prm_{masina_obj['id']}_{sel_cat_label[:25]}",
            ).strip()
        with c_val:
            val_noua = st.text_input(
                "Valoare",
                value=(item_cat.get("valoare") or "" if item_cat else ""),
                placeholder="ex: 24.0 / 6.2",
                key=f"ment_inp_val_{masina_obj['id']}_{sel_cat_label[:25]}",
            ).strip()
        with c_um:
            um_noua = st.text_input(
                "UM",
                value=(item_cat.get("um") or "" if item_cat else ""),
                placeholder="ex: V / bar",
                key=f"ment_inp_um_{masina_obj['id']}_{sel_cat_label[:25]}",
            ).strip()

        c_lnk, c_fil, c_db = st.columns([1.8, 1.5, 1.2])
        with c_lnk:
            lnk_nou = st.text_input(
                "Link documentație (opțional)",
                value=(item_cat.get("drive", "") if item_cat else ""),
                placeholder="https://drive.google.com/...",
                key=f"ment_inp_lnk_{masina_obj['id']}",
            ).strip()
        with c_fil:
            fil_nou = st.file_uploader(
                "Sau încarcă documentație",
                type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
                key=f"ment_up_doc_{masina_obj['id']}",
            )
        with c_db:
            salveaza_db = st.checkbox(
                "Salvează și în DB",
                value=(item_cat is None),
                key=f"ment_chk_db_{masina_obj['id']}",
            )

        if st.button("➕ Adaugă operațiunea în tabel", key=f"ment_btn_add_op_{masina_obj['id']}"):
            if not op_noua:
                st.warning("Selectează sau introdu o operațiune.")
            else:
                doc_final = lnk_nou
                if fil_nou is not None:
                    doc_final = _salveaza_doc_local_ment(fil_nou, f"m{masina_obj['id']}_op{len(rows_curente)+1}")
                if salveaza_db and item_cat is None:
                    adauga_operatiune_in_catalog_db(
                        sistem="Personalizat",
                        operatiune=op_noua,
                        parametru=prm_nou,
                        valoare=val_noua,
                        um=um_noua,
                        drive=doc_final,
                    )
                rows_curente.append({
                    "Ordine": len(rows_curente) + 1,
                    "Operațiune / Verificare": op_noua,
                    "Denumire parametru": prm_nou,
                    "Valoare": val_noua,
                    "UM": um_noua,
                    "Documentație": doc_final,
                    "Efectuat": True,
                })
                st.session_state[rows_key] = rows_curente
                st.toast("✅ Operațiunea a fost adăugată.")
                st.rerun()

        if rows_curente:
            st.markdown("#### 🗑️ Ștergere una sau mai multe operațiuni deodată")
            opt_del = {
                f"{i+1}. {str(r.get('Operațiune / Verificare') or '')[:85]}": i
                for i, r in enumerate(rows_curente)
            }
            de_sters = st.multiselect(
                "Selectează operațiunile de șters",
                options=list(opt_del.keys()),
                key=f"ment_ms_del_ops_{masina_obj['id']}",
            )
            if st.button("🗑️ Șterge operațiunile selectate", key=f"ment_btn_del_ops_{masina_obj['id']}"):
                if not de_sters:
                    st.warning("Selectează cel puțin o operațiune.")
                else:
                    indici_sters = {opt_del[k] for k in de_sters}
                    ramase = []
                    for idx_r, r_item in enumerate(rows_curente):
                        if idx_r not in indici_sters:
                            copie = dict(r_item)
                            copie["Ordine"] = len(ramase) + 1
                            ramase.append(copie)
                    st.session_state[rows_key] = ramase
                    st.toast(f"🗑️ Au fost șterse {len(indici_sters)} operațiuni.")
                    st.rerun()
    else:
        st.info("🔒 Sistemul este blocat. Deblochează din **SistemAdmin → Deblocare** pentru a adăuga, modifica sau șterge operațiuni.")

    df_init = pd.DataFrame(rows_curente) if rows_curente else pd.DataFrame(columns=[
        "Ordine",
        "Operațiune / Verificare",
        "Denumire parametru",
        "Valoare",
        "UM",
        "Documentație",
        "Efectuat",
    ])

    df_ed = st.data_editor(
        df_init,
        hide_index=True,
        num_rows="dynamic" if is_unlocked else "fixed",
        use_container_width=True,
        disabled=[] if is_unlocked else ["Ordine", "Operațiune / Verificare", "Denumire parametru", "Valoare", "UM", "Documentație", "Efectuat"],
        column_config={
            "Ordine": st.column_config.NumberColumn("Ordine", width="small", step=1),
            "Operațiune / Verificare": st.column_config.TextColumn("Operațiune / Verificare", width="large"),
            "Denumire parametru": st.column_config.TextColumn("Denumire parametru", width="medium"),
            "Valoare": st.column_config.TextColumn("Valoare", width="small"),
            "UM": st.column_config.TextColumn("UM", width="small"),
            "Documentație": st.column_config.TextColumn("Documentație", width="medium"),
            "Efectuat": st.column_config.CheckboxColumn("Efectuat", width="small"),
        },
        key=f"ment_ed_ops_table_{masina_obj['id']}_{st.session_state.get('ment_counter', 0)}",
    )

    if is_unlocked and df_ed is not None:
        st.session_state[rows_key] = _normalizare_randuri_operatiuni(df_ed.fillna("").to_dict(orient="records"))

    doc_links = []
    for r in (st.session_state[rows_key] or []):
        lnk = _normalizare_link_drive(r.get("Documentație") or "")
        if lnk:
            doc_links.append((f"{r.get('Ordine', '')}. {str(r.get('Operațiune / Verificare') or '')[:65]}", lnk))

    if doc_links:
        opt_doc = {lbl: url for lbl, url in doc_links}
        cd1, cd2 = st.columns([3.5, 1.5], vertical_alignment="center")
        sel_doc = cd1.selectbox(
            "Documentație atașată operațiunii",
            options=list(opt_doc.keys()),
            key=f"ment_sel_doc_{masina_obj['id']}",
        )
        cd2.link_button("📂 Deschide Documentația", opt_doc[sel_doc], use_container_width=True)

    return df_ed, nume_fisa, frec_sel, titlu_pdf


def _genereaza_pdf_cu_fallback(fisa_payload: dict) -> bytes:
    try:
        res = genereaza_pdf_mentenanta(fisa_payload)
        if isinstance(res, (bytes, bytearray)) and len(res) > 0:
            return bytes(res)
    except Exception:
        pass
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        titlu = str(fisa_payload.get("titlu_pdf_operatiuni") or "Operatiuni de intretinere")
        pdf.cell(0, 10, titlu.encode("latin-1", errors="replace").decode("latin-1"), ln=True)
        pdf.set_font("Helvetica", size=10)
        info = f"Client: {fisa_payload.get('firma_nume', '')} | Masina: {fisa_payload.get('masina_nume', '')} | Data: {fisa_payload.get('data_interventie', '')}"
        pdf.cell(0, 8, info.encode("latin-1", errors="replace").decode("latin-1"), ln=True)
        chk = fisa_payload.get("checklist_json") or {}
        fisa_spec = chk.get("fisa_specifica_utilaj") if isinstance(chk, dict) else {}
        for r in (fisa_spec.get("randuri") or []):
            prm = r.get("Denumire parametru") or r.get("Piese / Parametri Măsurați") or ""
            val = r.get("Valoare") or r.get("Valori / Observații") or ""
            um = r.get("UM") or ""
            linie = (
                f"{r.get('Ordine', '')}. {r.get('Operațiune / Verificare', '')} | "
                f"{prm}: {val} {um} | Efectuat: {r.get('Efectuat', '')}"
            )
            pdf.multi_cell(0, 6, linie.encode("latin-1", errors="replace").decode("latin-1"))
        out = pdf.output(dest="S")
        return out.encode("latin-1") if isinstance(out, str) else bytes(out)
    except Exception:
        titlu = str(fisa_payload.get("titlu_pdf_operatiuni") or "Operatiuni de intretinere")
        return f"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<< /Root 1 0 R >>\n%%EOF\n% {titlu}".encode("latin-1", errors="ignore")


def render_mentenanta():
    st.subheader("🛡️ Fișă de Mentenanță Preventivă & Audit Tehnic")
    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    setari = SetariRepository.get_setari()
    tehnician_def = setari.get("tehnician_implicit") or "Tehnician Nexus"

    if "ment_draft" not in st.session_state:
        _init_sau_reseteaza_ment_draft(tehnician_def)
    if "ment_salvat" not in st.session_state:
        st.session_state["ment_salvat"] = False
    if "ment_pdf_bytes" not in st.session_state:
        st.session_state["ment_pdf_bytes"] = None
    if "ment_pdf_name" not in st.session_state:
        st.session_state["ment_pdf_name"] = None
    if "ment_id_salvat" not in st.session_state:
        st.session_state["ment_id_salvat"] = None

    draft = st.session_state["ment_draft"]
    firme_db = FirmeRepository.get_all()
    if not firme_db:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în modulul 'Firme'.")
        return
    firme_dict = {f["nume_firma"]: f for f in firme_db}

    if st.session_state["ment_salvat"]:
        st.success(f"✅ Fișa de Mentenanță Preventivă #{st.session_state['ment_id_salvat']} a fost salvată!")
        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            if st.session_state["ment_pdf_bytes"]:
                nume_pdf = st.session_state.get("ment_pdf_name") or f"Operatiuni_de_intretinere_{st.session_state['ment_id_salvat']}.pdf"
                st.download_button(
                    label="📥 Descarcă PDF",
                    data=st.session_state["ment_pdf_bytes"],
                    file_name=nume_pdf,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
        with c_dl2:
            if st.button("➕ Fișă nouă", use_container_width=True):
                st.session_state["ment_salvat"] = False
                st.session_state["ment_pdf_bytes"] = None
                st.session_state["ment_pdf_name"] = None
                st.session_state["ment_id_salvat"] = None
                for k in [k for k in list(st.session_state.keys()) if k.startswith("ment_ops_rows_")]:
                    del st.session_state[k]
                _init_sau_reseteaza_ment_draft(tehnician_def)
                st.rerun()
        return

    c_top1, c_top2 = st.columns([3.5, 1.5], vertical_alignment="center")
    with c_top1:
        if draft.get("edit_fisa_id") is not None:
            st.info(f"✏️ **Editare fișă din istoric #{draft['edit_fisa_id']}** — operațiunile din fișa salvată sunt încărcate în tabel.")
        else:
            st.caption("📄 **Fișă nouă:** tabelul de operațiuni pornește gol; adaugă operațiuni din DB sau manual / copy-paste.")
    with c_top2:
        if st.button("➕ Fișă nouă (gol)", use_container_width=True):
            for k in [k for k in list(st.session_state.keys()) if k.startswith("ment_ops_rows_")]:
                del st.session_state[k]
            _init_sau_reseteaza_ment_draft(tehnician_def)
            st.rerun()

    opt_firme = ["-- Alege firma --"] + list(firme_dict.keys())
    idx_f = opt_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in opt_firme else 0
    col_id1, col_id2, col_id3 = st.columns(3)
    with col_id1:
        sel_firma = st.selectbox("1. Beneficiar / Client *", options=opt_firme, index=idx_f)
        draft["sel_firma"] = sel_firma

    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Selectează clientul și utilajul pentru a continua.")
        _render_istoric_mentenanta(firme_dict)
        return

    firma_obj = firme_dict[sel_firma]
    if draft.get("ultima_firma") != sel_firma and draft.get("edit_fisa_id") is None:
        draft["ultima_firma"] = sel_firma
        draft["verificator"] = firma_obj.get("nume_persoana") or "Client"
        draft["punct_lucru"] = firma_obj.get("adresa") or ""
        draft["sel_masina"] = "-- Alege mașina --"
        draft["ultima_masina"] = "-- Alege mașina --"

    masini_db = MasiniRepository.get_by_firma(firma_obj["id"])
    masini_dict = {m["denumire"]: m for m in masini_db}
    opt_masini = ["-- Alege mașina --"] + list(masini_dict.keys())
    idx_m = opt_masini.index(draft["sel_masina"]) if draft.get("sel_masina") in opt_masini else 0

    with col_id2:
        sel_masina = st.selectbox("2. Denumire Echipament / Mașină *", options=opt_masini, index=idx_m)
        draft["sel_masina"] = sel_masina

    with col_id3:
        data_interv = st.date_input("3. Data Intervenției", value=draft.get("data_interventie", date.today()))
        draft["data_interventie"] = data_interv

    if sel_masina == "-- Alege mașina --":
        st.info("ℹ️ Alege utilajul din lista clientului pentru a continua.")
        _render_istoric_mentenanta(firme_dict)
        return

    masina_obj = masini_dict[sel_masina]
    total_int_m = int(masina_obj.get("total_interventii", 0))
    prag_int_m = int(masina_obj.get("prag_interventii", 20))

    if draft.get("ultima_masina") != sel_masina and draft.get("edit_fisa_id") is None:
        draft["ultima_masina"] = sel_masina
        draft["producator_model"] = str(masina_obj.get("tip_masina") or "")
        draft["serie_fabricatie"] = str(masina_obj.get("serie") or "")
        if total_int_m >= prag_int_m:
            draft["nivel_grila"] = "Nivel B – CNC Biglia / Matec / >20h / Inginerie"
        else:
            draft["nivel_grila"] = "Nivel A – Multimarcă (<20h)"

    _asigura_coloane_intretinere_ment()
    tip_int_masina = masina_obj.get("tip_intretinere") or "Lunară"
    interval_din_db = int(masina_obj.get("interval_intretinere_zile") or 0)
    durata_implicita_zile = interval_din_db if interval_din_db > 0 else INTERVALE_ZILE.get(tip_int_masina, 30)

    # Mutat imediat sub selectoarele Client, Denumire echipament, Data
    with st.expander("📋 Date Identificare Echipament & Stare Tehnică", expanded=True):
        d1, d2, d3, d4 = st.columns(4)
        draft["punct_lucru"] = d1.text_input("Punct de Lucru / Oraș", value=str(draft.get("punct_lucru", "")))
        draft["producator_model"] = d2.text_input("Producător / Model", value=str(draft.get("producator_model", "")))
        draft["serie_fabricatie"] = d3.text_input("Serie Fabricație", value=str(draft.get("serie_fabricatie", "")))
        draft["nr_inventar"] = d4.text_input("Nr. Inventar Intern", value=str(draft.get("nr_inventar", "")))

        e1, e2, e3 = st.columns(3)
        draft["ore_functionare"] = e1.text_input("Ore Funcționare Utilaj", value=str(draft.get("ore_functionare", "")), placeholder="ex: 14520")
        draft["ore_cumulate"] = e2.text_input("Ore Cumulate (din 20h)", value=str(draft.get("ore_cumulate", "")), placeholder="ex: 6 / 20")
        opt_grila = [
            "Nivel A – Multimarcă (<20h)",
            "Nivel B – CNC Biglia / Matec / >20h / Inginerie"
        ]
        idx_gr = opt_grila.index(draft["nivel_grila"]) if draft.get("nivel_grila") in opt_grila else 0
        draft["nivel_grila"] = e3.selectbox("Nivel Grilă Aplicabilă", options=opt_grila, index=idx_gr)

        s1, s2, s3 = st.columns(3)
        opt_stare_ini = [
            "Funcțional",
            "Nefuncțional",
            "Degradare moderată",
            "Stare avansată de degradare"
        ]
        idx_si = opt_stare_ini.index(draft["stare_initiala"]) if draft.get("stare_initiala") in opt_stare_ini else 0
        draft["stare_initiala"] = s1.selectbox("Stare Inițială Utilaj", options=opt_stare_ini, index=idx_si)

        opt_stare_fin = [
            "Funcțional (parametri nominali)",
            "Funcțional cu restricții (necesită piese)",
            "Oprit siguranță"
        ]
        idx_sf = opt_stare_fin.index(draft["stare_finala"]) if draft.get("stare_finala") in opt_stare_fin else 0
        draft["stare_finala"] = s2.selectbox("Stare Finală Utilaj", options=opt_stare_fin, index=idx_sf)

        zile_add = durata_implicita_zile
        urmatoarea_rev_default = data_interv + timedelta(days=zile_add)
        urmatoarea_revizie = s3.date_input(
            f"Următoarea Revizie ({tip_int_masina})",
            value=urmatoarea_rev_default
        )

    if total_int_m >= prag_int_m:
        st.warning(f"🔔 **Atenție Grilă Tarifare:** Utilajul **{sel_masina}** a atins/depășit pragul (**{total_int_m} / {prag_int_m}** intervenții)! Se recomandă trecerea la următoarea grilă de tarifare (**Nivel B**).")
    else:
        st.info(f"📊 **Contor intervenții ({sel_masina}):** {total_int_m} / {prag_int_m} efectuate (mai sunt **{prag_int_m - total_int_m}** până la următoarea grilă).")

    este_fara_int = bool(masina_obj.get("fara_intretinere", False))
    with st.expander(f"🗓️ Planificare & Replanificare Întreținere — {sel_masina}", expanded=False):
        if este_fara_int:
            st.info("🚫 Această mașină este scoasă din întreținere (**Fără întreținere**).")
            with st.form(f"form_prog_ment_{masina_obj['id']}"):
                cp1, cp2 = st.columns(2)
                with cp1:
                    data_prog_noua = st.date_input(
                        "Programează întreținerea la data",
                        value=date.today() + timedelta(days=durata_implicita_zile),
                    )
                with cp2:
                    durata_prog_noua = st.number_input(
                        "Durata până la următoarea întreținere (zile)",
                        min_value=0,
                        step=15,
                        value=durata_implicita_zile,
                    )
                if st.form_submit_button("📅 Programează pentru întreținere", type="primary"):
                    _programeaza_masina_intretinere_ment(masina_obj["id"], data_prog_noua, int(durata_prog_noua))
                    st.success(f"✅ **{sel_masina}** a fost programată pentru întreținere la **{data_prog_noua}**.")
                    st.rerun()
        else:
            c_st1, c_st2 = st.columns([2.5, 1.3], vertical_alignment="center")
            with c_st1:
                st.caption(
                    f"Scadență curentă: **{masina_obj.get('data_intretinere') or 'Nesetată'}** | "
                    f"Ultima întreținere: **{masina_obj.get('ultima_intretinere') or 'Nicio înregistrare'}** | "
                    f"Durată ciclu: **{durata_implicita_zile} zile**"
                )
            with c_st2:
                if st.button("🚫 Scoate din întreținere", key=f"btn_scoate_ment_{masina_obj['id']}", use_container_width=True):
                    _scoate_masina_din_intretinere_ment(masina_obj["id"])
                    st.toast(f"🚫 {sel_masina} a fost scoasă din întreținere.")
                    st.rerun()

            with st.form(f"form_pasi_replan_ment_{masina_obj['id']}"):
                pasi_parcursi = st.checkbox(
                    "S-au parcurs toți pașii în întreținere / mentenanță — vreau să o replanific",
                    value=False,
                )
                cr1, cr2, cr3 = st.columns(3)
                with cr1:
                    data_efect_pasi = st.date_input("Data la care s-a făcut întreținerea", value=data_interv)
                with cr2:
                    durata_replan = st.number_input("Durata până la următoarea întreținere (zile)", min_value=1, step=15, value=durata_implicita_zile)
                with cr3:
                    urm_data_calculata = data_efect_pasi + timedelta(days=int(durata_replan))
                    urm_data_replan = st.date_input("Următoarea dată propusă", value=urm_data_calculata)

                st.caption(f"🧮 Propunere automată: **{data_efect_pasi}** + **{int(durata_replan)} zile** = **{urm_data_calculata}**.")

                if st.form_submit_button("🔁 Confirmă pașii & Replanifică", type="primary"):
                    if not pasi_parcursi:
                        st.warning("⚠️ Bifează că s-au parcurs toți pașii în întreținere/mentenanță înainte de replanificare.")
                    else:
                        _replanifica_dupa_pasi_ment(
                            masina_id=masina_obj["id"],
                            data_efectuare=data_efect_pasi,
                            urmatoarea_data=urm_data_replan,
                            interval_zile=int(durata_replan),
                        )
                        st.success(
                            f"✅ **{sel_masina}** marcată ca efectuată la **{data_efect_pasi}** și replanificată la **{urm_data_replan}**."
                        )
                        st.rerun()

    with st.expander(f"🛠️ Operațiuni Mentenanță — {sel_masina} ({masina_obj.get('tip_masina') or '-'})", expanded=True):
        df_ops_utilaj, nume_fisa_activa, frec_fisa_activa, titlu_pdf_activ = _render_sectiune_operatiuni(
            masina_obj=masina_obj,
            firma_nume=sel_firma,
            data_interv=data_interv,
            is_unlocked=is_unlocked,
            frecventa_init=tip_int_masina,
        )

    st.markdown("---")
    st.markdown("### Recomandări Tehnice, Audit Upgrade / IIoT & Recepție Lucrări")
    draft["recomandari_iiot"] = st.text_area(
        "Constatări suplimentare & Recomandări de modernizare (Retrofit PLC / Senzoristică IIoT / Mentenanță Predictivă)",
        value=str(draft.get("recomandari_iiot", "")),
        height=95
    )

    r1, r2, r3 = st.columns(3)
    draft["tehnician"] = r1.text_input("Inginer / Tehnician Service", value=str(draft.get("tehnician", tehnician_def)))
    draft["verificator"] = r2.text_input("Reprezentant Beneficiar (Nume & Prenume)", value=str(draft.get("verificator", "")))
    draft["functie_verificator"] = r3.text_input("Funcție Reprezentant Beneficiar", value=str(draft.get("functie_verificator", "")))

    if st.button("💾 Salvează Fișa de Mentenanță & Generează PDF", type="primary", use_container_width=True):
        try:
            rows_key = f"ment_ops_rows_{masina_obj['id']}"
            ops_final = _normalizare_randuri_operatiuni(
                (df_ops_utilaj.fillna("").to_dict(orient="records"))
                if df_ops_utilaj is not None and not df_ops_utilaj.empty
                else (st.session_state.get(rows_key) or [])
            )

            checklist_payload = {
                "fisa_specifica_utilaj": {
                    "titlu": nume_fisa_activa,
                    "titlu_pdf": titlu_pdf_activ,
                    "denumire_masina": str(masina_obj.get("denumire") or "").strip(),
                    "tip_masina": str(masina_obj.get("tip_masina") or "").strip(),
                    "frecventa": frec_fisa_activa,
                    "randuri": ops_final,
                }
            }

            fisa_data = {
                "firma_id": firma_obj["id"],
                "masina_id": masina_obj["id"],
                "firma_nume": sel_firma,
                "masina_nume": sel_masina,
                "nume_fisa": nume_fisa_activa,
                "frecventa": frec_fisa_activa,
                "titlu_pdf_operatiuni": titlu_pdf_activ,
                "punct_lucru": draft["punct_lucru"],
                "producator_model": draft["producator_model"],
                "serie_fabricatie": draft["serie_fabricatie"],
                "nr_inventar": draft["nr_inventar"],
                "ore_functionare": draft["ore_functionare"],
                "ore_cumulate": draft["ore_cumulate"],
                "nivel_grila": draft["nivel_grila"],
                "stare_initiala": draft["stare_initiala"],
                "stare_finala": draft["stare_finala"],
                "checklist_json": checklist_payload,
                "recomandari_iiot": draft["recomandari_iiot"],
                "tehnician": draft["tehnician"],
                "verificator": draft["verificator"],
                "functie_verificator": draft["functie_verificator"],
                "data_interventie": data_interv,
                "urmatoarea_revizie": urmatoarea_revizie
            }

            edit_id = draft.get("edit_fisa_id")
            if edit_id is not None and hasattr(MentenantaRepository, "update"):
                MentenantaRepository.update(edit_id, fisa_data)
                salvat_id = edit_id
            else:
                salvat_id = MentenantaRepository.insert(fisa_data)

            fisa_data["id"] = salvat_id
            pdf_bytes = _genereaza_pdf_cu_fallback(fisa_data)
            nume_pdf_cur = construieste_nume_fisier_pdf(titlu_pdf_activ, salvat_id)

            for k in [k for k in list(st.session_state.keys()) if k.startswith("ment_ops_rows_")]:
                del st.session_state[k]

            st.session_state["ment_id_salvat"] = salvat_id
            st.session_state["ment_pdf_bytes"] = pdf_bytes
            st.session_state["ment_pdf_name"] = nume_pdf_cur
            st.session_state["ment_salvat"] = True
            _init_sau_reseteaza_ment_draft(tehnician_def)
            st.rerun()
        except Exception as exc:
            st.error(f"⚠️ Eroare la salvarea fișei / generarea PDF: {exc}")

    _render_istoric_mentenanta(firme_dict)


def _render_istoric_mentenanta(firme_dict: dict):
    st.markdown("---")
    st.subheader("📂 Istoric Fișe de Mentenanță Preventivă")
    fise_salvate = MentenantaRepository.get_all()
    if not fise_salvate:
        st.info("Nu există încă fișe de mentenanță preventivă salvate.")
        return

    for fisa in fise_salvate[:30]:
        fid = fisa["id"]
        data_str = str(fisa.get("data_interventie", ""))[:10]
        with st.expander(f"🛡️ Fișă #{fid} | {fisa.get('firma_nume')} — {fisa.get('masina_nume')} ({data_str}) | Stare: {fisa.get('stare_finala', '')}"):
            chk = fisa.get("checklist_json") or {}
            if isinstance(chk, str):
                try:
                    chk = json.loads(chk)
                except Exception:
                    chk = {}

            fisa_spec = chk.get("fisa_specifica_utilaj") if isinstance(chk, dict) else None
            frec_hist = (fisa_spec.get("frecventa") if isinstance(fisa_spec, dict) else "") or "Lunară"
            tip_hist = (fisa_spec.get("tip_masina") if isinstance(fisa_spec, dict) else "") or (fisa.get("producator_model") or "")
            titlu_pdf_hist = (
                (fisa_spec.get("titlu_pdf") if isinstance(fisa_spec, dict) else "")
                or construieste_titlu_operatiuni_pdf(
                    frecventa=frec_hist,
                    masina=fisa.get("masina_nume") or "",
                    tip_masina=tip_hist,
                    data_str=data_str,
                    firma=fisa.get("firma_nume") or "",
                )
            )

            c1, c2, c3, c4 = st.columns([2, 1, 1, 1], vertical_alignment="center")
            with c1:
                st.write(f"**Titlu:** {titlu_pdf_hist}")
                st.write(f"**Serie:** {fisa.get('serie_fabricatie') or '-'} | **Ore utilaj:** {fisa.get('ore_functionare') or '-'} | **Tehnician:** {fisa.get('tehnician') or '-'}")
                st.write(f"**Următoarea revizie:** {str(fisa.get('urmatoarea_revizie') or '-')[:10]}")
            with c2:
                if st.button("✏️ Editează", key=f"edit_ment_{fid}", use_container_width=True):
                    for k in [k for k in list(st.session_state.keys()) if k.startswith("ment_ops_rows_")]:
                        del st.session_state[k]
                    _incarca_fisa_din_istoric_pentru_editare(fisa, firme_dict)
                    st.rerun()
            with c3:
                fisa_pdf_payload = dict(fisa)
                fisa_pdf_payload["checklist_json"] = chk
                fisa_pdf_payload["frecventa"] = frec_hist
                fisa_pdf_payload["titlu_pdf_operatiuni"] = titlu_pdf_hist
                pdf_hist = _genereaza_pdf_cu_fallback(fisa_pdf_payload)
                nume_pdf_hist = construieste_nume_fisier_pdf(titlu_pdf_hist, fid)
                st.download_button(
                    label="📥 PDF",
                    data=pdf_hist,
                    file_name=nume_pdf_hist,
                    mime="application/pdf",
                    key=f"dl_ment_hist_{fid}",
                    use_container_width=True
                )
            with c4:
                if st.button("🗑️ Șterge", key=f"del_ment_{fid}", use_container_width=True):
                    MentenantaRepository.delete(fid)
                    st.rerun()

            if isinstance(fisa_spec, dict) and fisa_spec.get("randuri"):
                st.caption(f"**{fisa_spec.get('titlu', 'Operațiuni Mentenanță')}**")
                st.dataframe(pd.DataFrame(fisa_spec["randuri"]), hide_index=True, use_container_width=True)