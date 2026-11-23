# ----------------------------------
# --- pages/fise_mentenanta.py -----
# ----------------------------------

import json
from pathlib import Path
import pandas as pd
import streamlit as st
from config import db_cursor
from repositories.masini_repository import MasiniRepository

FRECVENTE_MENTENANTA = ["Zilnică", "Săptămânală", "Lunară", "Trimestrială", "Anuală"]

CATALOG_OPERATIUNI_INITIAL = [
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea și curățarea ștecherelor, prizelor industriale și conexiunilor principale de alimentare; aplicare spray de contact.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Curățarea tablourilor electrice de praf/șpan, strângerea conexiunilor și a șuruburilor de forță/comandă, aplicare spray de contact.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Decuplarea pe rând a conectorilor priză-ștecher / mufe industriale (Harting, M12), curățare și recuplare securizată.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea rezistențelor electrice de putere și a rezistenței de izolație a circuitelor.", "parametru": "Rezistență izolație", "valoare": "", "um": "MΩ", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea bobinelor motoarelor electrice (simetrie faze) și verificarea periilor / tahogeneratoarelor (unde este cazul).", "parametru": "Rezistență faze L1/L2/L3", "valoare": "", "um": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea absenței infiltrațiilor de lichide (ulei, emulsie de răcire, condens) în zona traseelor și conexiunilor electrice.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea conexiunilor senzorilor (inductivi/optici/capacitivi), a distanțelor de comutare și a integrității cablurilor.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea rezistenței de contact a butoanelor de comandă, E-Stop, releelor și contactoarelor (valoare admisă < 4 Ω).", "parametru": "Rezistență contact", "valoare": "", "um": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea valorilor rezistive ale senzorilor de temperatură (PT100 / PT1000 / termocuple) conform fișei tehnice.", "parametru": "Valoare rezistivă senzor", "valoare": "", "um": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Curățarea filtrelor, ventilatoarelor și căilor de aerisire ale tablourilor electrice și unităților chiller tablou.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificare/înlocuire baterii backup (PLC CPU, memorie CNC, encodere axe) + backup complet program PLC/CNC/HMI.", "parametru": "Tensiune baterie backup", "valoare": "", "um": "V", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Măsurarea tensiunilor de alimentare pe faze și a surselor DC 24V (abatere maximă admisă ±5% față de nominal).", "parametru": "Tensiune alimentare / 24V DC", "valoare": "", "um": "V", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Testarea circuitelor de siguranță: senzori/interlock-uri uși și panouri de acces, bariere optice, butoane E-Stop.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Verificarea funcționării motoarelor electrice, servomotoarelor și convertizoarelor (zgomot, vibrații, temperatură, curenți).", "parametru": "Curent absorbit", "valoare": "", "um": "A", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Verificarea funcționării normale a senzorilor de poziție/presiune/debit și reglarea pragurilor de detecție.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea jocurilor la elementele articulate (cuple cinematice, bucșe, rulmenți, șuruburi cu bile și ghidaje liniare).", "parametru": "Joc axe X/Y/Z", "valoare": "", "um": "mm", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Înlocuirea bucșelor, rulmenților sau cuplelor sferice cu uzură avansată sau durată de viață depășită.", "parametru": "Piesă înlocuită", "valoare": "", "um": "buc", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Înlocuirea simeringurilor, racletorilor de ghidaj și a elementelor de etanșare uzate.", "parametru": "Element etanșare", "valoare": "", "um": "buc", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea tensionării și stării de uzură a curelelor (trapezoidale, dințate) și lanțurilor de transmisie.", "parametru": "Săgeată / Tensiune", "valoare": "", "um": "mm", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea și estimarea jocurilor (backlash) în angrenaje, reductoare și casete de antrenare.", "parametru": "Backlash", "valoare": "", "um": "mm", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea funcționării și eficienței frânelor electromagnetice/mecanice ale motoarelor și axelor verticale.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea și completarea nivelului de ulei în reductoare/cutii de viteze; gresarea punctelor de ungere / pompă ungere centralizată.", "parametru": "Lubrifiant / Cantitate", "valoare": "", "um": "L", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificare arbore principal / spindle (forță strângere portsculă, runout, vibrații) și curățare evacuare șpan.", "parametru": "Forță strângere", "valoare": "", "um": "kN", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Pornirea grupului hidraulic și verificarea nivelului de zgomot, cavitației și vibrațiilor pompei hidraulice.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Verificarea presiunii de lucru pe manometre și a presiunii de preîncărcare a acumulatorilor hidraulici.", "parametru": "Presiune sistem", "valoare": "", "um": "bar", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Verificarea funcționării electrovalvelor/distribuitoarelor (inclusiv acționare manuală) și a curselor/vitezelor cilindrilor.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Inspectarea etanșeității circuitului: strângere racorduri, înlocuire furtunuri sau garnituri cu scurgeri de ulei.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Curățarea jojei magnetice de retur, curățarea/înlocuirea filtrelor de ulei și completarea/schimbul uleiului hidraulic.", "parametru": "Ulei hidraulic / Filtru", "valoare": "", "um": "L", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Verificarea grupului de preparare aer (FRL): presiune de lucru, curățare decantoare condens, verificare nivel ulei ungător.", "parametru": "Presiune aer", "valoare": "", "um": "bar", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Verificarea funcționării distribuitoarelor pneumatice și reglarea curselor/vitezelor cilindrilor din drosele.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Detectarea și remedierea pierderilor de aer (înlocuire furtunuri, fitinguri rapide, garnituri de etanșare).", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Testarea garniturilor interioare ale pistoanelor și distribuitoarelor prin decuplarea traseului nepresurizat (piston vs. distribuitor).", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "5. Vacuum", "operatiune": "Verificarea zgomotului și temperaturii pompei de vacuum în funcționare; inspectare scurgeri ulei de vid.", "parametru": "Temperatură pompă", "valoare": "", "um": "°C", "drive": ""},
    {"sistem": "5. Vacuum", "operatiune": "Cu utilajul oprit: curățare/înlocuire filtre vacuum, curățare traseu în amonte de filtru, verificare/completare ulei de vid.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "5. Vacuum", "operatiune": "Verificarea nivelului de vacuum cu manometrul/vacuummetrul și inspectarea furtunurilor de aspirație și colierelor.", "parametru": "Nivel vacuum", "valoare": "", "um": "mbar", "drive": ""},
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de răcire / emulsie / apă: izolare vane, verificare obturare conducte, curățare filtre/schimbătoare, verificare pompe.", "parametru": "Concentrație emulsie", "valoare": "", "um": "%", "drive": ""},
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de abur: izolare vane manuale, verificare presiune zero, verificare obturare conducte și vane de admisie.", "parametru": "", "valoare": "", "um": "", "drive": ""},
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de afumare / exhaustare: verificare obturare conducte evacuare, curățare depuneri și vane de admisie.", "parametru": "", "valoare": "", "um": "", "drive": ""},
]


def construieste_nume_fisa_masina(denumire_masina: str, tip_masina: str, frecventa: str) -> str:
    parti = [
        str(denumire_masina or "").strip(),
        str(tip_masina or "").strip(),
        str(frecventa or "Lunară").strip(),
    ]
    valide = [p for p in parti if p]
    return " - ".join(valide) if valide else f"Fișă Mentenanță - {str(frecventa or 'Lunară').strip()}"


def _asigura_tabele_fise_si_catalog():
    if st.session_state.get("_fise_tip_db_ok"):
        return
    with db_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS fise_mentenanta_tip_masina (
                id SERIAL PRIMARY KEY,
                denumire_masina VARCHAR(255) NOT NULL DEFAULT '',
                tip_masina VARCHAR(255) NOT NULL DEFAULT '',
                frecventa VARCHAR(50) NOT NULL DEFAULT 'Lunară',
                nume_fisa VARCHAR(255) NOT NULL DEFAULT '',
                pasi_json TEXT NOT NULL DEFAULT '[]',
                actualizat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fisa_tip_masina_frecventa
            ON fise_mentenanta_tip_masina (
                LOWER(TRIM(denumire_masina)),
                LOWER(TRIM(tip_masina)),
                LOWER(TRIM(frecventa))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS catalog_operatiuni_mentenanta (
                id SERIAL PRIMARY KEY,
                sistem VARCHAR(120) NOT NULL DEFAULT 'General',
                operatiune TEXT NOT NULL,
                parametru VARCHAR(255) NOT NULL DEFAULT '',
                valoare VARCHAR(120) NOT NULL DEFAULT '',
                um VARCHAR(50) NOT NULL DEFAULT '',
                drive TEXT NOT NULL DEFAULT '',
                creat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("SELECT COUNT(*) AS cnt FROM catalog_operatiuni_mentenanta")
        row_cnt = c.fetchone()
        cnt = int(row_cnt["cnt"] if isinstance(row_cnt, dict) else row_cnt[0]) if row_cnt else 0
        if cnt == 0:
            for it in CATALOG_OPERATIUNI_INITIAL:
                c.execute("""
                    INSERT INTO catalog_operatiuni_mentenanta
                        (sistem, operatiune, parametru, valoare, um, drive)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    it.get("sistem", "General"),
                    it.get("operatiune", ""),
                    it.get("parametru", ""),
                    it.get("valoare", ""),
                    it.get("um", ""),
                    it.get("drive", ""),
                ))
    st.session_state["_fise_tip_db_ok"] = True


@st.cache_data(ttl=120)
def incarca_catalog_operatiuni_db() -> list[dict]:
    _asigura_tabele_fise_si_catalog()
    with db_cursor() as c:
        c.execute("""
            SELECT id, sistem, operatiune, parametru, valoare, um, drive
            FROM catalog_operatiuni_mentenanta
            ORDER BY id ASC
        """)
        return [dict(r) for r in (c.fetchall() or [])]


def adauga_operatiune_in_catalog_db(
    sistem: str,
    operatiune: str,
    parametru: str = "",
    valoare: str = "",
    um: str = "",
    drive: str = "",
):
    _asigura_tabele_fise_si_catalog()
    op_clean = str(operatiune or "").strip()
    if not op_clean:
        return
    with db_cursor() as c:
        c.execute("""
            INSERT INTO catalog_operatiuni_mentenanta
                (sistem, operatiune, parametru, valoare, um, drive)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            str(sistem or "General").strip() or "General",
            op_clean,
            str(parametru or "").strip(),
            str(valoare or "").strip(),
            str(um or "").strip(),
            str(drive or "").strip(),
        ))
    incarca_catalog_operatiuni_db.clear()


@st.cache_data(ttl=180)
def _incarca_masini_catalog() -> list[dict]:
    masini = MasiniRepository.get_all() or []
    vazute = set()
    rez = []
    for m in masini:
        den = str(m.get("denumire") or "").strip()
        tip = str(m.get("tip_masina") or "").strip()
        if not den and not tip:
            continue
        cheie = (den.lower(), tip.lower())
        if cheie not in vazute:
            vazute.add(cheie)
            rez.append({"denumire_masina": den, "tip_masina": tip})
    rez.sort(key=lambda x: (x["denumire_masina"].lower(), x["tip_masina"].lower()))
    return rez


@st.cache_data(ttl=120)
def _incarca_fise_tip_db() -> list[dict]:
    _asigura_tabele_fise_si_catalog()
    with db_cursor() as c:
        c.execute("""
            SELECT id, denumire_masina, tip_masina, frecventa, nume_fisa, pasi_json, actualizat_la
            FROM fise_mentenanta_tip_masina
            ORDER BY denumire_masina ASC, tip_masina ASC, frecventa ASC
        """)
        rows = [dict(r) for r in (c.fetchall() or [])]
    for r in rows:
        raw = r.get("pasi_json")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                r["pasi"] = parsed if isinstance(parsed, list) else []
            except Exception:
                r["pasi"] = []
        elif isinstance(raw, list):
            r["pasi"] = raw
        else:
            r["pasi"] = []
        if not str(r.get("nume_fisa") or "").strip():
            r["nume_fisa"] = construieste_nume_fisa_masina(
                r.get("denumire_masina") or "",
                r.get("tip_masina") or "",
                r.get("frecventa") or "",
            )
    return rows


def _normalizare_pasi_df(pasi: list[dict]) -> pd.DataFrame:
    if not pasi:
        return pd.DataFrame(columns=[
            "Ordine",
            "Operațiune / Verificare",
            "Denumire parametru",
            "Valoare",
            "UM",
            "Documentație",
        ])
    randuri = []
    for idx, p in enumerate(pasi, start=1):
        if isinstance(p, dict):
            randuri.append({
                "Ordine": int(p.get("Ordine") or p.get("ordine") or idx),
                "Operațiune / Verificare": str(p.get("Operațiune / Verificare") or p.get("operatiune") or p.get("pas") or ""),
                "Denumire parametru": str(p.get("Denumire parametru") or p.get("parametru") or ""),
                "Valoare": str(p.get("Valoare") or p.get("valoare") or ""),
                "UM": str(p.get("UM") or p.get("um") or ""),
                "Documentație": str(p.get("Documentație") or p.get("Documentație Drive") or p.get("documentatie_drive") or ""),
            })
        else:
            randuri.append({
                "Ordine": idx,
                "Operațiune / Verificare": str(p),
                "Denumire parametru": "",
                "Valoare": "",
                "UM": "",
                "Documentație": "",
            })
    return pd.DataFrame(randuri)


def _df_la_pasi(df: pd.DataFrame) -> list[dict]:
    pasi = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        op = str(row.get("Operațiune / Verificare") or "").strip()
        prm = str(row.get("Denumire parametru") or "").strip()
        val = str(row.get("Valoare") or "").strip()
        um = str(row.get("UM") or "").strip()
        doc = str(row.get("Documentație") or "").strip()
        if not op and not prm and not val and not um and not doc:
            continue
        try:
            ord_val = int(row.get("Ordine") or i)
        except Exception:
            ord_val = i
        pasi.append({
            "Ordine": ord_val,
            "Operațiune / Verificare": op,
            "Denumire parametru": prm,
            "Valoare": val,
            "UM": um,
            "Documentație": doc,
        })
    return pasi


def _salveaza_fisa_tip_masina(
    denumire_masina: str,
    tip_masina: str,
    frecventa: str,
    pasi: list[dict],
    nume_fisa: str = "",
):
    _asigura_tabele_fise_si_catalog()
    den_clean = str(denumire_masina or "").strip()
    tip_clean = str(tip_masina or "").strip()
    frec_clean = str(frecventa or "Lunară").strip()
    nume_clean = str(nume_fisa or "").strip() or construieste_nume_fisa_masina(den_clean, tip_clean, frec_clean)
    payload_json = json.dumps(pasi, ensure_ascii=False)

    with db_cursor() as c:
        c.execute("""
            INSERT INTO fise_mentenanta_tip_masina
                (denumire_masina, tip_masina, frecventa, nume_fisa, pasi_json, actualizat_la)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (
                LOWER(TRIM(denumire_masina)),
                LOWER(TRIM(tip_masina)),
                LOWER(TRIM(frecventa))
            )
            DO UPDATE SET
                denumire_masina = EXCLUDED.denumire_masina,
                tip_masina = EXCLUDED.tip_masina,
                nume_fisa = EXCLUDED.nume_fisa,
                pasi_json = EXCLUDED.pasi_json,
                actualizat_la = CURRENT_TIMESTAMP
        """, (den_clean, tip_clean, frec_clean, nume_clean, payload_json))

    _incarca_fise_tip_db.clear()


def _gaseste_fisa_tip(fise: list[dict], denumire_masina: str, tip_masina: str, frecventa: str):
    den_l = denumire_masina.strip().lower()
    tip_l = tip_masina.strip().lower()
    frec_l = frecventa.strip().lower()
    for f in fise:
        if (
            str(f.get("denumire_masina") or "").strip().lower() == den_l
            and str(f.get("tip_masina") or "").strip().lower() == tip_l
            and str(f.get("frecventa") or "").strip().lower() == frec_l
        ):
            return f
    return None


def obtine_fisa_tip_pentru_utilaj(denumire_masina: str, tip_masina: str, frecventa: str) -> dict:
    fise_db = _incarca_fise_tip_db()
    den_clean = str(denumire_masina or "").strip()
    tip_clean = str(tip_masina or "").strip()
    frec_clean = str(frecventa or "Lunară").strip()

    fisa = _gaseste_fisa_tip(fise_db, den_clean, tip_clean, frec_clean)
    if fisa:
        return {
            "denumire_masina": den_clean,
            "tip_masina": tip_clean,
            "frecventa": frec_clean,
            "nume_fisa": fisa.get("nume_fisa") or construieste_nume_fisa_masina(den_clean, tip_clean, frec_clean),
            "pasi": fisa.get("pasi") or [],
        }
    return {
        "denumire_masina": den_clean,
        "tip_masina": tip_clean,
        "frecventa": frec_clean,
        "nume_fisa": construieste_nume_fisa_masina(den_clean, tip_clean, frec_clean),
        "pasi": [],
    }


def _editor_config_fise():
    return {
        "Ordine": st.column_config.NumberColumn("Ordine", width="small", step=1),
        "Operațiune / Verificare": st.column_config.TextColumn("Operațiune / Verificare", width="large"),
        "Denumire parametru": st.column_config.TextColumn("Denumire parametru", width="medium"),
        "Valoare": st.column_config.TextColumn("Valoare", width="small"),
        "UM": st.column_config.TextColumn("UM", width="small"),
        "Documentație": st.column_config.TextColumn("Documentație", width="medium"),
    }


def _salveaza_fisier_doc_local(uploaded_file, prefix_key: str) -> str:
    folder = Path("uploads/documentatie_mentenanta")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    dest = folder / f"{prefix_key}_{safe_name}"
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def _render_controale_editare_operatiuni(state_key_pasi: str, prefix_key: str):
    curente = list(st.session_state.get(state_key_pasi) or [])
    catalog_db = incarca_catalog_operatiuni_db()

    st.markdown("#### 📎 Încarcă / Setează operațiune, denumire parametru, valoare, UM și documentație")
    opt_dict = {"-- Introdu manual / copy-paste --": None}
    for item in catalog_db:
        opt_dict[f"[{item['sistem']}] {item['operatiune']}"] = item

    sel_op_label = st.selectbox(
        "Alege operațiunea din listă (sau introdu manual / copy-paste)",
        options=list(opt_dict.keys()),
        key=f"sel_op_cat_{prefix_key}",
    )
    item_cat = opt_dict.get(sel_op_label)

    c1, c2, c3, c4 = st.columns([2.2, 1.2, 0.9, 0.7])
    with c1:
        op_text = st.text_input(
            "Operațiune / Verificare (manual sau copy-paste)",
            value=(item_cat["operatiune"] if item_cat else ""),
            key=f"inp_op_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()
    with c2:
        param_text = st.text_input(
            "Denumire parametru",
            value=(item_cat.get("parametru") or "" if item_cat else ""),
            placeholder="ex: Tensiune / Piesă",
            key=f"inp_param_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()
    with c3:
        val_text = st.text_input(
            "Valoare",
            value=(item_cat.get("valoare") or "" if item_cat else ""),
            placeholder="ex: 24.0 / 1",
            key=f"inp_val_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()
    with c4:
        um_text = st.text_input(
            "UM",
            value=(item_cat.get("um") or "" if item_cat else ""),
            placeholder="ex: V / buc",
            key=f"inp_um_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()

    d1, d2, d3 = st.columns([1.8, 1.5, 1.2])
    with d1:
        link_drive_nou = st.text_input(
            "Link documentație (opțional)",
            value=(item_cat.get("drive", "") if item_cat else ""),
            placeholder="https://drive.google.com/...",
            key=f"inp_drive_ops_{prefix_key}",
        ).strip()
    with d2:
        fisier_doc = st.file_uploader(
            "Sau încarcă fișier documentație",
            type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
            key=f"up_doc_ops_{prefix_key}",
        )
    with d3:
        salveaza_in_db = st.checkbox(
            "Salvează și în DB",
            value=(item_cat is None),
            key=f"chk_save_db_{prefix_key}",
        )

    if st.button("➕ Adaugă operațiunea în tabel", key=f"btn_add_ops_{prefix_key}"):
        if not op_text:
            st.warning("Selectează sau introdu o operațiune.")
            return
        doc_final = link_drive_nou
        if fisier_doc is not None:
            doc_final = _salveaza_fisier_doc_local(fisier_doc, f"{prefix_key}_op{len(curente)+1}")
        if salveaza_in_db and item_cat is None:
            adauga_operatiune_in_catalog_db(
                sistem="Personalizat",
                operatiune=op_text,
                parametru=param_text,
                valoare=val_text,
                um=um_text,
                drive=doc_final,
            )
        curente.append({
            "Ordine": len(curente) + 1,
            "Operațiune / Verificare": op_text,
            "Denumire parametru": param_text,
            "Valoare": val_text,
            "UM": um_text,
            "Documentație": doc_final,
        })
        st.session_state[state_key_pasi] = curente
        st.toast("✅ Operațiunea a fost adăugată.")
        st.rerun()

    if curente:
        st.markdown("#### 🗑️ Ștergere una sau mai multe operațiuni deodată")
        opt_del = {
            f"{i+1}. {str(p.get('Operațiune / Verificare') or '')[:85]}": i
            for i, p in enumerate(curente)
        }
        de_sters = st.multiselect(
            "Selectează operațiunile de șters",
            options=list(opt_del.keys()),
            key=f"ms_del_ops_{prefix_key}",
        )
        if st.button("🗑️ Șterge operațiunile selectate", key=f"btn_del_ops_{prefix_key}"):
            if not de_sters:
                st.warning("Selectează cel puțin o operațiune.")
            else:
                indici_sters = {opt_del[k] for k in de_sters}
                ramase = []
                for idx_r, item_r in enumerate(curente):
                    if idx_r not in indici_sters:
                        copie = dict(item_r)
                        copie["Ordine"] = len(ramase) + 1
                        ramase.append(copie)
                st.session_state[state_key_pasi] = ramase
                st.toast(f"🗑️ Au fost șterse {len(indici_sters)} operațiuni.")
                st.rerun()


def render_fise_mentenanta():
    st.subheader("📋 Fișe de Mentenanță Tip pe Mașină")
    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    if not is_unlocked:
        st.warning("dacă vrei să editezi fișele de întreținere deblochează sistemul")
        return

    fise_db = _incarca_fise_tip_db()
    catalog_masini = _incarca_masini_catalog()

    tab_edit, tab_lista = st.tabs([
        "🧩 Fișă Tip Mașină (fără client)",
        "📚 Fișe Tip Salvate în DB",
    ])

    with tab_edit:
        opt_preset = ["-- Introdu manual --"] + [
            f"{x['denumire_masina']} | {x['tip_masina']}" for x in catalog_masini
        ]
        sel_preset = st.selectbox("Selectează mașină și tip mașină", options=opt_preset, key="fmp_preset")

        def_den = ""
        def_tip = ""
        if sel_preset != "-- Introdu manual --":
            parti = sel_preset.split(" | ", 1)
            def_den = parti[0].strip()
            def_tip = parti[1].strip() if len(parti) > 1 else ""

        c1, c2, c3 = st.columns(3)
        with c1:
            den_masina = st.text_input("Denumire mașină *", value=def_den, key="fmp_den_masina").strip()
        with c2:
            tip_masina = st.text_input("Tip mașină *", value=def_tip, key="fmp_tip_masina").strip()
        with c3:
            frec_sel = st.selectbox("Tip mentenanță / Frecvență", options=FRECVENTE_MENTENANTA, key="fmp_frec")

        fisa_exs = _gaseste_fisa_tip(fise_db, den_masina, tip_masina, frec_sel)
        nume_auto = construieste_nume_fisa_masina(den_masina, tip_masina, frec_sel)
        nume_fisa_input = st.text_input(
            "Denumire fișă tip",
            value=(fisa_exs.get("nume_fisa") if fisa_exs else "") or nume_auto,
            key=f"fmp_nume_{den_masina.lower()}_{tip_masina.lower()}_{frec_sel.lower()}",
        ).strip() or nume_auto

        state_key_pasi = f"fmp_pasi_{den_masina.lower()}_{tip_masina.lower()}_{frec_sel.lower()}"
        if state_key_pasi not in st.session_state:
            st.session_state[state_key_pasi] = list(fisa_exs["pasi"]) if fisa_exs else []

        _render_controale_editare_operatiuni(
            state_key_pasi=state_key_pasi,
            prefix_key=f"tip_{den_masina.lower()}_{tip_masina.lower()}_{frec_sel.lower()}",
        )

        df_ed = st.data_editor(
            _normalizare_pasi_df(st.session_state[state_key_pasi]),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=_editor_config_fise(),
            key=f"editor_fisa_tip_{state_key_pasi}",
        )

        if st.button("💾 Salvează Fișa Tip în DB", type="primary", key="btn_salveaza_fisa_tip"):
            if not den_masina and not tip_masina:
                st.error("⚠️ Completează Denumirea mașinii și/sau Tipul mașinii.")
            else:
                pasi_noi = _df_la_pasi(df_ed)
                st.session_state[state_key_pasi] = pasi_noi
                _salveaza_fisa_tip_masina(den_masina, tip_masina, frec_sel, pasi_noi, nume_fisa=nume_fisa_input)
                st.success(f"✅ Fișa tip **„{nume_fisa_input}”** a fost salvată în baza de date.")
                st.rerun()

    with tab_lista:
        if not fise_db:
            st.info("Nu există fișe tip salvate în baza de date.")
        else:
            rez = [
                {
                    "Denumire fișă": f.get("nume_fisa"),
                    "Denumire mașină": f.get("denumire_masina") or "-",
                    "Tip mașină": f.get("tip_masina") or "-",
                    "Frecvență": f.get("frecventa"),
                    "Nr. operațiuni": len(f.get("pasi") or []),
                }
                for f in fise_db
            ]
            st.dataframe(pd.DataFrame(rez), hide_index=True, use_container_width=True)