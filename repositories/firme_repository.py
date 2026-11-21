#--------------------------------
#-----firme_repository.py--------
#--------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository
from repositories.setari_repository import SetariRepository

logger = logging.getLogger("NexIndCMMS.FirmeRepository")


def _rezolva_adaos(data: dict) -> float:
    val = data.get("adaos_comercial")
    if val is not None and str(val).strip() != "":
        return float(val)
    setari = SetariRepository.get_setari() or {}
    imp = setari.get("adaos_comercial_implicit")
    try:
        return float(imp) if imp is not None and str(imp).strip() != "" else 35.0
    except (TypeError, ValueError):
        return 35.0


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

        adaos_val = _rezolva_adaos(data)

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
            adaos_val
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

        adaos_val = _rezolva_adaos(data)

        query = """
            UPDATE firme 
            SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s, adaos_comercial=%s 
            WHERE id=%s
        """
        params = (
            nume.strip(), data.get('cui'), data.get('reg_com'),
            data.get('adresa'), data.get('banca'), data.get('cont'),
            data.get('nume_persoana'), data.get('email'), data.get('telefon'),
            adaos_val,
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