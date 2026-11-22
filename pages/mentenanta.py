# ------------------------------------------
# -------pages/mentenanta.py----------------
# ------------------------------------------

import json
import re
import uuid
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository, ALL_SISTEME_DEFAULT
from repositories.mentenanta_repository import MentenantaRepository, INTERVALE_ZILE
from repositories.setari_repository import SetariRepository
from services.pdf_service import genereaza_pdf_mentenanta
from pages.fise_mentenanta import (
    FRECVENTE_MENTENANTA,
    construieste_nume_fisa,
    obtine_fisa_pentru_utilaj,
)

SECTIONS_MENTENANTA = [
    {
        "key": "electric_decuplat",
        "sistem_cod": "Electric",
        "titlu": "1.A. SISTEM ELECTRIC, ELECTRONICĂ & AUTOMATIZARE — Utilaj DECUPLAT (Procedură LOTO)",
        "nota": "Procedură Lockout/Tagout (LOTO). Orice înlocuire de piesă electrică se execută exclusiv cu utilajul decuplat.",
        "necesar_label": "Componente electrice / plăci electronice ce necesită înlocuire sau reparare",
        "items": [
            {"id": "el_d_1", "spec": "Verificarea și curățarea ștecherelor, prizelor industriale și conexiunilor principale de alimentare; aplicare spray de contact.", "param_hint": ""},
            {"id": "el_d_2", "spec": "Curățarea tablourilor electrice de praf/șpan, strângerea conexiunilor și a șuruburilor de forță/comandă, aplicare spray de contact.", "param_hint": ""},
            {"id": "el_d_3", "spec": "Decuplarea pe rând a conectorilor priză-ștecher / mufe industriale (Harting, M12), curățare și recuplare securizată.", "param_hint": ""},
            {"id": "el_d_4", "spec": "Măsurarea rezistențelor electrice de putere și a rezistenței de izolație a circuitelor.", "param_hint": "R_iz (MΩ)"},
            {"id": "el_d_5", "spec": "Măsurarea bobinelor motoarelor electrice (simetrie faze) și verificarea periilor / tahogeneratoarelor (unde este cazul).", "param_hint": "L1/L2/L3 (Ω)"},
            {"id": "el_d_6", "spec": "Verificarea absenței infiltrațiilor de lichide (ulei, emulsie de răcire, condens) în zona traseelor și conexiunilor electrice.", "param_hint": ""},
            {"id": "el_d_7", "spec": "Verificarea conexiunilor senzorilor (inductivi/optici/capacitivi), a distanțelor de comutare și a integrității cablurilor.", "param_hint": ""},
            {"id": "el_d_8", "spec": "Măsurarea rezistenței de contact a butoanelor de comandă, E-Stop, releelor și contactoarelor (valoare admisă < 4 Ω).", "param_hint": "R_contact (Ω)"},
            {"id": "el_d_9", "spec": "Măsurarea valorilor rezistive ale senzorilor de temperatură (PT100 / PT1000 / termocuple) conform fișei tehnice.", "param_hint": "Valoare (Ω)"},
            {"id": "el_d_10", "spec": "Curățarea filtrelor, ventilatoarelor și căilor de aerisire ale tablourilor electrice și unităților chiller tablou.", "param_hint": ""},
            {"id": "el_d_11", "spec": "Verificare/înlocuire baterii backup (PLC CPU, memorie CNC, encodere axe) + backup complet program PLC/CNC/HMI.", "param_hint": "Status backup"},
        ]
    },
    {
        "key": "electric_cuplat",
        "sistem_cod": "Electric",
        "titlu": "1.B. SISTEM ELECTRIC, ELECTRONICĂ & AUTOMATIZARE — Utilaj CUPLAT (Sub Tensiune)",
        "nota": "Măsurători și teste funcționale sub tensiune nominală.",
        "necesar_label": "Observații suplimentare circuit de forță, comandă și siguranță",
        "items": [
            {"id": "el_c_1", "spec": "Măsurarea tensiunilor de alimentare pe faze și a surselor DC 24V (abatere maximă admisă ±5% față de nominal).", "param_hint": "U (V) / 24V"},
            {"id": "el_c_2", "spec": "Testarea circuitelor de siguranță: senzori/interlock-uri uși și panouri de acces, bariere optice, butoane E-Stop.", "param_hint": ""},
            {"id": "el_c_3", "spec": "Verificarea funcționării motoarelor electrice, servomotoarelor și convertizoarelor (zgomot, vibrații, temperatură, curenți).", "param_hint": "I_abs (A)"},
            {"id": "el_c_4", "spec": "Verificarea funcționării normale a senzorilor de poziție/presiune/debit și reglarea pragurilor de detecție.", "param_hint": ""},
        ]
    },
    {
        "key": "mecanic",
        "sistem_cod": "Mecanic",
        "titlu": "2. SISTEM MECANIC, TRANSMISII & GEOMETRIE (Utilaj Decuplat LOTO)",
        "nota": "Operațiuni efectuate cu utilajul decuplat de la sursa de energie electrică (LOTO).",
        "necesar_label": "Elemente mecanice ce necesită înlocuire înainte de următoarea revizie generală",
        "items": [
            {"id": "mec_1", "spec": "Verificarea jocurilor la elementele articulate (cuple cinematice, bucșe, rulmenți, șuruburi cu bile și ghidaje liniare).", "param_hint": "X / Y / Z (mm)"},
            {"id": "mec_2", "spec": "Înlocuirea bucșelor, rulmenților sau cuplelor sferice cu uzură avansată sau durată de viață depășită.", "param_hint": ""},
            {"id": "mec_3", "spec": "Înlocuirea simeringurilor, racletorilor de ghidaj și a elementelor de etanșare uzate.", "param_hint": ""},
            {"id": "mec_4", "spec": "Verificarea tensionării și stării de uzură a curelelor (trapezoidale, dințate) și lanțurilor de transmisie.", "param_hint": ""},
            {"id": "mec_5", "spec": "Verificarea și estimarea jocurilor (backlash) în angrenaje, reductoare și casete de antrenare.", "param_hint": ""},
            {"id": "mec_6", "spec": "Verificarea funcționării și eficienței frânelor electromagnetice/mecanice ale motoarelor și axelor verticale.", "param_hint": ""},
            {"id": "mec_7", "spec": "Verificarea și completarea nivelului de ulei în reductoare/cutii de viteze; gresarea punctelor de ungere / pompă ungere centralizată.", "param_hint": "Tip ulei/unsoare"},
            {"id": "mec_8", "spec": "Verificare arbore principal / spindle (forță strângere portsculă, runout, vibrații) și curățare evacuare șpan.", "param_hint": "Forță (kN)"},
        ]
    },
    {
        "key": "hidraulic",
        "sistem_cod": "Hidraulic",
        "titlu": "3. SISTEM HIDRAULIC & UNGERE",
        "nota": "Orice înlocuire se execută exclusiv după decuplarea electrică și depresurizarea completă a circuitului hidraulic.",
        "necesar_label": "Elemente hidraulice ce necesită înlocuire înainte de următoarea revizie generală",
        "items": [
            {"id": "hid_1", "spec": "Pornirea grupului hidraulic și verificarea nivelului de zgomot, cavitației și vibrațiilor pompei hidraulice.", "param_hint": ""},
            {"id": "hid_2", "spec": "Verificarea presiunii de lucru pe manometre și a presiunii de preîncărcare a acumulatorilor hidraulici.", "param_hint": "P_sistem (bar)"},
            {"id": "hid_3", "spec": "Verificarea funcționării electrovalvelor/distribuitoarelor (inclusiv acționare manuală) și a curselor/vitezelor cilindrilor.", "param_hint": ""},
            {"id": "hid_4", "spec": "Inspectarea etanșeității circuitului: strângere racorduri, înlocuire furtunuri sau garnituri cu scurgeri de ulei.", "param_hint": ""},
            {"id": "hid_5", "spec": "Curățarea jojei magnetice de retur, curățarea/înlocuirea filtrelor de ulei și completarea/schimbul uleiului hidraulic.", "param_hint": "Tip ulei"},
        ]
    },
    {
        "key": "pneumatic",
        "sistem_cod": "Pneumatic",
        "titlu": "4. SISTEM PNEUMATIC",
        "nota": "Orice înlocuire se execută exclusiv după izolarea de la rețeaua de aer comprimat și purjarea presiunii reziduale.",
        "necesar_label": "Elemente pneumatice ce necesită înlocuire înainte de următoarea revizie generală",
        "items": [
            {"id": "pne_1", "spec": "Verificarea grupului de preparare aer (FRL): presiune de lucru, curățare decantoare condens, verificare nivel ulei ungător.", "param_hint": "P_aer (bar)"},
            {"id": "pne_2", "spec": "Verificarea funcționării distribuitoarelor pneumatice și reglarea curselor/vitezelor cilindrilor din drosele.", "param_hint": ""},
            {"id": "pne_3", "spec": "Detectarea și remedierea pierderilor de aer (înlocuire furtunuri, fitinguri rapide, garnituri de etanșare).", "param_hint": ""},
            {"id": "pne_4", "spec": "Testarea garniturilor interioare ale pistoanelor și distribuitoarelor prin decuplarea traseului nepresurizat (piston vs. distribuitor).", "param_hint": ""},
        ]
    },
    {
        "key": "vacuum",
        "sistem_cod": "Vacuum",
        "titlu": "5. SISTEM VACUUM (Dacă utilajul este dotat)",
        "nota": "Verificări în funcționare și cu utilajul oprit de la comutatorul general.",
        "necesar_label": "Elemente sistem vacuum ce necesită înlocuire / reparare",
        "items": [
            {"id": "vac_1", "spec": "Verificarea zgomotului și temperaturii pompei de vacuum în funcționare; inspectare scurgeri ulei de vid.", "param_hint": "Temp (°C)"},
            {"id": "vac_2", "spec": "Cu utilajul oprit: curățare/înlocuire filtre vacuum, curățare traseu în amonte de filtru, verificare/completare ulei de vid.", "param_hint": ""},
            {"id": "vac_3", "spec": "Verificarea nivelului de vacuum cu manometrul/vacuummetrul și inspectarea furtunurilor de aspirație și colierelor.", "param_hint": "Vid (mbar)"},
        ]
    },
    {
        "key": "auxiliare",
        "sistem_cod": "Auxiliare",
        "titlu": "6. INSTALAȚII AUXILIARE (Răcire / Emulsie / Apă / Abur / Afumare)",
        "nota": "Orice intervenție se execută exclusiv după închiderea vanelor manuale și verificarea lipsei presiunii/circulației.",
        "necesar_label": "Elemente instalații auxiliare ce necesită înlocuire înainte de următoarea revizie",
        "items": [
            {"id": "aux_1", "spec": "Instalații de răcire / emulsie / apă: izolare vane, verificare obturare conducte, curățare filtre/schimbătoare, verificare pompe.", "param_hint": "Conc. emulsie (%)"},
            {"id": "aux_2", "spec": "Instalații de abur: izolare vane manuale, verificare presiune zero, verificare obturare conducte și vane de admisie.", "param_hint": ""},
            {"id": "aux_3", "spec": "Instalații de afumare / exhaustare: verificare obturare conducte evacuare, curățare depuneri și vane de admisie.", "param_hint": ""},
        ]
    }
]


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


