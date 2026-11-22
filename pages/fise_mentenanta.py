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
    {
        "sistem": "Electric",
        "operatiune": "Curățarea tablourilor electrice de praf/șpan, strângerea conexiunilor și a șuruburilor de forță/comandă, aplicare spray de contact.",
        "standard": "Conexiuni ferme, fără praf/șpan",
        "drive": "",
    },
    {
        "sistem": "Electric",
        "operatiune": "Măsurarea tensiunilor de alimentare pe faze și a surselor DC 24V (abatere maximă admisă ±5% față de nominal).",
        "standard": "U nominală (±5%) / 24V DC",
        "drive": "",
    },
    {
        "sistem": "Electric",
        "operatiune": "Testarea circuitelor de siguranță: senzori/interlock-uri uși și panouri de acces, bariere optice, butoane E-Stop.",
        "standard": "Oprire imediată și sigură la activare",
        "drive": "",
    },
    {
        "sistem": "Electric",
        "operatiune": "Verificarea conexiunilor senzorilor (inductivi/optici/capacitivi), a distanțelor de comutare și a integrității cablurilor.",
        "standard": "Semnal stabil, cabluri intacte",
        "drive": "",
    },
    {
        "sistem": "Electric",
        "operatiune": "Curățarea filtrelor, ventilatoarelor și căilor de aerisire ale tablourilor electrice și unităților chiller tablou.",
        "standard": "Flux aer liber, fără depuneri",
        "drive": "",
    },
    {
        "sistem": "Mecanic",
        "operatiune": "Verificarea și completarea nivelului de ulei în reductoare/cutii de viteze; gresarea punctelor de ungere / pompă ungere centralizată.",
        "standard": "Nivel conform reper, lubrifiant prescris",
        "drive": "",
    },
    {
        "sistem": "Mecanic",
        "operatiune": "Verificarea tensionării și stării de uzură a curelelor (trapezoidale, dințate) și lanțurilor de transmisie.",
        "standard": "Tensiune corectă, fără fisuri/uzură",
        "drive": "",
    },
    {
        "sistem": "Mecanic",
        "operatiune": "Verificarea jocurilor la elementele articulate (cuple cinematice, bucșe, rulmenți, șuruburi cu bile și ghidaje liniare).",
        "standard": "Fără jocuri anormale sau zgomote",
        "drive": "",
    },
    {
        "sistem": "Mecanic",
        "operatiune": "Înlocuirea simeringurilor, racletorilor de ghidaj și a elementelor de etanșare uzate.",
        "standard": "Etanșare bună, ghidaje curate",
        "drive": "",
    },
    {
        "sistem": "Hidraulic",
        "operatiune": "Verificarea presiunii de lucru pe manometre și a presiunii de preîncărcare a acumulatorilor hidraulici.",
        "standard": "Presiune în plaja nominală (bar)",
        "drive": "",
    },
    {
        "sistem": "Hidraulic",
        "operatiune": "Inspectarea etanșeității circuitului: strângere racorduri, înlocuire furtunuri sau garnituri cu scurgeri de ulei.",
        "standard": "Fără scurgeri sau pierderi vizibile",
        "drive": "",
    },
    {
        "sistem": "Hidraulic",
        "operatiune": "Curățarea jojei magnetice de retur, curățarea/înlocuirea filtrelor de ulei și completarea/schimbul uleiului hidraulic.",
        "standard": "Filtre curate, nivel ulei conform",
        "drive": "",
    },
    {
        "sistem": "Pneumatic",
        "operatiune": "Verificarea grupului de preparare aer (FRL): presiune de lucru, curățare decantoare condens, verificare nivel ulei ungător.",
        "standard": "P_aer nominală, condens evacuat",
        "drive": "",
    },
    {
        "sistem": "Pneumatic",
        "operatiune": "Detectarea și remedierea pierderilor de aer (înlocuire furtunuri, fitinguri rapide, garnituri de etanșare).",
        "standard": "Fără pierderi audibile/vizibile de aer",
        "drive": "",
    },
    {
        "sistem": "Auxiliare",
        "operatiune": "Instalații de răcire / emulsie / apă: izolare vane, verificare obturare conducte, curățare filtre/schimbătoare, verificare pompe.",
        "standard": "Circulație normală, concentrație/debit ok",
        "drive": "",
    },
]

