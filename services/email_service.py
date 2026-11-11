#-----------------------
#------email_service.py-
#-----------------------

import smtplib
from email.message import EmailMessage
import streamlit as st
from repositories.setari_repository import SetariRepository
from config import logger

def trimite_email_raport(destinatar_client: str, subiect: str, corp_mesaj: str, pdf_bytes: bytes, nume_fisier: str):
    setari = SetariRepository.get_setari()
    smtp_srv = setari["smtp_server"]
    smtp_p = setari["smtp_port"]
    smtp_u = setari["smtp_user"]
    smtp_pwd = st.secrets.get("SMTP_PASSWORD", setari["smtp_pass"])
    email_tehnician = setari["email_tehnician"]
    
    msg = EmailMessage()
    msg['Subject'] = subiect
    msg['From'] = smtp_u if smtp_u else "contact@nexusindustrial.ro"
    
    destinatari = []
    if destinatar_client and destinatar_client.strip():
        destinatari.append(destinatar_client.strip())
    if email_tehnician and email_tehnician.strip():
        destinatari.append(email_tehnician.strip())
    destinatari.append("beniamin.chetran@nexusindustrial.ro")
    destinatari.append("contact@nexusindustrial.ro")
    
    destinatari_unice = list(set([d for d in destinatari if d and d.strip()]))
    msg['To'] = ", ".join(destinatari_unice)
    msg.set_content(corp_mesaj)
    if pdf_bytes:
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=nume_fisier)
    
    try:
        with smtplib.SMTP(smtp_srv, int(smtp_p), timeout=10) as server:
            server.starttls()
            if smtp_pwd and smtp_u:
                server.login(smtp_u, smtp_pwd)
                server.send_message(msg)
        logger.info(f"E-mail trimis cu succes către: {msg['To']}")
    except Exception as e:
        logger.error(f"Eroare trimitere email: {e}")