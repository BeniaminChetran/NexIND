#-----------------------
#------email_service.py-
#-----------------------

import smtplib
from email.message import EmailMessage
import streamlit as st
from repositories.setari_repository import SetariRepository
from config import logger


def trimite_email_raport(
    destinatar_client: str,
    subiect: str,
    corp_mesaj: str,
    pdf_bytes: bytes,
    nume_fisier: str,
) -> tuple[bool, str]:
    setari = SetariRepository.get_setari() or {}
    smtp_srv = str(setari.get("smtp_server") or "").strip()
    smtp_p = setari.get("smtp_port") or 587
    smtp_u = str(setari.get("smtp_user") or "").strip()
    smtp_pwd = st.secrets.get("SMTP_PASSWORD", setari.get("smtp_pass") or "")

    if not smtp_srv or not smtp_u or not smtp_pwd:
        msg = "Configurația SMTP din Setări / Secrets este incompletă."
        logger.warning(msg)
        return False, msg

    msg = EmailMessage()
    msg["Subject"] = subiect
    msg["From"] = smtp_u

    destinatari = []
    for camp_setari in ("email_tehnician", "email_1", "email_2"):
        val = str(setari.get(camp_setari) or "").strip()
        if val:
            destinatari.append(val)

    if destinatar_client and str(destinatar_client).strip():
        for e_cli in str(destinatar_client).replace(";", ",").split(","):
            if e_cli.strip():
                destinatari.append(e_cli.strip())

    destinatari_unice = list(dict.fromkeys([d for d in destinatari if d]))
    if not destinatari_unice:
        msg = "Nu există nicio adresă de email configurată (nici în Setări, nici la Client)."
        logger.warning(msg)
        return False, msg

    msg["To"] = ", ".join(destinatari_unice)
    msg.set_content(corp_mesaj)
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=nume_fisier,
        )

    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p), timeout=15) as server:
            server.starttls()
            server.login(smtp_u, smtp_pwd)
            server.send_message(msg)
        logger.info(f"E-mail trimis cu succes către: {msg['To']}")
        return True, f"Trimis către: {msg['To']}"
    except Exception as e:
        logger.error(f"Eroare trimitere email: {e}")
        return False, str(e)