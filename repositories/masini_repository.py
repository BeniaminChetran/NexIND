#--------------------------------
#-----masini_repository.py-------
#--------------------------------

from config import db_cursor, logger

class MasiniRepository:
    @staticmethod
    def get_all():
        with db_cursor() as cur:
            cur.execute("SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere FROM masini ORDER BY denumire")
            return cur.fetchall()

    @staticmethod
    def get_by_firma(firma_id: int):
        with db_cursor() as c:
            c.execute("""
                SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina 
                FROM masini m
                JOIN firme f ON m.firma_id = f.id
                WHERE f.id = %s 
                ORDER BY m.denumire
            """, (firma_id,))
            return c.fetchall()

    @staticmethod
    def insert(data: dict):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['firma_id'], data['denumire'], data.get('tip_masina'), data.get('serie'),
                data.get('an_fabricatie'), data.get('subansambluri'), data.get('erori'),
                data.get('defecte'), data.get('remediu'), data.get('piese_necesare'),
                data.get('piese_inlocuite'), data.get('tipuri_fluide'), data.get('data_intretinere'),
                data.get('tip_intretinere')
            ))
        logger.info(f"Mașină adăugată: {data['denumire']}")

    @staticmethod
    def delete(masina_id: int):
        with db_cursor() as c:
            c.execute("DELETE FROM masini WHERE id=%s", (masina_id,))
        logger.info(f"Mașina #{masina_id} a fost ștearsă.")