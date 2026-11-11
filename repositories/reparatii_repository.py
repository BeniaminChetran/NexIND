#----------------------------------
#----reparatii_repository.py-------
#----------------------------------

from config import db_cursor
import json

class ReparatiiRepository:
    @staticmethod
    def get_all():
        with db_cursor() as c:
            c.execute("""
                SELECT id, firma, masina, subansamblu, defect, cod_eroare, piese_json, 
                       titlu AS titlu_lucrare, simptom, solutie, stare_finala AS stare_fin, 
                       durata AS durata_min, optimizari, tehnician AS tehnician_nume, 
                       verificator AS verificator_nume, data_creare AS data, tip_interventie 
                FROM reparatii 
                ORDER BY id DESC
            """)
            return c.fetchall()

    @staticmethod
    def insert(data):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO reparatii (
                    firma, masina, subansamblu, defect, cod_eroare, piese_json, 
                    titlu, simptom, solutie, stare_finala, durata, optimizari, 
                    tehnician, verificator, tip_interventie
                ) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get("firma"), data.get("masina"), data.get("subansamblu"), 
                data.get("defect"), data.get("cod_eroare"), json.dumps(data.get("piese_valide", []), ensure_ascii=False), 
                data.get("titlu_lucrare"), data.get("simptom"), data.get("solutie"), 
                data.get("stare_fin"), data.get("durata_min"), data.get("optimizari"), 
                data.get("tehnician_nume"), data.get("verificator_nume"), data.get("tip_interventie")
            ))
            res = c.fetchone()
            return res['id'] if res else None