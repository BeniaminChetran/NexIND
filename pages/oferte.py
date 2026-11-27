# ------------------------------------------------
# --- pages/oferte.py ----------------------------
# ------------------------------------------------

from datetime import date, datetime
import json
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from services.pdf_service import genereaza_pdf_oferta, get_date_firma_mea


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
                    st.session_state["oferta_status"] = "Ciornă