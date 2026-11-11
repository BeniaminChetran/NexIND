#------------------------------------------
#--reparatii_electronice_repository.py-----
#------------------------------------------

import json
from config import db_cursor

class ReparatiiElectroniceRepository:
    @staticmethod
    def get_all():
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii_electronice ORDER BY id DESC")
            return c.fetchall()

    @staticmethod
    def insert(data):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO reparatii_electronice (firma_id, masina_id, firma_nume, masina_nume, piesa_subansamblu, defect_reclamat, componente_json, stare_finala, tehnician, verificator, data_creare)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                data.get("firma_id"),
                data.get("masina_id"),
                data.get("firma_nume"),
                data.get("masina_nume"),
                data.get("piesa_subansamblu"),
                data.get("defect_reclamat"),
                json.dumps(data.get("componente_json"), ensure_ascii=False),
                data.get("stare_finala"),
                data.get("tehnician"),
                data.get("verificator")
            ))
            res = c.fetchone()
            return res['id'] if res else None