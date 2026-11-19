#--------------------------------
#-----setari_repository.py-------
#--------------------------------

import logging
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.SetariRepository")

class SetariRepository(BaseRepository):
    @classmethod
    def get_setari(cls):
        query = "SELECT * FROM setari LIMIT 1"
        res = cls().fetch_one(query)
        defaults = {
            "nume_firma_mea": "SC Nexus Industrial SRL",
            "cui_mea": "",
            "reg_com_mea": "",
            "adresa_mea": "",
            "banca_mea": "",
            "iban_mea": "",
            "swep_mea": "",
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "google_sheet_url": "",
            "email_tehnician": "",
            "cota_tva": 21.0,
            "pass": "",
            "valabilitate_implicita": "15 zile",
            "termeni_plata_impliciti": "5 zile de la emiterea facturii",
            "intocmit_de_implicit": "Echipa Nexus Industrial",
            "tehnician_implicit": "Tehnician Nexus"
        }
        if res:
            for k, v in defaults.items():
                if res.get(k) is None or str(res.get(k)).strip() == "":
                    if k in (
                        "cota_tva",
                        "valabilitate_implicita",
                        "termeni_plata_impliciti",
                        "intocmit_de_implicit",
                        "tehnician_implicit"
                    ):
                        res[k] = v
            return res
        return defaults

    @classmethod
    def save_setari(cls, data: dict):
        from config import db_cursor
        existing = cls.get_setari()
        parola_curenta = data.get("pass") if data.get("pass") is not None else existing.get("pass", "")
        with db_cursor() as c:
            c.execute("DELETE FROM setari")
            c.execute("""
                INSERT INTO setari (
                    nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea, 
                    iban_mea, swep_mea, smtp_server, smtp_port, smtp_user, 
                    smtp_pass, google_sheet_url, email_tehnician, cota_tva, pass,
                    valabilitate_implicita, termeni_plata_impliciti,
                    intocmit_de_implicit, tehnician_implicit
                ) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get('nume_firma_mea'), data.get('cui_mea'), data.get('reg_com_mea'),
                data.get('adresa_mea'), data.get('banca_mea'), data.get('iban_mea'),
                data.get('swep_mea'), data.get('smtp_server'), data.get('smtp_port'),
                data.get('smtp_user'), data.get('smtp_pass'), data.get('google_sheet_url'),
                data.get('email_tehnician'), float(data.get('cota_tva', 21.0)),
                parola_curenta,
                data.get('valabilitate_implicita', '15 zile'),
                data.get('termeni_plata_impliciti', '5 zile de la emiterea facturii'),
                data.get('intocmit_de_implicit', 'Echipa Nexus Industrial'),
                data.get('tehnician_implicit', 'Tehnician Nexus')
            ))
        logger.info("Setările au fost salvate în baza de date.")

    @classmethod
    def update_pass(cls, noua_parola: str):
        from config import db_cursor
        with db_cursor() as c:
            c.execute("SELECT COUNT(*) AS cnt FROM setari")
            row = c.fetchone()
            if row and row.get("cnt", 0) == 0:
                c.execute("INSERT INTO setari (pass) VALUES (%s)", (noua_parola,))
            else:
                c.execute("UPDATE setari SET pass = %s", (noua_parola,))
        logger.info("Parola a fost actualizată în setări.")