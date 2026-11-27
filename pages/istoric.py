# ----------------------------------
# ------- istoric.py ---------------
# ----------------------------------

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.documentatie_repository import DocumentatieRepository
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.reparatii_repository import ReparatiiRepository
from services.pdf_service import genereaza_pdf


@dataclass(frozen=True)
class IstoricConfig:
    """Configurație centralizată pentru UI, validări și valori implicite."""

    optiune_toate_firmele: str = "Toate firmele"
    optiune_toate_masinile: str = "Toate mașinile"
    stari_finale: tuple[str, ...] = ("Funcțională", "În testare", "Oprită / Necesar piese")
    tipuri_interventie: tuple[str, ...] = ("reparatie", "diagnostic", "consultanta")
    tipuri_piesa: tuple[str, ...] = ("Utilizata", "Inlocuita", "Necesara", "De Comandat")
    tip_piesa_implicit: str = "Necesara"
    tehnician_implicit: str = "Tehnician Nexus"
    verificator_implicit: str = "Client"
    durata_implicita_min: int = 60
    pas_durata_min: int = 15
    durata_minima_min: int = 0
    cantitate_minima_piesa: int = 1
    limita_rezultate_doc: int = 6
    lungime_max_termen_doc: int = 60
    valori_cod_eroare_gol: tuple[str, ...] = ("", "niciunul", "none", "null")
    tag_solutie: str = "[SOL]"
    tag_implicit_doc: str = "[ERR]"
    categorie_doc_implicita: str = "CNC"
    tip_fisier_doc_implicit: str = "doc"


CFG = IstoricConfig()


# ---------------------------------------------------------------------------
# Utilitare de normalizare și pregătire date (pure, rapide, ușor de testat)
# ---------------------------------------------------------------------------

def _normalizeaza_piese(piese_raw: Any) -> list[dict[str, Any]]:
    """Convertește orice format de listă/JSON de piese într-o structură uniformă."""
    if not piese_raw:
        return []

    if isinstance(piese_raw, str):
        try:
            piese_raw = json.loads(piese_raw)
        except (TypeError, ValueError):
            return []

    if not isinstance(piese_raw, list):
        return []

    rezultat: list[dict[str, Any]] = []
    for item in piese_raw:
        if not isinstance(item, dict):
            continue
        denumire = str(item.get("Piesa") or item.get("piesa") or "").strip()
        if not denumire:
            continue

        cant_raw = item.get("Cantitate") if item.get("Cantitate") is not None else item.get("cantitate", CFG.cantitate_minima_piesa)
        try:
            cantitate = max(CFG.cantitate_minima_piesa, int(cant_raw))
        except (TypeError, ValueError):
            cantitate = CFG.cantitate_minima_piesa

        tip = str(item.get("Tip") or item.get("tip") or CFG.tip_piesa_implicit).strip()
        if tip not in CFG.tipuri_piesa:
            tip = CFG.tip_piesa_implicit

        rezultat.append({
            "Piesa": denumire,
            "Cantitate": cantitate,
            "Tip": tip,
        })
    return rezultat