FISE_GENERALE_IMPLICITE = {
    "Zilnică": [
        {
            "Ordine": 1,
            "Operațiune / Verificare": "Curățare zonă de lucru și senzori",
            "Standard / Observații": "Fără resturi sau praf",
            "Documentație Drive": "",
        },
        {
            "Ordine": 2,
            "Operațiune / Verificare": "Verificare presiune aer / nivel lichide",
            "Standard / Observații": "În parametri normali",
            "Documentație Drive": "",
        },
        {
            "Ordine": 3,
            "Operațiune / Verificare": "Control zgomote, vibrații sau scurgeri",
            "Standard / Observații": "Fără anomalii",
            "Documentație Drive": "",
        },
    ],
    "Săptămânală": [
        {
            "Ordine": 1,
            "Operațiune / Verificare": "Curățare filtre și ventilatoare răcire",
            "Standard / Observații": "Flux aer liber",
            "Documentație Drive": "",
        },
        {
            "Ordine": 2,
            "Operațiune / Verificare": "Verificare strângere conexiuni și ghidaje",
            "Standard / Observații": "Fără jocuri",
            "Documentație Drive": "",
        },
    ],
    "Lunară": [
        {
            "Ordine": 1,
            "Operațiune / Verificare": "Lubrifiere puncte de ungere conform manual",
            "Standard / Observații": "Vaselină / ulei prescris",
            "Documentație Drive": "",
        },
        {
            "Ordine": 2,
            "Operațiune / Verificare": "Verificare cabluri, senzori și siguranțe",
            "Standard / Observații": "Izolație intactă",
            "Documentație Drive": "",
        },
    ],
    "Trimestrială": [
        {
            "Ordine": 1,
            "Operațiune / Verificare": "Calibrare / verificare aliniere și parametri",
            "Standard / Observații": "În toleranțe",
            "Documentație Drive": "",
        },
        {
            "Ordine": 2,
            "Operațiune / Verificare": "Revizie elemente de uzură și curele/furtunuri",
            "Standard / Observații": "Înlocuire dacă e cazul",
            "Documentație Drive": "",
        },
    ],
    "Anuală": [
        {
            "Ordine": 1,
            "Operațiune / Verificare": "Revizie generală mecanică și electrică",
            "Standard / Observații": "Verificare completă",
            "Documentație Drive": "",
        },
        {
            "Ordine": 2,
            "Operațiune / Verificare": "Înlocuire consumabile / lichide conform plan",
            "Standard / Observații": "Conform carte tehnică",
            "Documentație Drive": "",
        },
    ],
}


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
        return pd.DataFrame([{
            "Ordine": 1,
            "Operațiune / Verificare": "",
            "Standard / Observații": "",
            "Documentație Drive": "",
        }])
    randuri = []
    for idx, p in enumerate(pasi, start=1):
        if isinstance(p, dict):
            doc_link = (
                p.get("Documentație Drive")
                or p.get("Documentatie Drive")
                or p.get("documentatie_drive")
                or p.get("drive_url")
                or ""
            )
            randuri.append({
                "Ordine": int(p.get("Ordine") or p.get("ordine") or idx),
                "Operațiune / Verificare": str(p.get("Operațiune / Verificare") or p.get("operatiune") or p.get("pas") or ""),
                "Standard / Observații": str(p.get("Standard / Observații") or p.get("observatii") or ""),
                "Documentație Drive": str(doc_link or "").strip(),
            })
        else:
            randuri.append({
                "Ordine": idx,
                "Operațiune / Verificare": str(p),
                "Standard / Observații": "",
                "Documentație Drive": "",
            })
    return pd.DataFrame(randuri)


