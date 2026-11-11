#--------------------------------
#-----reparatii_repository.py----
#--------------------------------

import json
from config import db_cursor, logger

class ReparatiiRepository:
    @staticmethod
    def insert(data: dict):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO reparatii (firma, masina, subansamblu, defect, cod_eroare, piese_json, titlu, simptom, solutie, stare_finala, durata, optimizari, tehnician, verificator, tip_interventie) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['firma'], data['masina'], data['subansamblu'], data['defect'],
                data['cod_eroare'], json.dumps(data['piese_valide'], ensure_ascii=False),
                data['titlu_lucrare'], data['simptom'], data['solutie'], data['stare_fin'],
                data['durata_min'], data['optimizari'], data['tehnician_nume'],
                data['verificator_nume'], data['tip_interventie']
            ))
            res = c.fetchone()
            logger.info(f"Reparație nouă înregistrată cu ID #{res['id']}")
            return res['id'] if res else None

    @staticmethod
    def get_by_id(rid: int):
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii WHERE id = %s", (rid,))
            return c.fetchone()

    @staticmethod
    def delete(rid: int):
        with db_cursor() as c:
            c.execute("DELETE FROM reparatii WHERE id = %s", (rid,))
        logger.info(f"Raportul #{rid} a fost șters.")