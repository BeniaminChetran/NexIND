import json
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository[cite: 6]


@st.cache_resource
def _asigura_indexuri_reparatii_once() -> bool:
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reparatii_firma ON reparatii (firma);
            CREATE INDEX IF NOT EXISTS idx_reparatii_data_creare ON reparatii (data_creare DESC, id DESC);
            """
        )
    return True


class ReparatiiRepository(BaseRepository):
    @classmethod
    @st.cache_data(ttl=300)
    def get_all(cls_or_self=None):
        _asigura_indexuri_reparatii_once()
        query = """
            SELECT id, firma, masina, subansamblu, defect, cod_eroare, piese_json,
                   titlu AS titlu_lucrare, simptom, solutie, stare_finala AS stare_fin,
                   durata AS durata_min, optimizari, tehnician AS tehnician_nume,
                   verificator AS verificator_nume, data_creare AS data, tip_interventie
            FROM reparatii
            ORDER BY id DESC
        """[cite: 6]
        return BaseRepository().fetch_all(query)[cite: 6]

    @classmethod
    @st.cache_data(ttl=180)
    def get_recente_pentru_piese(cls_or_self=None, limit: int = 500):
        _asigura_indexuri_reparatii_once()
        lim = max(1, int(limit))
        query = """
            SELECT id, firma, masina, piese_json
            FROM reparatii
            WHERE piese_json IS NOT NULL AND piese_json <> ''
            ORDER BY id DESC
            LIMIT %s
        """
        return BaseRepository().fetch_all(query, (lim,))

    @classmethod
    def insert(cls, data):
        _asigura_indexuri_reparatii_once()
        query = """
            INSERT INTO reparatii (
                firma, masina, subansamblu, defect, cod_eroare, piese_json,
                titlu, simptom, solutie, stare_finala, durata, optimizari,
                tehnician, verificator, tip_interventie
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """[cite: 6]
        params = (
            data.get("firma"),
            data.get("masina"),
            data.get("subansamblu"),
            data.get("defect"),
            data.get("cod_eroare"),
            json.dumps(data.get("piese_valide", []), ensure_ascii=False),
            data.get("titlu_lucrare"),
            data.get("simptom"),
            data.get("solutie"),
            data.get("stare_fin"),
            data.get("durata_min"),
            data.get("optimizari"),
            data.get("tehnician_nume"),
            data.get("verificator_nume"),
            data.get("tip_interventie"),
        )[cite: 6]
        res = cls().execute_returning(query, params)[cite: 6]
        cls.get_all.clear()[cite: 6]
        cls.get_recente_pentru_piese.clear()
        return res["id"] if res else None[cite: 6]