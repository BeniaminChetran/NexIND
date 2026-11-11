#--------------------------------
#-----piese_repository.py----
#--------------------------------

from config import db_cursor, logger

class PieseRepository:
    @staticmethod
    def get_all():
        with db_cursor() as cur:
            cur.execute("SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese ORDER BY denumire")
            return cur.fetchall()

    @staticmethod
    def get_filtrate(select_masina_unica: str):
        with db_cursor() as cur:
            if select_masina_unica != "Toate mașinile / General":
                cur.execute("""
                    SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese 
                    WHERE LOWER(TRIM(masina_montaj)) LIKE LOWER(%s)
                       OR LOWER(masina_montaj) LIKE LOWER(%s)
                       OR LOWER(masina_montaj) LIKE LOWER(%s)
                       OR LOWER(TRIM(masina_montaj)) = 'general'
                       OR masina_montaj = ''
                       OR masina_montaj IS NULL
                    ORDER BY denumire
                """, (
                    f"%{select_masina_unica.strip()}%", 
                    f"{select_masina_unica.strip()},%", 
                    f"%, {select_masina_unica.strip()}%"
                ))
            else:
                cur.execute("SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, subansamblu FROM piese ORDER BY denumire")
            return cur.fetchall()

    @staticmethod
    def insert(data: dict):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO piese (denumire, cod_producator, cod_comercial, masina_montaj, subansamblu) 
                VALUES (%s, %s, %s, %s, %s)
            """, (data['denumire'], data.get('cod_producator'), data.get('cod_comercial'), data.get('masina_montaj'), data.get('subansamblu')))
        logger.info(f"Piesă adăugată: {data['denumire']}")

    @staticmethod
    def delete(piesa_id: int):
        with db_cursor() as c:
            c.execute("DELETE FROM piese WHERE id=%s", (piesa_id,))
        logger.info(f"Piesa #{piesa_id} a fost ștearsă.")