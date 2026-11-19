#------------------------------------------
#--repositories/mentenanta_repository.py---
#------------------------------------------

import json
import logging
import streamlit as st
from datetime import date, timedelta
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.MentenantaRepository")

INTERVALE_ZILE = {
    "Lunară": 30,
    "Trimestrială": 90,
    "La 6 luni": 180,
    "Anuală": 365,
}


class MentenantaRepository(BaseRepository):
    @staticmethod
    def ensure_schema():
        """Creează/actualizează automat tabela și coloanele necesare fără migrare manuală."""
        with db_cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS mentenanta_preventiva (
                    id SERIAL PRIMARY KEY,
                    firma_id INTEGER,
                    masina_id INTEGER,
                    firma_nume VARCHAR(255) NOT NULL,
                    masina_nume VARCHAR(255) NOT NULL,
                    punct_lucru VARCHAR(255) DEFAULT '',
                    producator_model VARCHAR(255) DEFAULT '',
                    serie_fabricatie VARCHAR(150) DEFAULT '',
                    nr_inventar VARCHAR(150) DEFAULT '',
                    ore_functionare VARCHAR(100) DEFAULT '',
                    ore_cumulate VARCHAR(100) DEFAULT '',
                    nivel_grila VARCHAR(150) DEFAULT '',
                    stare_initiala VARCHAR(150) DEFAULT '',
                    stare_finala VARCHAR(150) DEFAULT '',
                    checklist_json JSONB DEFAULT '{}'::jsonb,
                    recomandari_iiot TEXT DEFAULT '',
                    tehnician VARCHAR(255) DEFAULT '',
                    verificator VARCHAR(255) DEFAULT '',
                    functie_verificator VARCHAR(255) DEFAULT '',
                    data_interventie DATE DEFAULT CURRENT_DATE,
                    urmatoarea_revizie DATE
                )
            """)
            c.execute("""
                ALTER TABLE masini
                ADD COLUMN IF NOT EXISTS sisteme_active TEXT DEFAULT 'Electric,Mecanic,Hidraulic,Pneumatic,Vacuum,Auxiliare'
            """)

    @staticmethod
    @st.cache_data(ttl=120)
    def get_all():
        MentenantaRepository.ensure_schema()
        query = "SELECT * FROM mentenanta_preventiva ORDER BY id DESC"
        return BaseRepository().fetch_all(query)

    @classmethod
    def get_by_masina(cls, firma_nume: str, masina_nume: str):
        cls.ensure_schema()
        query = """
            SELECT * FROM mentenanta_preventiva
            WHERE firma_nume = %s AND masina_nume = %s
            ORDER BY id DESC
        """
        return cls().fetch_all(query, (firma_nume, masina_nume))

    @classmethod
    def insert(cls, data: dict) -> int:
        cls.ensure_schema()
        with db_cursor() as c:
            c.execute("""
                INSERT INTO mentenanta_preventiva (
                    firma_id, masina_id, firma_nume, masina_nume,
                    punct_lucru, producator_model, serie_fabricatie, nr_inventar,
                    ore_functionare, ore_cumulate, nivel_grila,
                    stare_initiala, stare_finala, checklist_json,
                    recomandari_iiot, tehnician, verificator, functie_verificator,
                    data_interventie, urmatoarea_revizie
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get("firma_id"),
                data.get("masina_id"),
                data.get("firma_nume", ""),
                data.get("masina_nume", ""),
                data.get("punct_lucru", ""),
                data.get("producator_model", ""),
                data.get("serie_fabricatie", ""),
                data.get("nr_inventar", ""),
                data.get("ore_functionare", ""),
                data.get("ore_cumulate", ""),
                data.get("nivel_grila", ""),
                data.get("stare_initiala", ""),
                data.get("stare_finala", ""),
                json.dumps(data.get("checklist_json", {}), ensure_ascii=False),
                data.get("recomandari_iiot", ""),
                data.get("tehnician", ""),
                data.get("verificator", ""),
                data.get("functie_verificator", ""),
                data.get("data_interventie") or date.today(),
                data.get("urmatoarea_revizie")
            ))
            row = c.fetchone()
            new_id = row["id"] if row else None

            # Actualizează automat data următoarei întrețineri pe mașină
            if data.get("masina_id") and data.get("urmatoarea_revizie"):
                urmat_str = (
                    data["urmatoarea_revizie"].strftime("%Y-%m-%d")
                    if hasattr(data["urmatoarea_revizie"], "strftime")
                    else str(data["urmatoarea_revizie"])[:10]
                )
                c.execute(
                    "UPDATE masini SET data_intretinere = %s WHERE id = %s",
                    (urmat_str, data["masina_id"])
                )

        cls.get_all.clear()
        logger.info(f"Fișă mentenanță preventivă #{new_id} salvată pentru {data.get('masina_nume')}")
        return new_id

    @classmethod
    def delete(cls, fisa_id: int):
        cls.ensure_schema()
        cls().execute("DELETE FROM mentenanta_preventiva WHERE id = %s", (fisa_id,))
        cls.get_all.clear()