def _df_la_pasi(df: pd.DataFrame) -> list[dict]:
    pasi = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        op = str(row.get("Operațiune / Verificare") or "").strip()
        obs = str(row.get("Standard / Observații") or "").strip()
        doc_link = str(row.get("Documentație Drive") or "").strip()
        if not op and not obs and not doc_link:
            continue
        try:
            ord_val = int(row.get("Ordine") or i)
        except Exception:
            ord_val = i
        pasi.append({
            "Ordine": ord_val,
            "Operațiune / Verificare": op,
            "Standard / Observații": obs,
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
    """
    Returnează fișa activă pentru (denumire_masina, tip_masina, frecventa) — fără firmă:
    1. Fișă proprie salvată pe denumire_masina + tip_masina + frecventa
    2. Fișă generală pe frecventa
    3. Fișă implicită pe frecventa
    """
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
    pasi_gen = (fisa_gen.get("pasi") if fisa_gen else None) or FISE_GENERALE_IMPLICITE.get(frec_clean, [])
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
        "Standard / Observații": st.column_config.TextColumn("Standard / Observații", width="medium"),
        "Documentație Drive": st.column_config.TextColumn(
            "Documentație Drive",
            help="Link-ul Google Drive (https://drive.google.com/...) sau calea documentației operațiunii",
            width="medium",
        ),
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

    st.markdown("#### ➕ Adaugă operațiuni din listă")
    opt_dict = {
        f"[{item['sistem']}] {item['operatiune'][:90]}": item
        for item in CATALOG_OPERATIUNI_PREDEFINITE
    }
    selectate = st.multiselect(
        "Alege una sau mai multe operațiuni din listă",
        options=list(opt_dict.keys()),
        key=f"ms_ops_{prefix_key}",
    )
    link_drive_nou = st.text_input(
        "Link Google Drive pentru operațiunile adăugate (opțional)",
        placeholder="https://drive.google.com/...",
        key=f"inp_drive_ops_{prefix_key}",
    ).strip()

    if st.button("📥 Adaugă operațiunile selectate în fișă", key=f"btn_add_ops_{prefix_key}"):
        if not selectate:
            st.warning("Selectează cel puțin o operațiune din listă.")
            return
        urm_ord = len(curente) + 1
        for label in selectate:
            it = opt_dict[label]
            curente.append({
                "Ordine": urm_ord,
                "Operațiune / Verificare": it["operatiune"],
                "Standard / Observații": it["standard"],
                "Documentație Drive": link_drive_nou or it.get("drive", ""),
            })
            urm_ord += 1
        st.session_state[state_key_pasi] = curente
        st.toast(f"✅ S-au adăugat {len(selectate)} operațiuni în fișă.")
        st.rerun()

    if curente:
        st.markdown("#### 📎 Încarcă / Setează documentația pe operațiune")
        opt_idx = {
            f"{i+1}. {str(p.get('Operațiune / Verificare') or '')[:75]}": i
            for i, p in enumerate(curente)
        }
        idx_sel = st.selectbox(
            "Selectează operațiunea pentru documentație",
            options=list(opt_idx.keys()),
            key=f"sel_doc_op_{prefix_key}",
        )
        pos = opt_idx[idx_sel]
        doc_curent = str(curente[pos].get("Documentație Drive") or "")

        cd1, cd2 = st.columns([2.2, 1.8])
        with cd1:
            link_manual = st.text_input(
                "Link Google Drive operațiune",
                value=doc_curent,
                placeholder="https://drive.google.com/...",
                key=f"inp_doc_op_{prefix_key}_{pos}",
            ).strip()
        with cd2:
            fisier_doc = st.file_uploader(
                "Sau încarcă fișier documentație",
                type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
                key=f"up_doc_op_{prefix_key}_{pos}",
            )

        if st.button("💾 Aplică documentația pe operațiune", key=f"btn_apply_doc_{prefix_key}_{pos}"):
            val_final = link_manual
            if fisier_doc is not None:
                val_final = _salveaza_fisier_documentatie_local(fisier_doc, f"{prefix_key}_op{pos+1}")
            curente[pos]["Documentație Drive"] = val_final
            st.session_state[state_key_pasi] = curente
            st.toast("✅ Documentația a fost actualizată pe operațiune.")
            st.rerun()

        st.markdown("#### 🗑️ Ștergere multiplă operațiuni")
        opt_del = {
            f"{i+1}. {str(p.get('Operațiune / Verificare') or '')[:80]}": i
            for i, p in enumerate(curente)
        }
        de_sters = st.multiselect(
            "Selectează una sau mai multe operațiuni de șters",
            options=list(opt_del.keys()),
            key=f"ms_del_ops_{prefix_key}",
        )
        if st.button("🗑️ Șterge operațiunile selectate", key=f"btn_del_ops_{prefix_key}"):
            if not de_sters:
                st.warning("Selectează cel puțin o operațiune de șters.")
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

    st.caption("🔓 **Sistem deblocat:** poți încărca operațiuni dintr-o listă, atașa documentație pe fiecare operațiune, șterge mai multe operațiuni deodată și salva fișa pe Denumire mașină + Tip mașină + Frecvență.")

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
        fisa_gen_sursa = _gaseste_fisa(fise_db, este_generala=True, frecventa=frec_prop)
        pasi_gen_sursa = fisa_gen_sursa["pasi"] if fisa_gen_sursa else FISE_GENERALE_IMPLICITE.get(frec_prop, [])

        nume_auto = construieste_nume_fisa(den_masina, tip_masina, frec_prop, este_generala=False)
        nume_init = (fisa_prop.get("nume_fisa") if fisa_prop else "") or nume_auto
        nume_fisa_input = st.text_input(
            "Denumire fișă (Denumire mașină + Tip mașină + Frecvență)",
            value=nume_init,
            key=f"fmp_nume_fisa_{den_masina.lower()}_{tip_masina.lower()}_{frec_prop.lower()}",
        ).strip() or nume_auto

        state_key_pasi = f"fmp_pasi_lucru_{den_masina.lower()}_{tip_masina.lower()}_{frec_prop.lower()}"
        if state_key_pasi not in st.session_state:
            st.session_state[state_key_pasi] = list(fisa_prop["pasi"]) if fisa_prop else list(pasi_gen_sursa)

        col_b1, col_b2 = st.columns([1.6, 2.4])
        with col_b1:
            if st.button("📂 Încarcă din Fișa Generală", key="btn_desfasoara_fisa_gen", use_container_width=True):
                st.session_state[state_key_pasi] = list(pasi_gen_sursa)
                st.rerun()
        with col_b2:
            if fisa_prop:
                st.info(f"✏️ Fișă proprie existentă: **{nume_fisa_input}**.")
            else:
                st.caption("ℹ️ Se pornește de la fișa generală; la salvare se creează fișa proprie.")

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
        pasi_gen_init = fisa_gen["pasi"] if fisa_gen else FISE_GENERALE_IMPLICITE.get(frec_gen, [])

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