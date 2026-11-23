# ----------------------------------
# --- pages/fise_mentenanta.py -----
# ----------------------------------

import json
from pathlib import Path
import pandas as pd
import streamlit as st
from config import db_cursor
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository

FRECVENTE_MENTENANTA = ["Zilnică", "Săptămânală", "Lunară", "Trimestrială", "Anuală"]


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
                piese_json TEXT NOT NULL DEFAULT '[]',
                consumabile_json TEXT NOT NULL DEFAULT '[]',
                documentatii_json TEXT NOT NULL DEFAULT '[]',
                creat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS piese_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS consumabile_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS documentatii_json TEXT NOT NULL DEFAULT '[]'")
    st.session_state["_fise_tip_db_ok"] = True


def _parse_json_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def formateaza_piese_text(piese: list[dict]) -> str:
    linii = []
    for p in _parse_json_list(piese):
        if not isinstance(p, dict):
            continue
        den = str(p.get("piesa") or "").strip()
        if not den:
            continue
        cant = str(p.get("cantitate") or "").strip()
        um = str(p.get("um") or "buc").strip()
        loc = str(p.get("loc_utilizare") or "").strip()
        bucata = f"{den} - {cant} {um}".strip() if cant else den
        if loc:
            bucata += f" ({loc})"
        linii.append(bucata)
    return "; ".join(linii)


def formateaza_consumabile_text(consumabile: list[dict]) -> str:
    linii = []
    for cm in _parse_json_list(consumabile):
        if not isinstance(cm, dict):
            continue
        den = str(cm.get("material") or "").strip()
        if not den:
            continue
        cant = str(cm.get("cantitate") or "").strip()
        um = str(cm.get("um") or "").strip()
        loc = str(cm.get("loc_utilizare") or "").strip()
        cant_txt = f"{cant}{um}" if (cant and um in ("ml", "g", "kg", "l", "L")) else f"{cant} {um}".strip()
        bucata = f"{den} - {cant_txt}" if cant_txt else den
        if loc:
            bucata += f" [{loc}]"
        linii.append(bucata)
    return "; ".join(linii)


def formateaza_documentatii_text(documentatii: list[dict]) -> str:
    linii = []
    for idx, d in enumerate(_parse_json_list(documentatii), start=1):
        if isinstance(d, dict):
            titlu = str(d.get("titlu") or f"Link {idx}").strip()
            url = str(d.get("url") or "").strip()
            if url:
                linii.append(f"{titlu}: {url}")
        elif isinstance(d, str) and d.strip():
            linii.append(d.strip())
    return " | ".join(linii)


@st.cache_data(ttl=120)
def incarca_catalog_operatiuni_db() -> list[dict]:
    _asigura_tabele_fise_si_catalog()
    with db_cursor() as c:
        c.execute("""
            SELECT id, sistem, operatiune, parametru, valoare, um,
                   piese_json, consumabile_json, documentatii_json
            FROM catalog_operatiuni_mentenanta
            ORDER BY sistem ASC, id ASC
        """)
        rows = [dict(r) for r in (c.fetchall() or [])]
    for r in rows:
        r["piese"] = _parse_json_list(r.get("piese_json"))
        r["consumabile"] = _parse_json_list(r.get("consumabile_json"))
        r["documentatii"] = _parse_json_list(r.get("documentatii_json"))
    return rows


