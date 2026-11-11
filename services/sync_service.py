#-------------------------------
#-------sync_service.py---------
#-------------------------------

import json
import urllib.request
import threading
from repositories.setari_repository import SetariRepository
from services.email_service import trimite_email_raport
from config import logger

def update_google_sheet(payload_sheet: dict):
    setari_info = SetariRepository.get_setari()
    sheet_url = setari_info['google_sheet_url']
    if sheet_url:
        try:
            req = urllib.request.Request(
                sheet_url, 
                data=json.dumps(payload_sheet).encode('utf-8'), 
                headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read().decode('utf-8')
            logger.info("Google Sheet sincronizat cu succes.")
        except Exception as e:
            logger.error(f"Eroare sync Google Sheet: {e}")

def background_sync_task(payload_sheet: dict, email_client: str, subiect: str, corp_mesaj: str, pdf_bytes: bytes, nume_fisier: str):
    update_google_sheet(payload_sheet)
    if email_client:
        trimite_email_raport(email_client, subiect, corp_mesaj, pdf_bytes, nume_fisier)