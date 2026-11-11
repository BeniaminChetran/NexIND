#----------------------------------
#----masuratori_repository.py------
#----------------------------------

from config import db_cursor

class MasuratoriRepository:
    @staticmethod
    def get_by_masina(masina_id):
        with db_cursor() as c:
            c.execute("""
                SELECT id, firma_id, masina_id, subansamblu, parametru, valoare, unitate_masura, data_masurare 
                FROM parametri_masurati 
                WHERE masina_id = %s 
                ORDER BY data_masurare ASC
            """, (masina_id,))
            return c.fetchall()

    @staticmethod
    def insert(data):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO parametri_masurati (firma_id, masina_id, subansamblu, parametru, valoare, unitate_masura, data_masurare)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get("firma_id"),
                data.get("masina_id"),
                data.get("subansamblu"),
                data.get("parametru"),
                data.get("valoare"),
                data.get("unitate_masura"),
                data.get("data_masurare")
            ))
            res = c.fetchone()
            return res['id'] if res else None