def _get_items_pentru_masina(sec: dict, masina_obj: dict | None) -> list:
    s_key = sec["key"]
    if masina_obj:
        custom_map = masina_obj.get("verificari_custom_json") or {}
        if isinstance(custom_map, dict) and s_key in custom_map and isinstance(custom_map[s_key], list):
            return custom_map[s_key]
    return list(sec["items"])


def _build_df_for_section(sec: dict, masina_obj: dict | None = None, default_status: str = "DA") -> pd.DataFrame:
    items = _get_items_pentru_masina(sec, masina_obj)
    rows = []
    for it in items:
        hint = it.get("param_hint", "")
        obs_init = f"{hint}: " if hint else ""
        rows.append({
            "ID": it.get("id", str(uuid.uuid4())[:8]),
            "Operațiune": it.get("spec", ""),
            "Conformitate": default_status,
            "Observații / Valori Măsurate": obs_init
        })
    return pd.DataFrame(rows)


def _incarca_dfs_pentru_masina(masina_obj: dict | None, default_status: str = "DA"):
    st.session_state["ment_dfs"] = {
        sec["key"]: _build_df_for_section(sec, masina_obj, default_status)
        for sec in SECTIONS_MENTENANTA
    }
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _init_sau_reseteaza_ment_draft(tehnician_def: str, default_status: str = "DA"):
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
        "necesar": {sec["key"]: "" for sec in SECTIONS_MENTENANTA},
        "capitole_excluse": [],
    }
    _incarca_dfs_pentru_masina(None, default_status)


