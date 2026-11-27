# ----------------------------------
# --- pages/fise_mentenanta.py -----
# ----------------------------------

import json
import re
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


@st.cache_resource
def _asigura_tabele_fise_si_catalog() -> bool:
    """Rulează DDL-ul o singură dată pe durata de viață a procesului serverului."""
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
                parametri_json TEXT NOT NULL DEFAULT '[]',
                piese_json TEXT NOT NULL DEFAULT '[]',
                consumabile_json TEXT NOT NULL DEFAULT '[]',
                documentatii_json TEXT NOT NULL DEFAULT '[]',
                creat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS parametri_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS piese_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS consumabile_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ADD COLUMN IF NOT EXISTS documentatii_json TEXT NOT NULL DEFAULT '[]'")
        c.execute("ALTER TABLE catalog_operatiuni_mentenanta ENABLE ROW LEVEL SECURITY;")
        c.execute("ALTER TABLE fise_mentenanta_tip_masina ENABLE ROW LEVEL SECURITY;")
    return True


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


def construieste_lista_parametri(
    parametri_init: list[dict] | None = None,
    parametru_singur: str = "",
    valoare_singura: str = "",
    um_singura: str = "",
) -> list[dict]:
    lista = [dict(x) for x in _parse_json_list(parametri_init) if isinstance(x, dict)]
    prm_s = str(parametru_singur or "").strip()
    val_s = str(valoare_singura or "").strip()
    um_s = str(um_singura or "").strip()
    if not lista and any([prm_s, val_s, um_s]):
        lista.append({
            "parametru": prm_s,
            "valoare": val_s,
            "um": um_s,
        })
    return lista


def formateaza_parametri_text(
    parametri: list[dict] | None,
    fallback_prm: str = "",
    fallback_val: str = "",
    fallback_um: str = "",
) -> str:
    linii = []
    for prm in _parse_json_list(parametri):
        if not isinstance(prm, dict):
            continue
        den = str(prm.get("parametru") or prm.get("denumire") or "").strip()
        val = str(prm.get("valoare") or "").strip()
        um = str(prm.get("um") or "").strip()
        if not any([den, val, um]):
            continue
        val_um = f"{val} {um}".strip() if (val or um) else ""
        if den and val_um:
            linii.append(f"{den}: {val_um}")
        elif den:
            linii.append(den)
        else:
            linii.append(val_um)
    if linii:
        return "; ".join(linii)
    f_prm = str(fallback_prm or "").strip()
    f_val = str(fallback_val or "").strip()
    f_um = str(fallback_um or "").strip()
    val_um_f = f"{f_val} {f_um}".strip() if (f_val or f_um) else ""
    if f_prm and val_um_f:
        return f"{f_prm}: {val_um_f}"
    return f_prm or val_um_f


