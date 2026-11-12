#------------------------------------------
#-------repositories/oferte_repository.py--
#------------------------------------------

import json
from config import db_cursor

class OferteRepository:
    @staticmethod
    def get_all():
        with db_cursor() as cur:
            cur.execute("""
                SELECT id, numar_oferta, data_emitere, firma, titlu, total_general, status, data_creare 
                FROM oferte 
                ORDER BY id DESC
            """)
            return cur.fetchall()

    @staticmethod
    def get_by_id(oferta_id):
        with db_cursor() as cur:
            cur.execute("SELECT * FROM oferte WHERE id = %s", (oferta_id,))
            return cur.fetchone()

    @staticmethod
    def insert(data):
        with db_cursor() as cur:
            cur.execute("""
                INSERT INTO oferte (
                    numar_oferta, data_emitere, firma, cui_client, adresa_client, 
                    titlu, valabilitate, termeni_plata, observatii, articole_json, 
                    subtotal, tva, total_general, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data["numar_oferta"],
                data["data"],
                data["client"],
                data["cui_client"],
                data["adresa_client"],
                data["titlu"],
                data["valabilitate"],
                data["termeni_plata"],
                data["observatii"],
                json.dumps(data["articole"], ensure_ascii=False),
                data["subtotal"],
                data["tva"],
                data["total_general"],
                data.get("status", "Emisă")
            ))
            res = cur.fetchone()
            return res["id"] if res else None

    @staticmethod
    def update_status(oferta_id, status_nou):
        with db_cursor() as cur:
            cur.execute("UPDATE oferte SET status = %s WHERE id = %s", (status_nou, oferta_id))

    @staticmethod
    def delete(oferta_id):
        with db_cursor() as cur:
            cur.execute("DELETE FROM oferte WHERE id = %s", (oferta_id,))