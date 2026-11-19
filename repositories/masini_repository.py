#--------------------------------
#-----masini_repository.py-------
#--------------------------------

import logging
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.MasiniRepository")

ALL_SISTEME_DEFAULT = "Electric,Mecanic,Hidraulic,Pneumatic,Vacuum,Auxiliare"

class MasiniRepository(BaseRepository):
    @staticmethod
    def _ensure_sisteme_col():
        try:
            with db_cursor() as c:
                c.execute(f"""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS sisteme_active TEXT DEFAULT '{ALL_SISTEME_DEFAULT}'
                """)
        except Exception as e:
            logger.debug(f"Verificare coloană sisteme_active: {e}")

    @classmethod
    def get_all(cls):
        cls._ensure_sisteme_col()
        query = """
            SELECT id, firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere,
                   COALESCE(NULLIF(TRIM(sisteme_active), ''), %s) AS sisteme_active
            FROM masini 
            ORDER BY denumire
        """
        return cls().fetch_all(query, (ALL_SISTEME_DEFAULT,))

    @classmethod
    def get_by_firma(cls, firma_id: int):
        cls._ensure_sisteme_col()
        query = """
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina, m.serie, m.an_fabricatie,
                   m.data_intretinere, m.tip_intretinere, m.tipuri_fluide,
                   COALESCE(NULLIF(TRIM(m.sisteme_active), ''), %s) AS sisteme_active
            FROM masini m
            JOIN firme f ON m.firma_id = f.id
            WHERE f.id = %s 
            ORDER BY m.denumire
        """
        return cls().fetch_all(query, (ALL_SISTEME_DEFAULT, firma_id))

    @classmethod
    def insert(cls, data: dict):
        cls._ensure_sisteme_col()
        query = """
            INSERT INTO masini (firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori, defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide, data_intretinere, tip_intretinere, sisteme_active) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data['firma_id'], data['denumire'], data.get('tip_masina'),
            data.get('serie') or data.get('nr_serie'),
            data.get('an_fabricatie'), data.get('subansambluri'), data.get('erori'),
            data.get('defecte'), data.get('remediu') or data.get('reparatii'),
            data.get('piese_necesare'),
            data.get('piese_inlocuite'), data.get('tipuri_fluide'), data.get('data_intretinere'),
            data.get('tip_intretinere'),
            data.get('sisteme_active') or ALL_SISTEME_DEFAULT
        )
        cls().execute(query, params)
        logger.info(f"Mașină adăugată: {data['denumire']}")

    @classmethod
    def delete(cls, masina_id: int):
        query = "DELETE FROM masini WHERE id=%s"
        cls().execute(query, (masina_id,))
        logger.info(f"Mașina #{masina_id} a fost ștearsă.")