def _aplica_status_global(status_nou: str):
    if "ment_dfs" not in st.session_state:
        return
    for sec in SECTIONS_MENTENANTA:
        df = st.session_state["ment_dfs"].get(sec["key"])
        if df is not None and not df.empty:
            df["Conformitate"] = status_nou
            st.session_state["ment_dfs"][sec["key"]] = df
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _construieste_randuri_complete_frecventa(
    pasi_fisa: list[dict],
    sectiuni_active: list[dict],
    capitole_excluse: list[str],
    doc_overrides: dict[str, str],
) -> list[dict]:
    rows = []
    vazute = set()
    ord_curent = 1

    for p in (pasi_fisa or []):
        op_txt = str(p.get("Operațiune / Verificare") or p.get("operatiune") or p.get("pas") or "").strip()
        if not op_txt:
            continue
        std_txt = str(p.get("Standard / Observații") or p.get("observatii") or "").strip()
        raw_doc = (
            p.get("Documentație Drive")
            or p.get("Documentatie Drive")
            or p.get("documentatie_drive")
            or p.get("drive_url")
            or ""
        )
        cheie_op = op_txt.lower()
        doc_final = doc_overrides.get(cheie_op, str(raw_doc or "").strip())
        rows.append({
            "Ordine": ord_curent,
            "Operațiune / Verificare": op_txt,
            "Standard / Observații": std_txt,
            "Documentație Drive": doc_final,
            "Efectuat": True,
            "Valori Măsurate / Observații": "",
        })
        vazute.add(cheie_op)
        ord_curent += 1

    excluse_set = set(capitole_excluse or [])
    for sec in sectiuni_active:
        if sec["key"] in excluse_set:
            continue
        df_sec = st.session_state.get("ment_dfs", {}).get(sec["key"])
        if df_sec is None or df_sec.empty:
            continue
        for _, r in df_sec.iterrows():
            op_txt = str(r.get("Operațiune") or "").strip()
            if not op_txt:
                continue
            cheie_op = op_txt.lower()
            if cheie_op in vazute:
                continue
            conf_val = str(r.get("Conformitate") or "DA").strip()
            obs_val = str(r.get("Observații / Valori Măsurate") or "").strip()
            doc_final = doc_overrides.get(cheie_op, "")
            rows.append({
                "Ordine": ord_curent,
                "Operațiune / Verificare": op_txt,
                "Standard / Observații": f"[{sec['sistem_cod']}] Conformitate: {conf_val}",
                "Documentație Drive": doc_final,
                "Efectuat": conf_val != "NU",
                "Valori Măsurate / Observații": obs_val,
            })
            vazute.add(cheie_op)
            ord_curent += 1

    return rows


