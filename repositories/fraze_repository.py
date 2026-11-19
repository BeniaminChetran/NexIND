#------------------------------------------
#-------repositories/fraze_repository.py---
#------------------------------------------

import streamlit as st
from repositories.base_repository import BaseRepository

class FrazeRepository(BaseRepository):
    @staticmethod
    @st.cache_data(ttl=300)
    def get_all():
        query = "SELECT id, titlu, continut FROM fraze_predefinite ORDER BY id"
        return BaseRepository().fetch_all(query) or []

    @classmethod
    def insert(cls, titlu: str, continut: str):
        query = "INSERT INTO fraze_predefinite (titlu, continut) VALUES (%s, %s)"
        cls().execute(query, (titlu, continut))
        cls.get_all.clear()

    @classmethod
    def delete(cls, fraza_id: int):
        query = "DELETE FROM fraze_predefinite WHERE id = %s"
        cls().execute(query, (fraza_id,))
        cls.get_all.clear()