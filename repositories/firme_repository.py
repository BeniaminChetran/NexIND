#--------------------------------
#-----firme_repository.py--------
#--------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.FirmeRepository")

class FirmeRepository(BaseRepository):
    @staticmethod
    @st.cache_data(ttl=300)
    def get_all():
        query = """
            SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon, adaos_comercial 
            FROM firme 
            ORDER BY nume_firma
        """
        return BaseRepository().fetch_all(query)

    @classmethod
    def insert(cls, data: dict):
        nume = data.get('nume_firma')
        if not nume or not str(nume).strip():
            logger.error("Tentativă de inserare firmă fără nume.")
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")

        query = """
            INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon, adaos_comercial) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            nume.strip(), 
            data.get('cui'), 
            data.get('reg_com'),
            data.get('adresa'), 
            data.get('banca'), 
            data.get('cont'),
            data.get('nume_persoana'), 
            data.get('email'), 
            data.get('telefon'),
            data.get('adaos_comercial', 20.00)
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Firma nouă adăugată cu succes: {nume}")

    @classmethod
    def update(cls, firma_id: int, data: dict):
        if not firma_id:
            raise ValueError("ID-ul firmei este obligatoriu pentru actualizare.")

        nume = data.get('nume_firma')
        if not nume or not str(nume).strip():
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")

        query = """
            UPDATE firme 
            SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s, adaos_comercial=%s 
            WHERE id=%s
        """
        params = (
            nume.strip(), data.get('cui'), data.get('reg_com'),
            data.get('adresa'), data.get('banca'), data.get('cont'),
            data.get('nume_persoana'), data.get('email'), data.get('telefon'),
            data.get('adaos_comercial', 20.00),
            firma_id
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Firma #{firma_id} a fost actualizată.")

    @classmethod
    def delete(cls, firma_id: int):
        if not firma_id:
            raise ValueError("ID-ul firmei este invalid pentru ștergere.")
        query = "DELETE FROM firme WHERE id=%s"
        cls().execute(query, (firma_id,))
        cls.get_all.clear()
        logger.warning(f"Firma #{firma_id} a fost ștearsă din baza de date.")