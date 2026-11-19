#--------------------------------
#-----piese_repository.py--------
#--------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.PieseRepository")

class PieseRepository(BaseRepository):
    @staticmethod
    def _asigura_coloana_termen_livrare():
        try:
            BaseRepository().execute(
                "ALTER TABLE piese ADD COLUMN IF NOT EXISTS termen_livrare VARCHAR(100) DEFAULT '1'"
            )
        except Exception as e:
            logger.debug(f"Verificare coloană termen_livrare: {e}")

    @staticmethod
    @st.cache_data(ttl=300)
    def get_all(cls_or_self=None):
        PieseRepository._asigura_coloana_termen_livrare()
        query = """
            SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, 
                   subansamblu, parametri, pret_achizitie, 
                   COALESCE(NULLIF(TRIM(valuta_achizitie), ''), 'RON') AS valuta_achizitie, 
                   link_furnizor, COALESCE(termen_livrare, '1') AS termen_livrare
            FROM piese 
            ORDER BY denumire
        """
        return BaseRepository().fetch_all(query)

    @classmethod
    def get_filtrate(cls, select_masina_unica: str):
        cls._asigura_coloana_termen_livrare()
        if select_masina_unica != "Toate mașinile / General":
            query = """
                SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, 
                       subansamblu, parametri, pret_achizitie, 
                       COALESCE(NULLIF(TRIM(valuta_achizitie), ''), 'RON') AS valuta_achizitie, 
                       link_furnizor, COALESCE(termen_livrare, '1') AS termen_livrare
                FROM piese 
                WHERE LOWER(TRIM(masina_montaj)) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(TRIM(masina_montaj)) = 'general'
                   OR masina_montaj = ''
                   OR masina_montaj IS NULL
                ORDER BY denumire
            """
            params = (
                f"%{select_masina_unica.strip()}%", 
                f"{select_masina_unica.strip()},%", 
                f"%, {select_masina_unica.strip()}%"
            )
            return cls().fetch_all(query, params)
        else:
            return cls().get_all()

    @classmethod
    def insert(cls, data: dict):
        cls._asigura_coloana_termen_livrare()
        valuta = str(data.get('valuta_achizitie') or 'RON').strip().upper()
        if valuta not in ("RON", "EUR"):
            valuta = "RON"
        query = """
            INSERT INTO piese (
                denumire, cod_producator, cod_comercial, masina_montaj, 
                subansamblu, parametri, pret_achizitie, valuta_achizitie, 
                link_furnizor, termen_livrare
            ) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data['denumire'], 
            data.get('cod_producator'), 
            data.get('cod_comercial'), 
            data.get('masina_montaj'), 
            data.get('subansamblu'),
            data.get('parametri', ''),
            data.get('pret_achizitie', 0.00),
            valuta,
            data.get('link_furnizor', ''),
            str(data.get('termen_livrare') or '1').strip()
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Piesă adăugată: {data['denumire']} ({valuta})")

    @classmethod
    def update(cls, piesa_id: int, data: dict):
        cls._asigura_coloana_termen_livrare()
        valuta = str(data.get('valuta_achizitie') or 'RON').strip().upper()
        if valuta not in ("RON", "EUR"):
            valuta = "RON"
        query = """
            UPDATE piese 
            SET denumire=%s, cod_producator=%s, cod_comercial=%s, subansamblu=%s, 
                parametri=%s, pret_achizitie=%s, valuta_achizitie=%s, 
                link_furnizor=%s, termen_livrare=%s
            WHERE id=%s
        """
        params = (
            data['denumire'],
            data.get('cod_producator'),
            data.get('cod_comercial'),
            data.get('subansamblu'),
            data.get('parametri', ''),
            data.get('pret_achizitie', 0.00),
            valuta,
            data.get('link_furnizor', ''),
            str(data.get('termen_livrare') or '1').strip(),
            piesa_id
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Piesa #{piesa_id} a fost actualizată ({valuta}).")

    @classmethod
    def delete(cls, piesa_id: int):
        query = "DELETE FROM piese WHERE id=%s"
        cls().execute(query, (piesa_id,))
        cls.get_all.clear()
        logger.info(f"Piesa #{piesa_id} ștearsă.")