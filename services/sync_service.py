#-------------------------------
#-------sync_service.py---------
#-------------------------------

import json
import urllib.request
import streamlit as st
import io
import re

from repositories.setari_repository import SetariRepository
from config import logger
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


def update_google_sheet(payload_sheet: dict) -> tuple[bool, str]:
    setari_info = SetariRepository.get_setari()
    sheet_url = (setari_info.get("google_sheet_url") or "").strip() if setari_info else ""
    if not sheet_url:
        msg = "URL-ul Google Sheet nu este configurat în Setări."
        logger.warning(msg)
        return False, msg

    try:
        req = urllib.request.Request(
            sheet_url,
            data=json.dumps(payload_sheet, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raspuns_text = response.read().decode("utf-8", errors="ignore")
        logger.info(f"Google Sheet sincronizat ({payload_sheet.get('tip_inregistrare', 'activitate')}): {raspuns_text}")
        if '"error"' in raspuns_text.lower():
            return False, f"Eroare Apps Script: {raspuns_text}"
        return True, "OK"
    except Exception as e:
        logger.error(f"Eroare sync Google Sheet: {e}")
        return False, str(e)


def background_sync_task(payload_sheet: dict):
    payload_cu_tip = dict(payload_sheet)
    payload_cu_tip.setdefault("tip_inregistrare", "activitate")
    update_google_sheet(payload_cu_tip)


def sync_oferta_in_fundal(date_oferta: dict):
    """
    Formatează datele ofertei de preț și inserează un rând nou în foaia 'Oferte de pret'
    (inclusiv când oferta este 'Anulată' sau 'Modificată').
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
    stare_oferta = str(date_oferta.get("stare_oferta") or date_oferta.get("status") or "Emisă").strip()
    nr_oferta = str(date_oferta.get("numar_oferta") or date_oferta.get("id") or "")
    client_nume = str(date_oferta.get("client", ""))
    titlu_oferta = str(date_oferta.get("titlu", "Ofertă de preț"))
    intocmit_de = str(date_oferta.get("intocmit_de", ""))

    data_bruta = date_oferta.get("data", "")
    data_str = data_bruta.strftime("%d.%m.%Y") if hasattr(data_bruta, "strftime") else str(data_bruta)[:10]

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
        "valabilitate": str(date_oferta.get("valabilitate", "")),
        "titlu": titlu_oferta,
    }

    ok, err_msg = update_google_sheet(payload_oferta)
    if not ok:
        st.warning(f"⚠️ Sincronizare Google Sheet (Oferte): {err_msg}")
        
def _get_drive_service():
    sa_info = st.secrets.get("gcp_service_account")
    if not sa_info:
        return None, "Lipsește secțiunea [gcp_service_account] din st.secrets."
    creds = service_account.Credentials.from_service_account_info(
        dict(sa_info),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False), ""


def _rezolva_folder_drive(service, locatie_setata: str) -> tuple[str | None, str]:
    txt = str(locatie_setata or "").strip()
    if not txt:
        txt = "Oferte"

    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", txt)
    if m:
        return m.group(1), ""
    if re.fullmatch(r"[a-zA-Z0-9_-]{25,}", txt):
        return txt, ""

    nume_escapat = txt.replace("'", "\\'")
    resp = (
        service.files()
        .list(
            q=f"mimeType='application/vnd.google-apps.folder' and name='{nume_escapat}' and trashed=false",
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    fisiere = resp.get("files", [])
    if fisiere:
        return fisiere[0]["id"], ""

    folder_creat = (
        service.files()
        .create(
            body={"name": txt, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return folder_creat.get("id"), ""


def salveaza_pdf_oferta_in_gdrive(pdf_bytes: bytes, nume_fisier: str) -> tuple[bool, str]:
    if not pdf_bytes:
        return False, "Conținutul PDF este gol."

    service, err_srv = _get_drive_service()
    if service is None:
        return False, err_srv

    try:
        setari_info = SetariRepository.get_setari() or {}
        locatie_setata = str(setari_info.get("locatie_oferte_gdrive") or "Oferte").strip()
        folder_id, err_fld = _rezolva_folder_drive(service, locatie_setata)
        if not folder_id:
            return False, err_fld or "Nu s-a putut identifica folderul Google Drive."

        metadata = {"name": nume_fisier, "parents": [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False)
        creat = (
            service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
        logger.info(f"PDF încărcat pe Google Drive: {creat.get('name')} (id={creat.get('id')})")
        return True, f"Încărcat în Google Drive ({locatie_setata}): {creat.get('name')}"
    except Exception as e:
        logger.error(f"Eroare upload PDF Google Drive: {e}")
        return False, str(e)[cite: 6]