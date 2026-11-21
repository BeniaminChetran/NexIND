#----------------------------------------------
#---repositories/documentatie_repository.py----
#----------------------------------------------

import json
import logging
import streamlit as st
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.DocumentatieRepository")

TAGURI_DOCUMENTATIE = ("[ERR]", "[SCH]", "[PRM]", "[TST]", "[MEC]", "[SOL]")
CATEGORII_DOCUMENTATIE = ("CNC", "VFD", "PLC", "HMI", "Sursa_Driver", "Masina", "Altele")


class DocumentatieRepository(BaseRepository):
    @classmethod
    def ensure_schema(cls):
        try:
            with db_cursor() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS documentatie_tehnica (
                        id SERIAL PRIMARY KEY,
                        masina_id INTEGER NULL,
                        categorie VARCHAR(50) NOT NULL DEFAULT 'CNC',
                        tip_sistem VARCHAR(120) NOT NULL DEFAULT '',
                        titlu VARCHAR(255) NOT NULL,
                        gdrive_file_id VARCHAR(255) DEFAULT '',
                        gdrive_url TEXT DEFAULT '',
                        tip_fisier VARCHAR(30) DEFAULT 'pdf',
                        tag_sectiune VARCHAR(20) DEFAULT '[ERR]',
                        interval_pagini VARCHAR(80) DEFAULT '',
                        coduri_eroare_hmi TEXT DEFAULT '',
                        coduri_eroare_driver TEXT DEFAULT '',
                        text_indexat TEXT DEFAULT '',
                        creat_la TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        actualizat_la TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS idx_doc_masina_id ON documentatie_tehnica (masina_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_doc_tip_sistem ON documentatie_tehnica (LOWER(tip_sistem))")
                c.execute("CREATE INDEX IF NOT EXISTS idx_doc_tag_sectiune ON documentatie_tehnica (tag_sectiune)")
        except Exception as e:
            logger.error(f"Eroare la verificarea schemei documentatie_tehnica: {e}")

    @staticmethod
    @st.cache_data(ttl=120)
    def get_all():
        DocumentatieRepository.ensure_schema()
        query = """
            SELECT id, masina_id, categorie, tip_sistem, titlu,
                   gdrive_file_id, gdrive_url, tip_fisier, tag_sectiune,
                   interval_pagini, coduri_eroare_hmi, coduri_eroare_driver,
                   text_indexat, creat_la, actualizat_la
            FROM documentatie_tehnica
            ORDER BY id DESC
        """
        return BaseRepository().fetch_all(query)

    @classmethod
    def insert(cls, data: dict):
        cls.ensure_schema()
        titlu = str(data.get("titlu") or "").strip()
        if not titlu:
            raise ValueError("Titlul documentației este obligatoriu.")

        tag = str(data.get("tag_sectiune") or "[ERR]").strip().upper()
        if tag not in TAGURI_DOCUMENTATIE:
            tag = "[ERR]"

        query = """
            INSERT INTO documentatie_tehnica (
                masina_id, categorie, tip_sistem, titlu,
                gdrive_file_id, gdrive_url, tip_fisier, tag_sectiune,
                interval_pagini, coduri_eroare_hmi, coduri_eroare_driver, text_indexat
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("masina_id"),
            str(data.get("categorie") or "CNC").strip(),
            str(data.get("tip_sistem") or "").strip(),
            titlu,
            str(data.get("gdrive_file_id") or "").strip(),
            str(data.get("gdrive_url") or "").strip(),
            str(data.get("tip_fisier") or "pdf").strip(),
            tag,
            str(data.get("interval_pagini") or "").strip(),
            str(data.get("coduri_eroare_hmi") or "").strip(),
            str(data.get("coduri_eroare_driver") or "").strip(),
            str(data.get("text_indexat") or "").strip(),
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Documentație adăugată: {titlu} ({tag})")

@classmethod
    def update(cls, doc_id: int, data: dict):
        if not doc_id:
            return
        cls.ensure_schema()
        titlu = str(data.get("titlu") or "").strip()
        if not titlu:
            raise ValueError("Titlul documentației este obligatoriu.")

        tag = str(data.get("tag_sectiune") or "[ERR]").strip().upper()
        if tag not in TAGURI_DOCUMENTATIE:
            tag = "[ERR]"

        query = """
            UPDATE documentatie_tehnica
            SET categorie = %s,
                tip_sistem = %s,
                titlu = %s,
                gdrive_url = %s,
                tag_sectiune = %s,
                interval_pagini = %s,
                coduri_eroare_hmi = %s,
                coduri_eroare_driver = %s,
                text_indexat = %s,
                actualizat_la = NOW()
            WHERE id = %s
        """
        params = (
            str(data.get("categorie") or "CNC").strip(),
            str(data.get("tip_sistem") or "").strip(),
            titlu,
            str(data.get("gdrive_url") or "").strip(),
            tag,
            str(data.get("interval_pagini") or "").strip(),
            str(data.get("coduri_eroare_hmi") or "").strip(),
            str(data.get("coduri_eroare_driver") or "").strip(),
            str(data.get("text_indexat") or "").strip(),
            int(doc_id),
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Documentația #{doc_id} a fost actualizată.")

    @classmethod
    def delete(cls, doc_id: int):
        if not doc_id:
            return
        cls().execute("DELETE FROM documentatie_tehnica WHERE id = %s", (int(doc_id),))
        cls.get_all.clear()
        logger.warning(f"Documentația #{doc_id} a fost ștearsă.")