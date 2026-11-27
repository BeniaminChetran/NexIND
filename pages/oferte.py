# ------------------------------------------------
# --- pages/oferte.py ----------------------------
# ------------------------------------------------


import json
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

from config import db_cursor
from datetime import date, datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from services.pdf_service import genereaza_pdf_oferta, get_date_firma_mea
from repositories.tarife_repository import TarifeRepository


COLS_OFERTA = [
    "Ordine",
    "Descriere",
    "UM",
    "Cantitate",
    "Pret Unitar",
    "Moneda",
    "Termen livrare",
]


@st.cache_data(ttl=3600)
def obtine_curs_bnr() -> float | None:
    """Returnează cursul EUR/RON de la BNR sau None dacă nu poate fi obținut (fără valori ghicite)."""
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/xml,text/xml,text/html,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    }
    ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request("https://www.bnr.ro/nbrfxrates.xml", headers=headers_browser)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            for cube in root.iter("{http://www.bnr.ro/xsd}Cube"):
                if cube.get("date"):
                    for rate in cube.findall("{http://www.bnr.ro/xsd}Rate"):
                        if rate.get("currency") == "EUR" and rate.text:
                            return float(rate.text)
    except Exception:
        pass

    try:
        req_cb = urllib.request.Request("https://www.cursbnr.ro/", headers=headers_browser)
        with urllib.request.urlopen(req_cb, timeout=5, context=ctx) as response:
            html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r"1\s*EURO\s*=\s*([0-9]+\.[0-9]{4})\s*Lei", html, re.IGNORECASE)
            if match:
                return float(match.group(1))
    except Exception:
        pass

    try:
        url_ecb = "https://api.frankfurter.app/latest?from=EUR&to=RON"
        req_ecb = urllib.request.Request(url_ecb, headers=headers_browser)
        with urllib.request.urlopen(req_ecb, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "rates" in data and "RON" in data["rates"]:
                return float(data["rates"]["RON"])
    except Exception:
        pass

    return None


def _asigura_tabel_oferte_db():
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS oferte_client (
                id SERIAL PRIMARY KEY,
                firma_id INTEGER,
                nume_firma TEXT NOT NULL,
                masina TEXT,
                data_oferta TEXT NOT NULL,
                adaos_comercial_pct DOUBLE PRECISION NOT NULL,
                discount_pct DOUBLE PRECISION DEFAULT 0.0,
                discount_val DOUBLE PRECISION DEFAULT 0.0,
                cota_tva_pct DOUBLE PRECISION NOT NULL,
                subtotal DOUBLE PRECISION DEFAULT 0.0,
                total_general DOUBLE PRECISION DEFAULT 0.0,
                status_oferta TEXT DEFAULT 'Ciornă',
                trimisa_la_client BOOLEAN DEFAULT FALSE,
                data_trimitere TEXT,
                linii_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _salveaza_oferta_in_db(
    oferta_id: int | None,
    firma_id,
    nume_firma: str,
    masina: str,
    data_oferta: str,
    adaos_pct: float,
    discount_pct: float,
    discount_val: float,
    cota_tva_pct: float,
    tot: dict,
    df_linii: pd.DataFrame,
    status_oferta: str = "Salvată",
    trimisa_la_client: bool = False,
    data_trimitere: str | None = None,
) -> int:
    _asigura_tabel_oferte_db()
    linii_clean = []
    for idx, r in df_linii.iterrows():
        desc = str(r.get("Descriere") or "").strip()
        if not desc:
            continue
        linii_clean.append({
            "Ordine": int(r.get("Ordine") or (idx + 1)),
            "Descriere": desc,
            "UM": str(r.get("UM") or "buc").strip() or "buc",
            "Cantitate": float(r.get("Cantitate")),
            "Pret Unitar": round(float(r.get("Pret Unitar")), 2),
            "Moneda": str(r.get("Moneda")).strip().upper(),
            "Termen livrare": str(r.get("Termen livrare") or "").strip(),
        })

    linii_json = json.dumps(linii_clean, ensure_ascii=False)
    fid_int = int(firma_id) if firma_id is not None else None

    with db_cursor() as cur:
        if oferta_id is not None:
            cur.execute(
                """
                UPDATE oferte_client
                SET firma_id = %s,
                    nume_firma = %s,
                    masina = %s,
                    data_oferta = %s,
                    adaos_comercial_pct = %s,
                    discount_pct = %s,
                    discount_val = %s,
                    cota_tva_pct = %s,
                    subtotal = %s,
                    total_general = %s,
                    status_oferta = %s,
                    trimisa_la_client = %s,
                    data_trimitere = COALESCE(%s, data_trimitere),
                    linii_json = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    fid_int,
                    nume_firma,
                    masina,
                    data_oferta,
                    float(adaos_pct),
                    float(discount_pct),
                    float(discount_val),
                    float(cota_tva_pct),
                    float(tot["subtotal"]),
                    float(tot["total_general"]),
                    status_oferta,
                    bool(trimisa_la_client),
                    data_trimitere,
                    linii_json,
                    int(oferta_id),
                ),
            )
            return int(oferta_id)
        else:
            cur.execute(
                """
                INSERT INTO oferte_client (
                    firma_id, nume_firma, masina, data_oferta,
                    adaos_comercial_pct, discount_pct, discount_val, cota_tva_pct,
                    subtotal, total_general, status_oferta, trimisa_la_client,
                    data_trimitere, linii_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    fid_int,
                    nume_firma,
                    masina,
                    data_oferta,
                    float(adaos_pct),
                    float(discount_pct),
                    float(discount_val),
                    float(cota_tva_pct),
                    float(tot["subtotal"]),
                    float(tot["total_general"]),
                    status_oferta,
                    bool(trimisa_la_client),
                    data_trimitere,
                    linii_json,
                ),
            )
            row = cur.fetchone()
            if isinstance(row, dict):
                return int(row["id"])
            return int(row[0])


def _listeaza_oferte_salvate(limit: int = 30) -> list[dict]:
    _asigura_tabel_oferte_db()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, nume_firma, masina, data_oferta, total_general, status_oferta, trimisa_la_client, data_trimitere
            FROM oferte_client
            ORDER BY id DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        rows = cur.fetchall() or []
        cols = [d[0] for d in cur.description] if cur.description else []
        res = []
        for r in rows:
            res.append(r if isinstance(r, dict) else dict(zip(cols, r)))
        return res


def _incarca_oferta_din_db(oferta_id: int) -> dict | None:
    _asigura_tabel_oferte_db()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM oferte_client WHERE id = %s", (int(oferta_id),))
        row = cur.fetchone()
        if not row:
            return None
        if isinstance(row, dict):
            return row
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def _extrage_adaos_firma(firma_obj: dict) -> tuple[bool, str, float | None]:
    if not isinstance(firma_obj, dict):
        return False, "Lipsește obiectul firmei selectate.", None
    raw = firma_obj.get("adaos_comercial")
    if raw is None or str(raw).strip() == "":
        nume = str(firma_obj.get("nume_firma") or "selectată").strip()
        return False, f"Lipsește valoarea «adaos_comercial» în baza de date pentru firma «{nume}».", None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        nume = str(firma_obj.get("nume_firma") or "selectată").strip()
        return False, f"Valoarea «adaos_comercial» pentru firma «{nume}» nu este un număr valid.", None
    if val < 0:
        return False, "Valoarea «adaos_comercial» a firmei nu poate fi negativă.", None
    return True, "", val


def valideaza_si_calculeaza_linie_oferta(
    piesa_catalog: dict,
    cantitate: float,
    adaos_comercial_pct: float | None,
) -> tuple[bool, str, dict | None]:
    """Validează piesa și adaosul fără valori ghicite."""
    if adaos_comercial_pct is None:
        return False, "Lipsește adaosul comercial al firmei.", None

    den_p = str(piesa_catalog.get("denumire") or "").strip()
    if not den_p:
        return False, "Lipsește denumirea piesei selectate.", None

    raw_pret = piesa_catalog.get("pret_achizitie")
    if raw_pret is None or str(raw_pret).strip() == "":
        return False, f"Lipsește prețul de achiziție pentru piesa «{den_p}» (pret inexistent).", None
    try:
        pret_achiz = float(raw_pret)
    except (TypeError, ValueError):
        return False, f"Prețul de achiziție pentru piesa «{den_p}» nu este valid.", None

    if pret_achiz <= 0.0:
        return False, f"Prețul de achiziție pentru piesa «{den_p}» este 0 sau lipsă (pret inexistent).", None

    raw_moneda = str(piesa_catalog.get("valuta_achizitie") or "").strip().upper()
    if not raw_moneda:
        return False, f"Lipsește moneda («valuta_achizitie») pentru piesa «{den_p}».", None

    if cantitate is None or float(cantitate) <= 0.0:
        return False, "Cantitatea trebuie să fie mai mare decât 0.", None

    cant = float(cantitate)
    pret_vanzare = round(pret_achiz * (1.0 + float(adaos_comercial_pct) / 100.0), 2)

    cod_p = str(
        piesa_catalog.get("cod_producator") or piesa_catalog.get("cod_comercial") or ""
    ).strip()
    desc_p = f"{den_p} ({cod_p})" if cod_p else den_p

    return True, "", {
        "desc": desc_p,
        "denumire": den_p,
        "cod": cod_p,
        "cant": cant,
        "pret_achiz": round(pret_achiz, 2),
        "pret_vanzare": pret_vanzare,
        "valoare": round(pret_vanzare * cant, 2),
        "moneda": raw_moneda,
    }


def _sincronizeaza_editor_inainte_de_adaugare() -> pd.DataFrame:
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    df_base = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_base.columns:
            df_base[col] = None
    df_base = df_base[COLS_OFERTA]

    counter = st.session_state.get("oferta_2_editor_counter", 0)
    ed_key = f"oferta_2_data_editor_{counter}"
    state_ed = st.session_state.get(ed_key)
    if isinstance(state_ed, dict):
        for idx_str, changes in (state_ed.get("edited_rows") or {}).items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df_base) and isinstance(changes, dict):
                for col_name, new_val in changes.items():
                    if col_name in df_base.columns:
                        df_base.at[idx, col_name] = new_val
    return df_base

st.session_state.setdefault("oferta_2_termen_piesa", "")

def _actualizeaza_termen_din_piesa():
    piesa_cheie = st.session_state.get("oferta_2_sel_piesa")
    piesa_info = piese_dict.get(piesa_cheie) if isinstance(piesa_cheie, str) else None
    if piesa_info:
        st.session_state["oferta_2_termen_piesa"] = str(piesa_info.get("termen_livrare") or "").strip()
    else:
        st.session_state["oferta_2_termen_piesa"] = ""

def calculeaza_oferta_fara_fallback(
    firma_obj: dict,
    df_linii: pd.DataFrame,
    cota_tva_pct,
    discount_pct: float = 0.0,
    discount_val: float = 0.0,
    curs_valutar: float | None = None,
) -> tuple[bool, list[str], dict | None]:
    """Calculează totalurile ofertei doar dacă toate câmpurile necesare există (fără fallback-uri)."""
    lipsuri: list[str] = []

    ok_ad, err_ad, adaos = _extrage_adaos_firma(firma_obj)
    if not ok_ad:
        lipsuri.append(err_ad)

    if cota_tva_pct is None or str(cota_tva_pct).strip() == "":
        lipsuri.append("Lipsește cota de TVA (%).")
        tva_pct = None
    else:
        try:
            tva_pct = float(cota_tva_pct)
            if tva_pct < 0:
                lipsuri.append("Cota de TVA (%) nu poate fi negativă.")
        except (TypeError, ValueError):
            lipsuri.append("Cota de TVA (%) nu este un număr valid.")
            tva_pct = None

    subtotal = 0.0
    monede_linii: set[str] = set()
    linii_valide: list[dict] = []

    if df_linii is None or df_linii.empty:
        lipsuri.append("Oferta nu conține nicio linie.")
    else:
        for idx, row in df_linii.iterrows():
            desc = str(row.get("Descriere") or "").strip()
            raw_cant = row.get("Cantitate")
            raw_pret = row.get("Pret Unitar")
            mon = str(row.get("Moneda") or "").strip().upper()

            if (
                not desc
                and (raw_cant is None or str(raw_cant).strip() == "" or pd.isna(raw_cant))
                and (raw_pret is None or str(raw_pret).strip() == "" or pd.isna(raw_pret))
            ):
                continue

            nr_rand = idx + 1
            rand_ok = True

            if not desc:
                lipsuri.append(f"Rândul {nr_rand}: lipsește «Descriere».")
                rand_ok = False

            if raw_cant is None or str(raw_cant).strip() == "" or pd.isna(raw_cant):
                lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): lipsește «Cantitate».")
                cant = None
                rand_ok = False
            else:
                try:
                    cant = float(raw_cant)
                    if cant <= 0:
                        lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Cantitate» trebuie să fie > 0.")
                        rand_ok = False
                except (TypeError, ValueError):
                    lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Cantitate» nu este numerică.")
                    cant = None
                    rand_ok = False

            if raw_pret is None or str(raw_pret).strip() == "" or pd.isna(raw_pret):
                lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): lipsește «Pret Unitar».")
                pret = None
                rand_ok = False
            else:
                try:
                    pret = float(raw_pret)
                    if pret <= 0:
                        lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Pret Unitar» lipsește sau este 0.")
                        rand_ok = False
                except (TypeError, ValueError):
                    lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Pret Unitar» nu este numeric.")
                    pret = None
                    rand_ok = False

            if not mon:
                lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): lipsește «Moneda».")
                rand_ok = False
            else:
                monede_linii.add(mon)

            if rand_ok and cant is not None and pret is not None:
                val_linie = round(cant * pret, 2)
                subtotal += val_linie
                linii_valide.append({
                    "Nr.": int(row.get("Ordine") or nr_rand),
                    "Descriere": desc,
                    "UM": str(row.get("UM") or "buc").strip() or "buc",
                    "Cantitate": cant,
                    "Preț Unitar": round(pret, 2),
                    "Valoare": val_linie,
                    "Monedă": mon,
                    "Termen livrare": str(row.get("Termen livrare") or "").strip(),
                })

    if not linii_valide and not lipsuri:
        lipsuri.append("Oferta nu conține nicio linie validă.")

    if len(monede_linii) > 1:
        if curs_valutar is None or float(curs_valutar) <= 0:
            lipsuri.append(
                f"Există monede diferite pe linii ({', '.join(sorted(monede_linii))}) și lipsește cursul valutar pentru conversie."
            )

    if lipsuri:
        return False, lipsuri, None

    subtotal = round(subtotal, 2)
    disc_pct_val = round(subtotal * max(0.0, float(discount_pct or 0.0)) / 100.0, 2)
    disc_val_fix = max(0.0, round(float(discount_val or 0.0), 2))
    baza = max(0.0, round(subtotal - disc_pct_val - disc_val_fix, 2))
    tva_val = round(baza * (tva_pct / 100.0), 2)
    total_gen = round(baza + tva_val, 2)

    return True, [], {
        "adaos_comercial_pct": adaos,
        "moneda_principala": next(iter(monede_linii)),
        "linii_valide": linii_valide,
        "subtotal": subtotal,
        "discount_procent_val": disc_pct_val,
        "discount_valoric": disc_val_fix,
        "baza_impozabila": baza,
        "tva_valoare": tva_val,
        "total_general": total_gen,
    }


