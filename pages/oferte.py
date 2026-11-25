# ----------------------------------
# -------pages/oferte.py------------
# ----------------------------------

from datetime import date
import json
import re
import ssl
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.fraze_repository import FrazeRepository
from repositories.masini_repository import MasiniRepository
from repositories.note_comanda_repository import (
    OPTIUNI_STARE_NOTA_COMANDA,
    NoteComandaRepository,
    normalizeaza_stare_nota_comanda,
)
from repositories.oferte_repository import OferteRepository
from repositories.piese_repository import PieseRepository
from repositories.setari_repository import SetariRepository
from repositories.tarife_repository import TarifeRepository
from services.pdf_service import genereaza_pdf_oferta
from services.sync_service import sync_oferta_in_fundal
from utils.draft_state import init_draft, lega_camp, reset_draft, sync_camp, widget_key

MAX_ORE_TRANSPORT_ZI = 10.0

COLOANE_OFERTA_EDITOR = [
    "Ordine",
    "Descriere",
    "UM",
    "Cantitate",
    "Pret Unitar",
    "Moneda",
    "Termen livrare",
]

_MAPARE_UM = {
    "ora": "ore",
    "oră": "ore",
    "ore": "ore",
    "buc": "buc",
    "bucata": "buc",
    "bucăți": "buc",
    "km": "km",
    "set": "set",
    "ml": "ml",
    "kg": "kg",
}

_CHEI_PERSOANA_CONTACT = (
    "nume_persoana",
    "persoana_contact",
    "pers_contact",
    "persoana",
    "contact",
    "reprezentant",
    "nume_contact",
)


def _df_oferta_gol() -> pd.DataFrame:
    return pd.DataFrame(columns=COLOANE_OFERTA_EDITOR)


def _asigura_df_oferta_editor() -> pd.DataFrame:
    df_ex = st.session_state.get("df_oferta_editor")
    if not isinstance(df_ex, pd.DataFrame):
        df_nou = _df_oferta_gol()
        st.session_state["df_oferta_editor"] = df_nou
        return df_nou

    df_work = df_ex.copy()
    schimbat = False
    if "Pret Unitar (RON)" in df_work.columns and "Pret Unitar" not in df_work.columns:
        df_work = df_work.rename(columns={"Pret Unitar (RON)": "Pret Unitar"})
        schimbat = True
    if "Moneda" not in df_work.columns:
        df_work["Moneda"] = "RON"
        schimbat = True
    if "Ordine" not in df_work.columns:
        df_work.insert(0, "Ordine", range(1, len(df_work) + 1))
        schimbat = True

    df_work = df_work.reset_index(drop=True)
    if schimbat:
        st.session_state["df_oferta_editor"] = df_work
    return df_work


def _asigura_mapare_furnizori_oferta() -> dict[str, dict]:
    """Păstrează legătura (furnizor, cod_piesa, pret_furnizor, moneda_furnizor) pentru descrierile din ofertă."""
    mp = st.session_state.get("oferta_furnizori_map")
    if not isinstance(mp, dict):
        mp = {}
        st.session_state["oferta_furnizori_map"] = mp
    return mp


@st.cache_data(ttl=120, show_spinner=False)
def _incarca_oferte_primite_furnizori() -> list[dict]:
    """Citește liniile primite de la furnizori din `cereri_oferta_linii` + `cereri_oferta`."""
    try:
        with db_cursor() as c:
            c.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cereri_oferta_linii'
                """
            )
            cols_lin = {
                (r["column_name"] if isinstance(r, dict) else r[0])
                for r in (c.fetchall() or [])
            }
            if not cols_lin:
                return []

            c.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cereri_oferta'
                """
            )
            cols_cer = {
                (r["column_name"] if isinstance(r, dict) else r[0])
                for r in (c.fetchall() or [])
            }

            if cols_cer:
                sel_cod = "co.cod_cerere" if "cod_cerere" in cols_cer else "'' AS cod_cerere"
                sel_cli = "co.firma_nume" if "firma_nume" in cols_cer else "'' AS firma_nume"
                sel_mas = "co.masina_nume" if "masina_nume" in cols_cer else "'' AS masina_nume"
                sel_st = "co.status_cerere" if "status_cerere" in cols_cer else "'' AS status_cerere"
                c.execute(
                    f"""
                    SELECT
                        col.*,
                        {sel_cod},
                        {sel_cli},
                        {sel_mas},
                        {sel_st}
                    FROM cereri_oferta_linii col
                    LEFT JOIN cereri_oferta co ON co.id = col.cerere_id
                    ORDER BY col.cerere_id DESC, col.id ASC
                    """
                )
            else:
                c.execute("SELECT * FROM cereri_oferta_linii ORDER BY id DESC")

            rows = [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        return []

    rezultat: list[dict] = []
    for r in rows:
        den = str(r.get("denumire_piesa") or "").strip()
        if not den:
            continue
        mon = str(r.get("moneda") or "EUR").strip().upper()
        if mon not in ("EUR", "RON"):
            mon = "EUR"
        rezultat.append({
            "linie_id": r.get("id"),
            "cerere_id": r.get("cerere_id"),
            "cod_cerere": str(r.get("cod_cerere") or "").strip(),
            "client_nume": str(r.get("firma_nume") or "").strip(),
            "masina_nume": str(r.get("masina_nume") or "").strip(),
            "status_cerere": str(r.get("status_cerere") or "").strip(),
            "furnizor_nume": str(r.get("furnizor_nume") or "").strip() or "Furnizor nespecificat",
            "piesa_denumire": den,
            "cod_piesa": str(r.get("cod_producator") or "").strip(),
            "piese_inlocuitoare": str(r.get("piese_inlocuitoare") or "").strip(),
            "cantitate": float(r.get("cantitate") or 1.0),
            "pret_furnizor": float(r.get("pret_unitar") or 0.0),
            "moneda": mon,
            "termen_livrare": str(r.get("termen_livrare_zile") or "1").strip() or "1",
            "selectat_initial": bool(r.get("selectat_pentru_client", False)),
        })
    return rezultat


@st.cache_data(ttl=3600)
def obtine_curs_bnr() -> float:
    headers_browser = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/xml,text/xml,text/html,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    }
    ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request("https://www.bnr.ro/nbrfxrates.xml", headers=headers_browser)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            root = ET.fromstring(response.read())
            for cube in root.iter("{http://www.bnr.ro/xsd}Cube"):
                if cube.get("date"):
                    for rate in cube.findall("{http://www.bnr.ro/xsd}Rate"):
                        if rate.get("currency") == "EUR":
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

    return 5.35


