#------------------------------
#-------setari.py--------------
#------------------------------

#----------------------------------
#-------setari.py------------------
#----------------------------------

import streamlit as st
from config import db_cursor

def render_setari():
    st.subheader("⚙️ Setări Aplicație & Conectare")
    
    # Preluare setări existente din baza de date
    setari_actuale = {}
    try:
        with db_cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS setari (
                    cheie VARCHAR(100) PRIMARY KEY,
                    valoare TEXT
                )
            """)
            c.execute("SELECT cheie, valoare FROM setari")
            setari_actuale = {row['cheie']: row['valoare'] for row in c.fetchall()}
    except Exception:
        pass

    with st.form("form_setari"):
        nume_firma = st.text_input("Nume Firma Ta", value=setari_actuale.get("nume_firma", "Nexus Industrial SRL"))
        cui = st.text_input("CUI", value=setari_actuale.get("cui", ""))
        reg_com = st.text_input("Nr. Reg. Com.", value=setari_actuale.get("reg_com", ""))
        adresa = st.text_input("Adresă", value=setari_actuale.get("adresa", ""))
        banca = st.text_input("Bancă", value=setari_actuale.get("banca", ""))
        ibann = st.text_input("IBAN (Cont)", value=setari_actuale.get("ibann", ""))
        swift = st.text_input("SWEP (SWIFT)", value=setari_actuale.get("swift", ""))
        
        st.markdown("---")
        smtp_server = st.text_input("SMTP Server", value=setari_actuale.get("smtp_server", "smtp.gmail.com"))
        smtp_port = st.number_input("SMTP Port", value=int(setari_actuale.get("smtp_port", 587)), step=1)
        user_gmail = st.text_input("User Gmail", value=setari_actuale.get("user_gmail", ""))
        app_pass = st.text_input("App Password (sau folosiți st.secrets)", type="password", value=setari_actuale.get("app_pass", ""))
        google_sheet_url = st.text_input("Google Sheet URL", value=setari_actuale.get("google_sheet_url", ""))
        email_tehnician = st.text_input("E-mail Tehnician", value=setari_actuale.get("email_tehnician", ""))

        if st.form_submit_button("💾 Salvează Setările"):
            valori = {
                "nume_firma": nume_firma, "cui": cui, "reg_com": reg_com, "adresa": adresa,
                "banca": banca, "ibann": ibann, "swift": swift, "smtp_server": smtp_server,
                "smtp_port": str(smtp_port), "user_gmail": user_gmail, "app_pass": app_pass,
                "google_sheet_url": google_sheet_url, "email_tehnician": email_tehnician
            }
            try:
                with db_cursor() as c:
                    for k, v in valori.items():
                        c.execute("""
                            INSERT INTO setari (cheie, valoare) VALUES (%s, %s)
                            ON CONFLICT (cheie) DO UPDATE SET valoare = EXCLUDED.valoare
                        """, (k, v))
                st.success("Setările au fost salvate cu succes în baza de date!")
                st.rerun()
            except Exception as e:
                st.error(f"Eroare la salvarea setărilor: {e}")