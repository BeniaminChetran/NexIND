#----------------------------------------------
#---services/gdrive_service.py----------------
#----------------------------------------------

import io
import json
import logging
import os
import re
import streamlit as st

logger = logging.getLogger("NexIndCMMS.GDriveService")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def extrage_drive_id(url_sau_id: str) -> str:
    """Extrage ID-ul de folder sau fișier dintr-un link Google Drive sau returnează ID-ul direct."""
    val = str(url_sau_id or "").strip()
    if not val:
        return ""
    # Dacă pare deja un ID curat (fără slash-uri sau spații)
    if "/" not in val and " " not in val and len(val) >= 10:
        return val

    patterns = [
        r"/folders/([a-zA-Z0-9_-]+)",
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, val)
        if m:
            return m.group(1)
    return ""


def detecteaza_tag_din_nume(nume_fisier: str) -> str:
    """Detectează eticheta [ERR], [SCH], [PRM], [TST], [MEC], [SOL] dacă există în numele fișierului."""
    upper_name = str(nume_fisier or "").upper()
    for tag in ("[ERR]", "[SCH]", "[PRM]", "[TST]", "[MEC]", "[SOL]"):
        if tag in upper_name:
            return tag
    return "[ERR]"


def detecteaza_tip_fisier(mime_type: str, nume_fisier: str) -> str:
    mt = str(mime_type or "").lower()
    nume = str(nume_fisier or "").lower()
    if "folder" in mt:
        return "folder"
    if "pdf" in mt or nume.endswith(".pdf"):
        return "pdf"
    if mt.startswith("image/") or any(nume.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
        return "img"
    return "doc"


def _get_drive_service():
    """Construiește clientul Google Drive API dacă există credențiale de Service Account."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        logger.info("Pachetele google-api-python-client / google-auth nu sunt instalate.")
        return None

    creds_info = None
    try:
        if "gdrive_service_account" in st.secrets:
            raw_sec = st.secrets["gdrive_service_account"]
            creds_info = dict(raw_sec) if not isinstance(raw_sec, str) else json.loads(raw_sec)
    except Exception:
        creds_info = None

    if not creds_info:
        env_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        if env_json:
            try:
                creds_info = json.loads(env_json)
            except Exception as e:
                logger.warning(f"Eroare la parsarea GDRIVE_SERVICE_ACCOUNT_JSON: {e}")

    if not creds_info:
        return None

    try:
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Eroare la inițializarea Google Drive API: {e}")
        return None


def listeaza_fisiere_folder(folder_url_sau_id: str, max_results: int = 100) -> tuple[list[dict], str]:
    """
    Listează fișierele și subfolderele dintr-un folder Google Drive.
    Returnează (lista_fisiere, mesaj_status).
    """
    folder_id = extrage_drive_id(folder_url_sau_id)
    if not folder_id:
        return [], "Nu s-a putut identifica un ID valid de folder Google Drive."

    service = _get_drive_service()
    if service is None:
        return [], "Google Drive API nu este configurat (adaugă `gdrive_service_account` în secrets sau folosește indexarea manuală)."

    try:
        query = f"'{folder_id}' in parents and trashed = false"
        resp = (
            service.files()
            .list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, mimeType, webViewLink, size, modifiedTime)",
                orderBy="folder,name",
            )
            .execute()
        )
        files = resp.get("files", [])
        rez = []
        for f in files:
            rez.append({
                "id": f.get("id", ""),
                "name": f.get("name", ""),
                "mimeType": f.get("mimeType", ""),
                "webViewLink": f.get("webViewLink", f"https://drive.google.com/open?id={f.get('id', '')}"),
                "tip_fisier": detecteaza_tip_fisier(f.get("mimeType", ""), f.get("name", "")),
                "tag_sugerat": detecteaza_tag_din_nume(f.get("name", "")),
            })
        return rez, f"S-au găsit {len(rez)} elemente în folder."
    except Exception as e:
        logger.error(f"Eroare la listarea folderului Drive {folder_id}: {e}")
        return [], f"Eroare la accesarea Google Drive: {e}"


def extrage_text_pdf_drive(file_id: str, max_pages: int = 60, max_chars: int = 12000) -> str:
    """
    Descarcă un PDF din Google Drive și extrage textul (doar dacă PDF-ul conține strat text).
    Pentru PDF-uri scanate / poze, va întoarce gol sau foarte puțin text, urmând să te bazezi pe etichete/notițe.
    """
    fid = extrage_drive_id(file_id)
    if not fid:
        return ""

    service = _get_drive_service()
    if service is None:
        return ""

    try:
        from googleapiclient.http import MediaIoBaseDownload
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        request = service.files().get_media(fileId=fid)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)

        reader = PdfReader(fh)
        fragmente = []
        total_chars = 0
        for idx, page in enumerate(reader.pages[:max_pages], start=1):
            txt = (page.extract_text() or "").strip()
            if txt:
                bloc = f"[Pag. {idx}] {txt}"
                fragmente.append(bloc)
                total_chars += len(bloc)
                if total_chars >= max_chars:
                    break

        return "\n".join(fragmente)[:max_chars]
    except Exception as e:
        logger.warning(f"Nu s-a putut extrage textul din PDF {fid}: {e}")
        return ""