def _normalizeaza_text_fara_diacritice(text: str) -> str:
    raw = str(text or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def este_ore_transport(descriere: str) -> bool:
    txt = _normalizeaza_text_fara_diacritice(descriere)
    return (
        ("ore transport" in txt)
        or ("ora transport" in txt)
        or ("ora de transport" in txt)
        or ("ore de transport" in txt)
    )


def _valideaza_si_plafoneaza_ore_transport(
    descriere: str, cantitate: float, max_ore: float = MAX_ORE_TRANSPORT_ZI
) -> tuple[float, bool]:
    cant = float(cantitate or 0.0)
    if este_ore_transport(descriere) and cant > max_ore:
        return float(max_ore), True
    return cant, False


def normalizeaza_um(um_brut: str) -> str:
    um_curat = um_brut.replace("Eur/", "").replace("EUR/", "").replace("RON/", "").strip().lower()
    return _MAPARE_UM.get(um_curat, "buc")


def converteste_in_moneda_oferta(pret_unitar: float, moneda_linie: str, moneda_tinta: str, curs_bnr: float) -> float:
    m_src = str(moneda_linie or "RON").strip().upper()
    m_dst = str(moneda_tinta or "EUR").strip().upper()
    val = float(pret_unitar or 0.0)
    if m_src == m_dst or curs_bnr <= 0:
        return round(val, 2)
    if m_src == "RON" and m_dst == "EUR":
        return round(val / curs_bnr, 2)
    if m_src == "EUR" and m_dst == "RON":
        return round(val * curs_bnr, 2)
    return round(val, 2)


def get_text_clauze_implicite(moneda: str, setari_firma: dict | None = None) -> str:
    fallback = (
        "Oferta de preț este exprimată în {MONEDA}, nu conține piese de schimb și este valabilă 15 zile.\n"
        "Costul pieselor de schimb se va transmite după constatare/diagnosticare.\n"
        "În funcție de complexitatea lucrărilor, durata intervenției poate suferi modificări. Acestea vă vor fi comunicate la fața locului."
    )
    if setari_firma is None:
        try:
            setari_firma = SetariRepository.get_setari() or {}
        except Exception:
            setari_firma = {}
    template_db = str(setari_firma.get("clauze_subsol_implicite") or "").strip()
    text_baza = template_db if template_db else fallback
    rezultat = text_baza.replace("{MONEDA}", moneda).replace("{moneda}", moneda)
    if "{MONEDA}" not in text_baza and "{moneda}" not in text_baza:
        mon_opusa = "RON" if moneda == "EUR" else "EUR"
        rezultat = rezultat.replace(f"exprimată în {mon_opusa}", f"exprimată în {moneda}")
    return rezultat


def extrage_nume_persoana_firma(client_obj: dict | None) -> str:
    if not client_obj:
        return ""
    for k in _CHEI_PERSOANA_CONTACT:
        val = client_obj.get(k)
        if val and str(val).strip():
            return str(val).strip()
    for k, val in client_obj.items():
        if ("pers" in k.lower() or "contact" in k.lower()) and val and str(val).strip():
            return str(val).strip()
    return ""


def _sincronizeaza_editor_inainte_de_adaugare() -> pd.DataFrame:
    counter = st.session_state.get("editor_reset_counter", 0)
    w_key = f"editor_linii_oferta_unic_{counter}"
    base_df = _asigura_df_oferta_editor()
    if w_key not in st.session_state:
        return base_df
    delta = st.session_state[w_key]
    if not isinstance(delta, dict):
        return base_df
    df_work = base_df.copy().reset_index(drop=True)
    for row_idx_str, changes in delta.get("edited_rows", {}).items():
        r_idx = int(row_idx_str)
        if 0 <= r_idx < len(df_work):
            for col_k, val_v in changes.items():
                if col_k in df_work.columns:
                    df_work.at[r_idx, col_k] = val_v
    del_rows = sorted(
        [int(i) for i in delta.get("deleted_rows", []) if 0 <= int(i) < len(df_work)], reverse=True
    )
    if del_rows:
        df_work = df_work.drop(index=del_rows).reset_index(drop=True)
    added_rows = delta.get("added_rows", [])
    if added_rows:
        df_work = pd.concat([df_work, pd.DataFrame(added_rows)], ignore_index=True)
    return df_work


def _defaults_oferta(
    valabilitate_def: str,
    termeni_plata_def: str,
    intocmit_de_def: str,
    moneda: str = "EUR",
    setari_firma: dict | None = None,
    curs_implicit: float | None = None,
) -> dict:
    curs_val = float(curs_implicit) if curs_implicit is not None else obtine_curs_bnr()
    return {
        "sel_firma": "-- Alege firma --",
        "moneda": moneda,
        "curs_valutar": curs_val,
        "numar_manual": OferteRepository.get_next_numar_oferta(),
        "data": date.today(),
        "titlu": "Ofertă de preț",
        "in_atentia": "În atenția ",
        "formula_adresare": "Ca urmare a discuției anterioare, revenim cu următoarea ofertă de preț.",
        "valabilitate": valabilitate_def,
        "termeni_plata": termeni_plata_def,
        "intocmit_de": intocmit_de_def,
        "acceptat_de": "",
        "sel_masina": "-- Fără utilaj / Introducere manuală --",
        "utilaj": "",
        "utilaj_tip": "",
        "utilaj_serie": "",
        "utilaj_an": "",
        "observatii": get_text_clauze_implicite(moneda, setari_firma),
        "ultima_firma_pers": "-- Alege firma --",
        "ultima_masina_selectata": "-- Fără utilaj / Introducere manuală --",
        "ultima_moneda_fraze": moneda,
        "tip_discount": "Fără discount",
        "valoare_discount_total": 0.0,
    }


def _init_sau_reseteaza_draft_oferta(
    valabilitate_def: str,
    termeni_plata_def: str,
    intocmit_de_def: str,
    moneda: str = "EUR",
    setari_firma: dict | None = None,
    curs_implicit: float | None = None,
) -> None:
    reset_draft(
        "oferta_draft",
        _defaults_oferta(valabilitate_def, termeni_plata_def, intocmit_de_def, moneda, setari_firma, curs_implicit),
        "ofs_cnt",
    )
    st.session_state["df_oferta_editor"] = _df_oferta_gol()
    st.session_state["oferta_furnizori_map"] = {}
    st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1


def _calculeaza_totaluri_cu_discount(
    df_valid: pd.DataFrame,
    moneda_oferta: str,
    curs_valutar: float,
    cota_tva_procent: float,
    tip_discount: str,
    valoare_discount_total: float,
) -> dict:
    subtotal_brut = 0.0
    discount_reper_total = 0.0
    linii = []
    col_pret_final = f"Pret Unitar ({moneda_oferta})"

    for _, r in df_valid.iterrows():
        cant_item = float(pd.to_numeric(r.get("Cantitate"), errors="coerce") or 1.0)
        pret_sursa = float(pd.to_numeric(r.get("Pret Unitar"), errors="coerce") or 0.0)
        moneda_sursa = str(r.get("Moneda") or "RON").strip().upper()
        disc_rep_pct = float(pd.to_numeric(r.get("Discount (%)"), errors="coerce") or 0.0)
        disc_rep_pct = max(0.0, min(100.0, disc_rep_pct))

        pret_unitar_conv = converteste_in_moneda_oferta(pret_sursa, moneda_sursa, moneda_oferta, curs_valutar)
        val_bruta_linie = round(cant_item * pret_unitar_conv, 2)
        disc_linie = round(val_bruta_linie * (disc_rep_pct / 100.0), 2) if tip_discount == "Discount pe reper (%)" else 0.0
        val_neta_linie = round(max(0.0, val_bruta_linie - disc_linie), 2)

        subtotal_brut += val_bruta_linie
        discount_reper_total += disc_linie

        linii.append({
            "Descriere": str(r.get("Descriere", "")).strip(),
            "UM": str(r.get("UM") or "buc"),
            "Cantitate": cant_item,
            "Pret Sursa": round(pret_sursa, 2),
            "Moneda Sursa": moneda_sursa,
            "Discount (%)": disc_rep_pct if tip_discount == "Discount pe reper (%)" else 0.0,
            col_pret_final: pret_unitar_conv,
            "Valoare Linie": val_neta_linie,
            "Termen livrare": str(r.get("Termen livrare", "") or ""),
        })

    subtotal_brut = round(subtotal_brut, 2)
    discount_reper_total = round(discount_reper_total, 2)

    if tip_discount == "Discount pe reper (%)":
        discount_valoare = discount_reper_total
    elif tip_discount == "Discount pe total (%)":
        pct_tot = max(0.0, min(100.0, float(valoare_discount_total or 0.0)))
        discount_valoare = round(subtotal_brut * (pct_tot / 100.0), 2)
    elif tip_discount == "Discount fix":
        discount_valoare = round(max(0.0, min(subtotal_brut, float(valoare_discount_total or 0.0))), 2)
    else:
        discount_valoare = 0.0

    subtotal_net = round(max(0.0, subtotal_brut - discount_valoare), 2)
    tva = round(subtotal_net * (cota_tva_procent / 100.0), 2)
    total_general = round(subtotal_net + tva, 2)

    return {
        "linii": linii,
        "subtotal_brut": subtotal_brut,
        "discount_valoare": discount_valoare,
        "subtotal": subtotal_net,
        "tva": tva,
        "total_general": total_general,
    }


def _construieste_linii_nota_comanda(
    df_valid: pd.DataFrame,
    moneda_oferta: str,
    curs_valutar: float,
    adaos_client: float,
) -> list[dict]:
    """Extrage liniile ofertate și le asociază furnizorul, codul piesei și prețul de achiziție/comandă."""
    mp_furn = _asigura_mapare_furnizori_oferta()
    rezultat: list[dict] = []

    for _, r in df_valid.iterrows():
        desc_full = str(r.get("Descriere") or "").strip()
        if not desc_full:
            continue
        cant = float(pd.to_numeric(r.get("Cantitate"), errors="coerce") or 1.0)
        pret_lin = float(pd.to_numeric(r.get("Pret Unitar"), errors="coerce") or 0.0)
        mon_lin = str(r.get("Moneda") or moneda_oferta).strip().upper()
        if mon_lin not in ("EUR", "RON"):
            mon_lin = moneda_oferta
        termen = str(r.get("Termen livrare") or "").strip()

        meta = mp_furn.get(desc_full) or mp_furn.get(desc_full.lower())
        if meta:
            furn_nume = str(meta.get("furnizor_nume") or "").strip() or "Furnizor nespecificat"
            piesa_den = str(meta.get("piesa_denumire") or desc_full).strip()
            cod_piesa = str(meta.get("cod_piesa") or "").strip()
            pret_cmd = float(meta.get("pret_furnizor") if meta.get("pret_furnizor") is not None else pret_lin)
            mon_cmd = str(meta.get("moneda_furnizor") or mon_lin).strip().upper()
        else:
            # Încearcă extragerea codului dintre paranteze din Descriere, ex: "Piesă (COD123)"
            cod_extr = ""
            m_cod = re.search(r"\(([^()]+)\)\s*$", desc_full)
            if m_cod:
                cod_extr = m_cod.group(1).strip()
            furn_nume = "Furnizor nespecificat"
            piesa_den = desc_full
            cod_piesa = cod_extr
            divisor = 1.0 + (float(adaos_client or 0.0) / 100.0)
            pret_cmd = round(pret_lin / divisor, 2) if divisor > 0 else pret_lin
            mon_cmd = mon_lin

        if mon_cmd not in ("EUR", "RON"):
            mon_cmd = moneda_oferta

        rezultat.append({
            "furnizor_nume": furn_nume,
            "piesa_denumire": piesa_den,
            "cod_piesa": cod_piesa,
            "cantitate": cant,
            "pret": round(pret_cmd, 2),
            "moneda": mon_cmd,
            "termen_livrare": termen,
            "stare_comanda": "Necomandat",
        })

    return rezultat


def _render_centralizare_oferte_furnizori(sel_firma: str, adaos_client: float, moneda_oferta: str, curs_valutar: float):
    """Centralizează ofertele primite de la furnizori și permite trecerea reperelor dorite în oferta de preț."""
    oferte_primite = _incarca_oferte_primite_furnizori()
    with st.expander("📥 Centralizare Oferte Primite de la Furnizori -> Trecere în Oferta de Preț", expanded=False):
        if not oferte_primite:
            st.info("Nu există încă oferte/linii primite de la furnizori înregistrate.")
            return

        clienti_opt = ["Toți clienții"] + sorted({
            x["client_nume"] for x in oferte_primite if x.get("client_nume")
        })
        default_cli_idx = 0
        if sel_firma != "-- Alege firma --" and sel_firma in clienti_opt:
            default_cli_idx = clienti_opt.index(sel_firma)

        fc1, fc2, fc3 = st.columns([1.5, 1.5, 1.5])
        with fc1:
            cli_sel = st.selectbox("Client cerere", options=clienti_opt, index=default_cli_idx, key="of_centr_cli_sel")
        with fc2:
            cereri_opt = ["Toate cererile"] + sorted({
                x["cod_cerere"] for x in oferte_primite
                if x.get("cod_cerere") and (cli_sel == "Toți clienții" or x.get("client_nume") == cli_sel)
            })
            cer_sel = st.selectbox("Cerere ofertă (RFQ)", options=cereri_opt, key="of_centr_cer_sel")
        with fc3:
            furn_opt = ["Toți furnizorii"] + sorted({
                x["furnizor_nume"] for x in oferte_primite
                if x.get("furnizor_nume")
                and (cli_sel == "Toți clienții" or x.get("client_nume") == cli_sel)
                and (cer_sel == "Toate cererile" or x.get("cod_cerere") == cer_sel)
            })
            furn_sel = st.selectbox("Furnizor", options=furn_opt, key="of_centr_furn_sel")

        filtrate = [
            x for x in oferte_primite
            if (cli_sel == "Toți clienții" or x.get("client_nume") == cli_sel)
            and (cer_sel == "Toate cererile" or x.get("cod_cerere") == cer_sel)
            and (furn_sel == "Toți furnizorii" or x.get("furnizor_nume") == furn_sel)
        ]
        if not filtrate:
            st.info("Nu există repere primite de la furnizori pentru filtrul curent.")
            return

        adaos_ef = float(adaos_client or 0.0) if sel_firma != "-- Alege firma --" else 20.0
        st.caption(
            f"💡 Bifează **Selectat** pe reperele dorite. La trecerea în oferta de preț se aplică automat adaosul comercial al firmei (**+{adaos_ef:g}%**)."
        )

        df_centr_init = pd.DataFrame([
            {
                "Selectat": bool(x.get("selectat_initial", False)),
                "Furnizor": x["furnizor_nume"],
                "Piesă": x["piesa_denumire"],
                "Cod Piesă": x["cod_piesa"],
                "Echivalente": x["piese_inlocuitoare"],
                "Cantitate": float(x["cantitate"]),
                "Preț Furnizor": float(x["pret_furnizor"]),
                "Monedă": x["moneda"],
                "Preț Cu Adaos": round(float(x["pret_furnizor"]) * (1.0 + adaos_ef / 100.0), 2),
                "Termen": x["termen_livrare"],
                "Client": x["client_nume"] or "-",
                "Cerere": x["cod_cerere"] or "-",
                "_cerere_id": x.get("cerere_id"),
            }
            for x in filtrate
        ])

        edited_centr = st.data_editor(
            df_centr_init,
            key=f"df_centr_oferte_furn_{cli_sel}_{cer_sel}_{furn_sel}_{len(df_centr_init)}",
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["Furnizor", "Piesă", "Cod Piesă", "Echivalente", "Monedă", "Preț Cu Adaos", "Client", "Cerere", "_cerere_id"],
            column_config={
                "Selectat": st.column_config.CheckboxColumn("✅ Alege", width="small"),
                "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                "Piesă": st.column_config.TextColumn("Piesă", width="large"),
                "Cod Piesă": st.column_config.TextColumn("Cod Piesă", width="small"),
                "Echivalente": st.column_config.TextColumn("Echivalente", width="medium"),
                "Cantitate": st.column_config.NumberColumn("Cant.", min_value=0.01, format="%.2f", width="small"),
                "Preț Furnizor": st.column_config.NumberColumn("Preț Furnizor", min_value=0.0, format="%.2f", width="small"),
                "Monedă": st.column_config.TextColumn("Monedă", width="small"),
                "Preț Cu Adaos": st.column_config.NumberColumn(f"Preț (+{adaos_ef:g}%)", format="%.2f", width="small"),
                "Termen": st.column_config.TextColumn("Termen", width="small"),
                "Client": st.column_config.TextColumn("Client", width="small"),
                "Cerere": st.column_config.TextColumn("Cerere", width="small"),
                "_cerere_id": None,
            },
        )

        if st.button("➡️ Trece Reperele Selectate în Oferta de Preț (+ Adaos)", type="primary", key="btn_trecere_oferte_furn_in_oferta"):
            alese = edited_centr[edited_centr["Selectat"].fillna(False).astype(bool)].copy()
            if alese.empty:
                st.warning("⚠️ Bifează cel puțin un reper din centralizator.")
                return

            df_baza = _sincronizeaza_editor_inainte_de_adaugare()
            mp_furn = _asigura_mapare_furnizori_oferta()
            noi_randuri = []
            cereri_ids_folosite = []

            for _, row in alese.iterrows():
                den_p = str(row.get("Piesă") or "").strip()
                if not den_p:
                    continue
                cod_p = str(row.get("Cod Piesă") or "").strip()
                ech_p = str(row.get("Echivalente") or "").strip()
                furn_p = str(row.get("Furnizor") or "").strip() or "Furnizor nespecificat"
                cant_p = float(pd.to_numeric(row.get("Cantitate"), errors="coerce") or 1.0)
                pret_furn_p = float(pd.to_numeric(row.get("Preț Furnizor"), errors="coerce") or 0.0)
                mon_p = str(row.get("Monedă") or moneda_oferta).strip().upper()
                if mon_p not in ("EUR", "RON"):
                    mon_p = moneda_oferta
                termen_p = str(row.get("Termen") or "1").strip() or "1"

                pret_cu_adaos = round(pret_furn_p * (1.0 + adaos_ef / 100.0), 2)
                desc_oferta = f"{den_p} ({cod_p})" if cod_p and cod_p.lower() not in den_p.lower() else den_p
                if ech_p and ech_p != "-":
                    desc_oferta += f" | Echiv: {ech_p}"

                noi_randuri.append({
                    "Ordine": len(df_baza) + len(noi_randuri) + 1,
                    "Descriere": desc_oferta,
                    "UM": "buc",
                    "Cantitate": cant_p,
                    "Pret Unitar": pret_cu_adaos,
                    "Moneda": mon_p,
                    "Termen livrare": termen_p,
                })

                info_furn = {
                    "furnizor_nume": furn_p,
                    "piesa_denumire": den_p,
                    "cod_piesa": cod_p,
                    "pret_furnizor": pret_furn_p,
                    "moneda_furnizor": mon_p,
                }
                mp_furn[desc_oferta] = info_furn
                mp_furn[desc_oferta.lower()] = info_furn

                cid_r = row.get("_cerere_id")
                if cid_r is not None and pd.notna(cid_r) and str(cid_r).strip().isdigit():
                    cereri_ids_folosite.append(int(cid_r))

            if noi_randuri:
                st.session_state["df_oferta_editor"] = pd.concat([df_baza, pd.DataFrame(noi_randuri)], ignore_index=True)
                st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                if cereri_ids_folosite:
                    st.session_state["oferta_cerere_furnizor_id"] = cereri_ids_folosite[0]

                cli_row = str(alese.iloc[0].get("Client") or "").strip()
                draft_obj = st.session_state.get("oferta_draft")
                if isinstance(draft_obj, dict) and cli_row and draft_obj.get("sel_firma") == "-- Alege firma --":
                    firme_all_c = FirmeRepository.get_all() or []
                    if any(str(f.get("nume_firma") or "").strip() == cli_row for f in firme_all_c):
                        draft_obj["sel_firma"] = cli_row
                        draft_obj["ultima_firma_pers"] = cli_row
                        st.session_state["ofs_cnt"] = st.session_state.get("ofs_cnt", 0) + 1

                st.toast(f"✅ {len(noi_randuri)} repere trecute în oferta de preț cu adaos +{adaos_ef:g}%.")
                st.rerun()


def render_tab_note_comanda_furnizori():
    """Tab separat pentru Notele de Comandă către Furnizori (stare pe reper și pe notă)."""
    st.subheader("📦 Note de Comandă către Furnizori")
    note_lista = NoteComandaRepository.get_all_cu_linii()

    if not note_lista:
        st.info("Nu există încă note de comandă către furnizori. Acestea se generează automat la salvarea unei oferte cu repere.")
        return

    furnizori_disp = ["Toți furnizorii"] + sorted({
        str(n.get("furnizor_nume") or "").strip() for n in note_lista if str(n.get("furnizor_nume") or "").strip()
    })
    stari_disp = ["Toate stările"] + OPTIUNI_STARE_NOTA_COMANDA

    nf1, nf2, nf3 = st.columns([1.5, 1.4, 1.6])
    with nf1:
        filtru_furn_nc = st.selectbox("Filtrează după furnizor", options=furnizori_disp, key="nc_filtru_furnizor")
    with nf2:
        filtru_stare_nc = st.selectbox("Filtrează după stare comandă", options=stari_disp, key="nc_filtru_stare")
    with nf3:
        cautare_nc = st.text_input("Caută piesă / cod / nr. notă / client", key="nc_cautare_text").strip().lower()

    note_filtrate = []
    for n in note_lista:
        furn_n = str(n.get("furnizor_nume") or "").strip()
        if filtru_furn_nc != "Toți furnizorii" and furn_n != filtru_furn_nc:
            continue

        linii_n = n.get("linii") or []
        if filtru_stare_nc != "Toate stările":
            st_gen = normalizeaza_stare_nota_comanda(n.get("stare_generala"))
            are_linie_st = any(normalizeaza_stare_nota_comanda(l.get("stare_comanda")) == filtru_stare_nc for l in linii_n)
            if st_gen != filtru_stare_nc and not are_linie_st:
                continue

        if cautare_nc:
            haystack = " ".join([
                str(n.get("numar_nota") or ""),
                str(n.get("furnizor_nume") or ""),
                str(n.get("client_nume") or ""),
                str(n.get("numar_oferta") or ""),
                " ".join(
                    f"{l.get('piesa_denumire') or ''} {l.get('cod_piesa') or ''}"
                    for l in linii_n
                ),
            ]).lower()
            if cautare_nc not in haystack:
                continue

        note_filtrate.append(n)

    if not note_filtrate:
        st.info("Nu există note de comandă care să corespundă filtrelor selectate.")
        return

    for n in note_filtrate:
        nid = int(n["id"])
        nr_nota = str(n.get("numar_nota") or f"NC-{nid}")
        furn_n = str(n.get("furnizor_nume") or "-")
        cli_n = str(n.get("client_nume") or "-")
        nr_of_n = str(n.get("numar_oferta") or "-")
        data_n = str(n.get("data_emitere") or "")[:10]
        mon_n = str(n.get("moneda") or "EUR")
        tot_n = float(n.get("total_nota") or 0.0)
        st_gen = normalizeaza_stare_nota_comanda(n.get("stare_generala"))
        linii_n = n.get("linii") or []

        with st.expander(
            f"📦 {nr_nota} | Furnizor: {furn_n} | Client: {cli_n} (Ofertă #{nr_of_n}) — {tot_n:,.2f} {mon_n} [{st_gen}]",
            expanded=False,
        ):
            hc1, hc2, hc3 = st.columns([2.2, 1.5, 0.9], vertical_alignment="bottom")
            with hc1:
                st.write(f"**Data emitere:** {data_n} | **Client:** {cli_n} | **Ofertă:** #{nr_of_n}")
            with hc2:
                idx_st_gen = OPTIUNI_STARE_NOTA_COMANDA.index(st_gen) if st_gen in OPTIUNI_STARE_NOTA_COMANDA else 0
                noua_st_gen = st.selectbox(
                    "Stare generală notă",
                    options=OPTIUNI_STARE_NOTA_COMANDA,
                    index=idx_st_gen,
                    key=f"nc_st_gen_sel_{nid}",
                )
            with hc3:
                if st.button("💾 Aplică", key=f"nc_btn_st_gen_{nid}", use_container_width=True):
                    NoteComandaRepository.update_nota_stare_generala(nid, noua_st_gen)
                    st.toast(f"✅ Starea notei {nr_nota} a devenit «{noua_st_gen}».")
                    st.rerun()

            if linii_n:
                df_l_init = pd.DataFrame([
                    {
                        "id": int(l["id"]),
                        "Furnizor": str(l.get("furnizor_nume") or furn_n),
                        "Piesă": str(l.get("piesa_denumire") or ""),
                        "Cod Piesă": str(l.get("cod_piesa") or ""),
                        "Cantitate": float(l.get("cantitate") or 1.0),
                        "Preț": float(l.get("pret") or 0.0),
                        "Monedă": str(l.get("moneda") or mon_n),
                        "Stare Comandă": normalizeaza_stare_nota_comanda(l.get("stare_comanda")),
                    }
                    for l in linii_n
                ])

                l_editor_key = f"nc_linii_editor_{nid}_{len(df_l_init)}"
                edited_l = st.data_editor(
                    df_l_init,
                    key=l_editor_key,
                    hide_index=True,
                    num_rows="fixed",
                    use_container_width=True,
                    disabled=["id", "Furnizor", "Piesă", "Cod Piesă", "Cantitate", "Preț", "Monedă"],
                    column_config={
                        "id": None,
                        "Furnizor": st.column_config.TextColumn("Nume Furnizor", width="medium"),
                        "Piesă": st.column_config.TextColumn("Denumire Piesă", width="large"),
                        "Cod Piesă": st.column_config.TextColumn("Cod Piesă", width="small"),
                        "Cantitate": st.column_config.NumberColumn("Cantitate", format="%.2f", width="small"),
                        "Preț": st.column_config.NumberColumn("Preț", format="%.2f", width="small"),
                        "Monedă": st.column_config.TextColumn("Monedă", width="small"),
                        "Stare Comandă": st.column_config.SelectboxColumn(
                            "Stare Comandă",
                            options=OPTIUNI_STARE_NOTA_COMANDA,
                            required=True,
                            width="medium",
                        ),
                    },
                )

                b_col1, b_col2 = st.columns([2.2, 1.0])
                with b_col1:
                    if st.button(
                        f"💾 Salvează Stările Pozițiilor ({nr_nota})",
                        type="primary",
                        key=f"nc_btn_save_linii_{nid}",
                        use_container_width=True,
                    ):
                        orig_st_map = {
                            int(r["id"]): normalizeaza_stare_nota_comanda(r["Stare Comandă"])
                            for _, r in df_l_init.iterrows()
                        }
                        nr_upd = 0
                        for _, r_ed in edited_l.iterrows():
                            lid = int(r_ed["id"])
                            st_noua = normalizeaza_stare_nota_comanda(r_ed.get("Stare Comandă"))
                            if st_noua != orig_st_map.get(lid):
                                NoteComandaRepository.update_linie_stare(lid, st_noua)
                                nr_upd += 1
                        if l_editor_key in st.session_state:
                            del st.session_state[l_editor_key]
                        st.toast(f"✅ Actualizate {nr_upd} poziții în nota {nr_nota}.")
                        st.rerun()
                with b_col2:
                    if st.button("🗑️ Șterge Nota", key=f"nc_btn_del_{nid}", use_container_width=True):
                        NoteComandaRepository.delete_nota(nid)
                        st.toast(f"🗑️ Nota {nr_nota} a fost ștearsă.")
                        st.rerun()


def render_oferte():
    st.subheader("💼 Generare & Gestiune Oferte de Preț")

    tab_oferte, tab_note_comanda = st.tabs(["📄 Oferte de Preț", "📦 Note de Comandă Furnizori"])

    with tab_note_comanda:
        render_tab_note_comanda_furnizori()
        return

    with tab_oferte:
        firme_list = FirmeRepository.get_all() or []
        if not firme_list:
            st.warning("⚠️ Adăugați cel puțin o firmă în Tabul de Firme înainte de a crea o ofertă.")
            return

        firme_dict = {f["nume_firma"]: f for f in firme_list}
        piese_catalog = PieseRepository.get_all() or []
        setari_firma = SetariRepository.get_setari() or {}
        curs_bnr_curent = obtine_curs_bnr()

        cota_tva_procent = float(setari_firma.get("cota_tva") if setari_firma.get("cota_tva") is not None else 21.0)
        valabilitate_def = str(setari_firma.get("valabilitate_implicita") or "15 zile")
        termeni_plata_def = str(setari_firma.get("termeni_plata_impliciti") or "5 zile de la emiterea facturii")
        intocmit_de_def = str(setari_firma.get("intocmit_de_implicit") or "Echipa Nexus Industrial")

        st.session_state.setdefault("editor_reset_counter", 0)
        _asigura_mapare_furnizori_oferta()

        init_draft(
            "oferta_draft",
            _defaults_oferta(valabilitate_def, termeni_plata_def, intocmit_de_def, "EUR", setari_firma, curs_bnr_curent),
            "ofs_cnt",
        )
        _asigura_df_oferta_editor()

        draft = st.session_state["oferta_draft"]

        top_c1, top_c2 = st.columns([4, 1], vertical_alignment="center")
        with top_c1:
            st.caption(
                "💾 Datele ofertei în lucru se păstrează automat chiar dacă schimbi tab-ul. Folosește **Salvează** sau **Anulare Ofertă** pentru a începe una nouă."
            )
        with top_c2:
            if st.button("❌ Anulare Ofertă", key="btn_anulare_oferta_top", type="secondary", use_container_width=True):
                _init_sau_reseteaza_draft_oferta(
                    valabilitate_def,
                    termeni_plata_def,
                    intocmit_de_def,
                    draft.get("moneda", "EUR"),
                    setari_firma,
                    float(draft.get("curs_valutar") or curs_bnr_curent),
                )
                st.session_state["ultima_oferta_salvata_msg"] = ""
                st.session_state["pdf_oferta_bytes"] = None
                st.toast("🗑️ Oferta în lucru a fost anulată și formularul a fost resetat.")
                st.rerun()

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            optiuni_firme = ["-- Alege firma --"] + list(firme_dict.keys())
            k_firma, v_firma = lega_camp("oferta_draft", "sel_firma", "-- Alege firma --", "ofs", "ofs_cnt")
            if v_firma not in optiuni_firme:
                st.session_state[k_firma] = "-- Alege firma --"
                draft["sel_firma"] = "-- Alege firma --"

            sel_firma = st.selectbox(
                "1. Selectează Clientul / Firma",
                options=optiuni_firme,
                key=k_firma,
                on_change=sync_camp,
                args=("oferta_draft", k_firma, "sel_firma"),
            )

            client_obj = {}
            adaos_client = 20.0
            nume_persoana_db = ""
            masini_firma = []
            if sel_firma != "-- Alege firma --":
                client_obj = firme_dict[sel_firma]
                adaos_client = float(client_obj.get("adaos_comercial", 20.0) or 20.0)
                nume_persoana_db = extrage_nume_persoana_firma(client_obj)
                masini_firma = MasiniRepository.get_by_firma(client_obj["id"]) or []
                st.caption(f"👤 Persoană de contact: **{nume_persoana_db or 'Nespecificată'}** | Adaos client: **{adaos_client:g}%**")

        with col_s2:
            opt_monede = ["EUR", "RON"]
            k_mon, v_mon = lega_camp("oferta_draft", "moneda", "EUR", "ofs", "ofs_cnt")
            if v_mon not in opt_monede:
                st.session_state[k_mon] = "EUR"
                draft["moneda"] = "EUR"

            moneda_oferta = st.selectbox(
                "Monedă Ofertă (afișare finală PDF & Total)",
                options=opt_monede,
                key=k_mon,
                on_change=sync_camp,
                args=("oferta_draft", k_mon, "moneda"),
            )

            k_curs, _ = lega_camp(
                "oferta_draft",
                "curs_valutar",
                curs_bnr_curent,
                "ofs",
                "ofs_cnt",
                transform=lambda x: float(x or curs_bnr_curent),
            )
            c_curs1, c_curs2 = st.columns([3, 1], vertical_alignment="bottom")
            with c_curs1:
                curs_valutar = st.number_input(
                    "Curs valutar BNR (1 EUR = X RON)",
                    step=0.0001,
                    format="%.4f",
                    key=k_curs,
                    on_change=sync_camp,
                    args=("oferta_draft", k_curs, "curs_valutar"),
                )
            with c_curs2:
                if st.button("🔄 BNR", help="Forțează actualizarea cursului BNR", use_container_width=True):
                    obtine_curs_bnr.clear()
                    nou_curs = obtine_curs_bnr()
                    draft["curs_valutar"] = nou_curs
                    st.session_state[k_curs] = nou_curs
                    st.rerun()

        if draft.get("ultima_firma_pers") != sel_firma:
            draft["ultima_firma_pers"] = sel_firma
            nou_atentie = (
                f"În atenția {nume_persoana_db}"
                if (sel_firma != "-- Alege firma --" and nume_persoana_db)
                else "În atenția "
            )
            nou_acceptat = nume_persoana_db if (sel_firma != "-- Alege firma --" and nume_persoana_db) else ""
            draft["in_atentia"] = nou_atentie
            draft["acceptat_de"] = nou_acceptat
            draft["sel_masina"] = "-- Fără utilaj / Introducere manuală --"
            draft["ultima_masina_selectata"] = "-- Fără utilaj / Introducere manuală --"
            draft["utilaj"] = ""
            draft["utilaj_tip"] = ""
            draft["utilaj_serie"] = ""
            draft["utilaj_an"] = ""

            st.session_state[widget_key("ofs", "in_atentia", "ofs_cnt")] = nou_atentie
            st.session_state[widget_key("ofs", "acceptat_de", "ofs_cnt")] = nou_acceptat
            st.session_state[widget_key("ofs", "sel_masina", "ofs_cnt")] = "-- Fără utilaj / Introducere manuală --"
            st.session_state[widget_key("ofs", "utilaj", "ofs_cnt")] = ""
            st.session_state[widget_key("ofs", "utilaj_tip", "ofs_cnt")] = ""
            st.session_state[widget_key("ofs", "utilaj_serie", "ofs_cnt")] = ""
            st.session_state[widget_key("ofs", "utilaj_an", "ofs_cnt")] = ""

        _render_centralizare_oferte_furnizori(
            sel_firma=sel_firma,
            adaos_client=adaos_client,
            moneda_oferta=moneda_oferta,
            curs_valutar=float(curs_valutar),
        )

        c1, c2 = st.columns(2)
        with c1:
            k_nr, _ = lega_camp("oferta_draft", "numar_manual", "", "ofs", "ofs_cnt")
            nr_oferta_input = st.text_input(
                "Număr Ofertă (nr. ordine din tabelul oferte)",
                key=k_nr,
                on_change=sync_camp,
                args=("oferta_draft", k_nr, "numar_manual"),
            )

            k_titlu, _ = lega_camp("oferta_draft", "titlu", "Ofertă de preț", "ofs", "ofs_cnt")
            titlu_oferta = st.text_input(
                "Titlu / Obiect Ofertă (intern)",
                key=k_titlu,
                on_change=sync_camp,
                args=("oferta_draft", k_titlu, "titlu"),
            )
        with c2:
            k_data, _ = lega_camp("oferta_draft", "data", date.today(), "ofs", "ofs_cnt")
            data_oferta = st.date_input(
                "Data emiterii",
                key=k_data,
                on_change=sync_camp,
                args=("oferta_draft", k_data, "data"),
            )

            k_at, _ = lega_camp("oferta_draft", "in_atentia", "În atenția ", "ofs", "ofs_cnt")
            in_atentia = st.text_input(
                "Destinatar (În atenția)",
                key=k_at,
                on_change=sync_camp,
                args=("oferta_draft", k_at, "in_atentia"),
            )

        cc1, cc2 = st.columns(2)
        with cc1:
            k_val, _ = lega_camp("oferta_draft", "valabilitate", valabilitate_def, "ofs", "ofs_cnt")
            valabilitate_oferta = st.text_input(
                "Termen de valabilitate",
                key=k_val,
                on_change=sync_camp,
                args=("oferta_draft", k_val, "valabilitate"),
            )

            k_int, _ = lega_camp("oferta_draft", "intocmit_de", intocmit_de_def, "ofs", "ofs_cnt")
            intocmit_de = st.text_input(
                "Întocmit / Emis de (reprezentant)",
                key=k_int,
                on_change=sync_camp,
                args=("oferta_draft", k_int, "intocmit_de"),
            )
        with cc2:
            k_plata, _ = lega_camp("oferta_draft", "termeni_plata", termeni_plata_def, "ofs", "ofs_cnt")
            termeni_plata_oferta = st.text_input(
                "Termeni de plată",
                key=k_plata,
                on_change=sync_camp,
                args=("oferta_draft", k_plata, "termeni_plata"),
            )

            k_acc, _ = lega_camp("oferta_draft", "acceptat_de", "", "ofs", "ofs_cnt")
            acceptat_de = st.text_input(
                "Acceptat / Reprezentant beneficiar",
                key=k_acc,
                on_change=sync_camp,
                args=("oferta_draft", k_acc, "acceptat_de"),
            )

        k_form, _ = lega_camp(
            "oferta_draft",
            "formula_adresare",
            "Ca urmare a discuției anterioare, revenim cu următoarea ofertă de preț.",
            "ofs",
            "ofs_cnt",
        )
        formula_adresare = st.text_area(
            "Text introductiv ofertă",
            height=68,
            key=k_form,
            on_change=sync_camp,
            args=("oferta_draft", k_form, "formula_adresare"),
        )

        grila_activa_utilaj = None
        with st.expander("🔧 Detalii Utilaj / Echipament (din lista de mașini a firmei)", expanded=True):
            masini_dict = {m["denumire"]: m for m in masini_firma}
            optiuni_masini = ["-- Fără utilaj / Introducere manuală --"] + list(masini_dict.keys())
            k_mof, v_mof = lega_camp(
                "oferta_draft", "sel_masina", "-- Fără utilaj / Introducere manuală --", "ofs", "ofs_cnt"
            )
            if v_mof not in optiuni_masini:
                st.session_state[k_mof] = "-- Fără utilaj / Introducere manuală --"
                draft["sel_masina"] = "-- Fără utilaj / Introducere manuală --"

            sel_masina_of = st.selectbox(
                "Alege utilajul / echipamentul din flota clientului:",
                options=optiuni_masini,
                key=k_mof,
                on_change=sync_camp,
                args=("oferta_draft", k_mof, "sel_masina"),
            )

            if sel_masina_of != "-- Fără utilaj / Introducere manuală --" and sel_masina_of in masini_dict:
                m_selectat_obj = masini_dict[sel_masina_of]
                grila_activa_utilaj = MasiniRepository.determina_grila_efectiva(m_selectat_obj)
                st.info(
                    f"💶 **Grilă tarifare activă pentru acest utilaj:** **{grila_activa_utilaj}** "
                    f"({m_selectat_obj.get('total_interventii', 0)}/{m_selectat_obj.get('prag_interventii', 20)} intervenții)"
                )

            if draft.get("ultima_masina_selectata") != sel_masina_of:
                draft["ultima_masina_selectata"] = sel_masina_of
                if sel_masina_of != "-- Fără utilaj / Introducere manuală --" and sel_masina_of in masini_dict:
                    m_obj = masini_dict[sel_masina_of]
                    draft["utilaj"] = str(m_obj.get("denumire") or "")
                    draft["utilaj_tip"] = str(m_obj.get("tip_masina") or m_obj.get("tip") or m_obj.get("model") or "")
                    draft["utilaj_serie"] = str(m_obj.get("serie") or m_obj.get("seria") or m_obj.get("nr_serie") or "")
                    draft["utilaj_an"] = str(m_obj.get("an_fabricatie") or m_obj.get("an") or "")
                else:
                    draft["utilaj"] = ""
                    draft["utilaj_tip"] = ""
                    draft["utilaj_serie"] = ""
                    draft["utilaj_an"] = ""

                st.session_state[widget_key("ofs", "utilaj", "ofs_cnt")] = draft["utilaj"]
                st.session_state[widget_key("ofs", "utilaj_tip", "ofs_cnt")] = draft["utilaj_tip"]
                st.session_state[widget_key("ofs", "utilaj_serie", "ofs_cnt")] = draft["utilaj_serie"]
                st.session_state[widget_key("ofs", "utilaj_an", "ofs_cnt")] = draft["utilaj_an"]

            k_unume, _ = lega_camp("oferta_draft", "utilaj", "", "ofs", "ofs_cnt")
            k_utip, _ = lega_camp("oferta_draft", "utilaj_tip", "", "ofs", "ofs_cnt")
            k_userie, _ = lega_camp("oferta_draft", "utilaj_serie", "", "ofs", "ofs_cnt")
            k_uan, _ = lega_camp("oferta_draft", "utilaj_an", "", "ofs", "ofs_cnt")

            cu1, cu2, cu3, cu4 = st.columns([3, 2, 2, 1.5])
            with cu1:
                utilaj_nume = st.text_input(
                    "Utilaj",
                    placeholder="ex: Mașină de debitat Bewo",
                    key=k_unume,
                    on_change=sync_camp,
                    args=("oferta_draft", k_unume, "utilaj"),
                )
            with cu2:
                utilaj_tip = st.text_input(
                    "Tip",
                    key=k_utip,
                    on_change=sync_camp,
                    args=("oferta_draft", k_utip, "utilaj_tip"),
                )
            with cu3:
                utilaj_serie = st.text_input(
                    "Seria",
                    key=k_userie,
                    on_change=sync_camp,
                    args=("oferta_draft", k_userie, "utilaj_serie"),
                )
            with cu4:
                utilaj_an = st.text_input(
                    "An fabric.",
                    key=k_uan,
                    on_change=sync_camp,
                    args=("oferta_draft", k_uan, "utilaj_an"),
                )

        st.markdown("---")

        piese_dict = {}
        for p in piese_catalog:
            val_p = str(p.get("valuta_achizitie") or "RON").strip().upper()
            if val_p not in ("RON", "EUR"):
                val_p = "RON"
            label_p = (
                f"{p['denumire']} (Achiziție: {float(p.get('pret_achizitie') or 0):.2f} {val_p} | "
                f"Termen: {p.get('termen_livrare') or '1'})"
            )
            piese_dict[label_p] = p

        tarife_disponibile = TarifeRepository.get_all() or []

        @st.fragment
        def _fragment_adaugare_rapida_si_tabel():
            st.markdown("##### ➕ Adăugare Rapidă Piesă din Catalog (EUR sau RON)")

            def on_schimbare_piesa_catalog():
                cheie_piesa = st.session_state.get("sel_cat_piesa", "-- Alege piesa --")
                if cheie_piesa != "-- Alege piesa --" and cheie_piesa in piese_dict:
                    st.session_state["termen_cat_piesa"] = str(piese_dict[cheie_piesa].get("termen_livrare") or "1")
                else:
                    st.session_state["termen_cat_piesa"] = "1"

            st.session_state.setdefault("termen_cat_piesa", "1")

            col_p1, col_p2, col_p3, col_p4 = st.columns([3, 1, 1, 1], vertical_alignment="bottom")
            with col_p1:
                sel_piesa_catalog = st.selectbox(
                    "Selectează piesă din stoc/catalog",
                    options=["-- Alege piesa --"] + list(piese_dict.keys()),
                    key="sel_cat_piesa",
                    on_change=on_schimbare_piesa_catalog,
                )
            with col_p2:
                cant_piesa = st.number_input("Cantitate", min_value=0.01, value=1.0, step=1.0, key="cant_cat_piesa")
            with col_p3:
                termen_piesa = st.text_input("Termen livrare", key="termen_cat_piesa")
            with col_p4:
                btn_add_piesa = st.button("➕ Adaugă", key="btn_add_piesa_frag", use_container_width=True)

            if btn_add_piesa:
                if sel_piesa_catalog == "-- Alege piesa --":
                    st.warning("⚠️ Selectați mai întâi o piesă din catalog!")
                else:
                    p_info = piese_dict[sel_piesa_catalog]
                    val_piesa = str(p_info.get("valuta_achizitie") or "RON").strip().upper()
                    if val_piesa not in ("RON", "EUR"):
                        val_piesa = "RON"
                    pret_achiz = float(p_info.get("pret_achizitie") or 0.0)
                    pret_vanzare = round(pret_achiz * (1.0 + adaos_client / 100.0), 2)
                    cod_p = str(p_info.get("cod_producator") or "").strip()
                    desc_p = f"{p_info['denumire']} ({cod_p})" if cod_p else str(p_info["denumire"])
                    df_baza_p = _sincronizeaza_editor_inainte_de_adaugare()
                    next_ord = len(df_baza_p) + 1

                    linie_piesa = pd.DataFrame([{
                        "Ordine": next_ord,
                        "Descriere": desc_p,
                        "UM": "buc",
                        "Cantitate": float(cant_piesa),
                        "Pret Unitar": pret_vanzare,
                        "Moneda": val_piesa,
                        "Termen livrare": str(termen_piesa or p_info.get("termen_livrare") or "1").strip(),
                    }])
                    st.session_state["df_oferta_editor"] = pd.concat([df_baza_p, linie_piesa], ignore_index=True)

                    furn_p = str(p_info.get("furnizor") or p_info.get("nume_furnizor") or "").strip()
                    mp_furn = _asigura_mapare_furnizori_oferta()
                    meta_p = {
                        "furnizor_nume": furn_p or "Furnizor nespecificat",
                        "piesa_denumire": str(p_info["denumire"]).strip(),
                        "cod_piesa": cod_p,
                        "pret_furnizor": pret_achiz,
                        "moneda_furnizor": val_piesa,
                    }
                    mp_furn[desc_p] = meta_p
                    mp_furn[desc_p.lower()] = meta_p

                    st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                    st.toast(f"✅ Piesa adăugată: {desc_p} ({pret_vanzare:.2f} {val_piesa})")

            st.markdown("##### 🚗 / 🛠️ Adăugare Rapidă Servicii & Transport (Tarife Implicite)")
            with st.expander("Selectează din lista de tarife standard configurate în Setări", expanded=True):
                opt_filtru_grila = ["Toate grilele", "Nivel A", "Nivel B", "Nivel C"]
                default_idx_grila = opt_filtru_grila.index(grila_activa_utilaj) if grila_activa_utilaj in opt_filtru_grila else 0
                filtru_grila_sel = st.radio(
                    "Filtrare listă tarife după grilă:",
                    options=opt_filtru_grila,
                    index=default_idx_grila,
                    horizontal=True,
                    key="radio_filtru_grila_tarife",
                )
                if filtru_grila_sel != "Toate grilele":
                    tarife_filtrate = [
                        t for t in tarife_disponibile if str(t.get("nivel_grila") or "Nivel A").strip() == filtru_grila_sel
                    ]
                else:
                    tarife_filtrate = tarife_disponibile

                tarife_dict = {
                    f"[{t.get('nivel_grila') or 'Nivel A'}] {t['descriere']} ({float(t['pret']):.2f} {t['moneda_um']})": t
                    for t in tarife_filtrate
                }

                def on_schimbare_serviciu():
                    cheie_aleasa = st.session_state.get("sel_tarif_standard", "-- Alege din listă --")
                    if cheie_aleasa != "-- Alege din listă --" and cheie_aleasa in tarife_dict:
                        desc_norm = _normalizeaza_text_fara_diacritice(tarife_dict[cheie_aleasa]["descriere"])
                        if desc_norm.startswith("ora de") or desc_norm.startswith("ore de") or este_ore_transport(desc_norm):
                            st.session_state["cant_tarif_std"] = None

                st.session_state.setdefault("cant_tarif_std", 1.0)

                col_srv1, col_srv2, col_srv3, col_srv4 = st.columns([3, 1, 1, 1], vertical_alignment="bottom")
                with col_srv1:
                    sel_tarif_key = st.selectbox(
                        "Alege serviciul / activitatea",
                        options=["-- Alege din listă --"] + list(tarife_dict.keys()),
                        key="sel_tarif_standard",
                        on_change=on_schimbare_serviciu,
                    )

                este_tarif_ore_tr = (
                    sel_tarif_key != "-- Alege din listă --" and este_ore_transport(tarife_dict[sel_tarif_key]["descriere"])
                )

                with col_srv2:
                    cant_tarif = st.number_input(
                        "Cantitate",
                        min_value=0.01,
                        max_value=MAX_ORE_TRANSPORT_ZI if este_tarif_ore_tr else None,
                        step=0.5 if este_tarif_ore_tr else 1.0,
                        placeholder="Introdu orele..." if este_tarif_ore_tr else None,
                        help=f"Maximum {int(MAX_ORE_TRANSPORT_ZI)} ore/zi pentru Ore transport" if este_tarif_ore_tr else None,
                        key="cant_tarif_std",
                    )
                with col_srv3:
                    termen_tarif = st.text_input("Termen livrare", value="1", key="termen_tarif_std")
                with col_srv4:
                    if st.button("➕ Adaugă", key="btn_add_tarif_std", use_container_width=True):
                        if sel_tarif_key != "-- Alege din listă --":
                            t_info = tarife_dict[sel_tarif_key]
                            if cant_tarif is None or float(cant_tarif) <= 0:
                                st.warning("⚠️ Vă rugăm să introduceți cantitatea înainte de a adăuga!")
                            else:
                                cant_valida, _ = _valideaza_si_plafoneaza_ore_transport(
                                    t_info["descriere"], float(cant_tarif)
                                )
                                pret_unitar = round(float(t_info["pret"]), 2)
                                mon_um_brut = str(t_info.get("moneda_um") or "RON").upper()
                                moneda_tarif = "EUR" if "EUR" in mon_um_brut else "RON"
                                um_normalizata = normalizeaza_um(mon_um_brut)
                                df_baza_s = _sincronizeaza_editor_inainte_de_adaugare()
                                next_ord = len(df_baza_s) + 1

                                linie_noua = pd.DataFrame([{
                                    "Ordine": next_ord,
                                    "Descriere": t_info["descriere"],
                                    "UM": um_normalizata,
                                    "Cantitate": cant_valida,
                                    "Pret Unitar": pret_unitar,
                                    "Moneda": moneda_tarif,
                                    "Termen livrare": termen_tarif,
                                }])
                                st.session_state["df_oferta_editor"] = pd.concat([df_baza_s, linie_noua], ignore_index=True)
                                st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                                st.toast(f"✅ Adăugat: {t_info['descriere']} ({pret_unitar:.2f} {moneda_tarif})")

            st.markdown("##### 📋 Tabel Poziții Ofertă (Prețuri pe linie în RON sau EUR)")
            st.caption(
                f"💡 **Reordonare / Inserare la mijloc:** Schimbă numărul în coloana **Ordine**, "
                f"inserează un rând gol la mijloc, sau folosește **Ctrl+C / Ctrl+V** pe celule. Monedă finală: **{moneda_oferta}** (curs BNR: **{curs_valutar:.4f}**)."
            )

            df_pt_editor = _asigura_df_oferta_editor().reset_index(drop=True)
            if "Ordine" not in df_pt_editor.columns:
                df_pt_editor.insert(0, "Ordine", range(1, len(df_pt_editor) + 1))

            reset_cnt = st.session_state.get("editor_reset_counter", 0)
            edited_oferta_df = st.data_editor(
                df_pt_editor,
                num_rows="dynamic",
                hide_index=True,
                column_config={
                    "Ordine": st.column_config.NumberColumn(
                        "Ordine", min_value=1, step=1, format="%d", default=len(df_pt_editor) + 1, width="small"
                    ),
                    "Descriere": st.column_config.TextColumn("Denumire Articol / Serviciu", required=False, width="large"),
                    "UM": st.column_config.SelectboxColumn(
                        "UM", options=["buc", "ore", "set", "ml", "kg", "km", "intervenție", "proiect"], default="buc", width="small"
                    ),
                    "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, format="%.2f", default=1.0, width="small"),
                    "Pret Unitar": st.column_config.NumberColumn("Preț Unitar", min_value=0.0, format="%.2f", default=0.0, width="small"),
                    "Moneda": st.column_config.SelectboxColumn("Moneda", options=["RON", "EUR"], default="EUR", width="small"),
                    "Termen livrare": st.column_config.TextColumn("Termen livrare", default="1", width="small"),
                },
                key=f"editor_linii_oferta_unic_{reset_cnt}",
                use_container_width=True,
            )

            st.session_state["_snapshot_edited_oferta_df"] = edited_oferta_df.copy()

            if not edited_oferta_df.empty:
                c_ord1, c_ins_pos, c_ins_btn = st.columns([2.0, 1.2, 1.8], vertical_alignment="bottom")
                if c_ord1.button("🔄 Aplică Ordinea & Renumerotează", key="btn_aplica_ordinea_oferta", use_container_width=True):
                    df_sortat = edited_oferta_df.copy()
                    df_sortat = df_sortat[df_sortat["Descriere"].fillna("").astype(str).str.strip() != ""].copy()
                    df_sortat["Ordine"] = pd.to_numeric(df_sortat["Ordine"], errors="coerce").fillna(999)
                    df_sortat = df_sortat.sort_values(by="Ordine", kind="mergesort").reset_index(drop=True)
                    df_sortat["Ordine"] = range(1, len(df_sortat) + 1)
                    st.session_state["df_oferta_editor"] = df_sortat
                    st.session_state["_snapshot_edited_oferta_df"] = df_sortat.copy()
                    st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                    st.rerun(scope="fragment")

                nr_randuri_cur = len(edited_oferta_df)
                poz_inserare = c_ins_pos.number_input(
                    "La poziția (Nr.)",
                    min_value=1,
                    max_value=nr_randuri_cur + 1,
                    value=min(2, nr_randuri_cur + 1),
                    step=1,
                    key="num_poz_inserare_oferta",
                )
                if c_ins_btn.button("➕ Inserează rând gol la mijloc", key="btn_insert_row_mid_oferta", use_container_width=True):
                    df_curent = edited_oferta_df.reset_index(drop=True)
                    idx_split = int(poz_inserare) - 1
                    rand_gol = pd.DataFrame([{
                        "Ordine": int(poz_inserare),
                        "Descriere": "",
                        "UM": "buc",
                        "Cantitate": 1.0,
                        "Pret Unitar": 0.0,
                        "Moneda": moneda_oferta,
                        "Termen livrare": "1",
                    }])
                    df_nou = pd.concat(
                        [df_curent.iloc[:idx_split], rand_gol, df_curent.iloc[idx_split:]],
                        ignore_index=True,
                    )
                    df_nou["Ordine"] = range(1, len(df_nou) + 1)
                    st.session_state["df_oferta_editor"] = df_nou
                    st.session_state["_snapshot_edited_oferta_df"] = df_nou.copy()
                    st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                    st.rerun(scope="fragment")

            depasire_transport = False
            if not edited_oferta_df.empty and {"Descriere", "Cantitate"}.issubset(edited_oferta_df.columns):
                for idx_row, row_val in edited_oferta_df.iterrows():
                    cant_raw = float(pd.to_numeric(row_val.get("Cantitate"), errors="coerce") or 0.0)
                    cant_val, plafonat = _valideaza_si_plafoneaza_ore_transport(row_val.get("Descriere"), cant_raw)
                    if plafonat:
                        edited_oferta_df.at[idx_row, "Cantitate"] = cant_val
                        depasire_transport = True

            if depasire_transport:
                st.session_state["df_oferta_editor"] = edited_oferta_df.reset_index(drop=True)
                st.session_state["_snapshot_edited_oferta_df"] = edited_oferta_df.reset_index(drop=True)
                st.warning(
                    f"⚠️ Limita legală de condus este de maximum **{int(MAX_ORE_TRANSPORT_ZI)} ore / zi**. "
                    f"Cantitatea pentru **Ore transport** a fost limitată automat la **{int(MAX_ORE_TRANSPORT_ZI)}**."
                )
                st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1
                st.rerun(scope="fragment")

            if not edited_oferta_df.empty:
                df_calc = edited_oferta_df[edited_oferta_df["Descriere"].fillna("").astype(str).str.strip() != ""]
                sub_final_prev = 0.0
                for _, r in df_calc.iterrows():
                    cant_p = float(pd.to_numeric(r.get("Cantitate"), errors="coerce") or 0.0)
                    pret_p = float(pd.to_numeric(r.get("Pret Unitar"), errors="coerce") or 0.0)
                    mon_p = str(r.get("Moneda") or "RON").strip().upper()
                    pret_conv = converteste_in_moneda_oferta(pret_p, mon_p, moneda_oferta, curs_valutar)
                    sub_final_prev += round(cant_p * pret_conv, 2)

                sub_final_prev = round(sub_final_prev, 2)
                tva_final_prev = round(sub_final_prev * (cota_tva_procent / 100.0), 2)
                tot_final_prev = round(sub_final_prev + tva_final_prev, 2)
                st.info(
                    f"🧮 **Previzualizare Total Ofertă ({moneda_oferta}):** **{sub_final_prev:,.2f} {moneda_oferta}** fără TVA | "
                    f"TVA ({cota_tva_procent:g}%): **{tva_final_prev:,.2f} {moneda_oferta}** | "
                    f"**TOTAL GENERAL: {tot_final_prev:,.2f} {moneda_oferta}** (curs BNR: {curs_valutar:.4f})"
                )

        _fragment_adaugare_rapida_si_tabel()

        st.markdown("##### 🎯 Discount Ofertă")
        k_td, _ = lega_camp("oferta_draft", "tip_discount", "Fără discount", "ofs", "ofs_cnt")
        k_vd, _ = lega_camp(
            "oferta_draft",
            "valoare_discount_total",
            0.0,
            "ofs",
            "ofs_cnt",
            transform=lambda x: float(x or 0.0),
        )

        cd1, cd2 = st.columns([2, 1.5], vertical_alignment="bottom")
        with cd1:
            tip_discount = st.selectbox(
                "Tip discount",
                options=["Fără discount", "Discount pe reper (%)", "Discount pe total (%)", "Discount fix"],
                key=k_td,
                on_change=sync_camp,
                args=("oferta_draft", k_td, "tip_discount"),
            )
        with cd2:
            if tip_discount == "Discount pe total (%)":
                valoare_discount_total = st.number_input(
                    "Discount total (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    format="%.2f",
                    key=k_vd,
                    on_change=sync_camp,
                    args=("oferta_draft", k_vd, "valoare_discount_total"),
                )
            elif tip_discount == "Discount fix":
                valoare_discount_total = st.number_input(
                    f"Discount fix ({moneda_oferta})",
                    min_value=0.0,
                    step=10.0,
                    format="%.2f",
                    key=k_vd,
                    on_change=sync_camp,
                    args=("oferta_draft", k_vd, "valoare_discount_total"),
                )
            elif tip_discount == "Discount pe reper (%)":
                valoare_discount_total = 0.0
                st.caption("Completează **Discount (%)** direct pe reperul dorit în tabelul de poziții.")
            else:
                valoare_discount_total = 0.0
                st.caption("Niciun discount aplicat.")

        st.markdown("##### 💬 Mențiuni / Clauze Subsol Ofertă")

        k_obs, v_obs = lega_camp(
            "oferta_draft", "observatii", get_text_clauze_implicite(moneda_oferta, setari_firma), "ofs", "ofs_cnt"
        )

        if draft.get("ultima_moneda_fraze") != moneda_oferta:
            moneda_veche = draft.get("ultima_moneda_fraze", "EUR")
            obs_actualizat = str(v_obs).replace(f"exprimată în {moneda_veche}", f"exprimată în {moneda_oferta}")
            draft["observatii"] = obs_actualizat
            draft["ultima_moneda_fraze"] = moneda_oferta
            st.session_state[k_obs] = obs_actualizat

        fraze_db = FrazeRepository.get_all() or []
        lista_continut_fraze = [f["continut"] for f in fraze_db if f.get("continut")]

        col_fr1, col_fr2 = st.columns([4, 1], vertical_alignment="bottom")
        with col_fr1:
            fraza_selectata = st.selectbox(
                "Inserează o clauză predefinită în textul de mai jos:",
                options=["-- Selectează clauza --"] + lista_continut_fraze,
                key="sel_fraza_adauga",
            )
        with col_fr2:
            if st.button("➕ Inserează", key="btn_add_fraza_lista", use_container_width=True):
                if fraza_selectata != "-- Selectează clauza --":
                    text_curent = str(st.session_state.get(k_obs, "")).strip()
                    nou_text = f"{text_curent}\n{fraza_selectata}" if text_curent else fraza_selectata
                    draft["observatii"] = nou_text
                    st.session_state[k_obs] = nou_text
                    st.rerun()

        observatii = st.text_area(
            "Text mențiuni subsol PDF:",
            height=145,
            key=k_obs,
            on_change=sync_camp,
            args=("oferta_draft", k_obs, "observatii"),
        )

        col_act1, col_act2 = st.columns([2, 1], vertical_alignment="bottom")
        with col_act1:
            if st.button("💾 Salvează și Generează PDF Ofertă", type="primary", key="btn_gen_pdf_oferta", use_container_width=True):
                if sel_firma == "-- Alege firma --":
                    st.error("⚠️ Vă rugăm să selectați o firmă client înainte de a salva oferta!")
                    return

                edited_oferta_df = st.session_state.get("_snapshot_edited_oferta_df", _asigura_df_oferta_editor())
                df_valid = edited_oferta_df[edited_oferta_df["Descriere"].fillna("").astype(str).str.strip() != ""].copy()
                if df_valid.empty:
                    st.error("Adăugați cel puțin un articol în tabel.")
                    return

                for _, r_chk in df_valid.iterrows():
                    _, plafonat_chk = _valideaza_si_plafoneaza_ore_transport(
                        r_chk.get("Descriere"), float(r_chk.get("Cantitate", 0))
                    )
                    if plafonat_chk:
                        st.error(
                            f"⚠️ Activitatea **{r_chk.get('Descriere')}** nu poate depăși **{int(MAX_ORE_TRANSPORT_ZI)} ore / zi**!"
                        )
                        return

                if "Ordine" in df_valid.columns:
                    df_valid["Ordine"] = pd.to_numeric(df_valid["Ordine"], errors="coerce").fillna(999)
                    df_valid = df_valid.sort_values(by="Ordine", kind="mergesort")

                calc_res = _calculeaza_totaluri_cu_discount(
                    df_valid=df_valid,
                    moneda_oferta=moneda_oferta,
                    curs_valutar=float(curs_valutar),
                    cota_tva_procent=cota_tva_procent,
                    tip_discount=tip_discount,
                    valoare_discount_total=float(valoare_discount_total or 0.0),
                )

                nr_oferta = nr_oferta_input.strip() or OferteRepository.get_next_numar_oferta()

                date_oferta_db = {
                    "numar_oferta": nr_oferta,
                    "data": data_oferta,
                    "client": sel_firma,
                    "cui_client": client_obj.get("cui", ""),
                    "reg_com_client": client_obj.get("reg_com", "") or client_obj.get("nr_reg_com", ""),
                    "adresa_client": client_obj.get("adresa", ""),
                    "in_atentia": in_atentia,
                    "titlu": titlu_oferta,
                    "formula_adresare": formula_adresare,
                    "valabilitate": valabilitate_oferta,
                    "termeni_plata": termeni_plata_oferta,
                    "intocmit_de": intocmit_de,
                    "acceptat_de": acceptat_de,
                    "utilaj": utilaj_nume,
                    "utilaj_tip": utilaj_tip,
                    "utilaj_serie": utilaj_serie,
                    "utilaj_an": utilaj_an,
                    "observatii": observatii,
                    "moneda": moneda_oferta,
                    "curs_valutar": float(curs_valutar),
                    "cota_tva": float(cota_tva_procent),
                    "articole": calc_res["linii"],
                    "subtotal_brut": calc_res["subtotal_brut"],
                    "tip_discount": tip_discount,
                    "valoare_discount_input": float(valoare_discount_total or 0.0),
                    "valoare_discount": calc_res["discount_valoare"],
                    "subtotal": calc_res["subtotal"],
                    "tva": calc_res["tva"],
                    "total_general": calc_res["total_general"],
                    "status": "Emisă",
                    "este_revizuita": False,
                    "actiune_registru": "Emisă",
                }

                id_generat = OferteRepository.insert(date_oferta_db)
                nr_final_pdf = nr_oferta if nr_oferta else id_generat
                date_oferta_db["id"] = nr_final_pdf
                date_oferta_db["numar_oferta"] = nr_final_pdf

                linii_nc = _construieste_linii_nota_comanda(
                    df_valid=df_valid,
                    moneda_oferta=moneda_oferta,
                    curs_valutar=float(curs_valutar),
                    adaos_client=adaos_client,
                )
                note_generate = NoteComandaRepository.genereaza_din_oferta(
                    oferta_id=id_generat,
                    numar_oferta=str(nr_final_pdf),
                    data_emitere=data_oferta,
                    client_nume=sel_firma,
                    linii_furnizor=linii_nc,
                    cerere_oferta_id=st.session_state.pop("oferta_cerere_furnizor_id", None),
                    observatii=f"Generată automat din oferta #{nr_final_pdf}",
                )

                sync_oferta_in_fundal(date_oferta_db)

                st.session_state["pdf_oferta_bytes"] = genereaza_pdf_oferta(date_oferta_db)
                st.session_state["pdf_oferta_nume"] = f"Oferta_{nr_final_pdf}_{sel_firma.replace(' ', '_')}.pdf"
                nc_txt = (
                    " | Note comandă generate: "
                    + ", ".join(f"{nc['numar_nota']} ({nc['furnizor_nume']})" for nc in note_generate)
                    if note_generate
                    else ""
                )
                st.session_state["ultima_oferta_salvata_msg"] = (
                    f"✅ Oferta #{nr_final_pdf} a fost salvată ({calc_res['total_general']:,.2f} {moneda_oferta}){nc_txt}! "
                    f"Formularul este pregătit pentru o ofertă nouă."
                )

                _init_sau_reseteaza_draft_oferta(
                    valabilitate_def,
                    termeni_plata_def,
                    intocmit_de_def,
                    moneda_oferta,
                    setari_firma,
                    float(curs_valutar),
                )
                st.rerun()

        with col_act2:
            if st.button("❌ Anulare Ofertă", key="btn_anulare_oferta_jos", use_container_width=True):
                _init_sau_reseteaza_draft_oferta(
                    valabilitate_def,
                    termeni_plata_def,
                    intocmit_de_def,
                    moneda_oferta,
                    setari_firma,
                    float(curs_valutar),
                )
                st.session_state["ultima_oferta_salvata_msg"] = ""
                st.session_state["pdf_oferta_bytes"] = None
                st.rerun()

        if st.session_state.get("ultima_oferta_salvata_msg"):
            st.success(st.session_state["ultima_oferta_salvata_msg"])

        if st.session_state.get("pdf_oferta_bytes"):
            nume_fisier_dl = st.session_state.get("pdf_oferta_nume", "Oferta_Pret.pdf")
            st.download_button(
                label="📥 Descarcă PDF Ofertă de Preț",
                data=st.session_state["pdf_oferta_bytes"],
                file_name=nume_fisier_dl,
                mime="application/pdf",
                type="primary",
            )

        st.markdown("---")
        st.subheader("📂 Istoric, Revizuire Prețuri și Căutare Avansată Oferte")

        f_col1, f_col2, f_col3 = st.columns(3, vertical_alignment="bottom")
        with f_col1:
            firme_filtru_opt = ["Toate firmele"] + list(firme_dict.keys())
            filtru_firma = st.selectbox("Filtrează după firmă", options=firme_filtru_opt, key="filtru_oferte_firma")
        with f_col2:
            filtru_text = st.text_input(
                "Caută după număr, titlu sau conținut", placeholder="ex: 28 sau Bewo", key="filtru_oferte_text"
            )
        with f_col3:
            filtru_status = st.selectbox(
                "Filtrează după status",
                options=["Toate", "Emisă", "Revizuită", "Acceptată", "Respinsă", "Facturată"],
                key="filtru_oferte_status",
            )

        oferte_salvate = OferteRepository.get_all() or []
        txt_search = str(filtru_text or "").strip().lower()

        oferte_filtrate = [
            of
            for of in oferte_salvate
            if ((filtru_firma == "Toate firmele") or (of["firma"] == filtru_firma))
            and ((filtru_status == "Toate") or (of["status"] == filtru_status))
            and (
                not txt_search
                or txt_search in str(of["numar_oferta"]).lower()
                or txt_search in str(of["titlu"]).lower()
                or txt_search in str(of["firma"]).lower()
            )
        ]

        if not oferte_filtrate:
            st.info("Nu există oferte care să corespundă filtrelor selectate.")
            return

        st.info(f"S-au găsit **{len(oferte_filtrate)}** oferte care corespund filtrelor.")

        for of in oferte_filtrate:
            oid = of["id"]
            nr_of = of["numar_oferta"]
            data_of = str(of["data_emitere"])[:10]
            moneda_of = of.get("moneda") or "EUR"
            curs_of = float(of.get("curs_valutar") or curs_valutar or 1.0)
            firma_hist_obj = firme_dict.get(of["firma"], {})
            total_afisat = float(of.get("total_general") or 0.0)

            with st.expander(
                f"📄 Ofertă #{nr_of} | {of['firma']} | {of['titlu']} — Total: {total_afisat:,.2f} {moneda_of} ({of['status']})"
            ):
                col_det1, col_det2, col_det3 = st.columns([2, 1, 1], vertical_alignment="bottom")
                with col_det1:
                    st.write(f"**Data emiterii:** {data_of} | **Curs BNR:** {curs_of:.4f} RON/EUR")
                    st.write(f"**Valabilitate:** {of.get('valabilitate') or valabilitate_def}")
                    st.write(f"**Termeni plată:** {of.get('termeni_plata') or termeni_plata_def}")
                with col_det2:
                    lista_statusuri = ["Emisă", "Revizuită", "Acceptată", "Respinsă", "Facturată"]
                    idx_st = lista_statusuri.index(of["status"]) if of["status"] in lista_statusuri else 0
                    nou_status = st.selectbox("Status Ofertă", lista_statusuri, index=idx_st, key=f"status_of_hist_{oid}")
                    if st.button("Actualizează Status", key=f"upd_status_{oid}", use_container_width=True):
                        OferteRepository.update_status(oid, nou_status)
                        sync_oferta_in_fundal({
                            "id": nr_of,
                            "numar_oferta": nr_of,
                            "data": of["data_emitere"],
                            "client": of["firma"],
                            "titlu": of["titlu"],
                            "moneda": moneda_of,
                            "curs_valutar": curs_of,
                            "total_general": total_afisat,
                            "status": nou_status,
                            "actiune_registru": f"Status -> {nou_status}",
                            "observatii": f"Status ofertă #{nr_of} actualizat la: {nou_status}",
                        })
                        st.success("Status actualizat și sincronizat în Registru activități!")
                        st.rerun()
                with col_det3:
                    if st.button("🗑️ Șterge Ofertă", key=f"del_of_{oid}", type="secondary", use_container_width=True):
                        sub_ant = round(total_afisat / (1.0 + cota_tva_procent / 100.0), 2)
                        sync_oferta_in_fundal({
                            "id": nr_of,
                            "numar_oferta": nr_of,
                            "data": of["data_emitere"],
                            "client": of["firma"],
                            "titlu": of["titlu"],
                            "moneda": moneda_of,
                            "curs_valutar": curs_of,
                            "subtotal": sub_ant,
                            "tva": round(total_afisat - sub_ant, 2),
                            "total_general": 0.0,
                            "valoare_anterioara": total_afisat,
                            "status": "Ștearsă",
                            "este_stearsa": True,
                            "actiune_registru": "Ștearsă",
                            "observatii": f"Ofertă #{nr_of} ȘTEARSĂ (valoare anterioară: {total_afisat:,.2f} {moneda_of})",
                        })
                        OferteRepository.delete(oid)
                        st.success("Oferta a fost ștearsă și înregistrată în Registru activități!")
                        st.rerun()

                articole_salvate = of.get("articole_json", [])
                if isinstance(articole_salvate, str):
                    try:
                        articole_salvate = json.loads(articole_salvate)
                    except Exception:
                        articole_salvate = []

                col_pret_hist = f"Pret Unitar ({moneda_of})"
                hist_state_key = f"df_hist_state_{oid}"
                hist_counter_key = f"hist_editor_counter_{oid}"
                st.session_state.setdefault(hist_counter_key, 0)

                if hist_state_key not in st.session_state:
                    df_art_vechi = (
                        pd.DataFrame(articole_salvate)
                        if articole_salvate
                        else pd.DataFrame(
                            columns=[
                                "Ordine",
                                "Descriere",
                                "UM",
                                "Cantitate",
                                "Pret Sursa",
                                "Moneda Sursa",
                                col_pret_hist,
                                "Termen livrare",
                            ]
                        )
                    )
                    for c_name in list(df_art_vechi.columns):
                        if "Pret Unitar" in c_name and c_name != col_pret_hist:
                            if col_pret_hist not in df_art_vechi.columns:
                                df_art_vechi = df_art_vechi.rename(columns={c_name: col_pret_hist})
                            else:
                                df_art_vechi = df_art_vechi.drop(columns=[c_name])
                    if col_pret_hist not in df_art_vechi.columns:
                        df_art_vechi[col_pret_hist] = 0.0
                    if "Pret Sursa" not in df_art_vechi.columns:
                        df_art_vechi["Pret Sursa"] = pd.to_numeric(df_art_vechi[col_pret_hist], errors="coerce").fillna(0.0)
                    if "Moneda Sursa" not in df_art_vechi.columns:
                        df_art_vechi["Moneda Sursa"] = moneda_of
                    if "Termen livrare" not in df_art_vechi.columns:
                        df_art_vechi["Termen livrare"] = ""
                    df_art_vechi = df_art_vechi.reset_index(drop=True)
                    df_art_vechi["Ordine"] = range(1, len(df_art_vechi) + 1)

                    coloane_ordonate_h = [
                        "Ordine",
                        "Descriere",
                        "UM",
                        "Cantitate",
                        "Pret Sursa",
                        "Moneda Sursa",
                        col_pret_hist,
                        "Termen livrare",
                    ]
                    alte_col_h = [c for c in df_art_vechi.columns if c not in coloane_ordonate_h]
                    st.session_state[hist_state_key] = df_art_vechi[coloane_ordonate_h + alte_col_h]

                st.markdown("##### ✏️ Editare & Reordonare Poziții / Prețuri (pentru Revizuire Ofertă):")
                st.caption(
                    f"💡 Modifică **Preț Sursa** și **Moneda Sursa** — coloana **{col_pret_hist}** și totalul PDF se recalculează automat folosind cursul BNR (**{curs_of:.4f}**)."
                )
                df_hist_curent = st.session_state[hist_state_key].reset_index(drop=True)
                df_art_editat_hist = st.data_editor(
                    df_hist_curent,
                    num_rows="dynamic",
                    hide_index=True,
                    column_config={
                        "Ordine": st.column_config.NumberColumn(
                            "Ordine", min_value=1, step=1, format="%d", default=len(df_hist_curent) + 1, width="small"
                        ),
                        "Descriere": st.column_config.TextColumn("Denumire Articol / Serviciu", required=False, width="large"),
                        "UM": st.column_config.SelectboxColumn(
                            "UM", options=["buc", "ore", "set", "ml", "kg", "km", "intervenție", "proiect"], default="buc", width="small"
                        ),
                        "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, format="%.2f", default=1.0, width="small"),
                        "Pret Sursa": st.column_config.NumberColumn("Preț Sursa", min_value=0.0, format="%.2f", default=0.0, width="small"),
                        "Moneda Sursa": st.column_config.SelectboxColumn("Moneda Sursa", options=["RON", "EUR"], default=moneda_of, width="small"),
                        col_pret_hist: st.column_config.NumberColumn(
                            f"Preț ({moneda_of}) [Auto]", min_value=0.0, format="%.2f", default=0.0, disabled=True, width="small"
                        ),
                        "Termen livrare": st.column_config.TextColumn("Termen livrare", default="1", width="small"),
                    },
                    key=f"hist_editor_{oid}_{st.session_state[hist_counter_key]}",
                    use_container_width=True,
                )

                if not df_art_editat_hist.empty:
                    df_art_editat_hist = df_art_editat_hist.copy()
                    for idx_h, r_h in df_art_editat_hist.iterrows():
                        p_src_val = float(pd.to_numeric(r_h.get("Pret Sursa"), errors="coerce") or 0.0)
                        m_src_val = str(r_h.get("Moneda Sursa") or moneda_of).strip().upper()
                        df_art_editat_hist.at[idx_h, col_pret_hist] = converteste_in_moneda_oferta(
                            p_src_val, m_src_val, moneda_of, curs_of
                        )

                    df_h_calc = df_art_editat_hist[df_art_editat_hist["Descriere"].fillna("").astype(str).str.strip() != ""].copy()
                    cant_ser = pd.to_numeric(df_h_calc["Cantitate"], errors="coerce").fillna(0.0)
                    pret_ser = pd.to_numeric(df_h_calc[col_pret_hist], errors="coerce").fillna(0.0)
                    sub_hist_prev = round(float((cant_ser * pret_ser).sum()), 2)
                    tva_hist_prev = round(sub_hist_prev * (cota_tva_procent / 100.0), 2)
                    tot_hist_prev = round(sub_hist_prev + tva_hist_prev, 2)

                    st.info(
                        f"🧮 **Total Recalculat (Previzualizare Live — {moneda_of}):** "
                        f"**{sub_hist_prev:,.2f} {moneda_of}** fără TVA | "
                        f"TVA ({cota_tva_procent:g}%): **{tva_hist_prev:,.2f} {moneda_of}** | "
                        f"**TOTAL GENERAL: {tot_hist_prev:,.2f} {moneda_of}**"
                    )

                    ch_ord1, ch_ins_pos, ch_ins_btn = st.columns([2.0, 1.2, 1.8], vertical_alignment="bottom")
                    if ch_ord1.button("🔄 Aplică Ordinea & Renumerotează", key=f"btn_ord_hist_{oid}", use_container_width=True):
                        df_h_sort = df_art_editat_hist[
                            df_art_editat_hist["Descriere"].fillna("").astype(str).str.strip() != ""
                        ].copy()
                        df_h_sort["Ordine"] = pd.to_numeric(df_h_sort["Ordine"], errors="coerce").fillna(999)
                        df_h_sort = df_h_sort.sort_values(by="Ordine", kind="mergesort").reset_index(drop=True)
                        df_h_sort["Ordine"] = range(1, len(df_h_sort) + 1)
                        st.session_state[hist_state_key] = df_h_sort
                        st.session_state[hist_counter_key] += 1
                        st.rerun()

                    nr_h_cur = len(df_art_editat_hist)
                    poz_h_ins = ch_ins_pos.number_input(
                        "La poziția (Nr.)",
                        min_value=1,
                        max_value=nr_h_cur + 1,
                        value=min(2, nr_h_cur + 1),
                        step=1,
                        key=f"num_poz_ins_hist_{oid}",
                    )
                    if ch_ins_btn.button("➕ Inserează rând gol la mijloc", key=f"btn_ins_mid_hist_{oid}", use_container_width=True):
                        df_h_c = df_art_editat_hist.reset_index(drop=True)
                        idx_h_sp = int(poz_h_ins) - 1
                        rand_h_gol = pd.DataFrame([{
                            "Ordine": int(poz_h_ins),
                            "Descriere": "",
                            "UM": "buc",
                            "Cantitate": 1.0,
                            "Pret Sursa": 0.0,
                            "Moneda Sursa": moneda_of,
                            col_pret_hist: 0.0,
                            "Termen livrare": "1",
                        }])
                        df_h_nou = pd.concat([df_h_c.iloc[:idx_h_sp], rand_h_gol, df_h_c.iloc[idx_h_sp:]], ignore_index=True)
                        df_h_nou["Ordine"] = range(1, len(df_h_nou) + 1)
                        st.session_state[hist_state_key] = df_h_nou
                        st.session_state[hist_counter_key] += 1
                        st.rerun()

                obs_hist_editat = st.text_area(
                    "Mențiuni subsol ofertă",
                    value=str(of.get("observatii") or ""),
                    height=95,
                    key=f"hist_obs_{oid}",
                )

                c_hbtn1, c_hbtn2 = st.columns(2)
                with c_hbtn1:
                    if st.button(
                        f"🔄 Salvează Revizia & Generează PDF Revizuit #{nr_of}",
                        type="primary",
                        key=f"rev_pdf_hist_{oid}",
                        use_container_width=True,
                    ):
                        df_h_val = df_art_editat_hist[
                            df_art_editat_hist["Descriere"].fillna("").astype(str).str.strip() != ""
                        ].copy()
                        if "Ordine" in df_h_val.columns:
                            df_h_val["Ordine"] = pd.to_numeric(df_h_val["Ordine"], errors="coerce").fillna(999)
                            df_h_val = df_h_val.sort_values(by="Ordine", kind="mergesort").reset_index(drop=True)

                        df_h_val["Cantitate"] = pd.to_numeric(df_h_val["Cantitate"], errors="coerce").fillna(0.0)
                        df_h_val["Pret Sursa"] = pd.to_numeric(df_h_val["Pret Sursa"], errors="coerce").fillna(0.0)
                        df_h_val["Moneda Sursa"] = (
                            df_h_val["Moneda Sursa"].fillna(moneda_of).astype(str).str.strip().str.upper()
                        )
                        df_h_val[col_pret_hist] = [
                            converteste_in_moneda_oferta(p_s, m_s, moneda_of, curs_of)
                            for p_s, m_s in zip(df_h_val["Pret Sursa"], df_h_val["Moneda Sursa"])
                        ]

                        df_h_sync = df_h_val.copy()
                        df_h_sync["Ordine"] = range(1, len(df_h_sync) + 1)
                        st.session_state[hist_state_key] = df_h_sync
                        st.session_state[hist_counter_key] += 1

                        linii_rev = df_h_val.drop(columns=["Ordine"], errors="ignore").to_dict(orient="records")
                        for l_r in linii_rev:
                            _, plafonat_r = _valideaza_si_plafoneaza_ore_transport(
                                l_r.get("Descriere"), float(l_r.get("Cantitate", 0))
                            )
                            if plafonat_r:
                                st.error(
                                    f"⚠️ Activitatea **{l_r.get('Descriere')}** nu poate depăși **{int(MAX_ORE_TRANSPORT_ZI)} ore / zi**!"
                                )
                                st.stop()

                        sub_rev = round(
                            sum(round(float(l.get("Cantitate", 1)) * float(l.get(col_pret_hist, 0)), 2) for l in linii_rev), 2
                        )
                        tva_rev = round(sub_rev * (cota_tva_procent / 100.0), 2)
                        tot_rev = round(sub_rev + tva_rev, 2)

                        OferteRepository.update_oferta_revizuita(oid, linii_rev, tot_rev, obs_hist_editat)

                        pers_hist = extrage_nume_persoana_firma(firma_hist_obj)
                        date_pdf_rev = {
                            "id": nr_of,
                            "numar_oferta": nr_of,
                            "data": of["data_emitere"],
                            "client": of["firma"],
                            "cui_client": firma_hist_obj.get("cui", ""),
                            "reg_com_client": firma_hist_obj.get("reg_com", "") or firma_hist_obj.get("nr_reg_com", ""),
                            "adresa_client": firma_hist_obj.get("adresa", ""),
                            "in_atentia": f"În atenția {pers_hist}" if pers_hist else "",
                            "titlu": of["titlu"],
                            "valabilitate": of.get("valabilitate") or valabilitate_def,
                            "termeni_plata": of.get("termeni_plata") or termeni_plata_def,
                            "intocmit_de": intocmit_de_def,
                            "acceptat_de": pers_hist,
                            "observatii": obs_hist_editat,
                            "moneda": moneda_of,
                            "curs_valutar": curs_of,
                            "cota_tva": float(cota_tva_procent),
                            "articole": linii_rev,
                            "subtotal": sub_rev,
                            "tva": tva_rev,
                            "total_general": tot_rev,
                            "valoare_anterioara": total_afisat,
                            "status": "Revizuită",
                            "este_revizuita": True,
                            "actiune_registru": "Revizuită",
                        }
                        sync_oferta_in_fundal(date_pdf_rev)

                        st.session_state[f"pdf_hist_bytes_{oid}"] = genereaza_pdf_oferta(date_pdf_rev)
                        st.session_state[f"pdf_hist_nume_{oid}"] = f"Oferta_{nr_of}_REVIZUITA.pdf"
                        st.session_state[f"msg_rev_ok_{oid}"] = (
                            f"✅ Oferta #{nr_of} a fost recalculată ({tot_rev:,.2f} {moneda_of}), "
                            f"salvată ca REVIZUITĂ și trimisă în Registru activități!"
                        )
                        st.rerun()

                with c_hbtn2:
                    if st.button(f"📥 Generează PDF Ofertă #{nr_of} (forma curentă)", key=f"dl_pdf_hist_{oid}", use_container_width=True):
                        df_h_cur_val = df_art_editat_hist[
                            df_art_editat_hist["Descriere"].fillna("").astype(str).str.strip() != ""
                        ].copy()
                        if "Ordine" in df_h_cur_val.columns:
                            df_h_cur_val["Ordine"] = pd.to_numeric(df_h_cur_val["Ordine"], errors="coerce").fillna(999)
                            df_h_cur_val = df_h_cur_val.sort_values(by="Ordine", kind="mergesort")
                        df_h_cur_val["Cantitate"] = pd.to_numeric(df_h_cur_val["Cantitate"], errors="coerce").fillna(0.0)
                        df_h_cur_val["Pret Sursa"] = pd.to_numeric(df_h_cur_val["Pret Sursa"], errors="coerce").fillna(0.0)
                        df_h_cur_val["Moneda Sursa"] = (
                            df_h_cur_val["Moneda Sursa"].fillna(moneda_of).astype(str).str.strip().str.upper()
                        )
                        df_h_cur_val[col_pret_hist] = [
                            converteste_in_moneda_oferta(p_s, m_s, moneda_of, curs_of)
                            for p_s, m_s in zip(df_h_cur_val["Pret Sursa"], df_h_cur_val["Moneda Sursa"])
                        ]
                        linii_cur = df_h_cur_val.drop(columns=["Ordine"], errors="ignore").to_dict(orient="records")
                        for l_c in linii_cur:
                            _, plafonat_c = _valideaza_si_plafoneaza_ore_transport(
                                l_c.get("Descriere"), float(l_c.get("Cantitate", 0))
                            )
                            if plafonat_c:
                                st.error(
                                    f"⚠️ Activitatea **{l_c.get('Descriere')}** nu poate depăși **{int(MAX_ORE_TRANSPORT_ZI)} ore / zi**!"
                                )
                                st.stop()

                        sub_cur = sum(float(l.get("Cantitate", 1)) * float(l.get(col_pret_hist, 0)) for l in linii_cur)
                        tva_cur = round(sub_cur * (cota_tva_procent / 100.0), 2)
                        tot_cur = round(sub_cur + tva_cur, 2)
                        este_rev = of.get("status") == "Revizuită"

                        pers_hist = extrage_nume_persoana_firma(firma_hist_obj)
                        date_pdf = {
                            "id": nr_of,
                            "numar_oferta": nr_of,
                            "data": of["data_emitere"],
                            "client": of["firma"],
                            "cui_client": firma_hist_obj.get("cui", ""),
                            "reg_com_client": firma_hist_obj.get("reg_com", "") or firma_hist_obj.get("nr_reg_com", ""),
                            "adresa_client": firma_hist_obj.get("adresa", ""),
                            "in_atentia": f"În atenția {pers_hist}" if pers_hist else "",
                            "titlu": of["titlu"],
                            "valabilitate": of.get("valabilitate") or valabilitate_def,
                            "termeni_plata": of.get("termeni_plata") or termeni_plata_def,
                            "intocmit_de": intocmit_de_def,
                            "acceptat_de": pers_hist,
                            "observatii": obs_hist_editat,
                            "moneda": moneda_of,
                            "curs_valutar": curs_of,
                            "cota_tva": float(cota_tva_procent),
                            "articole": linii_cur,
                            "subtotal": round(sub_cur, 2),
                            "tva": tva_cur,
                            "total_general": tot_cur,
                            "este_revizuita": este_rev,
                        }
                        st.session_state[f"pdf_hist_bytes_{oid}"] = genereaza_pdf_oferta(date_pdf)
                        sufix = "_REVIZUITA" if este_rev else ""
                        st.session_state[f"pdf_hist_nume_{oid}"] = f"Oferta_{nr_of}{sufix}.pdf"

                if st.session_state.get(f"msg_rev_ok_{oid}"):
                    st.success(st.session_state[f"msg_rev_ok_{oid}"])

                if st.session_state.get(f"pdf_hist_bytes_{oid}"):
                    nume_hist_dl = st.session_state[f"pdf_hist_nume_{oid}"]
                    st.download_button(
                        label=f"⬇️ Descarcă {nume_hist_dl}",
                        data=st.session_state[f"pdf_hist_bytes_{oid}"],
                        file_name=nume_hist_dl,
                        mime="application/pdf",
                        type="primary",
                        key=f"btn_dl_real_{oid}",
                    )