def _construieste_payload_pdf_service(
    oferta_id: int | None,
    firma_obj: dict,
    masina_selectata: str,
    data_oferta_str: str,
    df_linii: pd.DataFrame,
    disc_pct: float,
    disc_val: float,
    cota_tva: float,
    tot: dict,
    curs_valutar: float | None,
    este_revizuita: bool,
) -> dict:
    moneda_oferta = tot["moneda_principala"]
    articole_pdf = []
    for idx, r in df_linii.iterrows():
        desc = str(r.get("Descriere") or "").strip()
        if not desc:
            continue
        mon_lin = str(r.get("Moneda") or moneda_oferta).strip().upper()
        pret_lin = round(float(r.get("Pret Unitar")), 2)
        articole_pdf.append({
            "Ordine": int(r.get("Ordine") or (idx + 1)),
            "Descriere": desc,
            "UM": str(r.get("UM") or "buc").strip() or "buc",
            "Cantitate": float(r.get("Cantitate")),
            "Pret Unitar": pret_lin,
            f"Pret Unitar ({mon_lin})": pret_lin,
            "Termen livrare": str(r.get("Termen livrare") or "").strip(),
        })

    if disc_pct > 0:
        tip_disc = "Discount pe total (%)"
        val_disc_in = float(disc_pct)
    elif disc_val > 0:
        tip_disc = "Discount fix"
        val_disc_in = float(disc_val)
    else:
        tip_disc = "Fără discount"
        val_disc_in = 0.0

    return {
        "id": oferta_id,
        "numar_oferta": oferta_id,
        "data": data_oferta_str,
        "client": str(firma_obj.get("nume_firma") or "").strip(),
        "cui_client": str(firma_obj.get("cui") or "").strip(),
        "reg_com_client": str(firma_obj.get("nr_reg_com") or firma_obj.get("reg_com") or "").strip(),
        "adresa_client": str(firma_obj.get("adresa") or "").strip(),
        "utilaj": masina_selectata if masina_selectata != "-- Fără mașină --" else "",
        "moneda": moneda_oferta,
        "curs_valutar": float(curs_valutar) if curs_valutar else 0.0,
        "articole": articole_pdf,
        "tip_discount": tip_disc,
        "valoare_discount_input": val_disc_in,
        "valoare_discount": round(tot["discount_procent_val"] + tot["discount_valoric"], 2),
        "cota_tva": float(cota_tva),
        "este_revizuita": este_revizuita,
    }


