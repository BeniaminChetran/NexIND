# ----------------------------------
# --- pages/fise_mentenanta.py -----
# ----------------------------------

import json
import pandas as pd
import streamlit as st
from config import db_cursor
from repositories.masini_repository import MasiniRepository

FRECVENTE_MENTENANTA = ["Zilnică", "Săptămânală", "Lunară", "Trimestrială", "Anuală"]

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
            help="Liye link-ul complet (https://drive.google.com/...) către documentația operațiunii",
            width="medium",
        ),
    }


def render_fise_mentenanta():
    st.subheader("📋 Fișe Mentenanță Preventivă (Denumire + Tip Mașină + Frecvență)")
    st.caption("Fără legătură cu firma: poți încărca operațiuni, linkuri Google Drive către documentație și salva fișa cu denumirea standard.")

    fise_db = _incarca_fise_din_db()
    catalog_masini = _incarca_catalog_masini_fara_firma()

    tab_gen, tab_proprie, tab_lista = st.tabs([
        "📄 Fișă Generală (pe frecvență)",
        "🧩 Desfășurare / Fișă Proprie Mașină",
        "📚 Toate Fișele Salvate",
    ])

    with tab_gen:
        frec_gen = st.selectbox("Frecvență fișă generală", options=FRECVENTE_MENTENANTA, key="fmp_gen_frec")
        fisa_gen = _gaseste_fisa(fise_db, este_generala=True, frecventa=frec_gen)
        pasi_gen_init = fisa_gen["pasi"] if fisa_gen else FISE_GENERALE_IMPLICITE.get(frec_gen, [])

        df_gen_ed = st.data_editor(
            _normalizare_pasi_df(pasi_gen_init),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=_editor_config_fise(),
            key=f"editor_fisa_gen_{frec_gen}",
        )
        if st.button("💾 Salvează Fișa Generală", type="primary", key="btn_salveaza_fisa_gen"):
            pasi_noi = _df_la_pasi(df_gen_ed)
            _salveaza_fisa(True, "", "", frec_gen, pasi_noi, nume_fisa=construieste_nume_fisa("", "", frec_gen, True))
            st.success(f"✅ Fișa generală ({frec_gen}) a fost salvată.")
            st.rerun()

    with tab_proprie:
        st.markdown("Alege sau introdu **Denumirea mașinii**, **Tipul mașinii** și **Frecvența**, adaugă operațiunile și linkurile Google Drive, apoi salvează.")

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
            st.session_state[state_key_pasi] = fisa_prop["pasi"] if fisa_prop else pasi_gen_sursa

        col_b1, col_b2 = st.columns([1.6, 2.4])
        with col_b1:
            if st.button("📂 Desfășoară din Fișa Generală", key="btn_desfasoara_fisa_gen", use_container_width=True):
                st.session_state[state_key_pasi] = list(pasi_gen_sursa)
                st.rerun()
        with col_b2:
            if fisa_prop:
                st.info(f"✏️ Există deja o fișă proprie salvată: **{nume_fisa_input}**.")
            else:
                st.caption("ℹ️ Se pornește de la fișa generală; la salvare se creează fișa proprie.")

        df_prop_ed = st.data_editor(
            _normalizare_pasi_df(st.session_state[state_key_pasi]),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config=_editor_config_fise(),
            key=f"editor_fisa_prop_{state_key_pasi}",
        )

        if st.button("💾 Salvează Fișa Proprie", type="primary", key="btn_salveaza_fisa_prop"):
            if not den_masina and not tip_masina:
                st.error("⚠️ Completează cel puțin **Denumirea mașinii** sau **Tipul mașinii**.")
            else:
                pasi_prop_noi = _df_la_pasi(df_prop_ed)
                st.session_state[state_key_pasi] = pasi_prop_noi
                _salveaza_fisa(False, den_masina, tip_masina, frec_prop, pasi_prop_noi, nume_fisa=nume_fisa_input)
                st.success(f"✅ Fișa proprie **„{nume_fisa_input}”** a fost salvată.")
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
                    "Nr. pași": len(f.get("pasi") or []),
                }
                for f in fise_db
            ]
            st.dataframe(pd.DataFrame(rezumat), hide_index=True, use_container_width=True)
            