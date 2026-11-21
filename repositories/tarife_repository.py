#------------------------------------------
#-------repositories/tarife_repository.py--
#------------------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.TarifeRepository")

NIVELE_TARIFE = ("Nivel A", "Nivel B", "Nivel C")


class TarifeRepository(BaseRepository):
    @classmethod
    def _ensure_nivel_col(cls):
        try:
            cls().execute("""
                ALTER TABLE tarife_implicite
                ADD COLUMN IF NOT EXISTS nivel_grila VARCHAR(30) DEFAULT 'Nivel A'
            """)
            cls().execute("""
                UPDATE tarife_implicite
                SET nivel_grila = 'Nivel A'
                WHERE nivel_grila IS NULL OR TRIM(nivel_grila) = ''
            """)
        except Exception:
            pass

    @staticmethod
    @st.cache_data(ttl=300)
    def get_all():
        TarifeRepository._ensure_nivel_col()
        query = """
            SELECT id, descriere, moneda_um, pret, COALESCE(NULLIF(TRIM(nivel_grila), ''), 'Nivel A') AS nivel_grila
            FROM tarife_implicite
            ORDER BY id
        """
        return BaseRepository().fetch_all(query)

    @classmethod
    def update_pret(cls, tarif_id: int, nou_pret: float):
        cls._ensure_nivel_col()
        query = "UPDATE tarife_implicite SET pret = %s WHERE id = %s"
        cls().execute(query, (float(nou_pret), tarif_id))
        cls.get_all.clear()
        logger.info(f"Tariful #{tarif_id} a fost actualizat la {nou_pret}")

    @classmethod
    def insert(cls, data: dict):
        cls._ensure_nivel_col()
        nivel = str(data.get("nivel_grila") or "Nivel A").strip()
        if nivel not in NIVELE_TARIFE:
            nivel = "Nivel A"
        query = """
            INSERT INTO tarife_implicite (descriere, moneda_um, pret, nivel_grila)
            VALUES (%s, %s, %s, %s)
        """
        cls().execute(query, (data['descriere'], data['moneda_um'], float(data['pret']), nivel))
        cls.get_all.clear()

    @classmethod
    def delete(cls, tarif_id: int):
        query = "DELETE FROM tarife_implicite WHERE id = %s"
        cls().execute(query, (tarif_id,))
        cls.get_all.clear()

    @classmethod
    def trece_la_nivel(cls, nivel_tinta: str, sursa_nivel: str | None = None) -> int:
        """
        Trece/copiază tarifele pe nivel_tinta ('Toate', 'Nivel A', 'Nivel B', 'Nivel C').
        Fiecare nivel își păstrează propriile rânduri, astfel încât prețurile se pot modifica separat pe fiecare nivel.
        Returnează numărul de înregistrări create.
        """
        cls._ensure_nivel_col()
        toate = cls.get_all() or []
        if not toate:
            return 0

        if sursa_nivel and sursa_nivel in NIVELE_TARIFE:
            sursa = [t for t in toate if str(t.get("nivel_grila") or "Nivel A").strip() == sursa_nivel]
            if not sursa:
                sursa = toate
        else:
            sursa = toate

        nivele_destinatie = list(NIVELE_TARIFE) if nivel_tinta == "Toate" else [nivel_tinta]
        existente_chei = {
            (
                str(t.get("nivel_grila") or "Nivel A").strip(),
                str(t.get("descriere") or "").strip().lower(),
                str(t.get("moneda_um") or "").strip().lower()
            )
            for t in toate
        }

        adaugate = 0
        for niv in nivele_destinatie:
            if niv not in NIVELE_TARIFE:
                continue
            for t in sursa:
                desc = str(t.get("descriere") or "").strip()
                mon_um = str(t.get("moneda_um") or "").strip()
                pret = float(t.get("pret") or 0.0)
                if not desc:
                    continue
                cheie = (niv, desc.lower(), mon_um.lower())
                if cheie not in existente_chei:
                    cls().execute(
                        "INSERT INTO tarife_implicite (descriere, moneda_um, pret, nivel_grila) VALUES (%s, %s, %s, %s)",
                        (desc, mon_um, pret, niv)
                    )
                    existente_chei.add(cheie)
                    adaugate += 1

        cls.get_all.clear()
        logger.info(f"Trecere tarife către '{nivel_tinta}' (sursă: {sursa_nivel or 'toate'}): {adaugate} tarife adăugate.")
        return adaugate