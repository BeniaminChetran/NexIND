#----------------------------------
#-------setari.py------------------
#----------------------------------

import streamlit as st
from config import db_cursor

def render_setari():
    st.subheader("⚙️ Setări Aplicație & Conectare")
    
    @st.fragment
    def render_setari_fragment():
        setari_actuale = {
            "nume_firma_mea": "Nexus Industrial SRL", "cui_mea": "", "reg_com_mea": "", 
            "adresa_mea": "", "banca_mea": "", "iban_mea": "", "swep_mea": "", 
            "smtp_server": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "", 
            "smtp_pass": "", "google_sheet_url": "", "email_tehnician": ""
        }
        try:
            with db_cursor() as cur:
                cur.execute("SELECT * FROM setari LIMIT 1")
                res = cur.fetchone()
                if res:
                    setari_actuale.update(res)
        except Exception as e:
            st.warning(f"Nu s-au putut citi setările: {e}")

        with st.form("form_setari"):
            s_nume = st.text_input("Nume Firma Ta", value=setari_actuale.get('nume_firma_mea', ''))
            s_cui = st.text_input("CUI", value=setari_actuale.get('cui_mea', ''))
            s_reg = st.text_input("Nr. Reg. Com.", value=setari_actuale.get('reg_com_mea', ''))
            s_adresa = st.text_input("Adresă", value=setari_actuale.get('adresa_mea', ''))
            s_banca = st.text_input("Bancă", value=setari_actuale.get('banca_mea', ''))
            s_iban = st.text_input("IBAN (Cont)", value=setari_actuale.get('iban_mea', ''))
            s_swep = st.text_input("SWEP (SWIFT)", value=setari_actuale.get('swep_mea', ''))
            
            st.markdown("---")
            s_srv = st.text_input("SMTP Server", value=setari_actuale.get('smtp_server', 'smtp.gmail.com'))
            s_prt = st.number_input("SMTP Port", value=int(setari_actuale.get('smtp_port') or 587), step=1)
            s_usr = st.text_input("User Gmail", value=setari_actuale.get('smtp_user', ''))
            s_pwd = st.text_input("App Password (sau folosiți st.secrets)", type="password", value=setari_actuale.get('smtp_pass', ''))
            s_sheet = st.text_input("Google Sheet URL", value=setari_actuale.get('google_sheet_url', ''))
            s_email_teh = st.text_input("E-mail Tehnician", value=setari_actuale.get('email_tehnician', ''))

            if st.form_submit_button("💾 Salvează Setările"):
                try:
                    with db_cursor() as c:
                        c.execute("DELETE FROM setari")
                        c.execute("""
                            INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (s_nume, s_cui, s_reg, s_adresa, s_banca, s_iban, s_swep, s_srv, s_prt, s_usr, s_pwd, s_sheet, s_email_teh))
                    st.success("Setările au fost salvate cu succes în baza de date!")
                except Exception as e:
                    st.error(f"Eroare la salvarea setărilor: {e}")

    render_setari_fragment()