#--------------------------------
#-----setari_repository.py-------
#--------------------------------

from config import db_cursor, logger

class SetariRepository:
    @staticmethod
    def get_setari():
        with db_cursor() as cur:
            cur.execute("SELECT * FROM setari LIMIT 1")
            res = cur.fetchone()
        if res:
            return res
        return {
            "nume_firma_mea": "Nexus Industrial SRL", "cui_mea": "", "reg_com_mea": "", 
            "adresa_mea": "", "banca_mea": "", "iban_mea": "", "swep_mea": "", 
            "smtp_server": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "", 
            "smtp_pass": "", "google_sheet_url": "", "email_tehnician": ""
        }

    @staticmethod
    def save_setari(data: dict):
        with db_cursor() as c:
            c.execute("DELETE FROM setari")
            c.execute("""
                INSERT INTO setari (nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url, email_tehnician) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get('nume_firma_mea'), data.get('cui_mea'), data.get('reg_com_mea'),
                data.get('adresa_mea'), data.get('banca_mea'), data.get('iban_mea'),
                data.get('swep_mea'), data.get('smtp_server'), data.get('smtp_port'),
                data.get('smtp_user'), data.get('smtp_pass'), data.get('google_sheet_url'),
                data.get('email_tehnician')
            ))
        logger.info("Setările au fost salvate în baza de date.")