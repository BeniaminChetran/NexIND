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

CATALOG_OPERATIUNI_PREDEFINITE = [
    # 1.A. SISTEM ELECTRIC - DECUPLAT (LOTO)
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea și curățarea ștecherelor, prizelor industriale și conexiunilor principale de alimentare; aplicare spray de contact.", "standard": "Conexiuni ferme, fără praf/șpan", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Curățarea tablourilor electrice de praf/șpan, strângerea conexiunilor și a șuruburilor de forță/comandă, aplicare spray de contact.", "standard": "Tablou curat, strângeri ferme", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Decuplarea pe rând a conectorilor priză-ștecher / mufe industriale (Harting, M12), curățare și recuplare securizată.", "standard": "Conectori curați, fixați", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea rezistențelor electrice de putere și a rezistenței de izolație a circuitelor.", "standard": "Izolație conform normativ", "parametru": "R_iz", "valoare": "MΩ", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea bobinelor motoarelor electrice (simetrie faze) și verificarea periilor / tahogeneratoarelor (unde este cazul).", "standard": "Faze echilibrate", "parametru": "L1/L2/L3", "valoare": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea absenței infiltrațiilor de lichide (ulei, emulsie de răcire, condens) în zona traseelor și conexiunilor electrice.", "standard": "Fără infiltrații", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificarea conexiunilor senzorilor (inductivi/optici/capacitivi), a distanțelor de comutare și a integrității cablurilor.", "standard": "Semnal stabil, cabluri intacte", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea rezistenței de contact a butoanelor de comandă, E-Stop, releelor și contactoarelor (valoare admisă < 4 Ω).", "standard": "Sub 4 Ω", "parametru": "R_contact", "valoare": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Măsurarea valorilor rezistive ale senzorilor de temperatură (PT100 / PT1000 / termocuple) conform fișei tehnice.", "standard": "Conform tabel temperatură", "parametru": "R_senzor", "valoare": "Ω", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Curățarea filtrelor, ventilatoarelor și căilor de aerisire ale tablourilor electrice și unităților chiller tablou.", "standard": "Flux aer liber, fără depuneri", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.A Electric (LOTO)", "operatiune": "Verificare/înlocuire baterii backup (PLC CPU, memorie CNC, encodere axe) + backup complet program PLC/CNC/HMI.", "standard": "Backup salvat, baterie OK", "parametru": "Tensiune baterie", "valoare": "V", "drive": ""},

    # 1.B. SISTEM ELECTRIC - CUPLAT
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Măsurarea tensiunilor de alimentare pe faze și a surselor DC 24V (abatere maximă admisă ±5% față de nominal).", "standard": "U nominală (±5%) / 24V DC", "parametru": "U / 24V DC", "valoare": "V", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Testarea circuitelor de siguranță: senzori/interlock-uri uși și panouri de acces, bariere optice, butoane E-Stop.", "standard": "Oprire imediată și sigură la activare", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Verificarea funcționării motoarelor electrice, servomotoarelor și convertizoarelor (zgomot, vibrații, temperatură, curenți).", "standard": "Funcționare normală", "parametru": "I_abs", "valoare": "A", "drive": ""},
    {"sistem": "1.B Electric (Sub tensiune)", "operatiune": "Verificarea funcționării normale a senzorilor de poziție/presiune/debit și reglarea pragurilor de detecție.", "standard": "Comutare corectă", "parametru": "", "valoare": "", "drive": ""},

    # 2. SISTEM MECANIC
    {"sistem": "2. Mecanic", "operatiune": "Verificarea jocurilor la elementele articulate (cuple cinematice, bucșe, rulmenți, șuruburi cu bile și ghidaje liniare).", "standard": "Fără jocuri anormale sau zgomote", "parametru": "Joc axe X/Y/Z", "valoare": "mm", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Înlocuirea bucșelor, rulmenților sau cuplelor sferice cu uzură avansată sau durată de viață depășită.", "standard": "Piese noi montate corect", "parametru": "Piesă înlocuită", "valoare": "buc", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Înlocuirea simeringurilor, racletorilor de ghidaj și a elementelor de etanșare uzate.", "standard": "Etanșare bună, ghidaje curate", "parametru": "Element etanșare", "valoare": "buc", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea tensionării și stării de uzură a curelelor (trapezoidale, dințate) și lanțurilor de transmisie.", "standard": "Tensiune corectă, fără fisuri/uzură", "parametru": "Tensiune / Săgeată", "valoare": "mm / Hz", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea și estimarea jocurilor (backlash) în angrenaje, reductoare și casete de antrenare.", "standard": "În limitele admise", "parametru": "Backlash", "valoare": "mm", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea funcționării și eficienței frânelor electromagnetice/mecanice ale motoarelor și axelor verticale.", "standard": "Frânare sigură fără alunecare", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificarea și completarea nivelului de ulei în reductoare/cutii de viteze; gresarea punctelor de ungere / pompă ungere centralizată.", "standard": "Nivel conform reper, lubrifiant prescris", "parametru": "Lubrifiant / Nivel", "valoare": "OK", "drive": ""},
    {"sistem": "2. Mecanic", "operatiune": "Verificare arbore principal / spindle (forță strângere portsculă, runout, vibrații) și curățare evacuare șpan.", "standard": "Parametri nominali, curat", "parametru": "Forță strângere", "valoare": "kN", "drive": ""},

    # 3. SISTEM HIDRAULIC
    {"sistem": "3. Hidraulic", "operatiune": "Pornirea grupului hidraulic și verificarea nivelului de zgomot, cavitației și vibrațiilor pompei hidraulice.", "standard": "Fără cavitație sau vibrații excesive", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Verificarea presiunii de lucru pe manometre și a presiunii de preîncărcare a acumulatorilor hidraulici.", "standard": "Presiune în plaja nominală", "parametru": "P_sistem", "valoare": "bar", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Verificarea funcționării electrovalvelor/distribuitoarelor (inclusiv acționare manuală) și a curselor/vitezelor cilindrilor.", "standard": "Curse complete și fluide", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Inspectarea etanșeității circuitului: strângere racorduri, înlocuire furtunuri sau garnituri cu scurgeri de ulei.", "standard": "Fără scurgeri sau pierderi vizibile", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "3. Hidraulic", "operatiune": "Curățarea jojei magnetice de retur, curățarea/înlocuirea filtrelor de ulei și completarea/schimbul uleiului hidraulic.", "standard": "Filtre curate, nivel ulei conform", "parametru": "Tip ulei / Filtru", "valoare": "L / buc", "drive": ""},

    # 4. SISTEM PNEUMATIC
    {"sistem": "4. Pneumatic", "operatiune": "Verificarea grupului de preparare aer (FRL): presiune de lucru, curățare decantoare condens, verificare nivel ulei ungător.", "standard": "P_aer nominală, condens evacuat", "parametru": "P_aer", "valoare": "bar", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Verificarea funcționării distribuitoarelor pneumatice și reglarea curselor/vitezelor cilindrilor din drosele.", "standard": "Acționare rapidă și precisă", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Detectarea și remedierea pierderilor de aer (înlocuire furtunuri, fitinguri rapide, garnituri de etanșare).", "standard": "Fără pierderi audibile/vizibile de aer", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "4. Pneumatic", "operatiune": "Testarea garniturilor interioare ale pistoanelor și distribuitoarelor prin decuplarea traseului nepresurizat (piston vs. distribuitor).", "standard": "Fără scăpări interne", "parametru": "", "valoare": "", "drive": ""},

    # 5. SISTEM VACUUM
    {"sistem": "5. Vacuum", "operatiune": "Verificarea zgomotului și temperaturii pompei de vacuum în funcționare; inspectare scurgeri ulei de vid.", "standard": "Temperatură și zgomot normale", "parametru": "Temp pompă", "valoare": "°C", "drive": ""},
    {"sistem": "5. Vacuum", "operatiune": "Cu utilajul oprit: curățare/înlocuire filtre vacuum, curățare traseu în amonte de filtru, verificare/completare ulei de vid.", "standard": "Filtre și trasee curate", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "5. Vacuum", "operatiune": "Verificarea nivelului de vacuum cu manometrul/vacuummetrul și inspectarea furtunurilor de aspirație și colierelor.", "standard": "Nivel vacuum conform", "parametru": "Vid", "valoare": "mbar", "drive": ""},

    # 6. INSTALAȚII AUXILIARE
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de răcire / emulsie / apă: izolare vane, verificare obturare conducte, curățare filtre/schimbătoare, verificare pompe.", "standard": "Circulație normală, concentrație/debit ok", "parametru": "Concentrație emulsie", "valoare": "%", "drive": ""},
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de abur: izolare vane manuale, verificare presiune zero, verificare obturare conducte și vane de admisie.", "standard": "Vane și conducte fără obturări", "parametru": "", "valoare": "", "drive": ""},
    {"sistem": "6. Auxiliare", "operatiune": "Instalații de afumare / exhaustare: verificare obturare conducte evacuare, curățare depuneri și vane de admisie.", "standard": "Evacuare liberă, fără depuneri", "parametru": "", "valoare": "", "drive": ""},
]

FISE_GENERALE_IMPLICITE = {f: [] for f in FRECVENTE_MENTENANTA}


def construieste_nume_fisa(
    denumire_masina: str,
    tip_masina: str,
    frecventa: str,
    este_generala: bool = False,
) -> str:
    frec = str(frecventa or "Lunară").strip()
    if este_generala:
        return f"Fișă Generală + {frec}"
    parti = [
        str(denumire_masina or "").strip(),
        str(tip_masina or "").strip(),
        frec,
    ]
    parti_valide = [p for p in parti if p]
    return " + ".join(parti_valide) if parti_valide else f"Fișă Mentenanță + {frec}"


def _asigura_tabela_fise():
    if st.session_state.get("_fise_mp_tabela_verificata"):
        return
    with db_cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS fise_mentenanta_preventiva (
                id SERIAL PRIMARY KEY,
                este_generala BOOLEAN NOT NULL DEFAULT FALSE,
                denumire_masina VARCHAR(255) NOT NULL DEFAULT '',
                tip_masina VARCHAR(255) NOT NULL DEFAULT '',
                frecventa VARCHAR(50) NOT NULL,
                nume_fisa VARCHAR(255) NOT NULL DEFAULT '',
                pasi_json TEXT NOT NULL DEFAULT '[]',
                actualizat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            ALTER TABLE fise_mentenanta_preventiva
            ADD COLUMN IF NOT EXISTS nume_fisa VARCHAR(255) NOT NULL DEFAULT ''
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_fisa_mentenanta_cheie
            ON fise_mentenanta_preventiva (
                este_generala,
                LOWER(TRIM(denumire_masina)),
                LOWER(TRIM(tip_masina)),
                LOWER(TRIM(frecventa))
            )
        """)
    st.session_state["_fise_mp_tabela_verificata"] = True


@st.cache_data(ttl=180)
def _incarca_catalog_masini_fara_firma() -> list[dict]:
    masini = MasiniRepository.get_all() or []
    vazute = set()
    rezultat = []
    for m in masini:
        den = str(m.get("denumire") or "").strip()
        tip = str(m.get("tip_masina") or "").strip()
        if not den and not tip:
            continue
        cheie = (den.lower(), tip.lower())
        if cheie not in vazute:
            vazute.add(cheie)
            rezultat.append({"denumire_masina": den, "tip_masina": tip})
    rezultat.sort(key=lambda x: (x["denumire_masina"].lower(), x["tip_masina"].lower()))
    return rezultat


@st.cache_data(ttl=120)
def _incarca_fise_din_db() -> list[dict]:
    _asigura_tabela_fise()
    with db_cursor() as c:
        c.execute("""
            SELECT id, este_generala, denumire_masina, tip_masina, frecventa, nume_fisa, pasi_json, actualizat_la
            FROM fise_mentenanta_preventiva
            ORDER BY este_generala DESC, denumire_masina ASC, tip_masina ASC, frecventa ASC
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
            r["nume_fisa"] = construieste_nume_fisa(
                r.get("denumire_masina") or "",
                r.get("tip_masina") or "",
                r.get("frecventa") or "",
                este_generala=bool(r.get("este_generala")),
            )
    return rows


def _normalizare_pasi_df(pasi: list[dict]) -> pd.DataFrame:
    if not pasi:
        return pd.DataFrame(columns=[
            "Ordine",
            "Operațiune / Verificare",
            "Piese / Parametri Măsurați",
            "Valori / Observații",
            "Documentație",
        ])
    randuri = []
    for idx, p in enumerate(pasi, start=1):
        if isinstance(p, dict):
            doc_link = (
                p.get("Documentație")
                or p.get("Documentație Drive")
                or p.get("Documentatie Drive")
                or p.get("documentatie_drive")
                or p.get("drive_url")
                or ""
            )
            param_val = (
                p.get("Piese / Parametri Măsurați")
                or p.get("Parametru")
                or p.get("parametru")
                or p.get("Standard / Observații")
                or ""
            )
            val_obs = (
                p.get("Valori / Observații")
                or p.get("Valoare")
                or p.get("valoare")
                or p.get("observatii")
                or ""
            )
            randuri.append({
                "Ordine": int(p.get("Ordine") or p.get("ordine") or idx),
                "Operațiune / Verificare": str(p.get("Operațiune / Verificare") or p.get("operatiune") or p.get("pas") or ""),
                "Piese / Parametri Măsurați": str(param_val or ""),
                "Valori / Observații": str(val_obs or ""),
                "Documentație": str(doc_link or "").strip(),
            })
        else:
            randuri.append({
                "Ordine": idx,
                "Operațiune / Verificare": str(p),
                "Piese / Parametri Măsurați": "",
                "Valori / Observații": "",
                "Documentație": "",
            })
    return pd.DataFrame(randuri)


def _df_la_pasi(df: pd.DataFrame) -> list[dict]:
    pasi = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        op = str(row.get("Operațiune / Verificare") or "").strip()
        prm = str(row.get("Piese / Parametri Măsurați") or "").strip()
        val = str(row.get("Valori / Observații") or "").strip()
        doc_link = str(row.get("Documentație") or row.get("Documentație Drive") or "").strip()
        if not op and not prm and not val and not doc_link:
            continue
        try:
            ord_val = int(row.get("Ordine") or i)
        except Exception:
            ord_val = i
        pasi.append({
            "Ordine": ord_val,
            "Operațiune / Verificare": op,
            "Piese / Parametri Măsurați": prm,
            "Valori / Observații": val,
            "Standard / Observații": f"{prm}: {val}".strip(": ") if (prm or val) else "",
            "Documentație": doc_link,
            "Documentație Drive": doc_link,
        })
    return pasi


def _salveaza_fisa(
    este_generala: bool,
    denumire_masina: str,
    tip_masina: str,
    frecventa: str,
    pasi: list[dict],
    nume_fisa: str = "",
):
    _asigura_tabela_fise()
    den_clean = "" if este_generala else str(denumire_masina or "").strip()
    tip_clean = "" if este_generala else str(tip_masina or "").strip()
    frec_clean = str(frecventa or "Lunară").strip()
    nume_clean = str(nume_fisa or "").strip() or construieste_nume_fisa(
        den_clean, tip_clean, frec_clean, este_generala=este_generala
    )
    payload_json = json.dumps(pasi, ensure_ascii=False)

    with db_cursor() as c:
        c.execute("""
            INSERT INTO fise_mentenanta_preventiva
                (este_generala, denumire_masina, tip_masina, frecventa, nume_fisa, pasi_json, actualizat_la)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (
                este_generala,
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
        """, (bool(este_generala), den_clean, tip_clean, frec_clean, nume_clean, payload_json))

    _incarca_fise_din_db.clear()


def _gaseste_fisa(
    fise: list[dict],
    este_generala: bool,
    denumire_masina: str = "",
    tip_masina: str = "",
    frecventa: str = "",
):
    frec_l = frecventa.strip().lower()
    if este_generala:
        for f in fise:
            if bool(f.get("este_generala")) and str(f.get("frecventa") or "").strip().lower() == frec_l:
                return f
        return None

    den_l = denumire_masina.strip().lower()
    tip_l = tip_masina.strip().lower()
    for f in fise:
        if (
            not bool(f.get("este_generala"))
            and str(f.get("denumire_masina") or "").strip().lower() == den_l
            and str(f.get("tip_masina") or "").strip().lower() == tip_l
            and str(f.get("frecventa") or "").strip().lower() == frec_l
        ):
            return f
    return None


def obtine_fisa_pentru_utilaj(denumire_masina: str, tip_masina: str, frecventa: str) -> dict:
    fise_db = _incarca_fise_din_db()
    frec_clean = str(frecventa or "Lunară").strip()
    den_clean = str(denumire_masina or "").strip()
    tip_clean = str(tip_masina or "").strip()

    fisa_prop = _gaseste_fisa(
        fise_db,
        este_generala=False,
        denumire_masina=den_clean,
        tip_masina=tip_clean,
        frecventa=frec_clean,
    )
    if fisa_prop:
        return {
            "sursa": "proprie",
            "frecventa": frec_clean,
            "denumire_masina": den_clean,
            "tip_masina": tip_clean,
            "nume_fisa": fisa_prop.get("nume_fisa") or construieste_nume_fisa(den_clean, tip_clean, frec_clean, False),
            "pasi": fisa_prop.get("pasi") or [],
        }

    fisa_gen = _gaseste_fisa(fise_db, este_generala=True, frecventa=frec_clean)
    pasi_gen = (fisa_gen.get("pasi") if fisa_gen else None) or []
    return {
        "sursa": "generala",
        "frecventa": frec_clean,
        "denumire_masina": den_clean,
        "tip_masina": tip_clean,
        "nume_fisa": (fisa_gen.get("nume_fisa") if fisa_gen else None) or construieste_nume_fisa(den_clean, tip_clean, frec_clean, False),
        "pasi": pasi_gen,
    }


def _editor_config_fise():
    return {
        "Ordine": st.column_config.NumberColumn("Ordine", width="small", step=1),
        "Operațiune / Verificare": st.column_config.TextColumn("Operațiune / Verificare", width="large"),
        "Piese / Parametri Măsurați": st.column_config.TextColumn("Piese / Parametri Măsurați", width="medium"),
        "Valori / Observații": st.column_config.TextColumn("Valori / Observații", width="medium"),
        "Documentație": st.column_config.TextColumn("Documentație", width="medium"),
    }


def _salveaza_fisier_documentatie_local(uploaded_file, prefix_key: str) -> str:
    folder = Path("uploads/documentatie_mentenanta")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    dest = folder / f"{prefix_key}_{safe_name}"
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def _render_controale_editare_operatiuni(state_key_pasi: str, prefix_key: str):
    curente = list(st.session_state.get(state_key_pasi) or [])

    st.markdown("#### ➕ Încarcă / Setează operațiune și documentație")
    opt_dict = {
        f"-- Introdu manual / copy-paste --": None,
    }
    for item in CATALOG_OPERATIUNI_PREDEFINITE:
        lbl = f"[{item['sistem']}] {item['operatiune']}"
        opt_dict[lbl] = item

    sel_op_label = st.selectbox(
        "Alege operațiunea din listă (sau lasă manual / copy-paste)",
        options=list(opt_dict.keys()),
        key=f"sel_op_cat_{prefix_key}",
    )
    item_cat = opt_dict.get(sel_op_label)

    c1, c2, c3 = st.columns([2.4, 1.3, 1.0])
    with c1:
        op_text = st.text_input(
            "Operațiune / Verificare (poți scrie sau lipi cu copy-paste)",
            value=(item_cat["operatiune"] if item_cat else ""),
            key=f"inp_op_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()
    with c2:
        param_text = st.text_input(
            "Piesă / Parametru măsurat",
            value=(item_cat.get("parametru") or item_cat.get("standard") or "" if item_cat else ""),
            placeholder="ex: Rulment SKF / Tensiune 24V",
            key=f"inp_param_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()
    with c3:
        val_text = st.text_input(
            "Valoare / Observații",
            value=(item_cat.get("valoare") or "" if item_cat else ""),
            placeholder="ex: 24.1 V / 1 buc",
            key=f"inp_val_txt_{prefix_key}_{sel_op_label[:25]}",
        ).strip()

    d1, d2 = st.columns([2.2, 1.8])
    with d1:
        link_drive_nou = st.text_input(
            "Link Google Drive / Documentație (opțional)",
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

    if st.button("📥 Adaugă operațiunea în tabel", key=f"btn_add_ops_{prefix_key}"):
        if not op_text:
            st.warning("Introdu sau selectează o operațiune.")
            return
        doc_final = link_drive_nou
        if fisier_doc is not None:
            doc_final = _salveaza_fisier_documentatie_local(fisier_doc, f"{prefix_key}_op{len(curente)+1}")
        curente.append({
            "Ordine": len(curente) + 1,
            "Operațiune / Verificare": op_text,
            "Piese / Parametri Măsurați": param_text,
            "Valori / Observații": val_text,
            "Standard / Observații": f"{param_text}: {val_text}".strip(": ") if (param_text or val_text) else "",
            "Documentație": doc_final,
            "Documentație Drive": doc_final,
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
    st.subheader("📋 Creare & Administrare Fișe de Mentenanță Preventivă")
    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    if not is_unlocked:
        st.warning(
            "🔒 **Sistemul este blocat.** Pentru a vedea și edita listele de operațiuni de mentenanță, "
            "deblochează sistemul introducând parola (din **SistemAdmin → Deblocare**)."
        )
        return

    st.caption("🔓 **Sistem deblocat:** alege operațiuni din listă (sau introdu manual / copy-paste), atașează documentație, completează piese/parametri/valori și șterge una sau mai multe operațiuni deodată.")

    fise_db = _incarca_fise_din_db()
    catalog_masini = _incarca_catalog_masini_fara_firma()

    tab_proprie, tab_gen, tab_lista = st.tabs([
        "🧩 Creare / Editare Fișă Mașină",
        "📄 Fișă Generală (pe frecvență)",
        "📚 Toate Fișele Salvate",
    ])

    with tab_proprie:
        optiuni_preset = ["-- Introdu manual --"] + [
            f"{x['denumire_masina']} | {x['tip_masina']}" for x in catalog_masini
        ]
        sel_preset = st.selectbox("Precompletare din utilajele existente (fără firmă)", options=optiuni_preset, key="fmp_preset")

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
            frec_prop = st.selectbox("Tip întreținere / Frecvență", options=FRECVENTE_MENTENANTA, key="fmp_prop_frec")

        fisa_prop = _gaseste_fisa(
            fise_db,
            este_generala=False,
            denumire_masina=den_masina,
            tip_masina=tip_masina,
            frecventa=frec_prop,
        )

        nume_auto = construieste_nume_fisa(den_masina, tip_masina, frec_prop, este_generala=False)
        nume_init = (fisa_prop.get("nume_fisa") if fisa_prop else "") or nume_auto
        nume_fisa_input = st.text_input(
            "Denumire fișă (Denumire mașină + Tip mașină + Frecvență)",
            value=nume_init,
            key=f"fmp_nume_fisa_{den_masina.lower()}_{tip_masina.lower()}_{frec_prop.lower()}",
        ).strip() or nume_auto

        state_key_pasi = f"fmp_pasi_lucru_{den_masina.lower()}_{tip_masina.lower()}_{frec_prop.lower()}"
        if state_key_pasi not in st.session_state:
            st.session_state[state_key_pasi] = list(fisa_prop["pasi"]) if fisa_prop else []

        _render_controale_editare_operatiuni(
            state_key_pasi=state_key_pasi,
            prefix_key=f"prop_{den_masina.lower()}_{tip_masina.lower()}_{frec_prop.lower()}",
        )

        df_prop_ed = st.data_editor(
            _normalizare_pasi_df(st.session_state[state_key_pasi]),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=_editor_config_fise(),
            key=f"editor_fisa_prop_{state_key_pasi}",
        )

        if st.button("💾 Salvează Fișa de Mentenanță", type="primary", key="btn_salveaza_fisa_prop"):
            if not den_masina and not tip_masina:
                st.error("⚠️ Completează cel puțin **Denumirea mașinii** sau **Tipul mașinii**.")
            else:
                pasi_prop_noi = _df_la_pasi(df_prop_ed)
                st.session_state[state_key_pasi] = pasi_prop_noi
                _salveaza_fisa(False, den_masina, tip_masina, frec_prop, pasi_prop_noi, nume_fisa=nume_fisa_input)
                st.success(f"✅ Fișa **„{nume_fisa_input}”** a fost salvată.")
                st.rerun()

    with tab_gen:
        frec_gen = st.selectbox("Frecvență fișă generală", options=FRECVENTE_MENTENANTA, key="fmp_gen_frec")
        fisa_gen = _gaseste_fisa(fise_db, este_generala=True, frecventa=frec_gen)
        pasi_gen_init = fisa_gen["pasi"] if fisa_gen else []

        state_key_gen = f"fmp_pasi_gen_{frec_gen.lower()}"
        if state_key_gen not in st.session_state:
            st.session_state[state_key_gen] = list(pasi_gen_init)

        _render_controale_editare_operatiuni(
            state_key_pasi=state_key_gen,
            prefix_key=f"gen_{frec_gen.lower()}",
        )

        df_gen_ed = st.data_editor(
            _normalizare_pasi_df(st.session_state[state_key_gen]),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=_editor_config_fise(),
            key=f"editor_fisa_gen_{frec_gen}",
        )
        if st.button("💾 Salvează Fișa Generală", type="primary", key="btn_salveaza_fisa_gen"):
            pasi_noi = _df_la_pasi(df_gen_ed)
            st.session_state[state_key_gen] = pasi_noi
            _salveaza_fisa(True, "", "", frec_gen, pasi_noi, nume_fisa=construieste_nume_fisa("", "", frec_gen, True))
            st.success(f"✅ Fișa generală ({frec_gen}) a fost salvată.")
            st.rerun()

    with tab_lista:
        if not fise_db:
            st.info("Nu există încă fișe salvate în baza de date.")
        else:
            rezumat = [
                {
                    "Denumire fișă": f.get("nume_fisa") or construieste_nume_fisa(
                        f.get("denumire_masina") or "",
                        f.get("tip_masina") or "",
                        f.get("frecventa") or "",
                        este_generala=bool(f.get("este_generala")),
                    ),
                    "Tip fișă": "Generală" if f.get("este_generala") else "Proprie",
                    "Denumire mașină": "-" if f.get("este_generala") else (f.get("denumire_masina") or "-"),
                    "Tip mașină": "-" if f.get("este_generala") else (f.get("tip_masina") or "-"),
                    "Frecvență": f.get("frecventa"),
                    "Nr. operațiuni": len(f.get("pasi") or []),
                }
                for f in fise_db
            ]
            st.dataframe(pd.DataFrame(rezumat), hide_index=True, use_container_width=True)