def _extrage_piese_din_editor(df_editat: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Extrage și curăță rândurile valide din tabela st.data_editor."""
    if df_editat is None or df_editat.empty or "Piesa" not in df_editat.columns:
        return []
    records = df_editat.dropna(subset=["Piesa"]).to_dict(orient="records")
    return _normalizeaza_piese(records)


def _formateaza_piese_pentru_index(piese_lista: list[dict[str, Any]]) -> str:
    """Transformă lista normalizată de piese într-un rezumat lizibil pentru index."""
    if not piese_lista:
        return ""
    return ", ".join(
        f"{p['Piesa']} ({p['Cantitate']} buc, {p['Tip']})"
        for p in piese_lista
        if p.get("Piesa")
    )


def _construieste_df_piese(piese_lista: list[dict[str, Any]]) -> pd.DataFrame:
    """Creează DataFrame-ul pentru editorul de piese cu schemă garantată."""
    date = piese_lista or [{"Piesa": None, "Cantitate": CFG.cantitate_minima_piesa, "Tip": CFG.tip_piesa_implicit}]
    return pd.DataFrame(date, columns=["Piesa", "Cantitate", "Tip"])


def _index_optiune(optiuni: tuple[str, ...], valoare: Any) -> int:
    val = str(valoare or "").strip()
    return optiuni.index(val) if val in optiuni else 0


# ---------------------------------------------------------------------------
# Strat de acces date + cache pe sesiune (fără rerun și fără scanări inutile)
# ---------------------------------------------------------------------------

def _incarca_documentatie() -> tuple[list[dict[str, Any]], str | None]:
    """Încarcă documentația și semnalează explicit eventualele erori."""
    try:
        docs = DocumentatieRepository.get_all() or []
        return docs, None
    except Exception as exc:
        return [], str(exc)


def _cauta_docs_pentru_raport(termen: str, limita: int = CFG.limita_rezultate_doc) -> tuple[list[dict[str, Any]], str | None]:
    """Caută rapid în indexul de documentație cu limitare timpurie (early-exit)."""
    docs, err = _incarca_documentatie()
    if err:
        return [], err

    q = str(termen or "").strip().lower()
    if not q:
        return docs[:limita], None

    campuri_cautare = (
        "tag_sectiune",
        "titlu",
        "tip_sistem",
        "coduri_eroare_hmi",
        "coduri_eroare_driver",
        "interval_pagini",
        "piese_necesare",
        "text_indexat",
    )

    potrivite: list[dict[str, Any]] = []
    for doc in docs:
        if any(q in str(doc.get(camp) or "").lower() for camp in campuri_cautare):
            potrivite.append(doc)
            if len(potrivite) >= limita:
                break
    return potrivite, None


def _actualizeaza_raport_in_db(rid: int, payload: dict[str, Any]) -> None:
    """Actualizează raportul prin repository dacă există metoda, altfel prin SQL parametrizat."""
    if hasattr(ReparatiiRepository, "update"):
        ReparatiiRepository.update(rid, payload)
    else:
        with db_cursor() as c:
            c.execute(
                """
                UPDATE reparatii
                SET titlu=%s, simptom=%s, defect=%s, solutie=%s, durata=%s,
                    stare_finala=%s, tip_interventie=%s, tehnician=%s, verificator=%s,
                    optimizari=%s, piese_json=%s
                WHERE id=%s
                """,
                (
                    payload["titlu"],
                    payload["simptom"],
                    payload["defect"],
                    payload["solutie"],
                    payload["durata"],
                    payload["stare_finala"],
                    payload["tip_interventie"],
                    payload["tehnician"],
                    payload["verificator"],
                    payload["optimizari"],
                    json.dumps(payload["piese_json"], ensure_ascii=False),
                    rid,
                ),
            )
    if hasattr(ReparatiiRepository.get_all, "clear"):
        ReparatiiRepository.get_all.clear()


def _sterge_raport_callback(rid: int, selectbox_key: str) -> None:
    """Callback executat înainte de re-randarea naturală Streamlit -> elimină nevoia de st.rerun()."""
    try:
        if hasattr(ReparatiiRepository, "delete"):
            ReparatiiRepository.delete(rid)
        else:
            with db_cursor() as c:
                c.execute("DELETE FROM reparatii WHERE id=%s", (rid,))

        if hasattr(ReparatiiRepository.get_all, "clear"):
            ReparatiiRepository.get_all.clear()

        # Curățăm selecția curentă înainte să se deseneze din nou selectbox-ul
        st.session_state.pop(selectbox_key, None)
        st.session_state.pop(f"hist_pdf_cache_{rid}", None)
        st.session_state["hist_flash_msg"] = ("success", f"Raportul #{rid} a fost șters cu succes!")
    except Exception as exc:
        st.session_state["hist_flash_msg"] = ("error", f"Eroare la ștergerea raportului #{rid}: {exc}")


# ---------------------------------------------------------------------------
# Componenta principală UI
# ---------------------------------------------------------------------------

def render_istoric() -> None:
    st.subheader("📜 Istoric Intervenții & Căutare Avansată")

    @st.fragment
    def render_istoric_izolat() -> None:
        # Afișare mesaje persistate din callback-uri (fără rerun manual)
        flash = st.session_state.pop("hist_flash_msg", None)
        if flash:
            nivel, mesaj = flash
            getattr(st, nivel, st.info)(mesaj)

        # 1. Încărcare nomenclatoare o singură dată pe ciclu
        firme_db = FirmeRepository.get_all() or []
        firme_by_name = {
            str(f.get("nume_firma") or "").strip(): f
            for f in firme_db
            if f.get("nume_firma")
        }
        firme_opt = [CFG.optiune_toate_firmele, *firme_by_name.keys()]

        masini_db_toate = MasiniRepository.get_all() or []
        masini_id_map = {
            str(m.get("denumire") or "").strip(): m.get("id")
            for m in masini_db_toate
            if m.get("denumire")
        }

        with st.expander("🔍 Căutare și Filtrare Rapoarte", expanded=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                sel_f = st.selectbox("Filtrează după Firmă", options=firme_opt, key="hist_sel_f")

            if sel_f != CFG.optiune_toate_firmele and sel_f in firme_by_name:
                firma_id = firme_by_name[sel_f].get("id")
                masini_filtrate = (
                    MasiniRepository.get_by_firma(firma_id)
                    if firma_id is not None
                    else [m for m in masini_db_toate if m.get("firma_id") == firma_id]
                ) or []
            else:
                masini_filtrate = masini_db_toate

            masini_opt = [
                CFG.optiune_toate_masinile,
                *[str(m.get("denumire")).strip() for m in masini_filtrate if m.get("denumire")],
            ]

            # Validare defensivă a selecției mașinii când se schimbă firma
            if st.session_state.get("hist_sel_m") not in masini_opt:
                st.session_state["hist_sel_m"] = CFG.optiune_toate_masinile

            with col_f2:
                sel_m = st.selectbox("Filtrează după Mașină", options=masini_opt, key="hist_sel_m")

        # 2. Încărcare și filtrare rapoarte
        rapoarte = ReparatiiRepository.get_all() or []
        if sel_f != CFG.optiune_toate_firmele:
            rapoarte = [r for r in rapoarte if r.get("firma") == sel_f]
        if sel_m != CFG.optiune_toate_masinile:
            rapoarte = [r for r in rapoarte if r.get("masina") == sel_m]

        st.write(f"**Rezultate găsite:** {len(rapoarte)} rapoarte")

        if not rapoarte:
            st.info("Nu există rapoarte care să corespundă filtrelor selectate.")
            return

        rapoarte_by_id = {r["id"]: r for r in rapoarte if r.get("id") is not None}
        raport_ids = list(rapoarte_by_id.keys())

        # Validare defensivă a ID-ului selectat (evită erori după ștergere sau filtrare)
        if st.session_state.get("hist_sel_rap_id") not in rapoarte_by_id:
            st.session_state["hist_sel_rap_id"] = raport_ids[0]

        sel_rid = st.selectbox(
            "Selectează Raportul dorit pentru Vizualizare / Modificare",
            options=raport_ids,
            format_func=lambda rid_item: (
                f"Raport #{rid_item} | "
                f"{rapoarte_by_id[rid_item].get('firma', 'N/A')} - "
                f"{rapoarte_by_id[rid_item].get('masina', 'N/A')} "
                f"({str(rapoarte_by_id[rid_item].get('data') or 'N/A')[:10]})"
            ),
            key="hist_sel_rap_id",
        )

        r_data = rapoarte_by_id[sel_rid]
        rid = int(r_data["id"])

        st.markdown(f"### ✏️ Modificare Raport #{rid}")

        piese_catalog = sorted({
            str(p.get("denumire")).strip()
            for p in (PieseRepository.get_all() or [])
            if p.get("denumire")
        })
        piese_initiale = _normalizeaza_piese(r_data.get("piese_valide") or r_data.get("piese_json"))

        # Includem în catalog și piesele deja salvate pe raport dacă au fost șterse ulterior din nomenclator
        optiuni_piese_editor = sorted(set(piese_catalog) | {p["Piesa"] for p in piese_initiale})

        with st.form(f"form_mod_istoric_{rid}"):
            titlu_lucrare = st.text_input("Titlu Lucrare", value=str(r_data.get("titlu_lucrare") or ""), key=f"hist_tit_{rid}")
            simptom = st.text_area("Simptom Inițial", value=str(r_data.get("simptom") or ""), key=f"hist_simp_{rid}")
            defect = st.text_area("Defect Constatat", value=str(r_data.get("defect") or ""), key=f"hist_def_{rid}")
            solutie = st.text_area("Soluție / Lucrări Executate", value=str(r_data.get("solutie") or ""), key=f"hist_sol_{rid}")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                try:
                    durata_val = int(r_data.get("durata_min") or CFG.durata_implicita_min)
                except (TypeError, ValueError):
                    durata_val = CFG.durata_implicita_min

                durata_min = st.number_input(
                    "Durată (minute)",
                    min_value=CFG.durata_minima_min,
                    value=max(CFG.durata_minima_min, durata_val),
                    step=CFG.pas_durata_min,
                    key=f"hist_dur_{rid}",
                )
                stare_fin = st.selectbox(
                    "Stare Finală",
                    options=list(CFG.stari_finale),
                    index=_index_optiune(CFG.stari_finale, r_data.get("stare_fin")),
                    key=f"hist_stare_{rid}",
                )
                tip_interventie = st.selectbox(
                    "Tip Intervenție",
                    options=list(CFG.tipuri_interventie),
                    index=_index_optiune(CFG.tipuri_interventie, r_data.get("tip_interventie")),
                    key=f"hist_tip_{rid}",
                )

            with col_d2:
                tehnician = st.text_input(
                    "Tehnician",
                    value=str(r_data.get("tehnician_nume") or CFG.tehnician_implicit),
                    key=f"hist_tech_{rid}",
                )
                verificator = st.text_input(
                    "Verificator / Client",
                    value=str(r_data.get("verificator_nume") or CFG.verificator_implicit),
                    key=f"hist_ver_{rid}",
                )

            st.markdown("#### 🔩 Gestiune Piese")
            edited_piese_hist = st.data_editor(
                _construieste_df_piese(piese_initiale),
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Piesa": st.column_config.SelectboxColumn("Piesă", options=optiuni_piese_editor, required=True),
                    "Cantitate": st.column_config.NumberColumn(
                        "Cantitate",
                        min_value=CFG.cantitate_minima_piesa,
                        default=CFG.cantitate_minima_piesa,
                    ),
                    "Tip": st.column_config.SelectboxColumn(
                        "Tip",
                        options=list(CFG.tipuri_piesa),
                        default=CFG.tip_piesa_implicit,
                        required=True,
                    ),
                },
                key=f"editor_piese_hist_{rid}",
            )

            optimizari = st.text_area("Recomandări Tehnice", value=str(r_data.get("optimizari") or ""), key=f"hist_opt_{rid}")

            salvat = st.form_submit_button("💾 Salvează Modificările Raportului", type="primary")
            if salvat:
                piese_curente = _extrage_piese_din_editor(edited_piese_hist)
                try:
                    _actualizeaza_raport_in_db(
                        rid,
                        {
                            "titlu": titlu_lucrare.strip(),
                            "simptom": simptom.strip(),
                            "defect": defect.strip(),
                            "solutie": solutie.strip(),
                            "durata": int(durata_min),
                            "stare_finala": stare_fin,
                            "tip_interventie": tip_interventie,
                            "tehnician": tehnician.strip(),
                            "verificator": verificator.strip(),
                            "optimizari": optimizari.strip(),
                            "piese_json": piese_curente,
                        },
                    )
                    # Invalidăm PDF-ul vechi din sesiune dacă raportul s-a schimbat
                    st.session_state.pop(f"hist_pdf_cache_{rid}", None)
                    st.success("Modificările raportului au fost salvate cu succes!")
                except Exception as exc:
                    st.error(f"Eroare la salvarea modificărilor: {exc}")

        piese_curente_lista = _extrage_piese_din_editor(edited_piese_hist)

        # --- LEGĂTURA CU INDEXUL DE DOCUMENTAȚIE & SOLUȚII [SOL] ---
        with st.expander(f"📚 Documentație indexată asociată & Salvare ca Soluție (`{CFG.tag_solutie}`)", expanded=False):
            cod_err_raw = str(r_data.get("cod_eroare") or "").strip()
            cod_err_rap = "" if cod_err_raw.lower() in CFG.valori_cod_eroare_gol else cod_err_raw
            termen_def = cod_err_rap or str(defect or simptom or titlu_lucrare or "").strip()[: CFG.lungime_max_termen_doc]

            q_hist_doc = st.text_input(
                "Caută în indexul de documentație (cod eroare / simptom / defect)",
                value=termen_def,
                key=f"hist_q_doc_{rid}",
            )
            docs_gasite, doc_err = _cauta_docs_pentru_raport(q_hist_doc)
            if doc_err:
                st.warning(f"Indexul de documentație nu a putut fi interogat: {doc_err}")
            elif docs_gasite:
                for d in docs_gasite:
                    tag_d = d.get("tag_sectiune") or CFG.tag_implicit_doc
                    titlu_d = d.get("titlu") or "Fără titlu"
                    hmi_d = str(d.get("coduri_eroare_hmi") or "").strip()
                    drv_d = str(d.get("coduri_eroare_driver") or "").strip()
                    pag_d = str(d.get("interval_pagini") or "").strip()
                    url_d = str(d.get("gdrive_url") or "").strip()

                    detalii = [f"**{tag_d} {titlu_d}**"]
                    if hmi_d:
                        detalii.append(f"HMI: `{hmi_d}`")
                    if drv_d:
                        detalii.append(f"Driver/VFD: `{drv_d}`")
                    if pag_d:
                        detalii.append(f"Pagini: `{pag_d}`")
                    if url_d:
                        detalii.append(f"[Google Drive]({url_d})")
                    st.markdown("- " + " — ".join(detalii))
            else:
                st.caption("Nu s-au găsit înregistrări în index pentru criteriul curent.")

            if st.button(f"➕ Salvează acest raport ca Soluție (`{CFG.tag_solutie}`) în index", key=f"btn_promoveaza_sol_{rid}"):
                piese_txt = _formateaza_piese_pentru_index(piese_curente_lista)
                sectiuni = [
                    ("Simptom", simptom),
                    ("Defect", defect),
                    ("Soluție", solutie),
                    ("Recomandări", optimizari),
                    ("Piese necesare", piese_txt),
                ]
                parti_text = [f"{eticheta}: {str(val).strip()}" for eticheta, val in sectiuni if str(val or "").strip()]

                masina_nume_rap = str(r_data.get("masina") or "").strip()
                mid_rap = masini_id_map.get(masina_nume_rap)

                try:
                    DocumentatieRepository.insert({
                        "masina_id": int(mid_rap) if mid_rap is not None else None,
                        "categorie": str(r_data.get("categorie") or CFG.categorie_doc_implicita).strip(),
                        "tip_sistem": str(r_data.get("subansamblu") or "").strip(),
                        "titlu": f"{titlu_lucrare.strip() or 'Intervenție'} — {masina_nume_rap or 'General'}",
                        "gdrive_file_id": "",
                        "gdrive_url": "",
                        "tip_fisier": CFG.tip_fisier_doc_implicit,
                        "tag_sectiune": CFG.tag_solutie,
                        "interval_pagini": "",
                        "coduri_eroare_hmi": cod_err_rap,
                        "coduri_eroare_driver": "",
                        "piese_necesare": piese_txt,
                        "text_indexat": "\n".join(parti_text),
                    })
                    st.success(f"✅ Raportul a fost adăugat în indexul de documentație cu eticheta `{CFG.tag_solutie}`.")
                except Exception as exc:
                    st.error(f"Eroare la salvarea în index: {exc}")

        # --- ACȚIUNI PDF & ȘTERGERE (fără st.rerun) ---
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            pdf_cache_key = f"hist_pdf_cache_{rid}"
            if st.button("📄 Generează PDF Actualizat", key=f"btn_pdf_{rid}"):
                try:
                    st.session_state[pdf_cache_key] = genereaza_pdf({
                        "id": rid,
                        "client": r_data.get("firma"),
                        "masina": r_data.get("masina"),
                        "durata": int(durata_min),
                        "stare_finala": stare_fin,
                        "piese_json": piese_curente_lista,
                        "titlu": titlu_lucrare.strip(),
                        "simptom": simptom.strip(),
                        "defect": defect.strip(),
                        "solutie": solutie.strip(),
                        "optimizari": optimizari.strip(),
                        "tehnician": tehnician.strip(),
                        "verificator": verificator.strip(),
                        "data": r_data.get("data") or datetime.now(),
                        "tip_interventie": tip_interventie,
                    })
                except Exception as exc:
                    st.error(f"Eroare la generarea PDF-ului: {exc}")

            if pdf_cache_key in st.session_state:
                st.download_button(
                    label="📥 Descarcă PDF Actualizat",
                    data=st.session_state[pdf_cache_key],
                    file_name=f"Raport_{rid}_Actualizat.pdf",
                    mime="application/pdf",
                    key=f"dl_pdf_{rid}",
                )

        with col_b2:
            st.button(
                "🗑️ Șterge Raport",
                key=f"btn_del_{rid}",
                type="secondary",
                on_click=_sterge_raport_callback,
                args=(rid, "hist_sel_rap_id"),
            )

    render_istoric_izolat()