def rezuma_parametri_coloane(
    parametri: list[dict] | None,
    fallback_prm: str = "",
    fallback_val: str = "",
    fallback_um: str = "",
) -> tuple[str, str, str]:
    lista = [x for x in _parse_json_list(parametri) if isinstance(x, dict)]
    if not lista:
        return str(fallback_prm or "").strip(), str(fallback_val or "").strip(), str(fallback_um or "").strip()
    if len(lista) == 1:
        p0 = lista[0]
        return (
            str(p0.get("parametru") or p0.get("denumire") or "").strip(),
            str(p0.get("valoare") or "").strip(),
            str(p0.get("um") or "").strip(),
        )
    den_toate = [
        str(p.get("parametru") or p.get("denumire") or "").strip()
        for p in lista
        if str(p.get("parametru") or p.get("denumire") or "").strip()
    ]
    val_toate = [str(p.get("valoare") or "").strip() for p in lista if str(p.get("valoare") or "").strip()]
    um_toate = []
    for p in lista:
        u = str(p.get("um") or "").strip()
        if u and u not in um_toate:
            um_toate.append(u)
    return "; ".join(den_toate), "; ".join(val_toate), ", ".join(um_toate)


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
                   parametri_json, piese_json, consumabile_json, documentatii_json
            FROM catalog_operatiuni_mentenanta
            ORDER BY sistem ASC, id ASC
        """)
        rows = [dict(r) for r in (c.fetchall() or [])]
    for r in rows:
        r["parametri"] = construieste_lista_parametri(
            parametri_init=_parse_json_list(r.get("parametri_json")),
            parametru_singur=r.get("parametru") or "",
            valoare_singura=r.get("valoare") or "",
            um_singura=r.get("um") or "",
        )
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
    parametri: list[dict] | None = None,
    piese: list[dict] | None = None,
    consumabile: list[dict] | None = None,
    documentatii: list[dict] | None = None,
) -> int | None:
    _asigura_tabele_fise_si_catalog()
    op_clean = str(operatiune or "").strip()
    if not op_clean:
        return None
    lista_prm = construieste_lista_parametri(parametri, parametru, valoare, um)
    prm_col, val_col, um_col = rezuma_parametri_coloane(lista_prm, parametru, valoare, um)
    with db_cursor() as c:
        c.execute("""
            INSERT INTO catalog_operatiuni_mentenanta
                (sistem, operatiune, parametru, valoare, um, parametri_json, piese_json, consumabile_json, documentatii_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            str(sistem or "General").strip() or "General",
            op_clean,
            prm_col,
            val_col,
            um_col,
            json.dumps(lista_prm, ensure_ascii=False),
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
    parametri: list[dict] | None = None,
    piese: list[dict] | None = None,
    consumabile: list[dict] | None = None,
    documentatii: list[dict] | None = None,
):
    _asigura_tabele_fise_si_catalog()
    lista_prm = construieste_lista_parametri(parametri, parametru, valoare, um)
    prm_col, val_col, um_col = rezuma_parametri_coloane(lista_prm, parametru, valoare, um)
    with db_cursor() as c:
        c.execute("""
            UPDATE catalog_operatiuni_mentenanta
            SET sistem = %s,
                operatiune = %s,
                parametru = %s,
                valoare = %s,
                um = %s,
                parametri_json = %s,
                piese_json = %s,
                consumabile_json = %s,
                documentatii_json = %s
            WHERE id = %s
        """, (
            str(sistem or "General").strip() or "General",
            str(operatiune or "").strip(),
            prm_col,
            val_col,
            um_col,
            json.dumps(lista_prm, ensure_ascii=False),
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
    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", prefix_key)[:40]
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(uploaded_file.name).name)
    dest = folder / f"{safe_prefix}_{safe_name}"
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


@st.cache_data(ttl=180)
def _incarca_optiuni_piese_catalog() -> list[str]:
    piese_db = PieseRepository.get_all() or []
    return ["-- Introdu piesă manual --"] + [
        f"{p['denumire']}" + (f" ({p['cod_producator']})" if p.get("cod_producator") else "")
        for p in piese_db
    ]


# --- CALLBACK-URI BUILDER RESURSE (FĂRĂ st.rerun()) ---

def _cb_adauga_parametru(prefix_key: str):
    k_prm = f"res_prm_{prefix_key}"
    den = str(st.session_state.get(f"inp_prm_den_{prefix_key}") or "").strip()
    val = str(st.session_state.get(f"inp_prm_val_{prefix_key}") or "").strip()
    um = str(st.session_state.get(f"inp_prm_um_{prefix_key}") or "").strip()
    if not any([den, val, um]):
        st.session_state[f"msg_res_{prefix_key}"] = ("warning", "Introdu cel puțin o informație pentru parametru.")
        return
    st.session_state[k_prm].append({"parametru": den, "valoare": val, "um": um})
    st.session_state[f"inp_prm_den_{prefix_key}"] = ""
    st.session_state[f"inp_prm_val_{prefix_key}"] = ""
    st.session_state[f"inp_prm_um_{prefix_key}"] = ""


def _cb_sterge_element_resursa(state_list_key: str, idx: int):
    lista = st.session_state.get(state_list_key)
    if isinstance(lista, list) and 0 <= idx < len(lista):
        lista.pop(idx)


def _cb_selecteaza_piesa_catalog(prefix_key: str):
    sel = st.session_state.get(f"sel_p_{prefix_key}", "-- Introdu piesă manual --")
    st.session_state[f"inp_p_den_{prefix_key}"] = "" if sel == "-- Introdu piesă manual --" else sel


def _cb_adauga_piesa(prefix_key: str):
    k_piese = f"res_piese_{prefix_key}"
    den = str(st.session_state.get(f"inp_p_den_{prefix_key}") or "").strip()
    if not den:
        st.session_state[f"msg_res_{prefix_key}"] = ("warning", "Introdu sau selectează o piesă.")
        return
    cant = float(st.session_state.get(f"inp_p_cant_{prefix_key}") or 1.0)
    cant_fmt = int(cant) if cant.is_integer() else round(cant, 2)
    um = str(st.session_state.get(f"inp_p_um_{prefix_key}") or "buc").strip() or "buc"
    loc = str(st.session_state.get(f"inp_p_loc_{prefix_key}") or "").strip()
    st.session_state[k_piese].append({
        "piesa": den,
        "cantitate": cant_fmt,
        "um": um,
        "loc_utilizare": loc,
    })
    st.session_state[f"sel_p_{prefix_key}"] = "-- Introdu piesă manual --"
    st.session_state[f"inp_p_den_{prefix_key}"] = ""
    st.session_state[f"inp_p_loc_{prefix_key}"] = ""


def _cb_adauga_consumabil(prefix_key: str):
    k_cons = f"res_cons_{prefix_key}"
    den = str(st.session_state.get(f"inp_c_den_{prefix_key}") or "").strip()
    if not den:
        st.session_state[f"msg_res_{prefix_key}"] = ("warning", "Introdu denumirea materialului consumabil.")
        return
    cant = float(st.session_state.get(f"inp_c_cant_{prefix_key}") or 1.0)
    cant_fmt = int(cant) if cant.is_integer() else round(cant, 2)
    um = str(st.session_state.get(f"inp_c_um_{prefix_key}") or "buc").strip() or "buc"
    loc = str(st.session_state.get(f"inp_c_loc_{prefix_key}") or "").strip()
    st.session_state[k_cons].append({
        "material": den,
        "cantitate": cant_fmt,
        "um": um,
        "loc_utilizare": loc,
    })
    st.session_state[f"inp_c_den_{prefix_key}"] = ""
    st.session_state[f"inp_c_loc_{prefix_key}"] = ""


def _cb_adauga_documentatie(prefix_key: str):
    k_docs = f"res_docs_{prefix_key}"
    titlu = str(st.session_state.get(f"inp_d_titlu_{prefix_key}") or "").strip()
    url = str(st.session_state.get(f"inp_d_url_{prefix_key}") or "").strip()
    doc_file = st.session_state.get(f"up_d_file_{prefix_key}")
    final_url = url
    if doc_file is not None:
        final_url = _salveaza_fisier_doc_local(doc_file, f"{prefix_key}_doc{len(st.session_state[k_docs]) + 1}")
    if not final_url:
        st.session_state[f"msg_res_{prefix_key}"] = ("warning", "Introdu un link sau încarcă un fișier de documentație.")
        return
    titlu_final = titlu or f"Documentație #{len(st.session_state[k_docs]) + 1}"
    st.session_state[k_docs].append({"titlu": titlu_final, "url": final_url})
    st.session_state[f"inp_d_titlu_{prefix_key}"] = ""
    st.session_state[f"inp_d_url_{prefix_key}"] = ""


def render_builder_resurse_operatiune(
    prefix_key: str,
    parametri_init: list[dict] | None = None,
    piese_init: list[dict] | None = None,
    consumabile_init: list[dict] | None = None,
    documentatii_init: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    k_prm = f"res_prm_{prefix_key}"
    k_piese = f"res_piese_{prefix_key}"
    k_cons = f"res_cons_{prefix_key}"
    k_docs = f"res_docs_{prefix_key}"

    if k_prm not in st.session_state:
        st.session_state[k_prm] = list(_parse_json_list(parametri_init))
    if k_piese not in st.session_state:
        st.session_state[k_piese] = list(_parse_json_list(piese_init))
    if k_cons not in st.session_state:
        st.session_state[k_cons] = list(_parse_json_list(consumabile_init))
    if k_docs not in st.session_state:
        st.session_state[k_docs] = list(_parse_json_list(documentatii_init))

    msg_res = st.session_state.pop(f"msg_res_{prefix_key}", None)
    if msg_res:
        if msg_res[0] == "warning":
            st.warning(msg_res[1])
        else:
            st.info(msg_res[1])

    with st.expander("📐 Parametri măsurați / verificați (poți adăuga mai mulți)", expanded=bool(st.session_state[k_prm])):
        cprm1, cprm2, cprm3 = st.columns([2.2, 1.2, 0.9])
        with cprm1:
            st.text_input(
                "Denumire parametru",
                placeholder="ex: Tensiune alimentare / Presiune / Joc ax",
                key=f"inp_prm_den_{prefix_key}",
            )
        with cprm2:
            st.text_input(
                "Valoare",
                placeholder="ex: 24.0 / 6.2 / 0.02",
                key=f"inp_prm_val_{prefix_key}",
            )
        with cprm3:
            st.text_input(
                "UM",
                placeholder="ex: V / bar / mm",
                key=f"inp_prm_um_{prefix_key}",
            )

        st.button(
            "➕ Adaugă parametru la operațiune",
            key=f"btn_add_prm_{prefix_key}",
            on_click=_cb_adauga_parametru,
            args=(prefix_key,),
        )

        if st.session_state[k_prm]:
            for idx_pr, item_pr in enumerate(st.session_state[k_prm]):
                col_prt, col_prd = st.columns([4.5, 0.7], vertical_alignment="center")
                p_den = str(item_pr.get("parametru") or item_pr.get("denumire") or "").strip()
                p_val = str(item_pr.get("valoare") or "").strip()
                p_um = str(item_pr.get("um") or "").strip()
                val_um = f"`{p_val} {p_um}`".strip() if (p_val or p_um) else ""
                if p_den and val_um:
                    col_prt.markdown(f"- **{p_den}**: {val_um}")
                elif p_den:
                    col_prt.markdown(f"- **{p_den}**")
                else:
                    col_prt.markdown(f"- {val_um}")
                col_prd.button(
                    "🗑️",
                    key=f"del_prm_{prefix_key}_{idx_pr}",
                    on_click=_cb_sterge_element_resursa,
                    args=(k_prm, idx_pr),
                )

    opt_piese_catalog = _incarca_optiuni_piese_catalog()

    with st.expander("🔩 Piese necesare (poți adăuga mai multe / același tip de mai multe ori)", expanded=bool(st.session_state[k_piese])):
        cp1, cp2 = st.columns([2, 2])
        with cp1:
            st.selectbox(
                "Alege piesa din catalog (sau manual)",
                options=opt_piese_catalog,
                key=f"sel_p_{prefix_key}",
                on_change=_cb_selecteaza_piesa_catalog,
                args=(prefix_key,),
            )
        with cp2:
            st.text_input(
                "Denumire piesă",
                placeholder="ex: Rulment 6205 2RS / Senzor inductiv M12",
                key=f"inp_p_den_{prefix_key}",
            )

        cp3, cp4, cp5 = st.columns([1, 1, 2.2])
        with cp3:
            st.number_input("Cantitate", min_value=0.1, step=1.0, value=1.0, key=f"inp_p_cant_{prefix_key}")
        with cp4:
            st.text_input("UM", value="buc", key=f"inp_p_um_{prefix_key}")
        with cp5:
            st.text_input(
                "Loc montaj / Ansamblu (opțional)",
                placeholder="ex: Ax X - lagăr față",
                key=f"inp_p_loc_{prefix_key}",
            )

        st.button(
            "➕ Adaugă piesă la operațiune",
            key=f"btn_add_p_{prefix_key}",
            on_click=_cb_adauga_piesa,
            args=(prefix_key,),
        )

        if st.session_state[k_piese]:
            for idx_p, item_p in enumerate(st.session_state[k_piese]):
                col_pt, col_pd = st.columns([4.5, 0.7], vertical_alignment="center")
                loc_str = f" — *{item_p['loc_utilizare']}*" if item_p.get("loc_utilizare") else ""
                col_pt.markdown(f"- **{item_p['piesa']}** — `{item_p['cantitate']} {item_p.get('um', 'buc')}`{loc_str}")
                col_pd.button(
                    "🗑️",
                    key=f"del_p_{prefix_key}_{idx_p}",
                    on_click=_cb_sterge_element_resursa,
                    args=(k_piese, idx_p),
                )

    with st.expander("🧴 Materiale consumabile & locuri de utilizare (ex: WD40 - 50ml, pini 0.75 - 20buc)", expanded=bool(st.session_state[k_cons])):
        cc1, cc2, cc3, cc4 = st.columns([1.8, 0.9, 0.8, 2.2])
        with cc1:
            st.text_input(
                "Material consumabil",
                placeholder="ex: WD40 / Pini 0.75 / Vaselină Litiu",
                key=f"inp_c_den_{prefix_key}",
            )
        with cc2:
            st.number_input("Cantitate", min_value=0.1, step=1.0, value=50.0, key=f"inp_c_cant_{prefix_key}")
        with cc3:
            st.text_input("UM", value="ml", placeholder="ml / buc / g", key=f"inp_c_um_{prefix_key}")
        with cc4:
            st.text_input(
                "Locul unde se utilizează",
                placeholder="ex: Se curăță jiglorul 4 de la ansamblul cccc",
                key=f"inp_c_loc_{prefix_key}",
            )

        st.button(
            "➕ Adaugă consumabil la operațiune",
            key=f"btn_add_c_{prefix_key}",
            on_click=_cb_adauga_consumabil,
            args=(prefix_key,),
        )

        if st.session_state[k_cons]:
            for idx_c, item_c in enumerate(st.session_state[k_cons]):
                col_ct, col_cd = st.columns([4.5, 0.7], vertical_alignment="center")
                loc_c = f" → **{item_c['loc_utilizare']}**" if item_c.get("loc_utilizare") else ""
                col_ct.markdown(f"- **{item_c['material']}** — `{item_c['cantitate']} {item_c.get('um', '')}`{loc_c}")
                col_cd.button(
                    "🗑️",
                    key=f"del_c_{prefix_key}_{idx_c}",
                    on_click=_cb_sterge_element_resursa,
                    args=(k_cons, idx_c),
                )

    with st.expander("🔗 Link-uri / Fișiere documentație multiple (pentru sub-operațiuni executate deodată)", expanded=bool(st.session_state[k_docs])):
        cd1, cd2, cd3 = st.columns([1.8, 2.2, 1.5])
        with cd1:
            st.text_input(
                "Etichetă / Sub-operațiune",
                placeholder="ex: Demontarea axului axei X",
                key=f"inp_d_titlu_{prefix_key}",
            )
        with cd2:
            st.text_input(
                "Link documentație (Google Drive / URL)",
                placeholder="https://drive.google.com/...",
                key=f"inp_d_url_{prefix_key}",
            )
        with cd3:
            st.file_uploader(
                "Sau încarcă fișier",
                type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
                key=f"up_d_file_{prefix_key}",
            )

        st.button(
            "➕ Adaugă link / documentație",
            key=f"btn_add_d_{prefix_key}",
            on_click=_cb_adauga_documentatie,
            args=(prefix_key,),
        )

        if st.session_state[k_docs]:
            for idx_d, item_d in enumerate(st.session_state[k_docs]):
                col_dt, col_dd = st.columns([4.5, 0.7], vertical_alignment="center")
                col_dt.markdown(f"- **{item_d.get('titlu', 'Link')}**: `{item_d.get('url', '')}`")
                col_dd.button(
                    "🗑️",
                    key=f"del_d_{prefix_key}_{idx_d}",
                    on_click=_cb_sterge_element_resursa,
                    args=(k_docs, idx_d),
                )

    return (
        list(st.session_state[k_prm]),
        list(st.session_state[k_piese]),
        list(st.session_state[k_cons]),
        list(st.session_state[k_docs]),
    )


def reseteaza_builder_resurse_operatiune(prefix_key: str):
    for pfx in ("res_prm_", "res_piese_", "res_cons_", "res_docs_", "msg_res_"):
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
            prm_list = construieste_lista_parametri(
                parametri_init=p.get("parametri"),
                parametru_singur=p.get("Denumire parametru") or p.get("parametru") or "",
                valoare_singura=p.get("Valoare") or p.get("valoare") or "",
                um_singura=p.get("UM") or p.get("um") or "",
            )
            prm_col, val_col, um_col = rezuma_parametri_coloane(
                prm_list,
                p.get("Denumire parametru") or p.get("parametru") or "",
                p.get("Valoare") or p.get("valoare") or "",
                p.get("UM") or p.get("um") or "",
            )
            piese_txt = p.get("Piese necesare") or formateaza_piese_text(p.get("piese") or [])
            cons_txt = p.get("Materiale consumabile") or formateaza_consumabile_text(p.get("consumabile") or [])
            doc_txt = p.get("Documentație") or formateaza_documentatii_text(p.get("documentatii") or [])
            randuri.append({
                "Ordine": int(p.get("Ordine") or p.get("ordine") or idx),
                "Operațiune / Verificare": str(p.get("Operațiune / Verificare") or p.get("operatiune") or ""),
                "Denumire parametru": prm_col,
                "Valoare": val_col,
                "UM": um_col,
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
        prm_list = construieste_lista_parametri(vechi.get("parametri"), prm, val, um)
        pasi.append({
            "Ordine": ord_val,
            "Operațiune / Verificare": op,
            "Denumire parametru": prm,
            "Valoare": val,
            "UM": um,
            "Piese necesare": piese_txt,
            "Materiale consumabile": cons_txt,
            "Documentație": doc_txt,
            "parametri": prm_list,
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


def _render_sectiune_editare_catalog_db(catalog_db: list[dict]):
    st.markdown("### ⚙️ Editare Catalog Operațiuni în Baza de Date")
    st.caption("Tot ce modifici aici se salvează direct în DB și este disponibil imediat și de pe telefon, la client.")

    msg_cat = st.session_state.pop("msg_cat_db", None)
    if msg_cat:
        if msg_cat[0] == "success":
            st.success(msg_cat[1])
        elif msg_cat[0] == "toast":
            st.toast(msg_cat[1])

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
            "Parametru rapid / implicit (opțional)",
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

    prm_list, piese_list, cons_list, docs_list = render_builder_resurse_operatiune(
        prefix_key=builder_key,
        parametri_init=(item_sel.get("parametri") if item_sel else []),
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
                final_prm = construieste_lista_parametri(prm_list, prm_val, val_val, um_val)
                if item_sel:
                    actualizeaza_operatiune_in_catalog_db(
                        op_id=item_sel["id"],
                        sistem=sistem_val,
                        operatiune=op_val,
                        parametru=prm_val,
                        valoare=val_val,
                        um=um_val,
                        parametri=final_prm,
                        piese=piese_list,
                        consumabile=cons_list,
                        documentatii=docs_list,
                    )
                    st.session_state["msg_cat_db"] = ("success", f"✅ Operațiunea #{item_sel['id']} a fost actualizată în DB.")
                else:
                    new_id = adauga_operatiune_in_catalog_db(
                        sistem=sistem_val,
                        operatiune=op_val,
                        parametru=prm_val,
                        valoare=val_val,
                        um=um_val,
                        parametri=final_prm,
                        piese=piese_list,
                        consumabile=cons_list,
                        documentatii=docs_list,
                    )
                    reseteaza_builder_resurse_operatiune(builder_key)
                    st.session_state["msg_cat_db"] = ("success", f"✅ Operațiunea #{new_id} a fost adăugată în DB.")
                st.rerun()
    with b2:
        if item_sel and st.button("🗑️ Șterge din Catalog DB", use_container_width=True, key=f"cat_db_del_{edit_id}"):
            sterge_operatiune_din_catalog_db(item_sel["id"])
            reseteaza_builder_resurse_operatiune(builder_key)
            st.session_state["cat_db_sel_item"] = "➕ Adaugă operațiune nouă în catalog"
            st.session_state["msg_cat_db"] = ("toast", f"🗑️ Operațiunea #{item_sel['id']} a fost ștearsă.")
            st.rerun()

    if catalog_db:
        st.markdown("#### 📋 Lista completă din Catalogul DB")
        df_cat = pd.DataFrame([
            {
                "ID": x["id"],
                "Sistem": x["sistem"],
                "Operațiune": x["operatiune"],
                "Parametri": formateaza_parametri_text(
                    x.get("parametri"),
                    x.get("parametru") or "",
                    x.get("valoare") or "",
                    x.get("um") or "",
                ),
                "Piese necesare": formateaza_piese_text(x.get("piese") or []),
                "Materiale consumabile": formateaza_consumabile_text(x.get("consumabile") or []),
                "Documentație": formateaza_documentatii_text(x.get("documentatii") or []),
            }
            for x in catalog_db
        ])
        st.dataframe(df_cat, hide_index=True, use_container_width=True)


# --- CALLBACK-URI FIȘĂ TIP MAȘINĂ (STABILE & FĂRĂ st.rerun()) ---

def _cb_schimba_preset_masina():
    sel = st.session_state.get("fmp_preset", "-- Introdu manual --")
    if sel != "-- Introdu manual --":
        parti = sel.split(" | ", 1)
        st.session_state["fmp_den_masina"] = parti[0].strip()
        st.session_state["fmp_tip_masina"] = parti[1].strip() if len(parti) > 1 else ""
    else:
        st.session_state["fmp_den_masina"] = ""
        st.session_state["fmp_tip_masina"] = ""


def _cb_schimba_operatiune_catalog_fisa(opt_op_cat: dict, b_key: str):
    sel_lbl = st.session_state.get(f"fmp_sel_op_{b_key}")
    it_cat = opt_op_cat.get(sel_lbl)
    st.session_state[f"fmp_op_txt_{b_key}"] = it_cat["operatiune"] if it_cat else ""
    st.session_state[f"fmp_prm_txt_{b_key}"] = (it_cat.get("parametru") or "") if it_cat else ""
    st.session_state[f"fmp_val_txt_{b_key}"] = (it_cat.get("valoare") or "") if it_cat else ""
    st.session_state[f"fmp_um_txt_{b_key}"] = (it_cat.get("um") or "") if it_cat else ""
    st.session_state[f"fmp_chk_cat_{b_key}"] = it_cat is None
    st.session_state[f"res_prm_{b_key}"] = list(it_cat.get("parametri") or []) if it_cat else []
    st.session_state[f"res_piese_{b_key}"] = list(it_cat.get("piese") or []) if it_cat else []
    st.session_state[f"res_cons_{b_key}"] = list(it_cat.get("consumabile") or []) if it_cat else []
    st.session_state[f"res_docs_{b_key}"] = list(it_cat.get("documentatii") or []) if it_cat else []


def _cb_adauga_operatiune_in_fisa(b_key: str, it_cat: dict | None):
    op_txt = str(st.session_state.get(f"fmp_op_txt_{b_key}") or "").strip()
    if not op_txt:
        st.session_state["msg_fmp_tab"] = ("warning", "Introdu sau selectează o operațiune.")
        return

    prm_txt = str(st.session_state.get(f"fmp_prm_txt_{b_key}") or "").strip()
    val_txt = str(st.session_state.get(f"fmp_val_txt_{b_key}") or "").strip()
    um_txt = str(st.session_state.get(f"fmp_um_txt_{b_key}") or "").strip()

    prm_op = list(st.session_state.get(f"res_prm_{b_key}") or [])
    piese_op = list(st.session_state.get(f"res_piese_{b_key}") or [])
    cons_op = list(st.session_state.get(f"res_cons_{b_key}") or [])
    docs_op = list(st.session_state.get(f"res_docs_{b_key}") or [])

    final_prm = construieste_lista_parametri(prm_op, prm_txt, val_txt, um_txt)
    prm_col, val_col, um_col = rezuma_parametri_coloane(final_prm, prm_txt, val_txt, um_txt)

    if st.session_state.get(f"fmp_chk_cat_{b_key}") and it_cat is None:
        adauga_operatiune_in_catalog_db(
            sistem="General",
            operatiune=op_txt,
            parametru=prm_txt,
            valoare=val_txt,
            um=um_txt,
            parametri=final_prm,
            piese=piese_op,
            consumabile=cons_op,
            documentatii=docs_op,
        )

    pasi_crt = st.session_state.setdefault("fmp_pasi_activ", [])
    pasi_crt.append({
        "Ordine": len(pasi_crt) + 1,
        "Operațiune / Verificare": op_txt,
        "Denumire parametru": prm_col,
        "Valoare": val_col,
        "UM": um_col,
        "Piese necesare": formateaza_piese_text(piese_op),
        "Materiale consumabile": formateaza_consumabile_text(cons_op),
        "Documentație": formateaza_documentatii_text(docs_op),
        "parametri": final_prm,
        "piese": piese_op,
        "consumabile": cons_op,
        "documentatii": docs_op,
    })

    st.session_state[f"fmp_sel_op_{b_key}"] = "-- Introdu manual / copy-paste --"
    st.session_state[f"fmp_op_txt_{b_key}"] = ""
    st.session_state[f"fmp_prm_txt_{b_key}"] = ""
    st.session_state[f"fmp_val_txt_{b_key}"] = ""
    st.session_state[f"fmp_um_txt_{b_key}"] = ""
    st.session_state[f"fmp_chk_cat_{b_key}"] = True
    st.session_state[f"res_prm_{b_key}"] = []
    st.session_state[f"res_piese_{b_key}"] = []
    st.session_state[f"res_cons_{b_key}"] = []
    st.session_state[f"res_docs_{b_key}"] = []


def _cb_sterge_operatiuni_fisa(opt_del: dict):
    de_sters = st.session_state.get("fmp_ms_del_activ") or []
    if not de_sters:
        return
    indici = {opt_del[k] for k in de_sters if k in opt_del}
    ramase = []
    for idx_r, it_r in enumerate(st.session_state.get("fmp_pasi_activ") or []):
        if idx_r not in indici:
            cp = dict(it_r)
            cp["Ordine"] = len(ramase) + 1
            ramase.append(cp)
    st.session_state["fmp_pasi_activ"] = ramase
    st.session_state["fmp_ms_del_activ"] = []


def render_fise_mentenanta():
    st.subheader("📋 Catalog Operațiuni & Fișe Tip de Mentenanță (DB)")

    catalog_db = incarca_catalog_operatiuni_db()
    fise_db = _incarca_fise_tip_db()

    tab_catalog, tab_fise_tip, tab_lista = st.tabs([
        "⚙️ Editare Catalog Operațiuni (DB)",
        "🧩 Fișă Tip Mașină (fără client)",
        "📚 Fișe Tip Salvate în DB",
    ])

    with tab_catalog:
        _render_sectiune_editare_catalog_db(catalog_db)

    with tab_fise_tip:
        msg_fmp = st.session_state.pop("msg_fmp_tab", None)
        if msg_fmp:
            if msg_fmp[0] == "success":
                st.success(msg_fmp[1])
            elif msg_fmp[0] == "warning":
                st.warning(msg_fmp[1])
            elif msg_fmp[0] == "error":
                st.error(msg_fmp[1])

        catalog_masini = _incarca_masini_catalog()
        opt_preset = ["-- Introdu manual --"] + [
            f"{x['denumire_masina']} | {x['tip_masina']}" for x in catalog_masini
        ]
        st.selectbox(
            "Selectează mașină și tip mașină",
            options=opt_preset,
            key="fmp_preset",
            on_change=_cb_schimba_preset_masina,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            den_masina = st.text_input("Denumire mașină *", key="fmp_den_masina").strip()
        with c2:
            tip_masina = st.text_input("Tip mașină *", key="fmp_tip_masina").strip()
        with c3:
            frec_sel = st.selectbox("Tip mentenanță / Frecvență", options=FRECVENTE_MENTENANTA, key="fmp_frec")

        # Sincronizare stabilă: reîncarcă pașii din DB doar când se schimbă combinația mașină/tip/frecvență
        semnatura_fisa = (den_masina.lower(), tip_masina.lower(), frec_sel.lower())
        fisa_exs = _gaseste_fisa_tip(fise_db, den_masina, tip_masina, frec_sel)
        nume_auto = construieste_nume_fisa_masina(den_masina, tip_masina, frec_sel)

        if st.session_state.get("fmp_semnatura_curenta") != semnatura_fisa:
            st.session_state["fmp_semnatura_curenta"] = semnatura_fisa
            st.session_state["fmp_pasi_activ"] = list(fisa_exs["pasi"]) if fisa_exs else []
            st.session_state["fmp_nume_fisa_activ"] = (fisa_exs.get("nume_fisa") if fisa_exs else "") or nume_auto

        nume_fisa_input = st.text_input(
            "Denumire fișă tip",
            key="fmp_nume_fisa_activ",
        ).strip() or nume_auto

        st.markdown("#### 📎 Încarcă / Setează operațiune în fișa tip")
        opt_op_cat = {"-- Introdu manual / copy-paste --": None}
        for it in catalog_db:
            opt_op_cat[f"[{it['sistem']}] {it['operatiune']}"] = it

        b_key = "fmp_res_activ"
        sel_op_lbl = st.selectbox(
            "Alege operațiunea din Catalogul DB (sau introdu manual / copy-paste)",
            options=list(opt_op_cat.keys()),
            key=f"fmp_sel_op_{b_key}",
            on_change=_cb_schimba_operatiune_catalog_fisa,
            args=(opt_op_cat, b_key),
        )
        it_cat = opt_op_cat[sel_op_lbl]

        o1, o2, o3, o4 = st.columns([2.2, 1.2, 0.9, 0.7])
        with o1:
            st.text_input("Operațiune / Verificare", key=f"fmp_op_txt_{b_key}")
        with o2:
            st.text_input("Parametru rapid", key=f"fmp_prm_txt_{b_key}")
        with o3:
            st.text_input("Valoare", key=f"fmp_val_txt_{b_key}")
        with o4:
            st.text_input("UM", key=f"fmp_um_txt_{b_key}")

        render_builder_resurse_operatiune(
            prefix_key=b_key,
            parametri_init=(it_cat.get("parametri") if it_cat else []),
            piese_init=(it_cat.get("piese") if it_cat else []),
            consumabile_init=(it_cat.get("consumabile") if it_cat else []),
            documentatii_init=(it_cat.get("documentatii") if it_cat else []),
        )

        st.checkbox(
            "Salvează această operațiune și în Catalogul DB",
            value=(it_cat is None),
            key=f"fmp_chk_cat_{b_key}",
        )
        st.button(
            "➕ Adaugă operațiunea în fișa tip",
            key=f"fmp_btn_add_{b_key}",
            on_click=_cb_adauga_operatiune_in_fisa,
            args=(b_key, it_cat),
        )

        pasi_activi = st.session_state.get("fmp_pasi_activ") or []
        if pasi_activi:
            opt_del = {
                f"{i + 1}. {str(p.get('Operațiune / Verificare') or '')[:80]}": i
                for i, p in enumerate(pasi_activi)
            }
            st.multiselect(
                "Selectează operațiuni de șters din fișă",
                options=list(opt_del.keys()),
                key="fmp_ms_del_activ",
            )
            st.button(
                "🗑️ Șterge operațiunile selectate",
                key="fmp_btn_del_activ",
                on_click=_cb_sterge_operatiuni_fisa,
                args=(opt_del,),
            )

        df_ed = st.data_editor(
            _normalizare_pasi_df(pasi_activi),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="editor_fisa_tip_activ",
        )

        if st.button("💾 Salvează Fișa Tip în DB", type="primary", key="btn_salveaza_fisa_tip"):
            if not den_masina and not tip_masina:
                st.error("⚠️ Completează Denumirea mașinii și/sau Tipul mașinii.")
            else:
                pasi_noi = _df_la_pasi(df_ed, pasi_activi)
                st.session_state["fmp_pasi_activ"] = pasi_noi
                _salveaza_fisa_tip_masina(den_masina, tip_masina, frec_sel, pasi_noi, nume_fisa=nume_fisa_input)
                st.session_state["msg_fmp_tab"] = ("success", f"✅ Fișa tip **„{nume_fisa_input}”** a fost salvată în DB.")
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