def _render_fisa_specifica_utilaj(
    masina_obj: dict,
    firma_nume: str,
    data_interv: date,
    sectiuni_active: list[dict],
    capitole_excluse: list[str],
    is_unlocked: bool,
    frecventa_init: str = "Lunară",
):
    den_masina = str(masina_obj.get("denumire") or "").strip()
    tip_masina = str(masina_obj.get("tip_masina") or "").strip()

    idx_frec = FRECVENTE_MENTENANTA.index(frecventa_init) if frecventa_init in FRECVENTE_MENTENANTA else 2
    frec_sel = st.selectbox(
        "Tip întreținere / Frecvență",
        options=FRECVENTE_MENTENANTA,
        index=idx_frec,
        key=f"ment_frec_fisa_{masina_obj['id']}",
    )

    fisa = obtine_fisa_pentru_utilaj(den_masina, tip_masina, frec_sel)
    nume_fisa = fisa.get("nume_fisa") or construieste_nume_fisa(den_masina, tip_masina, frec_sel, False)
    eticheta_sursa = "Fișă proprie" if fisa.get("sursa") == "proprie" else "Fișă generală"
    titlu_pdf = construieste_titlu_operatiuni_pdf(
        frecventa=frec_sel,
        masina=den_masina,
        tip_masina=tip_masina,
        data_str=str(data_interv),
        firma=firma_nume,
    )

    st.caption(f"Fișă: **{nume_fisa}** ({eticheta_sursa}) | Titlu PDF: **{titlu_pdf}**")

    doc_key = f"ment_doc_overrides_{masina_obj['id']}_{frec_sel}"
    doc_overrides = st.session_state.setdefault(doc_key, {})

    pasi_fisa = fisa.get("pasi") or []
    rows = _construieste_randuri_complete_frecventa(
        pasi_fisa=pasi_fisa,
        sectiuni_active=sectiuni_active,
        capitole_excluse=capitole_excluse,
        doc_overrides=doc_overrides,
    )

    if not rows:
        st.info("Nu există operațiuni definite pentru această mașină, tip și frecvență.")
        df_gol = pd.DataFrame(columns=[
            "Ordine",
            "Operațiune / Verificare",
            "Standard / Observații",
            "Documentație Drive",
            "Efectuat",
            "Valori Măsurate / Observații",
        ])
        return df_gol, nume_fisa, frec_sel, titlu_pdf

    doc_links = []
    for r in rows:
        link_norm = _normalizare_link_drive(r.get("Documentație Drive") or "")
        if link_norm:
            doc_links.append((f"{r['Ordine']}. {str(r['Operațiune / Verificare'])[:65]}", link_norm))

    df_fisa = pd.DataFrame(rows)
    df_ed = st.data_editor(
        df_fisa,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=["Ordine", "Operațiune / Verificare", "Standard / Observații", "Documentație Drive"],
        column_config={
            "Ordine": st.column_config.NumberColumn("Ordine", width="small"),
            "Operațiune / Verificare": st.column_config.TextColumn("Operațiune / Verificare", width="large"),
            "Standard / Observații": st.column_config.TextColumn("Standard / Observații", width="medium"),
            "Documentație Drive": st.column_config.LinkColumn(
                "Documentație Drive",
                display_text="Deschide Drive",
                width="small",
            ),
            "Efectuat": st.column_config.CheckboxColumn("Efectuat", width="small"),
            "Valori Măsurate / Observații": st.column_config.TextColumn(
                "Valori Măsurate / Observații",
                width="medium",
            ),
        },
        key=f"ment_ed_fisa_spec_{masina_obj['id']}_{frec_sel}",
    )

    if doc_links:
        opt_doc = {label: url for label, url in doc_links}
        cd1, cd2 = st.columns([3.5, 1.5], vertical_alignment="center")
        sel_doc = cd1.selectbox(
            "Documentație operațiune (Google Drive)",
            options=list(opt_doc.keys()),
            key=f"ment_sel_doc_{masina_obj['id']}_{frec_sel}",
        )
        cd2.link_button("📂 Deschide în Google Drive", opt_doc[sel_doc], use_container_width=True)

    if is_unlocked:
        with st.expander("📎 Încarcă / Setează documentația pentru operațiunea selectată", expanded=False):
            opt_ops = {
                f"{r['Ordine']}. {str(r['Operațiune / Verificare'])[:75]}": str(r["Operațiune / Verificare"]).strip().lower()
                for r in rows
            }
            sel_op_doc = st.selectbox(
                "Alege operațiunea",
                options=list(opt_ops.keys()),
                key=f"ment_upload_op_sel_{masina_obj['id']}_{frec_sel}",
            )
            cheie_op_sel = opt_ops[sel_op_doc]
            val_curent = doc_overrides.get(cheie_op_sel, "")

            u1, u2 = st.columns([2.2, 1.8])
            with u1:
                link_nou = st.text_input(
                    "Link Google Drive",
                    value=val_curent,
                    placeholder="https://drive.google.com/...",
                    key=f"ment_upload_link_{masina_obj['id']}_{frec_sel}_{cheie_op_sel[:20]}",
                ).strip()
            with u2:
                fis_nou = st.file_uploader(
                    "Sau încarcă documentație",
                    type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
                    key=f"ment_upload_file_{masina_obj['id']}_{frec_sel}_{cheie_op_sel[:20]}",
                )

            if st.button("💾 Salvează documentația operațiunii", key=f"ment_btn_save_doc_{masina_obj['id']}_{frec_sel}"):
                val_final = link_nou
                if fis_nou is not None:
                    val_final = _salveaza_doc_local_ment(fis_nou, f"m{masina_obj['id']}_{frec_sel}")
                doc_overrides[cheie_op_sel] = val_final
                st.session_state[doc_key] = doc_overrides
                st.toast("✅ Documentația a fost atașată operațiunii.")
                st.rerun()

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
            linie = f"{r.get('Ordine', '')}. {r.get('Operațiune / Verificare', '')} | Efectuat: {r.get('Efectuat', '')} | {r.get('Valori Măsurate / Observații', '')}"
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
        _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
    if "ment_salvat" not in st.session_state:
        st.session_state["ment_salvat"] = False
    if "ment_pdf_bytes" not in st.session_state:
        st.session_state["ment_pdf_bytes"] = None
    if "ment_pdf_name" not in st.session_state:
        st.session_state["ment_pdf_name"] = None
    if "ment_id_salvat" not in st.session_state:
        st.session_state["ment_id_salvat"] = None

    draft = st.session_state["ment_draft"]

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
            if st.button("➕ Completează o fișă nouă", use_container_width=True):
                st.session_state["ment_salvat"] = False
                st.session_state["ment_pdf_bytes"] = None
                st.session_state["ment_pdf_name"] = None
                st.session_state["ment_id_salvat"] = None
                _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
                st.rerun()
        return

    firme_db = FirmeRepository.get_all()
    if not firme_db:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în modulul 'Firme'.")
        return

    firme_dict = {f["nume_firma"]: f for f in firme_db}
    opt_firme = ["-- Alege firma --"] + list(firme_dict.keys())

    top_1, top_2, top_3, top_4 = st.columns([3.2, 1.3, 1.3, 1.2], vertical_alignment="center")
    with top_1:
        st.caption("⚡ **Mod Audit Rapid:** toate punctele pornesc pe **DA**; modifică doar neconformitățile (**NU** / **N/A**) și valorile măsurate.")
    with top_2:
        if st.button("✅ Setează tot DA", use_container_width=True):
            _aplica_status_global("DA")
            st.toast("✅ Toate punctele au fost setate pe DA.")
            st.rerun()
    with top_3:
        if st.button("⬜ Setează tot N/A", use_container_width=True):
            _aplica_status_global("N/A")
            st.toast("⬜ Toate punctele au fost setate pe N/A.")
            st.rerun()
    with top_4:
        if st.button("❌ Resetează", use_container_width=True):
            _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
            st.rerun()

    # 1. IDENTIFICARE CLIENT & UTILAJ
    idx_f = opt_firme.index(draft["sel_firma"]) if draft.get("sel_firma") in opt_firme else 0
    col_id1, col_id2, col_id3 = st.columns(3)
    with col_id1:
        sel_firma = st.selectbox("1. Beneficiar / Client *", options=opt_firme, index=idx_f)
        draft["sel_firma"] = sel_firma

    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Selectează clientul și utilajul pentru a încărca operațiunile de mentenanță.")
        _render_istoric_mentenanta(firme_dict)
        return

    firma_obj = firme_dict[sel_firma]
    if draft.get("ultima_firma") != sel_firma:
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

    if draft.get("ultima_masina") != sel_masina:
        draft["ultima_masina"] = sel_masina
        draft["producator_model"] = str(masina_obj.get("tip_masina") or "")
        draft["serie_fabricatie"] = str(masina_obj.get("serie") or "")
        if total_int_m >= prag_int_m:
            draft["nivel_grila"] = "Nivel B – CNC Biglia / Matec / >20h / Inginerie"
        else:
            draft["nivel_grila"] = "Nivel A – Multimarcă (<20h)"
        _incarca_dfs_pentru_masina(masina_obj, "DA")

    if total_int_m >= prag_int_m:
        st.warning(f"🔔 **Atenție Grilă Tarifare:** Utilajul **{sel_masina}** a atins/depășit pragul (**{total_int_m} / {prag_int_m}** intervenții)! Se recomandă trecerea la următoarea grilă de tarifare (**Nivel B**).")
    else:
        st.info(f"📊 **Contor intervenții ({sel_masina}):** {total_int_m} / {prag_int_m} efectuate (mai sunt **{prag_int_m - total_int_m}** până la următoarea grilă).")

    _asigura_coloane_intretinere_ment()
    este_fara_int = bool(masina_obj.get("fara_intretinere", False))
    tip_int_masina = masina_obj.get("tip_intretinere") or "Lunară"
    interval_din_db = int(masina_obj.get("interval_intretinere_zile") or 0)
    durata_implicita_zile = interval_din_db if interval_din_db > 0 else INTERVALE_ZILE.get(tip_int_masina, 30)

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

    sisteme_utilaj = [
        s.strip() for s in str(masina_obj.get("sisteme_active") or ALL_SISTEME_DEFAULT).split(",")
        if s.strip()
    ]
    if not sisteme_utilaj:
        sisteme_utilaj = ["Electric", "Mecanic", "Hidraulic", "Pneumatic", "Vacuum", "Auxiliare"]

    afiseaza_toate_sistemele = st.checkbox(
        f"Afișează toate cele 6 sisteme (utilajul are configurate: {', '.join(sisteme_utilaj)})",
        value=False
    )

    sectiuni_active = [
        sec for sec in SECTIONS_MENTENANTA
        if afiseaza_toate_sistemele or (sec["sistem_cod"] in sisteme_utilaj)
    ]
    capitole_excluse = draft.setdefault("capitole_excluse", [])

    with st.expander(f"🛠️ Operațiuni Mentenanță pe Frecvență — {sel_masina} ({masina_obj.get('tip_masina') or '-'})", expanded=True):
        df_fisa_utilaj, nume_fisa_activa, frec_fisa_activa, titlu_pdf_activ = _render_fisa_specifica_utilaj(
            masina_obj=masina_obj,
            firma_nume=sel_firma,
            data_interv=data_interv,
            sectiuni_active=sectiuni_active,
            capitole_excluse=capitole_excluse,
            is_unlocked=is_unlocked,
            frecventa_init=tip_int_masina,
        )

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

    with st.expander(f"🧩 Componență Sisteme Utilaj: {sel_masina}", expanded=False):
        comp_lista = masina_obj.get("componenta_sisteme_json") or []
        df_comp = pd.DataFrame(comp_lista) if comp_lista else pd.DataFrame(
            columns=["Sistem", "Element / Componentă", "Cod / Specificații", "Cantitate", "Observații"]
        )
        for col_req in ["Sistem", "Element / Componentă", "Cod / Specificații", "Cantitate", "Observații"]:
            if col_req not in df_comp.columns:
                df_comp[col_req] = ""

        if is_unlocked:
            st.caption("🔓 Mod editare activ (deblocat din **SistemAdmin → Deblocare**): poți adăuga sau scoate elemente din componența sistemelor acestei mașini.")
            edited_comp = st.data_editor(
                df_comp,
                num_rows="dynamic",
                column_config={
                    "Sistem": st.column_config.SelectboxColumn(
                        "Sistem",
                        options=["Electric", "Mecanic", "Hidraulic", "Pneumatic", "Vacuum", "Auxiliare"],
                        default="Electric",
                        required=True
                    ),
                    "Element / Componentă": st.column_config.TextColumn("Element / Componentă", required=True, width="medium"),
                    "Cod / Specificații": st.column_config.TextColumn("Cod / Specificații", width="medium"),
                    "Cantitate": st.column_config.TextColumn("Cantitate", default="1", width="small"),
                    "Observații": st.column_config.TextColumn("Observații", width="medium"),
                },
                key=f"ment_comp_ed_{masina_obj['id']}",
                use_container_width=True
            )
            if st.button("💾 Salvează Componența Sistemelor Utilajului", key=f"ment_save_comp_{masina_obj['id']}"):
                clean_comp = [
                    row for row in edited_comp.fillna("").to_dict(orient="records")
                    if str(row.get("Element / Componentă", "")).strip() != ""
                ]
                MasiniRepository.update_componenta_sisteme(masina_obj["id"], clean_comp)
                st.success("✅ Componența sistemelor a fost salvată pentru acest utilaj!")
                st.rerun()
        else:
            st.caption("🔒 Componență protejată (doar vizualizare). Deblochează din **SistemAdmin → Deblocare** pentru a adăuga/scoate elemente.")
            if df_comp.empty:
                st.info("Nu există elemente înregistrate în componența acestui utilaj.")
            else:
                st.dataframe(df_comp, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🔍 Verificări Tehnice pe Sisteme")
    if is_unlocked:
        st.caption("🔓 **Mod Administrator Deblocat:** În fiecare sistem poți adăuga verificări noi sau șterge una ori mai multe verificări selectate.")
    else:
        st.info("🔒 **Sistemul este blocat.** Pentru a edita/adăuga/șterge verificările pe sisteme, deblochează sistemul cu parola din **SistemAdmin → Deblocare**.")

    if capitole_excluse:
        c_r1, c_r2 = st.columns([3, 1.5], vertical_alignment="center")
        c_r1.caption(f"🚫 Capitole eliminate din această fișă: **{', '.join(capitole_excluse)}**")
        if c_r2.button("↩️ Restaurează capitolele", key="btn_rest_cap_ment", use_container_width=True):
            draft["capitole_excluse"] = []
            st.rerun()

    for sec in sectiuni_active:
        s_key = sec["key"]
        if s_key in capitole_excluse:
            continue

        df_sec = st.session_state["ment_dfs"][s_key]
        nr_nu = int((df_sec["Conformitate"] == "NU").sum()) if not df_sec.empty else 0
        badge = f" — ⚠️ {nr_nu} neconformități" if nr_nu > 0 else " — ✅ OK"

        with st.expander(f"{sec['titlu']}{badge}", expanded=(s_key in ("electric_decuplat", "electric_cuplat", "mecanic") or nr_nu > 0)):
            st.caption(f"ℹ️ {sec['nota']}")
            if is_unlocked:
                if st.button(f"🗑️ Elimină tot capitolul ({sec['sistem_cod']})", key=f"btn_del_cap_{s_key}"):
                    draft["capitole_excluse"].append(s_key)
                    st.toast(f"🗑️ Capitolul „{sec['sistem_cod']}” a fost eliminat din această fișă.")
                    st.rerun()

            edited_sec = st.data_editor(
                df_sec,
                hide_index=True,
                disabled=["ID"] if is_unlocked else ["ID", "Operațiune"],
                column_config={
                    "ID": None,
                    "Operațiune": st.column_config.TextColumn("Specificație Operațiune", width="large"),
                    "Conformitate": st.column_config.SelectboxColumn(
                        "Conformitate",
                        options=["DA", "NU", "N/A"],
                        required=True,
                        width="small"
                    ),
                    "Observații / Valori Măsurate": st.column_config.TextColumn(
                        "Observații / Valori Măsurate",
                        width="medium"
                    )
                },
                key=f"ment_ed_{s_key}_{st.session_state.get('ment_counter', 0)}",
                use_container_width=True
            )
            st.session_state["ment_dfs"][s_key] = edited_sec

            if is_unlocked:
                st.markdown("##### 🔐 Administrare verificări pentru acest sistem (individual pe mașină)")
                c_add1, c_add2, c_add3 = st.columns([3.5, 1.5, 1.2], vertical_alignment="bottom")
                noua_spec = c_add1.text_input(
                    "Verificare nouă",
                    placeholder="Descrierea operațiunii de verificare...",
                    key=f"inp_new_verif_{masina_obj['id']}_{s_key}"
                )
                nou_hint = c_add2.text_input(
                    "Parametru (opțional)",
                    placeholder="ex: Presiune (bar)",
                    key=f"inp_new_hint_{masina_obj['id']}_{s_key}"
                )
                if c_add3.button("➕ Adaugă", key=f"btn_add_verif_{masina_obj['id']}_{s_key}", use_container_width=True):
                    if noua_spec.strip():
                        items_curente = _get_items_pentru_masina(sec, masina_obj)
                        new_item = {
                            "id": f"cust_{uuid.uuid4().hex[:6]}",
                            "spec": noua_spec.strip(),
                            "param_hint": nou_hint.strip()
                        }
                        items_actualizate = items_curente + [new_item]
                        custom_map = dict(masina_obj.get("verificari_custom_json") or {})
                        custom_map[s_key] = items_actualizate
                        MasiniRepository.update_verificari_custom(masina_obj["id"], custom_map)

                        obs_init = f"{nou_hint.strip()}: " if nou_hint.strip() else ""
                        new_row = pd.DataFrame([{
                            "ID": new_item["id"],
                            "Operațiune": new_item["spec"],
                            "Conformitate": "DA",
                            "Observații / Valori Măsurate": obs_init
                        }])
                        st.session_state["ment_dfs"][s_key] = pd.concat([edited_sec, new_row], ignore_index=True)
                        st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1
                        st.toast("✅ Verificarea a fost adăugată pentru acest utilaj!")
                        st.rerun()
                    else:
                        st.warning("Introdu descrierea verificării înainte de a apăsa Adaugă.")

                if not edited_sec.empty:
                    opt_del = {
                        f"{idx+1}. {str(row['Operațiune'])[:85]}": row["ID"]
                        for idx, row in edited_sec.iterrows()
                    }
                    verif_de_sters = st.multiselect(
                        "Selectează una sau mai multe verificări de eliminat din acest sistem",
                        options=list(opt_del.keys()),
                        key=f"ms_del_verif_{masina_obj['id']}_{s_key}"
                    )
                    if st.button("🗑️ Elimină verificările selectate", key=f"btn_del_verif_{masina_obj['id']}_{s_key}"):
                        if not verif_de_sters:
                            st.warning("Selectează cel puțin o verificare de eliminat.")
                        else:
                            ids_sterse = {opt_del[k] for k in verif_de_sters}
                            items_curente = _get_items_pentru_masina(sec, masina_obj)
                            items_ramase = [it for it in items_curente if it.get("id") not in ids_sterse]
                            custom_map = dict(masina_obj.get("verificari_custom_json") or {})
                            custom_map[s_key] = items_ramase
                            MasiniRepository.update_verificari_custom(masina_obj["id"], custom_map)

                            st.session_state["ment_dfs"][s_key] = edited_sec[~edited_sec["ID"].isin(ids_sterse)].reset_index(drop=True)
                            st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1
                            st.toast(f"🗑️ Au fost eliminate {len(ids_sterse)} verificări.")
                            st.rerun()

            draft["necesar"][s_key] = st.text_area(
                sec["necesar_label"],
                value=str(draft["necesar"].get(s_key, "")),
                height=68,
                key=f"ment_nec_{s_key}_{st.session_state.get('ment_counter', 0)}"
            )

    st.markdown("---")
    st.markdown("### 7. Recomandări Tehnice, Audit Upgrade / IIoT & Recepție Lucrări")
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
            checklist_payload = {}
            capitole_excluse_set = set(draft.get("capitole_excluse") or [])
            for sec in SECTIONS_MENTENANTA:
                s_key = sec["key"]
                is_active = (s_key not in capitole_excluse_set) and (
                    afiseaza_toate_sistemele or (sec["sistem_cod"] in sisteme_utilaj)
                )
                df_cur = st.session_state["ment_dfs"][s_key].copy()
                if not is_active:
                    df_cur["Conformitate"] = "N/A"
                checklist_payload[s_key] = {
                    "titlu": sec["titlu"],
                    "nota": sec["nota"],
                    "necesar_label": sec["necesar_label"],
                    "necesar_text": draft["necesar"].get(s_key, ""),
                    "activ": is_active,
                    "randuri": df_cur.to_dict(orient="records")
                }

            fisa_spec_rows = (
                df_fisa_utilaj.fillna("").to_dict(orient="records")
                if df_fisa_utilaj is not None and not df_fisa_utilaj.empty
                else []
            )
            checklist_payload["fisa_specifica_utilaj"] = {
                "titlu": nume_fisa_activa,
                "titlu_pdf": titlu_pdf_activ,
                "denumire_masina": str(masina_obj.get("denumire") or "").strip(),
                "tip_masina": str(masina_obj.get("tip_masina") or "").strip(),
                "frecventa": frec_fisa_activa,
                "randuri": fisa_spec_rows,
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

            new_id = MentenantaRepository.insert(fisa_data)
            fisa_data["id"] = new_id
            pdf_bytes = _genereaza_pdf_cu_fallback(fisa_data)
            nume_pdf_cur = construieste_nume_fisier_pdf(titlu_pdf_activ, new_id)

            st.session_state["ment_id_salvat"] = new_id
            st.session_state["ment_pdf_bytes"] = pdf_bytes
            st.session_state["ment_pdf_name"] = nume_pdf_cur
            st.session_state["ment_salvat"] = True
            _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
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

            c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
            with c1:
                st.write(f"**Titlu:** {titlu_pdf_hist}")
                st.write(f"**Serie:** {fisa.get('serie_fabricatie') or '-'} | **Ore utilaj:** {fisa.get('ore_functionare') or '-'} | **Tehnician:** {fisa.get('tehnician') or '-'}")
                st.write(f"**Următoarea revizie:** {str(fisa.get('urmatoarea_revizie') or '-')[:10]}")
            with c2:
                fisa_pdf_payload = dict(fisa)
                fisa_pdf_payload["checklist_json"] = chk
                fisa_pdf_payload["frecventa"] = frec_hist
                fisa_pdf_payload["titlu_pdf_operatiuni"] = titlu_pdf_hist
                pdf_hist = _genereaza_pdf_cu_fallback(fisa_pdf_payload)
                nume_pdf_hist = construieste_nume_fisier_pdf(titlu_pdf_hist, fid)
                st.download_button(
                    label="📥 Descarcă PDF",
                    data=pdf_hist,
                    file_name=nume_pdf_hist,
                    mime="application/pdf",
                    key=f"dl_ment_hist_{fid}",
                    use_container_width=True
                )
            with c3:
                if st.button("🗑️ Șterge", key=f"del_ment_{fid}", use_container_width=True):
                    MentenantaRepository.delete(fid)
                    st.rerun()

            if isinstance(fisa_spec, dict) and fisa_spec.get("randuri"):
                st.caption(f"**{fisa_spec.get('titlu', 'Operațiuni Mentenanță')}**")
                st.dataframe(pd.DataFrame(fisa_spec["randuri"]), hide_index=True, use_container_width=True)