@st.fragment
def _fragment_deviz_oferta(
    firma_obj: dict,
    masina_selectata: str,
    data_oferta_str: str,
    adaos_client: float | None,
    eroare_adaos: str,
    cota_tva_implicita: float | None,
):
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    st.session_state.setdefault("oferta_2_editor_counter", 0)
    st.session_state.setdefault("oferta_2_eroare_piesa", "")
    st.session_state.setdefault("oferta_curenta_id", None)
    st.session_state.setdefault("oferta_status", "Ciornă")
    st.session_state.setdefault("oferta_pdf_bytes", None)
    st.session_state.setdefault("oferta_pdf_deschis", False)

    if eroare_adaos:
        st.error(f"⚠️ {eroare_adaos}")

    # Încărcare ofertă salvată din DB pentru modificări și regenerare PDF
    oferte_salvate = _listeaza_oferte_salvate(limit=30)
    if oferte_salvate:
        opt_oferte = {0: "-- Ofertă nouă --"}
        for o in oferte_salvate:
            oid = int(o["id"])
            st_lbl = "Trimisă la client" if o.get("trimisa_la_client") else str(o.get("status_oferta") or "Salvată")
            opt_oferte[oid] = f"#{oid} | {o.get('nume_firma')} | {o.get('data_oferta')} | {float(o.get('total_general') or 0.0):.2f} ({st_lbl})"

        c_load_sel, c_load_btn = st.columns([3.4, 1.2], vertical_alignment="bottom")
        with c_load_sel:
            sel_oid = st.selectbox(
                "Încarcă ofertă salvată pentru editare / revizuire PDF",
                options=list(opt_oferte.keys()),
                format_func=lambda x: opt_oferte.get(x, str(x)),
                key="oferta_select_incarcare_db",
            )
        with c_load_btn:
            if st.button("📂 Încarcă oferta", key="btn_incarca_oferta_db", use_container_width=True):
                if sel_oid == 0:
                    st.session_state["oferta_curenta_id"] = None
                    st.session_state["oferta_status"] = "Ciornă"
                    st.session_state["df_oferta_editor"] = pd.DataFrame(columns=COLS_OFERTA)
                    st.session_state["oferta_pdf_bytes"] = None
                    st.session_state["oferta_pdf_deschis"] = False
                    st.session_state["oferta_2_editor_counter"] = st.session_state.get("oferta_2_editor_counter", 0) + 1
                    st.rerun()
                else:
                    rec = _incarca_oferta_din_db(int(sel_oid))
                    if rec:
                        try:
                            linii_rec = json.loads(rec.get("linii_json") or "[]")
                        except Exception:
                            linii_rec = []
                        st.session_state["oferta_curenta_id"] = int(rec["id"])
                        st.session_state["oferta_status"] = str(rec.get("status_oferta") or "Salvată")
                        st.session_state["df_oferta_editor"] = pd.DataFrame(linii_rec, columns=COLS_OFERTA) if linii_rec else pd.DataFrame(columns=COLS_OFERTA)
                        st.session_state["oferta_2_disc_pct"] = float(rec.get("discount_pct") or 0.0)
                        st.session_state["oferta_2_disc_val"] = float(rec.get("discount_val") or 0.0)
                        if rec.get("cota_tva_pct") is not None:
                            st.session_state["oferta_2_tva_pct"] = float(rec["cota_tva_pct"])
                        st.session_state["oferta_pdf_bytes"] = None
                        st.session_state["oferta_pdf_deschis"] = False
                        st.session_state["oferta_2_editor_counter"] = st.session_state.get("oferta_2_editor_counter", 0) + 1
                        st.success(f"✅ Oferta #{rec['id']} a fost încărcată.")
                        st.rerun()

    oid_curent = st.session_state.get("oferta_curenta_id")
    status_curent = st.session_state.get("oferta_status", "Ciornă")
    st.caption(
        f"**Oferta curentă:** {f'#{oid_curent}' if oid_curent else 'Nesalvată încă'} | "
        f"**Status:** `{status_curent}`"
    )

    piese_all = PieseRepository.get_all() or []
    piese_dict: dict[str, dict] = {}
    for p in piese_all:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or p.get("cod_comercial") or "").strip()
        raw_p = p.get("pret_achizitie")
        mon = str(p.get("valuta_achizitie") or "").strip().upper()
        pret_lbl = f"{float(raw_p):.2f} {mon}".strip() if raw_p not in (None, "") else "preț lipsă"
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + f" — {pret_lbl}"
        piese_dict[eticheta] = p

    st.markdown("#### ➕ Adaugă piesă din catalog în ofertă")
    c_sel, c_cant, c_term, c_btn = st.columns([3.0, 1.0, 1.2, 1.2], vertical_alignment="bottom")
    with c_sel:
        opt_piese = ["-- Alege piesa --"] + list(piese_dict.keys())
    sel_piesa_catalog = st.selectbox(
        "Piesă din baza de date",
        options=opt_piese,
        key="oferta_2_sel_piesa",
        on_change=_actualizeaza_termen_din_piesa,
    )
    with c_cant:
        cant_piesa = st.number_input(
            "Cantitate",
            min_value=0.01,
            value=1.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_cant_piesa",
        )
    with c_term:
    termen_piesa = st.text_input(
        "Termen livrare",
        key="oferta_2_termen_piesa",
    )
    with c_btn:
        btn_add_piesa = st.button(
            "➕ Adaugă",
            type="primary",
            key="oferta_2_btn_add_piesa",
            use_container_width=True,
        )

    if btn_add_piesa:
        st.session_state["oferta_2_eroare_piesa"] = ""
        if sel_piesa_catalog == "-- Alege piesa --":
            st.session_state["oferta_2_eroare_piesa"] = "⚠️ Selectați mai întâi o piesă din catalog!"
        else:
            p_info = piese_dict[sel_piesa_catalog]
            ok_p, err_p, info_calc = valideaza_si_calculeaza_linie_oferta(
                piesa_catalog=p_info,
                cantitate=float(cant_piesa),
                adaos_comercial_pct=adaos_client,
            )
            if not ok_p or info_calc is None:
                st.session_state["oferta_2_eroare_piesa"] = f"⚠️ {err_p}"
            else:
                df_baza_p = _sincronizeaza_editor_inainte_de_adaugare()
                next_ord = len(df_baza_p) + 1
                termen_final = str(termen_piesa or p_info.get("termen_livrare") or "").strip()

                linie_piesa = pd.DataFrame([{
                    "Ordine": next_ord,
                    "Descriere": info_calc["desc"],
                    "UM": "buc",
                    "Cantitate": info_calc["cant"],
                    "Pret Unitar": info_calc["pret_vanzare"],
                    "Moneda": info_calc["moneda"],
                    "Termen livrare": termen_final,
                }])
                termen_final = str(termen_piesa or p_info.get("termen_livrare") or "").strip()
                st.session_state["df_oferta_editor"] = pd.concat(
                    [df_baza_p, linie_piesa],
                    ignore_index=True,
                )
                st.session_state["oferta_2_editor_counter"] = (
                    st.session_state.get("oferta_2_editor_counter", 0) + 1
                )

    if st.session_state.get("oferta_2_eroare_piesa"):
        st.error(st.session_state["oferta_2_eroare_piesa"])

    st.markdown("#### 🏷️ Adaugă din Grilă de Tarifare")
    grile_tarife = _construieste_grile_tarife()

    if not grile_tarife:
        st.info("Nu există tarife definite în **Setări → Tarife Standard**.")
    else:
        opt_grile = sorted(grile_tarife.keys())
        g_col1, g_col2, g_col3, g_col4, g_col5 = st.columns([1.4, 2.8, 1.0, 1.2, 1.2], vertical_alignment="bottom")

        with g_col1:
            sel_grila = st.selectbox(
                "Grilă tarifare",
                options=opt_grile,
                key="oferta_2_sel_grila_tarif",
            )

        tarife_in_grila = grile_tarife.get(sel_grila) or []
        mapa_tarife_grila: dict[str, dict] = {}
        for item_t in tarife_in_grila:
            raw_p = item_t.get("pret")
            pret_lbl = f"{float(raw_p):.2f}" if raw_p not in (None, "") else "preț lipsă"
            eticheta_t = f"{item_t['descriere']} — {pret_lbl} {item_t['moneda_um_raw']}".strip()
            mapa_tarife_grila[eticheta_t] = item_t

        with g_col2:
            opt_tarife = ["-- Alege tarif --"] + list(mapa_tarife_grila.keys())
            sel_tarif_lbl = st.selectbox(
                "Tarif / Activitate din grilă",
                options=opt_tarife,
                key="oferta_2_sel_tarif_grila",
            )

        with g_col3:
            cant_tarif = st.number_input(
                "Cantitate",
                min_value=0.01,
                value=1.0,
                step=1.0,
                format="%.2f",
                key="oferta_2_cant_tarif_grila",
            )

        with g_col4:
            termen_tarif = st.text_input(
                "Termen livrare",
                value="",
                placeholder="opțional",
                key="oferta_2_termen_tarif_grila",
            )

        with g_col5:
            btn_add_tarif = st.button(
                "➕ Adaugă tarif",
                key="oferta_2_btn_add_tarif_grila",
                use_container_width=True,
            )

        if btn_add_tarif:
            st.session_state["oferta_2_eroare_piesa"] = ""
            if sel_tarif_lbl == "-- Alege tarif --":
                st.session_state["oferta_2_eroare_piesa"] = "Selectați mai întâi un tarif din grila aleasă."
            else:
                t_info = mapa_tarife_grila[sel_tarif_lbl]
                raw_pret = t_info.get("pret")
                mon_t = str(t_info.get("moneda") or "").strip().upper()
                um_t = str(t_info.get("um") or "").strip()

                if raw_pret is None or str(raw_pret).strip() == "":
                    st.session_state["oferta_2_eroare_piesa"] = (
                        f"Lipsește prețul în grila «{sel_grila}» pentru «{t_info['descriere']}»."
                    )
                elif not mon_t:
                    st.session_state["oferta_2_eroare_piesa"] = (
                        f"Lipsește moneda în grila «{sel_grila}» pentru «{t_info['descriere']}»."
                    )
                else:
                    try:
                        pret_val = float(raw_pret)
                    except (TypeError, ValueError):
                        pret_val = -1.0

                    if pret_val < 0:
                        st.session_state["oferta_2_eroare_piesa"] = (
                            f"Prețul din grila «{sel_grila}» pentru «{t_info['descriere']}» nu este valid."
                        )
                    else:
                        df_baza_t = _sincronizeaza_editor_inainte_de_adaugare()
                        next_ord_t = len(df_baza_t) + 1
                        linie_tarif = pd.DataFrame([{
                            "Ordine": next_ord_t,
                            "Descriere": f"{t_info['descriere']} [{sel_grila}]",
                            "UM": um_t or "buc",
                            "Cantitate": float(cant_tarif),
                            "Pret Unitar": round(pret_val, 2),
                            "Moneda": mon_t,
                            "Termen livrare": str(termen_tarif or "").strip(),
                        }])
                        st.session_state["df_oferta_editor"] = pd.concat(
                            [df_baza_t, linie_tarif],
                            ignore_index=True,
                        )
                        st.session_state["oferta_2_editor_counter"] = (
                            st.session_state.get("oferta_2_editor_counter", 0) + 1
                        )

    st.markdown("#### 📋 Linii ofertă")
    df_init = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_init.columns:
            df_init[col] = None
    df_init = df_init[COLS_OFERTA]

    ed_key = f"oferta_2_data_editor_{st.session_state.get('oferta_2_editor_counter', 0)}"
    edited_df = st.data_editor(
        df_init,
        key=ed_key,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ordine": st.column_config.NumberColumn("Nr.", min_value=1, step=1, format="%d", width="small"),
            "Descriere": st.column_config.TextColumn("Descriere / Piesă / Serviciu", width="large", required=True),
            "UM": st.column_config.TextColumn("UM", width="small"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Pret Unitar": st.column_config.NumberColumn("Preț Vânzare", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Moneda": st.column_config.SelectboxColumn("Monedă", options=["RON", "EUR", "USD"], width="small"),
            "Termen livrare": st.column_config.TextColumn("Termen livrare", width="medium"),
        },
    )
    st.session_state["df_oferta_editor"] = edited_df

    st.markdown("#### 💶 Discounturi & TVA")
    d1, d2, d3 = st.columns(3)
    with d1:
        disc_pct = st.number_input(
            "Discount procentual (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_disc_pct",
        )
    with d2:
        disc_val = st.number_input(
            "Discount valoric",
            min_value=0.0,
            value=0.0,
            step=10.0,
            format="%.2f",
            key="oferta_2_disc_val",
        )
    with d3:
        cota_tva = st.number_input(
            "Cotă TVA (%)",
            min_value=0.0,
            max_value=100.0,
            value=cota_tva_implicita,
            step=1.0,
            format="%.2f",
            key="oferta_2_tva_pct",
        )

    curs_bnr = obtine_curs_bnr()
    ok_calc, lipsuri_calc, tot = calculeaza_oferta_fara_fallback(
        firma_obj=firma_obj,
        df_linii=edited_df,
        cota_tva_pct=cota_tva,
        discount_pct=disc_pct,
        discount_val=disc_val,
        curs_valutar=curs_bnr,
    )

    if ok_calc and tot is not None:
        st.markdown("#### 🧮 Valori calculate pe linie")
        st.dataframe(pd.DataFrame(tot["linii_valide"]), hide_index=True, use_container_width=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Subtotal (fără TVA)", f"{tot['subtotal']:.2f} {tot['moneda_principala']}")
        m2.metric("Total discounturi", f"{round(tot['discount_procent_val'] + tot['discount_valoric'], 2):.2f} {tot['moneda_principala']}")
        m3.metric(f"TVA ({float(cota_tva):g}%)", f"{tot['tva_valoare']:.2f} {tot['moneda_principala']}")
        m4.metric("Total General", f"{tot['total_general']:.2f} {tot['moneda_principala']}")
    else:
        st.warning("⚠️ Oferta nu poate fi calculată complet din cauza următoarelor lipsuri:")
        for msg in lipsuri_calc:
            st.markdown(f"- {msg}")

    st.divider()
    st.markdown("#### 💾 Salvare, PDF & Trimitere Client")

    nume_firma = str(firma_obj.get("nume_firma") or "").strip()
    firma_id = firma_obj.get("id")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💾 Salvează oferta în DB", type="primary", key="btn_salveaza_oferta_db", use_container_width=True):
            if not ok_calc or tot is None:
                st.error("⚠️ Nu pot salva oferta deoarece lipsesc valori obligatorii:")
                for msg in lipsuri_calc:
                    st.markdown(f"- {msg}")
            else:
                nou_id = _salveaza_oferta_in_db(
                    oferta_id=st.session_state.get("oferta_curenta_id"),
                    firma_id=firma_id,
                    nume_firma=nume_firma,
                    masina=masina_selectata,
                    data_oferta=data_oferta_str,
                    adaos_pct=tot["adaos_comercial_pct"],
                    discount_pct=disc_pct,
                    discount_val=disc_val,
                    cota_tva_pct=float(cota_tva),
                    tot=tot,
                    df_linii=edited_df,
                    status_oferta="Salvată",
                    trimisa_la_client=False,
                )
                st.session_state["oferta_curenta_id"] = nou_id
                st.session_state["oferta_status"] = "Salvată"
                st.success(f"✅ Oferta #{nou_id} a fost salvată în baza de date.")
                st.rerun()

    with b2:
        if st.button("📄 Generează & Vezi PDF", key="btn_genereaza_pdf_oferta", use_container_width=True):
            if not ok_calc or tot is None:
                st.error("⚠️ Nu pot genera PDF-ul deoarece lipsesc valori obligatorii:")
                for msg in lipsuri_calc:
                    st.markdown(f"- {msg}")
            else:
                era_deja_salvata = st.session_state.get("oferta_curenta_id") is not None
                nou_id = _salveaza_oferta_in_db(
                    oferta_id=st.session_state.get("oferta_curenta_id"),
                    firma_id=firma_id,
                    nume_firma=nume_firma,
                    masina=masina_selectata,
                    data_oferta=data_oferta_str,
                    adaos_pct=tot["adaos_comercial_pct"],
                    discount_pct=disc_pct,
                    discount_val=disc_val,
                    cota_tva_pct=float(cota_tva),
                    tot=tot,
                    df_linii=edited_df,
                    status_oferta=st.session_state.get("oferta_status", "Salvată"),
                    trimisa_la_client=(st.session_state.get("oferta_status") == "Verificată / Trimisă la client"),
                )
                st.session_state["oferta_curenta_id"] = nou_id

                payload_pdf = _construieste_payload_pdf_service(
                    oferta_id=nou_id,
                    firma_obj=firma_obj,
                    masina_selectata=masina_selectata,
                    data_oferta_str=data_oferta_str,
                    df_linii=edited_df,
                    disc_pct=disc_pct,
                    disc_val=disc_val,
                    cota_tva=float(cota_tva),
                    tot=tot,
                    curs_valutar=curs_bnr,
                    este_revizuita=era_deja_salvata,
                )
                try:
                    pdf_bytes = genereaza_pdf_oferta(payload_pdf)
                    st.session_state["oferta_pdf_bytes"] = pdf_bytes
                    st.session_state["oferta_pdf_deschis"] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"⚠️ Eroare la generarea PDF-ului: {exc}")

    with b3:
        if st.button("✅ Ofertă verificată — Trimite la client", key="btn_trimite_oferta_client", use_container_width=True):
            if not ok_calc or tot is None:
                st.error("⚠️ Nu pot trimite oferta deoarece lipsesc valori obligatorii:")
                for msg in lipsuri_calc:
                    st.markdown(f"- {msg}")
            else:
                data_trim = datetime.now().strftime("%Y-%m-%d %H:%M")
                nou_id = _salveaza_oferta_in_db(
                    oferta_id=st.session_state.get("oferta_curenta_id"),
                    firma_id=firma_id,
                    nume_firma=nume_firma,
                    masina=masina_selectata,
                    data_oferta=data_oferta_str,
                    adaos_pct=tot["adaos_comercial_pct"],
                    discount_pct=disc_pct,
                    discount_val=disc_val,
                    cota_tva_pct=float(cota_tva),
                    tot=tot,
                    df_linii=edited_df,
                    status_oferta="Verificată / Trimisă la client",
                    trimisa_la_client=True,
                    data_trimitere=data_trim,
                )
                st.session_state["oferta_curenta_id"] = nou_id
                st.session_state["oferta_status"] = "Verificată / Trimisă la client"
                st.success(f"📨 Oferta #{nou_id} a fost marcată ca **verificată și trimisă către client** ({data_trim}).")
                st.rerun()

    # Previzualizare PDF + închidere pentru revenire la modificări în tabel
    if st.session_state.get("oferta_pdf_deschis") and st.session_state.get("oferta_pdf_bytes"):
        st.markdown("#### 📑 Previzualizare PDF Ofertă")
        c_dl, c_close = st.columns([2.2, 1.4], vertical_alignment="center")
        nume_fisier_pdf = f"oferta_{st.session_state.get('oferta_curenta_id') or 'noua'}_{data_oferta_str}.pdf"
        with c_dl:
            st.download_button(
                "⬇️ Descarcă PDF",
                data=st.session_state["oferta_pdf_bytes"],
                file_name=nume_fisier_pdf,
                mime="application/pdf",
                key="btn_descarca_pdf_oferta",
                use_container_width=True,
            )
        with c_close:
            if st.button("❌ Închide PDF & Editează oferta", key="btn_inchide_pdf_oferta", use_container_width=True):
                st.session_state["oferta_pdf_deschis"] = False
                st.info("ℹ️ PDF-ul a fost închis. Poți modifica tabelul de ofertă, salva și genera din nou PDF-ul.")
                st.rerun()

        if hasattr(st, "pdf"):
            st.pdf(st.session_state["oferta_pdf_bytes"])
        else:
            st.info("ℹ️ Descarcă PDF-ul pentru verificare, apoi apasă **«❌ Închide PDF & Editează oferta»** dacă vrei să operezi modificări.")


