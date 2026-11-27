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
import io
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from config import db_cursor
from datetime import date, datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.tarife_repository import TarifeRepository
from services.pdf_service import genereaza_pdf_oferta, get_date_firma_mea
from services.sync_service import sync_oferta_in_fundal


COLS_OFERTA = [
    "Ordine",
    "Descriere",
    "UM",
    "Cantitate",
    "Pret Unitar",
    "Discount (%)",
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
                moneda_oferta TEXT DEFAULT 'EUR',
                curs_valutar DOUBLE PRECISION DEFAULT 0.0,
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
        cur.execute("ALTER TABLE oferte_client ADD COLUMN IF NOT EXISTS moneda_oferta TEXT DEFAULT 'EUR'")
        cur.execute("ALTER TABLE oferte_client ADD COLUMN IF NOT EXISTS curs_valutar DOUBLE PRECISION DEFAULT 0.0")


def _salveaza_oferta_in_db(
    oferta_id: int | None,
    firma_id,
    nume_firma: str,
    masina: str,
    data_oferta: str,
    moneda_oferta: str,
    curs_valutar: float | None,
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
        raw_disc_linie = r.get("Discount (%)")
        disc_linie = (
            0.0
            if (raw_disc_linie is None or pd.isna(raw_disc_linie) or str(raw_disc_linie).strip() == "")
            else float(raw_disc_linie)
        )

        linii_clean.append({
            "Ordine": int(r.get("Ordine") or (idx + 1)),
            "Descriere": desc,
            "UM": str(r.get("UM") or "buc").strip() or "buc",
            "Cantitate": float(r.get("Cantitate")),
            "Pret Unitar": round(float(r.get("Pret Unitar")), 2),
            "Discount (%)": round(disc_linie, 2),
            "Moneda": str(r.get("Moneda")).strip().upper(),
            "Termen livrare": str(r.get("Termen livrare") or "").strip(),
        })

    linii_json = json.dumps(linii_clean, ensure_ascii=False)
    fid_int = int(firma_id) if firma_id is not None else None
    curs_float = float(curs_valutar) if curs_valutar else 0.0

    with db_cursor() as cur:
        if oferta_id is not None:
            cur.execute(
                """
                UPDATE oferte_client
                SET firma_id = %s,
                    nume_firma = %s,
                    masina = %s,
                    data_oferta = %s,
                    moneda_oferta = %s,
                    curs_valutar = %s,
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
                    moneda_oferta,
                    curs_float,
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
                    moneda_oferta, curs_valutar,
                    adaos_comercial_pct, discount_pct, discount_val, cota_tva_pct,
                    subtotal, total_general, status_oferta, trimisa_la_client,
                    data_trimitere, linii_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    fid_int,
                    nume_firma,
                    masina,
                    data_oferta,
                    moneda_oferta,
                    curs_float,
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

def _normalizeaza_nume_firma(nume: str | None) -> str:
    txt = str(nume or "").strip().lower()
    txt = re.sub(r"[^a-z0-9ăâîșț]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _listeaza_oferte_salvate(
    firma_id=None,
    nume_firma: str | None = None,
    masina: str | None = None,
    limit: int = 30,
) -> list[dict]:
    _asigura_tabel_oferte_db()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, firma_id, nume_firma, masina, data_oferta, moneda_oferta,
                   total_general, status_oferta, trimisa_la_client, data_trimitere
            FROM oferte_client
            ORDER BY id DESC
            """
        )
        rows = cur.fetchall() or []
        cols = [d[0] for d in cur.description] if cur.description else []
        toate = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in rows]

    nume_tinta_norm = _normalizeaza_nume_firma(nume_firma)
    masina_tinta_norm = _normalizeaza_nume_firma(masina)
    are_filtru_masina = bool(
        masina and str(masina).strip() and str(masina).strip() != "-- Fără mașină --"
    )

    filtrate: list[dict] = []
    for o in toate:
        o_fid = o.get("firma_id")
        o_nume_norm = _normalizeaza_nume_firma(o.get("nume_firma"))

        match_firma = False
        if firma_id is not None and o_fid is not None:
            try:
                if int(o_fid) == int(firma_id):
                    match_firma = True
            except (TypeError, ValueError):
                pass

        if not match_firma and nume_tinta_norm and o_nume_norm:
            if o_nume_norm == nume_tinta_norm:
                match_firma = True

        if not match_firma:
            continue

        if are_filtru_masina:
            o_masina_norm = _normalizeaza_nume_firma(o.get("masina"))
            if o_masina_norm != masina_tinta_norm:
                continue

        filtrate.append(o)
        if len(filtrate) >= int(limit):
            break

    return filtrate

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
            df_base[col] = 0.0 if col == "Discount (%)" else None
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


def _converteste_suma_moneda(
    suma: float,
    moneda_sursa: str,
    moneda_tinta: str,
    curs_eur_ron: float | None,
) -> tuple[bool, float]:
    sursa = moneda_sursa.strip().upper()
    tinta = moneda_tinta.strip().upper()
    if sursa == tinta:
        return True, suma
    if curs_eur_ron is None or float(curs_eur_ron) <= 0:
        return False, 0.0
    curs = float(curs_eur_ron)
    if sursa == "EUR" and tinta == "RON":
        return True, suma * curs
    if sursa == "RON" and tinta == "EUR":
        return True, suma / curs
    return False, 0.0


def calculeaza_oferta_fara_fallback(
    firma_obj: dict,
    df_linii: pd.DataFrame,
    cota_tva_pct,
    moneda_oferta: str = "EUR",
    discount_pct: float = 0.0,
    discount_val: float = 0.0,
    curs_valutar: float | None = None,
) -> tuple[bool, list[str], dict | None]:
    """Calculează totalurile ofertei în moneda selectată (EUR/RON), incluzând discount pe reper."""
    lipsuri: list[str] = []
    moneda_tinta = str(moneda_oferta or "EUR").strip().upper()

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
    total_discount_repere = 0.0
    monede_diferite_detectate: set[str] = set()
    linii_valide: list[dict] = []

    if df_linii is None or df_linii.empty:
        lipsuri.append("Oferta nu conține nicio linie.")
    else:
        for idx, row in df_linii.iterrows():
            desc = str(row.get("Descriere") or "").strip()
            raw_cant = row.get("Cantitate")
            raw_pret = row.get("Pret Unitar")
            raw_disc_linie = row.get("Discount (%)")
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

            disc_linie_pct = 0.0
            if raw_disc_linie is not None and str(raw_disc_linie).strip() != "" and not pd.isna(raw_disc_linie):
                try:
                    disc_linie_pct = float(raw_disc_linie)
                    if disc_linie_pct < 0 or disc_linie_pct > 100:
                        lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Discount (%)» trebuie să fie între 0 și 100.")
                        rand_ok = False
                except (TypeError, ValueError):
                    lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): «Discount (%)» nu este numeric.")
                    rand_ok = False

            if not mon:
                lipsuri.append(f"Rândul {nr_rand} ({desc or 'fără descriere'}): lipsește «Moneda».")
                rand_ok = False
            elif mon != moneda_tinta:
                monede_diferite_detectate.add(mon)

            if rand_ok and cant is not None and pret is not None:
                ok_conv, pret_unitar_conv = _converteste_suma_moneda(pret, mon, moneda_tinta, curs_valutar)
                if not ok_conv:
                    lipsuri.append(
                        f"Rândul {nr_rand} ({desc}): nu se poate converti din {mon} în {moneda_tinta} fără un curs valutar valid."
                    )
                    continue

                pret_unitar_conv_r = round(pret_unitar_conv, 2)
                val_bruta_linie = round(cant * pret_unitar_conv_r, 2)
                val_disc_linie = round(val_bruta_linie * (disc_linie_pct / 100.0), 2)
                val_neta_linie = round(val_bruta_linie - val_disc_linie, 2)
                pret_net_unitar = round(pret_unitar_conv_r * (1.0 - disc_linie_pct / 100.0), 2)

                subtotal += val_neta_linie
                total_discount_repere += val_disc_linie

                linii_valide.append({
                    "Nr.": int(row.get("Ordine") or nr_rand),
                    "Descriere": desc,
                    "UM": str(row.get("UM") or "buc").strip() or "buc",
                    "Cantitate": cant,
                    f"Preț Unitar ({moneda_tinta})": pret_unitar_conv_r,
                    "Discount (%)": round(disc_linie_pct, 2),
                    f"Preț Net ({moneda_tinta})": pret_net_unitar,
                    f"Valoare ({moneda_tinta})": val_neta_linie,
                    "Monedă sursă": mon,
                    "Termen livrare": str(row.get("Termen livrare") or "").strip(),
                    "_pret_unitar_conv": pret_unitar_conv_r,
                    "_pret_net_unitar": pret_net_unitar,
                    "_valoare_neta": val_neta_linie,
                    "_valoare_discount_linie": val_disc_linie,
                })

    if not linii_valide and not lipsuri:
        lipsuri.append("Oferta nu conține nicio linie validă.")

    if monede_diferite_detectate and (curs_valutar is None or float(curs_valutar) <= 0):
        msg_curs = (
            f"Există linii în altă monedă decât {moneda_tinta} ({', '.join(sorted(monede_diferite_detectate))}) "
            "și lipsește cursul valutar pentru conversie."
        )
        if msg_curs not in lipsuri:
            lipsuri.append(msg_curs)

    if lipsuri:
        return False, lipsuri, None

    subtotal = round(subtotal, 2)
    total_discount_repere = round(total_discount_repere, 2)
    disc_pct_val = round(subtotal * max(0.0, float(discount_pct or 0.0)) / 100.0, 2)
    disc_val_fix = max(0.0, round(float(discount_val or 0.0), 2))
    baza = max(0.0, round(subtotal - disc_pct_val - disc_val_fix, 2))
    tva_val = round(baza * (tva_pct / 100.0), 2)
    total_gen = round(baza + tva_val, 2)

    return True, [], {
        "adaos_comercial_pct": adaos,
        "moneda_principala": moneda_tinta,
        "linii_valide": linii_valide,
        "subtotal": subtotal,
        "discount_repere_val": total_discount_repere,
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
    disc_pct: float,
    disc_val: float,
    cota_tva: float,
    tot: dict,
    curs_valutar: float | None,
    este_revizuita: bool,
) -> dict:
    moneda_oferta = tot["moneda_principala"]
    articole_pdf = []
    for lin in tot["linii_valide"]:
        disc_l = float(lin.get("Discount (%)") or 0.0)
        pret_pt_pdf = lin["_pret_net_unitar"] if disc_l > 0 else lin["_pret_unitar_conv"]
        desc_pdf = lin["Descriere"]
        if disc_l > 0:
            desc_pdf = f"{desc_pdf} (disc. {disc_l:g}%)"

        articole_pdf.append({
            "Ordine": lin["Nr."],
            "Descriere": desc_pdf,
            "UM": lin["UM"],
            "Cantitate": lin["Cantitate"],
            "Pret Unitar": pret_pt_pdf,
            f"Pret Unitar ({moneda_oferta})": pret_pt_pdf,
            "Discount (%)": disc_l,
            "Termen livrare": lin["Termen livrare"],
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
    moneda_oferta: str,
    curs_valutar_activ: float | None,
    adaos_client: float | None,
    eroare_adaos: str,
    cota_tva_implicita: float,
):
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    st.session_state.setdefault("oferta_2_editor_counter", 0)
    st.session_state.setdefault("oferta_2_eroare_piesa", "")
    st.session_state.setdefault("oferta_curenta_id", None)
    st.session_state.setdefault("oferta_status", "Ciornă")
    st.session_state.setdefault("oferta_pdf_bytes", None)
    st.session_state.setdefault("oferta_pdf_deschis", False)
    st.session_state.setdefault("oferta_2_termen_piesa", "")

    if eroare_adaos:
        st.error(f"⚠️ {eroare_adaos}")

    nume_firma = str(firma_obj.get("nume_firma") or "").strip()
    firma_id = firma_obj.get("id")

    # Istoric oferte salvate filtrat după firmă și opțional după mașina selectată
    are_masina_selectata = bool(masina_selectata and masina_selectata != "-- Fără mașină --")
    filtreaza_dupa_masina = True
    if are_masina_selectata:
        filtreaza_dupa_masina = st.checkbox(
            f"Filtrează istoricul doar pentru utilajul «{masina_selectata}»",
            value=True,
            key="oferta_filtreaza_istoric_masina",
        )

    oferte_salvate = _listeaza_oferte_salvate(
        firma_id=firma_id,
        nume_firma=nume_firma,
        masina=masina_selectata if (are_masina_selectata and filtreaza_dupa_masina) else None,
        limit=30,
    )

    opt_oferte = {0: "-- Ofertă nouă --"}
    for o in oferte_salvate:
        oid = int(o["id"])
        st_lbl = "Trimisă la client" if o.get("trimisa_la_client") else str(o.get("status_oferta") or "Salvată")
        mon_lbl = str(o.get("moneda_oferta") or "EUR")
        mas_lbl = str(o.get("masina") or "").strip()
        mas_txt = f" | {mas_lbl}" if mas_lbl and mas_lbl != "-- Fără mașină --" else ""
        opt_oferte[oid] = (
            f"#{oid} | {o.get('nume_firma')}{mas_txt} | {o.get('data_oferta')} | "
            f"{float(o.get('total_general') or 0.0):.2f} {mon_lbl} ({st_lbl})"
        )

    c_load_sel, c_load_btn = st.columns([3.4, 1.2], vertical_alignment="bottom")
    with c_load_sel:
        sel_oid = st.selectbox(
            f"Încarcă ofertă salvată ({nume_firma})",
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
                mas_rec = str(rec.get("masina") or "").strip()
                if mas_rec and mas_rec != "-- Fără mașină --":
                    st.session_state["oferta_2_masina_incarcata"] = mas_rec
                else:
                    st.session_state["oferta_2_masina_incarcata"] = None
                if rec:
                    try:
                        linii_rec = json.loads(rec.get("linii_json") or "[]")
                    except Exception:
                        linii_rec = []
                    df_loaded = pd.DataFrame(linii_rec) if linii_rec else pd.DataFrame(columns=COLS_OFERTA)
                    for col in COLS_OFERTA:
                        if col not in df_loaded.columns:
                            df_loaded[col] = 0.0 if col == "Discount (%)" else ""
                    df_loaded = df_loaded[COLS_OFERTA]

                    st.session_state["oferta_curenta_id"] = int(rec["id"])
                    st.session_state["oferta_status"] = str(rec.get("status_oferta") or "Salvată")
                    st.session_state["df_oferta_editor"] = df_loaded
                    if rec.get("moneda_oferta") in ("EUR", "RON"):
                        st.session_state["oferta_2_moneda_oferta"] = rec["moneda_oferta"]
                    if rec.get("curs_valutar") and float(rec["curs_valutar"]) > 0:
                        st.session_state["oferta_2_curs_valutar"] = float(rec["curs_valutar"])
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
        f"**Status:** `{status_curent}` | "
        f"**Monedă ofertă:** `{moneda_oferta}`"
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

    def _actualizeaza_termen_din_piesa():
        piesa_cheie = st.session_state.get("oferta_2_sel_piesa")
        piesa_info = piese_dict.get(piesa_cheie) if isinstance(piesa_cheie, str) else None
        if piesa_info:
            st.session_state["oferta_2_termen_piesa"] = str(piesa_info.get("termen_livrare") or "").strip()
        else:
            st.session_state["oferta_2_termen_piesa"] = ""

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
                    "Discount (%)": 0.0,
                    "Moneda": info_calc["moneda"],
                    "Termen livrare": termen_final,
                }])
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
        nivele_din_db = sorted(
            str(n).strip()
            for n in grile_tarife.keys()
            if str(n).strip()
        )
        opt_grile = ["Toate grilele"] + nivele_din_db

        g_col1, g_col2, g_col3, g_col4, g_col5 = st.columns(
            [1.0, 3.6, 0.75, 1.15, 1.1],
            vertical_alignment="bottom",
        )

        with g_col1:
            sel_grila = st.selectbox(
                "Grilă tarifare",
                options=opt_grile,
                key="oferta_2_sel_grila_tarif",
            )

        if sel_grila == "Toate grilele":
            tarife_in_grila = [
                item_t
                for lista_niv in grile_tarife.values()
                for item_t in lista_niv
            ]
        else:
            tarife_in_grila = grile_tarife.get(sel_grila) or []

        mapa_tarife_grila: dict[str, dict] = {}
        for item_t in tarife_in_grila:
            raw_p = item_t.get("pret")
            pret_lbl = f"{float(raw_p):.2f}" if raw_p not in (None, "") else "preț lipsă"
            niv_lbl = f" [{item_t['nivel_grila']}]" if sel_grila == "Toate grilele" else ""
            eticheta_t = f"{item_t['descriere']}{niv_lbl} — {pret_lbl} {item_t['moneda_um_raw']}".strip()
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
                "Cant.",
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
                nivel_efectiv = t_info.get("nivel_grila") or sel_grila
                raw_pret = t_info.get("pret")
                mon_t = str(t_info.get("moneda") or "").strip().upper()
                um_t = str(t_info.get("um") or "").strip()

                if raw_pret is None or str(raw_pret).strip() == "":
                    st.session_state["oferta_2_eroare_piesa"] = (
                        f"Lipsește prețul în grila «{nivel_efectiv}» pentru «{t_info['descriere']}»."
                    )
                elif not mon_t:
                    st.session_state["oferta_2_eroare_piesa"] = (
                        f"Lipsește moneda în grila «{nivel_efectiv}» pentru «{t_info['descriere']}»."
                    )
                else:
                    try:
                        pret_val = float(raw_pret)
                    except (TypeError, ValueError):
                        pret_val = -1.0

                    if pret_val < 0:
                        st.session_state["oferta_2_eroare_piesa"] = (
                            f"Prețul din grila «{nivel_efectiv}» pentru «{t_info['descriere']}» nu este valid."
                        )
                    else:
                        df_baza_t = _sincronizeaza_editor_inainte_de_adaugare()
                        next_ord_t = len(df_baza_t) + 1
                        linie_tarif = pd.DataFrame([{
                            "Ordine": next_ord_t,
                            "Descriere": f"{t_info['descriere']} [{nivel_efectiv}]",
                            "UM": um_t or "buc",
                            "Cantitate": float(cant_tarif),
                            "Pret Unitar": round(pret_val, 2),
                            "Discount (%)": 0.0,
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
    st.caption("💡 Poți aplica **Disc. reper (%)** individual pe fiecare reper direct în tabel.")
    df_init = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_init.columns:
            df_init[col] = 0.0 if col == "Discount (%)" else None
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
            "Discount (%)": st.column_config.NumberColumn(
                "Disc. reper (%)",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                format="%.2f",
                default=0.0,
                width="small",
            ),
            "Moneda": st.column_config.SelectboxColumn("Monedă", options=["RON", "EUR"], width="small"),
            "Termen livrare": st.column_config.TextColumn("Termen livrare", width="medium"),
        },
    )
    st.session_state["df_oferta_editor"] = edited_df

    st.markdown("#### 💶 Discounturi globale & TVA")
    d1, d2, d3 = st.columns(3)
    with d1:
        disc_pct = st.number_input(
            "Discount global procentual (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_disc_pct",
        )
    with d2:
        disc_val = st.number_input(
            f"Discount global valoric ({moneda_oferta})",
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

    ok_calc, lipsuri_calc, tot = calculeaza_oferta_fara_fallback(
        firma_obj=firma_obj,
        df_linii=edited_df,
        cota_tva_pct=cota_tva,
        moneda_oferta=moneda_oferta,
        discount_pct=disc_pct,
        discount_val=disc_val,
        curs_valutar=curs_valutar_activ,
    )

    if ok_calc and tot is not None:
        st.markdown(f"#### 🧮 Valori calculate pe linie ({moneda_oferta})")
        coloane_afisare = [
            "Nr.",
            "Descriere",
            "UM",
            "Cantitate",
            f"Preț Unitar ({moneda_oferta})",
            "Discount (%)",
            f"Preț Net ({moneda_oferta})",
            f"Valoare ({moneda_oferta})",
            "Monedă sursă",
            "Termen livrare",
        ]
        df_preview = pd.DataFrame(tot["linii_valide"])[coloane_afisare]
        st.dataframe(df_preview, hide_index=True, use_container_width=True)

        total_disc_global = round(tot["discount_procent_val"] + tot["discount_valoric"], 2)
        total_disc_cumulat = round(tot["discount_repere_val"] + total_disc_global, 2)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Subtotal net (fără TVA)", f"{tot['subtotal']:.2f} {moneda_oferta}")
        m2.metric(
            "Total discounturi",
            f"{total_disc_cumulat:.2f} {moneda_oferta}",
            help=f"Repere: {tot['discount_repere_val']:.2f} {moneda_oferta} | Global: {total_disc_global:.2f} {moneda_oferta}",
        )
        m3.metric(f"TVA ({float(cota_tva):g}%)", f"{tot['tva_valoare']:.2f} {moneda_oferta}")
        m4.metric("Total General", f"{tot['total_general']:.2f} {moneda_oferta}")
    else:
        st.warning("⚠️ Oferta nu poate fi calculată complet din cauza următoarelor lipsuri:")
        for msg in lipsuri_calc:
            st.markdown(f"- {msg}")

    # ----------------bloc semnatura--------------
    
    st.session_state.setdefault("semnatura_nexus_counter", 0)

    with st.expander("✍️ Semnătură", expanded=False):
        st.caption("Opțional — desenează semnătura Nexus Industrial pe ecran tactil.")

        col_clear, _ = st.columns([1.4, 3.6])
        with col_clear:
            if st.button("🗑️ Golește semnătura", key="btn_goleste_semnatura_nexus", use_container_width=True):
                st.session_state["semnatura_nexus_counter"] += 1
                st.rerun()

        canvas_key = f"canvas_semnatura_nexus_{st.session_state['semnatura_nexus_counter']}"
        canvas_semnatura = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=3,
            stroke_color="#0F172A",
            background_color="#FFFFFF",
            height=130,
            width=360,
            drawing_mode="freedraw",
            return_image_data=True,
            key=canvas_key,
        )

    semnatura_bytes = None
    img_arr = getattr(canvas_semnatura, "image_data", None)
    if img_arr is not None and getattr(img_arr, "size", 0) > 0:
        if (img_arr[:, :, :3] < 250).any():
            img_pil = Image.fromarray(img_arr.astype("uint8"), "RGBA")
            buf_sig = io.BytesIO()
            img_pil.save(buf_sig, format="PNG")
            semnatura_bytes = buf_sig.getvalue()
        
    #---------------------------------------------

    st.divider()
    st.markdown("#### 💾 Salvare, PDF & Trimitere Client")

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
                    moneda_oferta=moneda_oferta,
                    curs_valutar=curs_valutar_activ,
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
                st.success(f"✅ Oferta #{nou_id} ({moneda_oferta}) a fost salvată în baza de date.")
                st.rerun()

    with b2:
        oid_key = st.session_state.get("oferta_curenta_id") or "noua"
        if st.button("📄 Generează PDF", key=f"btn_genereaza_pdf_oferta_{oid_key}", use_container_width=True):
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
                    moneda_oferta=moneda_oferta,
                    curs_valutar=curs_valutar_activ,
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
                    disc_pct=disc_pct,
                    disc_val=disc_val,
                    cota_tva=float(cota_tva),
                    tot=tot,
                    curs_valutar=curs_valutar_activ,
                    este_revizuita=era_deja_salvata,
                )
                payload_pdf["semnatura_emitent_png"] = semnatura_bytes

                try:
                    sync_oferta_in_fundal({
                        "id": nou_id,
                        "numar_oferta": nou_id,
                        "data": data_oferta_str,
                        "client": nume_firma,
                        "titlu": f"Ofertă #{nou_id}" + (
                            f" — {masina_selectata}"
                            if masina_selectata and masina_selectata != "-- Fără mașină --"
                            else ""
                        ),
                        "moneda": moneda_oferta,
                        "total_general": tot["total_general"],
                        "status": "Revizuită" if era_deja_salvata else "Emisă",
                        "articole": payload_pdf["articole"],
                        "intocmit_de": "",
                        "valabilitate": "",
                    })
                except Exception as exc_sync:
                    st.warning(f"⚠️ Sincronizarea nu a reușit: {exc_sync}")

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
                    moneda_oferta=moneda_oferta,
                    curs_valutar=curs_valutar_activ,
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

    if st.session_state.get("oferta_pdf_deschis") and st.session_state.get("oferta_pdf_bytes"):
        st.success("✅ PDF-ul ofertei este pregătit. Descarcă-l pentru verificare, apoi apasă pe **«✅ Ofertă verificată — Trimite la client»** sau modifică tabelul și regenerează.")
        c_dl, c_close = st.columns([2.2, 1.4], vertical_alignment="center")
        nume_fisier_pdf = f"oferta_{st.session_state.get('oferta_curenta_id') or 'noua'}_{moneda_oferta}_{data_oferta_str}.pdf"
        with c_dl:
            st.download_button(
                "⬇️ Descarcă PDF",
                data=st.session_state["oferta_pdf_bytes"],
                file_name=nume_fisier_pdf,
                mime="application/pdf",
                key="btn_descarca_pdf_oferta",
                type="primary",
                use_container_width=True,
            )
        with c_close:
            if st.button("✖️ Ascunde descărcarea", key="btn_inchide_pdf_oferta", use_container_width=True):
                st.session_state["oferta_pdf_deschis"] = False
                st.session_state["oferta_pdf_bytes"] = None
                st.rerun()


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
    cota_tva_implicita = float(raw_tva_setari) if raw_tva_setari not in (None, "") else 0.0

    if "oferta_2_curs_valutar" not in st.session_state:
        curs_init = obtine_curs_bnr()
        st.session_state["oferta_2_curs_valutar"] = float(curs_init) if curs_init else 0.0

    st.session_state.setdefault("oferta_2_moneda_oferta", "EUR")

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
        mas_preincarcata = st.session_state.pop("oferta_2_masina_incarcata", None)
        if mas_preincarcata and mas_preincarcata in opt_mas:
            st.session_state["oferta_2_masina"] = mas_preincarcata
        masina_selectata = st.selectbox("Mașină / Utilaj", options=opt_mas, key="oferta_2_masina")

    ok_ad, eroare_adaos, adaos_client = _extrage_adaos_firma(firma_obj)

    with c3:
        data_oferta_str = date.today().isoformat()
        st.text_input("Data ofertă", value=data_oferta_str, disabled=True, key="oferta_2_data")

    # Rând dedicat pentru moneda finală a ofertei și cursul valutar BNR
    v1, v2, v3 = st.columns([1.4, 1.4, 1.6], vertical_alignment="bottom")
    with v1:
        moneda_oferta = st.selectbox(
            "Monedă ofertă finală",
            options=["EUR", "RON"],
            key="oferta_2_moneda_oferta",
        )
    with v2:
        curs_valutar_input = st.number_input(
            "Curs EUR / RON",
            min_value=0.0,
            step=0.0001,
            format="%.4f",
            key="oferta_2_curs_valutar",
        )
    with v3:
        if st.button("🔄 Actualizează curs valutar", key="btn_actualizeaza_curs_bnr", use_container_width=True):
            obtine_curs_bnr.clear()
            curs_nou = obtine_curs_bnr()
            if curs_nou and curs_nou > 0:
                st.session_state["oferta_2_curs_valutar"] = float(curs_nou)
                st.success(f"✅ Curs BNR actualizat: 1 EUR = {curs_nou:.4f} RON")
                st.rerun()
            else:
                st.warning("⚠️ Nu s-a putut prelua cursul BNR online. Poți introduce cursul manual.")

    curs_valutar_activ = (
        float(curs_valutar_input)
        if curs_valutar_input is not None and float(curs_valutar_input) > 0
        else None
    )

    _fragment_deviz_oferta(
        firma_obj=firma_obj,
        masina_selectata=masina_selectata,
        data_oferta_str=data_oferta_str,
        moneda_oferta=moneda_oferta,
        curs_valutar_activ=curs_valutar_activ,
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
