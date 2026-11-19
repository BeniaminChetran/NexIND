#------------------------------------------
#-------repositories/tarife_repository.py--
#------------------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.TarifeRepository")

class TarifeRepository(BaseRepository):
    @staticmethod
    @st.cache_data(ttl=300)
    def get_all():
        query = "SELECT id, descriere, moneda_um, pret FROM tarife_implicite ORDER BY id"
        return BaseRepository().fetch_all(query)

    @classmethod
    def update_pret(cls, tarif_id: int, nou_pret: float):
        query = "UPDATE tarife_implicite SET pret = %s WHERE id = %s"
        cls().execute(query, (nou_pret, tarif_id))
        cls.get_all.clear()
        logger.info(f"Tariful #{tarif_id} a fost actualizat la {nou_pret}")

    @classmethod
    def insert(cls, data: dict):
        query = "INSERT INTO tarife_implicite (descriere, moneda_um, pret) VALUES (%s, %s, %s)"
        cls().execute(query, (data['descriere'], data['moneda_um'], data['pret']))
        cls.get_all.clear()

    @classmethod
    def delete(cls, tarif_id: int):
        query = "DELETE FROM tarife_implicite WHERE id = %s"
        cls().execute(query, (tarif_id,))
        cls.get_all.clear()