#-------------------------------
#-------sync_service.py---------
#-------------------------------

import json
import urllib.request
import streamlit as st
from repositories.setari_repository import SetariRepository
from services.email_service import trimite_email_raport
from config import logger

def update_google_sheet(payload_sheet: dict) -> tuple[bool, str]:
    setari_info = SetariRepository.get_setari()
    sheet_url = (setari_info.get('google_sheet_url') or '').strip() if setari_info else ''
    if not sheet_url:
        msg = "URL-ul Google Sheet nu este configurat în Setări."
        logger.warning(msg)
        return False, msg

    try:
        req = urllib.request.Request(
            sheet_url,
            data=json.dumps(payload_sheet, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raspuns_text = response.read().decode('utf-8', errors='ignore')
        logger.info(f"Google Sheet sincronizat ({payload_sheet.get('tip_inregistrare', 'activitate')}): {raspuns_text}")
        if '"error"' in raspuns_text.lower():
            return False, f"Eroare Apps Script: {raspuns_text}"
        return True, "OK"
    except Exception as e:
        logger.error(f"Eroare sync Google Sheet: {e}")
        return False, str(e)

def background_sync_task(payload_sheet: dict, email_client: str, subiect: str, corp_mesaj: str, pdf_bytes: bytes, nume_fisier: str):
    payload_cu_tip = dict(payload_sheet)
    payload_cu_tip.setdefault("tip_inregistrare", "activitate")
    update_google_sheet(payload_cu_tip)
    if email_client:
        trimite_email_raport(email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier)

def sync_oferta_in_fundal(date_oferta: dict):
    """Formatează datele ofertei de preț și le trimite către foaia 'Oferte de pret'."""
    articole = date_oferta.get("articole", [])
    linii_produse = []
    for idx, art in enumerate(articole, 1):
        desc = str(art.get("Descriere", "")).strip()
        cant = float(art.get("Cantitate") or 1)
        um = str(art.get("UM", "buc")).strip()
        cant_fmt = f"{int(cant)}" if cant == int(cant) else f"{cant:g}"
        linii_produse.append(f"{idx}. {desc} ({cant_fmt} {um})")

    servicii_produse_text = "\n".join(linii_produse)
    moneda = str(date_oferta.get("moneda", "EUR")).strip()
    valoare_numerica = round(float(date_oferta.get("total_general") or 0.0), 2)

    data_bruta = date_oferta.get("data", "")
    data_str = data_bruta.strftime("%d.%m.%Y") if hasattr(data_bruta, "strftime") else str(data_bruta)[:10]

    payload_oferta = {
        "tip_inregistrare": "oferta",
        "nr_oferta": str(date_oferta.get("numar_oferta", "")),
        "data_oferta": data_str,
        "stare_oferta": str(date_oferta.get("status", "Emisă")),
        "valoare_oferta": valoare_numerica,
        "moneda": moneda,
        "client": str(date_oferta.get("client", "")),
        "servicii_produse": servicii_produse_text,
        "intocmit_de": str(date_oferta.get("intocmit_de", "")),
        "valabilitate": str(date_oferta.get("valabilitate", ""))
    }

    ok, err_msg = update_google_sheet(payload_oferta)
    if not ok:
        st.warning(f"⚠️ Oferta s-a salvat în baza de date, dar nu s-a sincronizat în Google Sheet: {err_msg}")