#------------------------------------------
#-------pages/mentenanta.py----------------
#------------------------------------------

import json
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository, ALL_SISTEME_DEFAULT
from repositories.mentenanta_repository import MentenantaRepository, INTERVALE_ZILE
from repositories.setari_repository import SetariRepository
from services.pdf_service import genereaza_pdf_mentenanta

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


def _build_default_df_for_section(sec: dict, default_status: str = "DA") -> pd.DataFrame:
    rows = []
    for it in sec["items"]:
        obs_init = f"{it['param_hint']}: " if it["param_hint"] else ""
        rows.append({
            "ID": it["id"],
            "Operațiune": it["spec"],
            "Conformitate": default_status,
            "Observații / Valori Măsurate": obs_init
        })
    return pd.DataFrame(rows)


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
        "necesar": {sec["key"]: "" for sec in SECTIONS_MENTENANTA}
    }
    st.session_state["ment_dfs"] = {
        sec["key"]: _build_default_df_for_section(sec, default_status)
        for sec in SECTIONS_MENTENANTA
    }
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def _aplica_status_global(status_nou: str):
    if "ment_dfs" not in st.session_state:
        return
    for sec in SECTIONS_MENTENANTA:
        df = st.session_state["ment_dfs"].get(sec["key"])
        if df is not None and not df.empty:
            df["Conformitate"] = status_nou
            st.session_state["ment_dfs"][sec["key"]] = df
    st.session_state["ment_counter"] = st.session_state.get("ment_counter", 0) + 1


def render_mentenanta():
    st.subheader("🛡️ Fișă de Mentenanță Preventivă & Audit Tehnic")

    setari = SetariRepository.get_setari()
    tehnician_def = setari.get("tehnician_implicit") or "Tehnician Nexus"

    if "ment_draft" not in st.session_state:
        _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
    if "ment_salvat" not in st.session_state:
        st.session_state["ment_salvat"] = False
    if "ment_pdf_bytes" not in st.session_state:
        st.session_state["ment_pdf_bytes"] = None
    if "ment_id_salvat" not in st.session_state:
        st.session_state["ment_id_salvat"] = None

    draft = st.session_state["ment_draft"]

    # Banner post-salvare
    if st.session_state["ment_salvat"]:
        st.success(f"✅ Fișa de Mentenanță Preventivă #{st.session_state['ment_id_salvat']} a fost salvată și data următoarei revizii pe utilaj a fost actualizată!")
        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            if st.session_state["ment_pdf_bytes"]:
                st.download_button(
                    label="📥 Descarcă Fișa de Mentenanță Preventivă (PDF)",
                    data=st.session_state["ment_pdf_bytes"],
                    file_name=f"Fisa_Mentenanta_Preventiva_{st.session_state['ment_id_salvat']}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
        with c_dl2:
            if st.button("➕ Completează o fișă nouă", use_container_width=True):
                st.session_state["ment_salvat"] = False
                st.session_state["ment_pdf_bytes"] = None
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

    # Bara de acțiuni rapide (1-Click Audit 4B + Reset)
    top_1, top_2, top_3, top_4 = st.columns([3.2, 1.3, 1.3, 1.2], vertical_alignment="center")
    with top_1:
        st.caption("⚡ **Mod Audit Rapid:** toate punctele pornesc pe **DA**; modifică doar neconformitățile (**NU** / **N/A**) și valorile măsurate.")
    with top_2:
        if st.button("✅ Setează tot DA", use_container_width=True, help="Marchează toate operațiunile active ca DA"):
            _aplica_status_global("DA")
            st.toast("✅ Toate punctele au fost setate pe DA.")
            st.rerun()
    with top_3:
        if st.button("⬜ Setează tot N/A", use_container_width=True, help="Marchează toate operațiunile ca N/A"):
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
        st.info("ℹ️ Selectează clientul și utilajul pentru a încărca capitolele de mentenanță aferente.")
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
    if draft.get("ultima_masina") != sel_masina:
        draft["ultima_masina"] = sel_masina
        draft["producator_model"] = str(masina_obj.get("tip_masina") or "")
        draft["serie_fabricatie"] = str(masina_obj.get("serie") or "")

    # Filtrare dinamică pe sistemele active ale utilajului (Varianta 4A)
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

        tip_int_masina = masina_obj.get("tip_intretinere") or "Trimestrială"
        zile_add = INTERVALE_ZILE.get(tip_int_masina, 90)
        urmatoarea_rev_default = data_interv + timedelta(days=zile_add)
        urmatoarea_revizie = s3.date_input(
            f"Următoarea Revizie ({tip_int_masina})",
            value=urmatoarea_rev_default
        )

    st.markdown("---")
    st.markdown("### 🔍 Verificări Tehnice pe Sisteme")

    sectiuni_active = [
        sec for sec in SECTIONS_MENTENANTA
        if afiseaza_toate_sistemele or (sec["sistem_cod"] in sisteme_utilaj)
    ]

    for sec in sectiuni_active:
        s_key = sec["key"]
        df_sec = st.session_state["ment_dfs"][s_key]
        nr_nu = int((df_sec["Conformitate"] == "NU").sum()) if not df_sec.empty else 0
        badge = f" — ⚠️ {nr_nu} neconformități" if nr_nu > 0 else " — ✅ OK"

        with st.expander(f"{sec['titlu']}{badge}", expanded=(s_key in ("electric_decuplat", "electric_cuplat", "mecanic") or nr_nu > 0)):
            st.caption(f"ℹ️ {sec['nota']}")
            edited_sec = st.data_editor(
                df_sec,
                hide_index=True,
                disabled=["ID", "Operațiune"],
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
        checklist_payload = {}
        for sec in SECTIONS_MENTENANTA:
            s_key = sec["key"]
            is_active = afiseaza_toate_sistemele or (sec["sistem_cod"] in sisteme_utilaj)
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

        fisa_data = {
            "firma_id": firma_obj["id"],
            "masina_id": masina_obj["id"],
            "firma_nume": sel_firma,
            "masina_nume": sel_masina,
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
        pdf_bytes = genereaza_pdf_mentenanta(fisa_data)

        st.session_state["ment_id_salvat"] = new_id
        st.session_state["ment_pdf_bytes"] = pdf_bytes
        st.session_state["ment_salvat"] = True
        _init_sau_reseteaza_ment_draft(tehnician_def, "DA")
        st.rerun()

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
            c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
            with c1:
                st.write(f"**Serie:** {fisa.get('serie_fabricatie') or '-'} | **Ore utilaj:** {fisa.get('ore_functionare') or '-'} | **Tehnician:** {fisa.get('tehnician') or '-'}")
                st.write(f"**Următoarea revizie:** {str(fisa.get('urmatoarea_revizie') or '-')[:10]}")
            with c2:
                chk = fisa.get("checklist_json") or {}
                if isinstance(chk, str):
                    try:
                        chk = json.loads(chk)
                    except Exception:
                        chk = {}
                fisa_pdf_payload = dict(fisa)
                fisa_pdf_payload["checklist_json"] = chk
                pdf_hist = genereaza_pdf_mentenanta(fisa_pdf_payload)
                st.download_button(
                    label="📥 Descarcă PDF",
                    data=pdf_hist,
                    file_name=f"Fisa_Mentenanta_{fid}_{str(fisa.get('masina_nume', '')).replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key=f"dl_ment_hist_{fid}",
                    use_container_width=True
                )
            with c3:
                if st.button("🗑️ Șterge", key=f"del_ment_{fid}", use_container_width=True):
                    MentenantaRepository.delete(fid)
                    st.rerun()
