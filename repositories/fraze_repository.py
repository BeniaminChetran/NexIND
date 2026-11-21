#------------------------------------------
#-------repositories/fraze_repository.py---
#------------------------------------------

import streamlit as st
from repositories.base_repository import BaseRepository


class FrazeRepository(BaseRepository):
    @classmethod
    @st.cache_data(ttl=300)
    def get_all(cls) -> list[dict]:
        query = "SELECT id, titlu, continut FROM fraze_predefinite ORDER BY id"
        rezultat = cls().fetch_all(query)
        return rezultat if isinstance(rezultat, list) else []

    @classmethod
    def insert(cls, titlu: str, continut: str) -> None:
        query = "INSERT INTO fraze_predefinite (titlu, continut) VALUES (%s, %s)"
        cls().execute(query, (titlu.strip(), continut.strip()))
        cls.get_all.clear()

    @classmethod
    def delete(cls, fraza_id: int) -> None:
        fid = int(fraza_id)
        query = "DELETE FROM fraze_predefinite WHERE id = %s"
        cls().execute(query, (fid,))
        cls.get_all.clear()
