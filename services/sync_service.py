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
    """
    Formatează datele ofertei de preț și le trimite către foaia 'Oferte de pret'.
    Dacă oferta a fost revizuită (modificată suma) sau ștearsă, trimite și o înregistrare
    în foaia 'Registru activitati' (tip_inregistrare = 'activitate').
    """
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
    valoare_anterioara = date_oferta.get("valoare_anterioara")
    stare_oferta = str(date_oferta.get("status", "Emisă")).strip()
    actiune_registru = str(date_oferta.get("actiune_registru") or stare_oferta).strip()
    nr_oferta = str(date_oferta.get("numar_oferta") or date_oferta.get("id") or "")
    client_nume = str(date_oferta.get("client", ""))
    titlu_oferta = str(date_oferta.get("titlu", "Ofertă de preț"))
    intocmit_de = str(date_oferta.get("intocmit_de", ""))

    data_bruta = date_oferta.get("data", "")
    data_str = data_bruta.strftime("%d.%m.%Y") if hasattr(data_bruta, "strftime") else str(data_bruta)[:10]

    # 1. Sincronizare în foaia 'Oferte de pret'
    payload_oferta = {
        "tip_inregistrare": "oferta",
        "nr_oferta": nr_oferta,
        "data_oferta": data_str,
        "stare_oferta": stare_oferta,
        "valoare_oferta": valoare_numerica,
        "valoare_anterioara": round(float(valoare_anterioara), 2) if valoare_anterioara is not None else "",
        "moneda": moneda,
        "client": client_nume,
        "servicii_produse": servicii_produse_text,
        "intocmit_de": intocmit_de,
        "valabilitate": str(date_oferta.get("valabilitate", ""))
    }

    ok, err_msg = update_google_sheet(payload_oferta)
    if not ok:
        st.warning(f"⚠️ Oferta s-a salvat în baza de date, dar nu s-a sincronizat în Google Sheet (Oferte): {err_msg}")

    # 2. Când se modifică suma prin Revizuire sau se Șterge o ofertă, trimitem și în 'Registru activitati'
    este_revizuire_sau_stergere = (
        actiune_registru in ("Revizuită", "Ștearsă")
        or stare_oferta in ("Revizuită", "Ștearsă")
        or bool(date_oferta.get("este_stearsa"))
    )
    if este_revizuire_sau_stergere:
        if actiune_registru == "Ștearsă" or stare_oferta == "Ștearsă":
            val_ant_txt = f"{float(valoare_anterioara):,.2f} {moneda}" if valoare_anterioara is not None else "N/A"
            descriere_activitate = (
                f"[ȘTERGERE OFERTĂ #{nr_oferta}] {titlu_oferta} | "
                f"Valoare ștearsă: {val_ant_txt}"
            )
            valoare_raportata = f"-{float(valoare_anterioara or 0.0):.2f} {moneda}"
        else:
            val_ant_txt = f"{float(valoare_anterioara):,.2f} {moneda}" if valoare_anterioara is not None else "N/A"
            descriere_activitate = (
                f"[REVIZUIRE OFERTĂ #{nr_oferta}] {titlu_oferta} | "
                f"Sumă modificată: {val_ant_txt} -> {valoare_numerica:,.2f} {moneda}"
            )
            valoare_raportata = f"{valoare_numerica:.2f} {moneda}"

        payload_registru_activitati = {
            "tip_inregistrare": "activitate",
            "data": data_str,
            "client": client_nume,
            "firma": client_nume,
            "utilaj": str(date_oferta.get("utilaj") or f"Ofertă #{nr_oferta}"),
            "tip_activitate": f"Ofertă {actiune_registru}",
            "status": actiune_registru,
            "descriere": descriere_activitate,
            "observatii": descriere_activitate,
            "tehnician": intocmit_de,
            "nr_oferta": nr_oferta,
            "valoare": valoare_raportata
        }
        ok_reg, err_reg = update_google_sheet(payload_registru_activitati)
        if not ok_reg:
            st.warning(f"⚠️ Nu s-a putut trimite înregistrarea în Registru activități: {err_reg}")