def render_oferte():
    st.title("💼 Oferte de Preț")

    firme_db = FirmeRepository.get_all() or []
    firme_dict = {
        str(f.get("nume_firma") or "").strip(): f
        for f in firme_db
        if str(f.get("nume_firma") or "").strip()
    }
    if not firme_dict:
        st.warning("⚠️ Nu există firme înregistrate.")
        return

    masini_db = MasiniRepository.get_all() or []
    setari_firma = get_date_firma_mea() or {}
    raw_tva_setari = setari_firma.get("cota_tva")
    cota_tva_implicita = float(raw_tva_setari) if raw_tva_setari not in (None, "") else None

    c1, c2, c3 = st.columns([2.2, 2.2, 1.2], vertical_alignment="bottom")
    with c1:
        sel_firma = st.selectbox("Firmă client *", options=list(firme_dict.keys()), key="oferta_2_firma")
    firma_obj = firme_dict[sel_firma]
    fid = firma_obj.get("id")

    with c2:
        masini_firma = [
            str(m.get("denumire") or "").strip()
            for m in masini_db
            if str(m.get("denumire") or "").strip() and (fid is None or m.get("firma_id") == fid)
        ]
        opt_mas = ["-- Fără mașină --"] + sorted(set(masini_firma))
        masina_selectata = st.selectbox("Mașină / Utilaj", options=opt_mas, key="oferta_2_masina")

    ok_ad, eroare_adaos, adaos_client = _extrage_adaos_firma(firma_obj)

    with c3:
        data_oferta_str = date.today().isoformat()
        st.text_input("Data ofertă", value=data_oferta_str, disabled=True, key="oferta_2_data")

    _fragment_deviz_oferta(
        firma_obj=firma_obj,
        masina_selectata=masina_selectata,
        data_oferta_str=data_oferta_str,
        adaos_client=adaos_client if ok_ad else None,
        eroare_adaos=eroare_adaos,
        cota_tva_implicita=cota_tva_implicita,
    )
    
    
def _parseaza_moneda_um(moneda_um: str) -> tuple[str, str]:
    raw = str(moneda_um or "").strip()
    if "/" in raw:
        parte_mon, parte_um = raw.split("/", 1)
        return parte_mon.strip().upper(), parte_um.strip()
    return raw.upper(), "buc"


def _construieste_grile_tarife() -> dict[str, list[dict]]:
    tarife_all = TarifeRepository.get_all() or []
    grile: dict[str, list[dict]] = {}

    for t in tarife_all:
        desc = str(t.get("descriere") or "").strip()
        if not desc:
            continue
        nivel = str(t.get("nivel_grila") or "").strip() or "Fără nivel"
        moneda, um = _parseaza_moneda_um(t.get("moneda_um") or "")
        grile.setdefault(nivel, []).append({
            "id": t.get("id"),
            "descriere": desc,
            "pret": t.get("pret"),
            "moneda": moneda,
            "um": um,
            "nivel_grila": nivel,
            "moneda_um_raw": str(t.get("moneda_um") or "").strip(),
        })

    return grile