def adauga_operatiune_in_catalog_db(
    sistem: str,
    operatiune: str,
    parametru: str = "",
    valoare: str = "",
    um: str = "",
    piese: list[dict] | None = None,
    consumabile: list[dict] | None = None,
    documentatii: list[dict] | None = None,
) -> int | None:
    _asigura_tabele_fise_si_catalog()
    op_clean = str(operatiune or "").strip()
    if not op_clean:
        return None
    with db_cursor() as c:
        c.execute("""
            INSERT INTO catalog_operatiuni_mentenanta
                (sistem, operatiune, parametru, valoare, um, piese_json, consumabile_json, documentatii_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            str(sistem or "General").strip() or "General",
            op_clean,
            str(parametru or "").strip(),
            str(valoare or "").strip(),
            str(um or "").strip(),
            json.dumps(piese or [], ensure_ascii=False),
            json.dumps(consumabile or [], ensure_ascii=False),
            json.dumps(documentatii or [], ensure_ascii=False),
        ))
        row = c.fetchone()
        new_id = int(row["id"] if isinstance(row, dict) else row[0]) if row else None
    incarca_catalog_operatiuni_db.clear()
    return new_id


def actualizeaza_operatiune_in_catalog_db(
    op_id: int,
    sistem: str,
    operatiune: str,
    parametru: str = "",
    valoare: str = "",
    um: str = "",
    piese: list[dict] | None = None,
    consumabile: list[dict] | None = None,
    documentatii: list[dict] | None = None,
):
    _asigura_tabele_fise_si_catalog()
    with db_cursor() as c:
        c.execute("""
            UPDATE catalog_operatiuni_mentenanta
            SET sistem = %s,
                operatiune = %s,
                parametru = %s,
                valoare = %s,
                um = %s,
                piese_json = %s,
                consumabile_json = %s,
                documentatii_json = %s
            WHERE id = %s
        """, (
            str(sistem or "General").strip() or "General",
            str(operatiune or "").strip(),
            str(parametru or "").strip(),
            str(valoare or "").strip(),
            str(um or "").strip(),
            json.dumps(piese or [], ensure_ascii=False),
            json.dumps(consumabile or [], ensure_ascii=False),
            json.dumps(documentatii or [], ensure_ascii=False),
            int(op_id),
        ))
    incarca_catalog_operatiuni_db.clear()


def sterge_operatiune_din_catalog_db(op_id: int):
    _asigura_tabele_fise_si_catalog()
    with db_cursor() as c:
        c.execute("DELETE FROM catalog_operatiuni_mentenanta WHERE id = %s", (int(op_id),))
    incarca_catalog_operatiuni_db.clear()


def _salveaza_fisier_doc_local(uploaded_file, prefix_key: str) -> str:
    folder = Path("uploads/documentatie_mentenanta")
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    dest = folder / f"{prefix_key}_{safe_name}"
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def render_builder_resurse_operatiune(
    prefix_key: str,
    piese_init: list[dict] | None = None,
    consumabile_init: list[dict] | None = None,
    documentatii_init: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Construiește interactiv pentru o operațiune:
    - Piese necesare (multiple, inclusiv mai multe de același fel, cu loc utilizare)
    - Materiale consumabile (multiple, ex: WD40 - 50ml, pini 0.75 - 20buc, cu locurile unde se utilizează)
    - Link-uri / fișiere de documentație multiple (pentru sub-operațiunile executate simultan)
    """
    k_piese = f"res_piese_{prefix_key}"
    k_cons = f"res_cons_{prefix_key}"
    k_docs = f"res_docs_{prefix_key}"

    if k_piese not in st.session_state:
        st.session_state[k_piese] = list(_parse_json_list(piese_init))
    if k_cons not in st.session_state:
        st.session_state[k_cons] = list(_parse_json_list(consumabile_init))
    if k_docs not in st.session_state:
        st.session_state[k_docs] = list(_parse_json_list(documentatii_init))

    piese_db = PieseRepository.get_all() or []
    opt_piese_catalog = ["-- Introdu piesă manual --"] + [
        f"{p['denumire']}" + (f" ({p['cod_producator']})" if p.get("cod_producator") else "")
        for p in piese_db
    ]

    with st.expander("🔩 Piese necesare (poți adăuga mai multe / același tip de mai multe ori)", expanded=bool(st.session_state[k_piese])):
        cp1, cp2 = st.columns([2, 2])
        with cp1:
            sel_piesa_cat = st.selectbox(
                "Alege piesa din catalog (sau manual)",
                options=opt_piese_catalog,
                key=f"sel_p_{prefix_key}",
            )
        with cp2:
            piesa_manual = st.text_input(
                "Denumire piesă",
                value="" if sel_piesa_cat == "-- Introdu piesă manual --" else sel_piesa_cat,
                placeholder="ex: Rulment 6205 2RS / Senzor inductiv M12",
                key=f"inp_p_den_{prefix_key}",
            ).strip()

        cp3, cp4, cp5 = st.columns([1, 1, 2.2])
        with cp3:
            cant_piesa = st.number_input("Cantitate", min_value=0.1, step=1.0, value=1.0, key=f"inp_p_cant_{prefix_key}")
        with cp4:
            um_piesa = st.text_input("UM", value="buc", key=f"inp_p_um_{prefix_key}").strip() or "buc"
        with cp5:
            loc_piesa = st.text_input(
                "Loc montaj / Ansamblu (opțional)",
                placeholder="ex: Ax X - lagăr față",
                key=f"inp_p_loc_{prefix_key}",
            ).strip()

        if st.button("➕ Adaugă piesă la operațiune", key=f"btn_add_p_{prefix_key}"):
            if not piesa_manual:
                st.warning("Introdu sau selectează o piesă.")
            else:
                cant_fmt = int(cant_piesa) if float(cant_piesa).is_integer() else round(float(cant_piesa), 2)
                st.session_state[k_piese].append({
                    "piesa": piesa_manual,
                    "cantitate": cant_fmt,
                    "um": um_piesa,
                    "loc_utilizare": loc_piesa,
                })
                st.rerun()

        if st.session_state[k_piese]:
            for idx_p, item_p in enumerate(st.session_state[k_piese]):
                col_pt, col_pd = st.columns([4.5, 0.7], vertical_alignment="center")
                loc_str = f" — *{item_p['loc_utilizare']}*" if item_p.get("loc_utilizare") else ""
                col_pt.markdown(f"- **{item_p['piesa']}** — `{item_p['cantitate']} {item_p.get('um', 'buc')}`{loc_str}")
                if col_pd.button("🗑️", key=f"del_p_{prefix_key}_{idx_p}"):
                    st.session_state[k_piese].pop(idx_p)
                    st.rerun()

    with st.expander("🧴 Materiale consumabile & locuri de utilizare (ex: WD40 - 50ml, pini 0.75 - 20buc)", expanded=bool(st.session_state[k_cons])):
        cc1, cc2, cc3, cc4 = st.columns([1.8, 0.9, 0.8, 2.2])
        with cc1:
            mat_den = st.text_input(
                "Material consumabil",
                placeholder="ex: WD40 / Pini 0.75 / Vaselină Litiu",
                key=f"inp_c_den_{prefix_key}",
            ).strip()
        with cc2:
            mat_cant = st.number_input("Cantitate", min_value=0.1, step=1.0, value=50.0, key=f"inp_c_cant_{prefix_key}")
        with cc3:
            mat_um = st.text_input("UM", value="ml", placeholder="ml / buc / g", key=f"inp_c_um_{prefix_key}").strip() or "buc"
        with cc4:
            mat_loc = st.text_input(
                "Locul unde se utilizează",
                placeholder="ex: Se curăță jiglorul 4 de la ansamblul cccc",
                key=f"inp_c_loc_{prefix_key}",
            ).strip()

        if st.button("➕ Adaugă consumabil la operațiune", key=f"btn_add_c_{prefix_key}"):
            if not mat_den:
                st.warning("Introdu denumirea materialului consumabil.")
            else:
                cant_fmt = int(mat_cant) if float(mat_cant).is_integer() else round(float(mat_cant), 2)
                st.session_state[k_cons].append({
                    "material": mat_den,
                    "cantitate": cant_fmt,
                    "um": mat_um,
                    "loc_utilizare": mat_loc,
                })
                st.rerun()

        if st.session_state[k_cons]:
            for idx_c, item_c in enumerate(st.session_state[k_cons]):
                col_ct, col_cd = st.columns([4.5, 0.7], vertical_alignment="center")
                loc_c = f" → **{item_c['loc_utilizare']}**" if item_c.get("loc_utilizare") else ""
                col_ct.markdown(f"- **{item_c['material']}** — `{item_c['cantitate']} {item_c.get('um', '')}`{loc_c}")
                if col_cd.button("🗑️", key=f"del_c_{prefix_key}_{idx_c}"):
                    st.session_state[k_cons].pop(idx_c)
                    st.rerun()

    with st.expander("🔗 Link-uri / Fișiere documentație multiple (pentru sub-operațiuni executate deodată)", expanded=bool(st.session_state[k_docs])):
        cd1, cd2, cd3 = st.columns([1.8, 2.2, 1.5])
        with cd1:
            doc_titlu = st.text_input(
                "Etichetă / Sub-operațiune",
                placeholder="ex: Demontarea axului axei X",
                key=f"inp_d_titlu_{prefix_key}",
            ).strip()
        with cd2:
            doc_url = st.text_input(
                "Link documentație (Google Drive / URL)",
                placeholder="https://drive.google.com/...",
                key=f"inp_d_url_{prefix_key}",
            ).strip()
        with cd3:
            doc_file = st.file_uploader(
                "Sau încarcă fișier",
                type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
                key=f"up_d_file_{prefix_key}",
            )

        if st.button("➕ Adaugă link / documentație", key=f"btn_add_d_{prefix_key}"):
            final_url = doc_url
            if doc_file is not None:
                final_url = _salveaza_fisier_doc_local(doc_file, f"{prefix_key}_doc{len(st.session_state[k_docs])+1}")
            if not final_url:
                st.warning("Introdu un link sau încarcă un fișier de documentație.")
            else:
                titlu_final = doc_titlu or f"Documentație #{len(st.session_state[k_docs]) + 1}"
                st.session_state[k_docs].append({
                    "titlu": titlu_final,
                    "url": final_url,
                })
                st.rerun()

        if st.session_state[k_docs]:
            for idx_d, item_d in enumerate(st.session_state[k_docs]):
                col_dt, col_dd = st.columns([4.5, 0.7], vertical_alignment="center")
                col_dt.markdown(f"- **{item_d.get('titlu', 'Link')}**: `{item_d.get('url', '')}`")
                if col_dd.button("🗑️", key=f"del_d_{prefix_key}_{idx_d}"):
                    st.session_state[k_docs].pop(idx_d)
                    st.rerun()

    return (
        list(st.session_state[k_piese]),
        list(st.session_state[k_cons]),
        list(st.session_state[k_docs]),
    )


def reseteaza_builder_resurse_operatiune(prefix_key: str):
    for pfx in ("res_piese_", "res_cons_", "res_docs_"):
        st.session_state.pop(f"{pfx}{prefix_key}", None)


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
        r["pasi"] = _parse_json_list(r.get("pasi_json"))
        if not str(r.get("nume_fisa") or "").strip():
            r["nume_fisa"] = construieste_nume_fisa_masina(
                r.get("denumire_masina") or "",
                r.get("tip_masina") or "",
                r.get("frecventa") or "",
            )
    return rows


def _normalizare_pasi_df(pasi: list[dict]) -> pd.DataFrame:
    cols = [
        "Ordine",
        "Operațiune / Verificare",
        "Denumire parametru",
        "Valoare",
        "UM",
        "Piese necesare",
        "Materiale consumabile",
        "Documentație",
    ]
    if not pasi:
        return pd.DataFrame(columns=cols)
    randuri = []
    for idx, p in enumerate(pasi, start=1):
        if isinstance(p, dict):
            piese_txt = p.get("Piese necesare") or formateaza_piese_text(p.get("piese") or [])
            cons_txt = p.get("Materiale consumabile") or formateaza_consumabile_text(p.get("consumabile") or [])
            doc_txt = p.get("Documentație") or formateaza_documentatii_text(p.get("documentatii") or [])
            randuri.append({
                "Ordine": int(p.get("Ordine") or p.get("ordine") or idx),
                "Operațiune / Verificare": str(p.get("Operațiune / Verificare") or p.get("operatiune") or ""),
                "Denumire parametru": str(p.get("Denumire parametru") or p.get("parametru") or ""),
                "Valoare": str(p.get("Valoare") or p.get("valoare") or ""),
                "UM": str(p.get("UM") or p.get("um") or ""),
                "Piese necesare": str(piese_txt or ""),
                "Materiale consumabile": str(cons_txt or ""),
                "Documentație": str(doc_txt or ""),
            })
    return pd.DataFrame(randuri) if randuri else pd.DataFrame(columns=cols)


def _df_la_pasi(df: pd.DataFrame, pasi_exist: list[dict]) -> list[dict]:
    pasi = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        op = str(row.get("Operațiune / Verificare") or "").strip()
        prm = str(row.get("Denumire parametru") or "").strip()
        val = str(row.get("Valoare") or "").strip()
        um = str(row.get("UM") or "").strip()
        piese_txt = str(row.get("Piese necesare") or "").strip()
        cons_txt = str(row.get("Materiale consumabile") or "").strip()
        doc_txt = str(row.get("Documentație") or "").strip()
        if not any([op, prm, val, um, piese_txt, cons_txt, doc_txt]):
            continue
        try:
            ord_val = int(row.get("Ordine") or i)
        except Exception:
            ord_val = i
        vechi = pasi_exist[i - 1] if (i - 1) < len(pasi_exist) and isinstance(pasi_exist[i - 1], dict) else {}
        pasi.append({
            "Ordine": ord_val,
            "Operațiune / Verificare": op,
            "Denumire parametru": prm,
            "Valoare": val,
            "UM": um,
            "Piese necesare": piese_txt,
            "Materiale consumabile": cons_txt,
            "Documentație": doc_txt,
            "piese": vechi.get("piese") or [],
            "consumabile": vechi.get("consumabile") or [],
            "documentatii": vechi.get("documentatii") or [],
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


def _render_sectiune_editare_catalog_db():
    st.markdown("### ⚙️ Editare Catalog Operațiuni în Baza de Date")
    st.caption("Tot ce modifici aici se salvează direct în DB și este disponibil imediat și de pe telefon, la client.")

    catalog_db = incarca_catalog_operatiuni_db()
    opt_cat = {"➕ Adaugă operațiune nouă în catalog": None}
    for it in catalog_db:
        opt_cat[f"#{it['id']} | [{it['sistem']}] {it['operatiune'][:75]}"] = it

    sel_lbl = st.selectbox(
        "Selectează o operațiune din DB pentru editare / ștergere (sau creează una nouă)",
        options=list(opt_cat.keys()),
        key="cat_db_sel_item",
    )
    item_sel = opt_cat[sel_lbl]
    edit_id = item_sel["id"] if item_sel else "nou"
    builder_key = f"cat_db_edit_{edit_id}"

    c1, c2 = st.columns([1.2, 2.8])
    with c1:
        sistem_val = st.text_input(
            "Capitol / Sistem",
            value=(item_sel.get("sistem") if item_sel else "General"),
            key=f"cat_db_sys_{edit_id}",
        ).strip()
    with c2:
        op_val = st.text_input(
            "Denumire operațiune / verificare *",
            value=(item_sel.get("operatiune") if item_sel else ""),
            key=f"cat_db_op_{edit_id}",
        ).strip()

    p1, p2, p3 = st.columns([2, 1, 1])
    with p1:
        prm_val = st.text_input(
            "Denumire parametru implicit (opțional)",
            value=(item_sel.get("parametru") if item_sel else ""),
            key=f"cat_db_prm_{edit_id}",
        ).strip()
    with p2:
        val_val = st.text_input(
            "Valoare implicită",
            value=(item_sel.get("valoare") if item_sel else ""),
            key=f"cat_db_val_{edit_id}",
        ).strip()
    with p3:
        um_val = st.text_input(
            "UM",
            value=(item_sel.get("um") if item_sel else ""),
            key=f"cat_db_um_{edit_id}",
        ).strip()

    piese_list, cons_list, docs_list = render_builder_resurse_operatiune(
        prefix_key=builder_key,
        piese_init=(item_sel.get("piese") if item_sel else []),
        consumabile_init=(item_sel.get("consumabile") if item_sel else []),
        documentatii_init=(item_sel.get("documentatii") if item_sel else []),
    )

    b1, b2 = st.columns([2, 1])
    with b1:
        if st.button("💾 Salvează în Catalogul DB", type="primary", use_container_width=True, key=f"cat_db_save_{edit_id}"):
            if not op_val:
                st.error("⚠️ Completează denumirea operațiunii.")
            else:
                if item_sel:
                    actualizeaza_operatiune_in_catalog_db(
                        op_id=item_sel["id"],
                        sistem=sistem_val,
                        operatiune=op_val,
                        parametru=prm_val,
                        valoare=val_val,
                        um=um_val,
                        piese=piese_list,
                        consumabile=cons_list,
                        documentatii=docs_list,
                    )
                    st.success(f"✅ Operațiunea #{item_sel['id']} a fost actualizată în DB.")
                else:
                    new_id = adauga_operatiune_in_catalog_db(
                        sistem=sistem_val,
                        operatiune=op_val,
                        parametru=prm_val,
                        valoare=val_val,
                        um=um_val,
                        piese=piese_list,
                        consumabile=cons_list,
                        documentatii=docs_list,
                    )
                    reseteaza_builder_resurse_operatiune(builder_key)
                    st.success(f"✅ Operațiunea #{new_id} a fost adăugată în DB.")
                st.rerun()
    with b2:
        if item_sel and st.button("🗑️ Șterge din Catalog DB", use_container_width=True, key=f"cat_db_del_{edit_id}"):
            sterge_operatiune_din_catalog_db(item_sel["id"])
            reseteaza_builder_resurse_operatiune(builder_key)
            st.toast(f"🗑️ Operațiunea #{item_sel['id']} a fost ștearsă.")
            st.rerun()

    if catalog_db:
        st.markdown("#### 📋 Lista completă din Catalogul DB")
        df_cat = pd.DataFrame([
            {
                "ID": x["id"],
                "Sistem": x["sistem"],
                "Operațiune": x["operatiune"],
                "Parametru": x.get("parametru") or "",
                "Valoare": x.get("valoare") or "",
                "UM": x.get("um") or "",
                "Piese necesare": formateaza_piese_text(x.get("piese") or []),
                "Materiale consumabile": formateaza_consumabile_text(x.get("consumabile") or []),
                "Documentație": formateaza_documentatii_text(x.get("documentatii") or []),
            }
            for x in catalog_db
        ])
        st.dataframe(df_cat, hide_index=True, use_container_width=True)


def render_fise_mentenanta():
    st.subheader("📋 Catalog Operațiuni & Fișe Tip de Mentenanță (DB)")
    is_unlocked = bool(st.session_state.get("is_unlocked", False))

    if not is_unlocked:
        st.warning("dacă vrei să editezi fișele de întreținere deblochează sistemul")
        return

    tab_catalog, tab_fise_tip, tab_lista = st.tabs([
        "⚙️ Editare Catalog Operațiuni (DB)",
        "🧩 Fișă Tip Mașină (fără client)",
        "📚 Fișe Tip Salvate în DB",
    ])

    with tab_catalog:
        _render_sectiune_editare_catalog_db()

    with tab_fise_tip:
        fise_db = _incarca_fise_tip_db()
        catalog_masini = _incarca_masini_catalog()
        catalog_db = incarca_catalog_operatiuni_db()

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

        st.markdown("#### 📎 Încarcă / Setează operațiune în fișa tip")
        opt_op_cat = {"-- Introdu manual / copy-paste --": None}
        for it in catalog_db:
            opt_op_cat[f"[{it['sistem']}] {it['operatiune']}"] = it

        sel_op_lbl = st.selectbox(
            "Alege operațiunea din Catalogul DB (sau introdu manual / copy-paste)",
            options=list(opt_op_cat.keys()),
            key=f"fmp_sel_op_{state_key_pasi}",
        )
        it_cat = opt_op_cat[sel_op_lbl]
        b_key = f"fmp_res_{state_key_pasi}_{it_cat['id'] if it_cat else 'man'}"

        o1, o2, o3, o4 = st.columns([2.2, 1.2, 0.9, 0.7])
        with o1:
            op_txt = st.text_input(
                "Operațiune / Verificare",
                value=(it_cat["operatiune"] if it_cat else ""),
                key=f"fmp_op_txt_{b_key}",
            ).strip()
        with o2:
            prm_txt = st.text_input(
                "Denumire parametru",
                value=(it_cat.get("parametru") or "" if it_cat else ""),
                key=f"fmp_prm_txt_{b_key}",
            ).strip()
        with o3:
            val_txt = st.text_input(
                "Valoare",
                value=(it_cat.get("valoare") or "" if it_cat else ""),
                key=f"fmp_val_txt_{b_key}",
            ).strip()
        with o4:
            um_txt = st.text_input(
                "UM",
                value=(it_cat.get("um") or "" if it_cat else ""),
                key=f"fmp_um_txt_{b_key}",
            ).strip()

        piese_op, cons_op, docs_op = render_builder_resurse_operatiune(
            prefix_key=b_key,
            piese_init=(it_cat.get("piese") if it_cat else []),
            consumabile_init=(it_cat.get("consumabile") if it_cat else []),
            documentatii_init=(it_cat.get("documentatii") if it_cat else []),
        )

        salveaza_cat = st.checkbox("Salvează această operațiune și în Catalogul DB", value=(it_cat is None), key=f"fmp_chk_cat_{b_key}")
        if st.button("➕ Adaugă operațiunea în fișa tip", key=f"fmp_btn_add_{b_key}"):
            if not op_txt:
                st.warning("Introdu sau selectează o operațiune.")
            else:
                if salveaza_cat and it_cat is None:
                    adauga_operatiune_in_catalog_db(
                        sistem="General",
                        operatiune=op_txt,
                        parametru=prm_txt,
                        valoare=val_txt,
                        um=um_txt,
                        piese=piese_op,
                        consumabile=cons_op,
                        documentatii=docs_op,
                    )
                st.session_state[state_key_pasi].append({
                    "Ordine": len(st.session_state[state_key_pasi]) + 1,
                    "Operațiune / Verificare": op_txt,
                    "Denumire parametru": prm_txt,
                    "Valoare": val_txt,
                    "UM": um_txt,
                    "Piese necesare": formateaza_piese_text(piese_op),
                    "Materiale consumabile": formateaza_consumabile_text(cons_op),
                    "Documentație": formateaza_documentatii_text(docs_op),
                    "piese": piese_op,
                    "consumabile": cons_op,
                    "documentatii": docs_op,
                })
                reseteaza_builder_resurse_operatiune(b_key)
                st.rerun()

        if st.session_state[state_key_pasi]:
            opt_del = {
                f"{i+1}. {str(p.get('Operațiune / Verificare') or '')[:80]}": i
                for i, p in enumerate(st.session_state[state_key_pasi])
            }
            de_sters = st.multiselect("Selectează operațiuni de șters din fișă", options=list(opt_del.keys()), key=f"fmp_ms_del_{state_key_pasi}")
            if st.button("🗑️ Șterge operațiunile selectate", key=f"fmp_btn_del_{state_key_pasi}") and de_sters:
                indici = {opt_del[k] for k in de_sters}
                ramase = []
                for idx_r, it_r in enumerate(st.session_state[state_key_pasi]):
                    if idx_r not in indici:
                        cp = dict(it_r)
                        cp["Ordine"] = len(ramase) + 1
                        ramase.append(cp)
                st.session_state[state_key_pasi] = ramase
                st.rerun()

        df_ed = st.data_editor(
            _normalizare_pasi_df(st.session_state[state_key_pasi]),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"editor_fisa_tip_{state_key_pasi}",
        )

        if st.button("💾 Salvează Fișa Tip în DB", type="primary", key="btn_salveaza_fisa_tip"):
            if not den_masina and not tip_masina:
                st.error("⚠️ Completează Denumirea mașinii și/sau Tipul mașinii.")
            else:
                pasi_noi = _df_la_pasi(df_ed, st.session_state[state_key_pasi])
                st.session_state[state_key_pasi] = pasi_noi
                _salveaza_fisa_tip_masina(den_masina, tip_masina, frec_sel, pasi_noi, nume_fisa=nume_fisa_input)
                st.success(f"✅ Fișa tip **„{nume_fisa_input}”** a fost salvată în DB.")
                st.rerun()

    with tab_lista:
        fise_db = _incarca_fise_tip_db()
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