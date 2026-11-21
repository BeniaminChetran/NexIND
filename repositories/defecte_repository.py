#------------------------------------------
#---repositories/defecte_repository.py-----
#------------------------------------------

import json
import logging
import streamlit as st
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.DefecteRepository")


def _normalizeaza_coduri_driver(coduri_input) -> tuple[list[dict], str]:
    """
    Acceptă o listă de dicționare/string-uri sau text separat prin virgulă/linie nouă.
    Returnează (lista_normalizata_json, text_concatenat_pentru_cautare).
    """
    items: list[dict] = []
    if isinstance(coduri_input, list):
        for el in coduri_input:
            if isinstance(el, dict):
                cod = str(el.get("cod") or "").strip()
                comp = str(el.get("componenta") or "").strip()
                if cod:
                    items.append({"cod": cod, "componenta": comp})
            else:
                cod = str(el or "").strip()
                if cod:
                    items.append({"cod": cod, "componenta": ""})
    elif isinstance(coduri_input, str):
        for parte in coduri_input.replace("\n", ",").split(","):
            cod = parte.strip()
            if cod:
                items.append({"cod": cod, "componenta": ""})

    text_join = ", ".join(
        f"{x['cod']} ({x['componenta']})" if x.get("componenta") else x["cod"]
        for x in items
    )
    return items, text_join


class DefecteRepository(BaseRepository):
    @classmethod
    def ensure_schema(cls):
        try:
            with db_cursor() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS defecte_interventii (
                        id SERIAL PRIMARY KEY,
                        masina_id INTEGER NULL,
                        tip_control_cnc VARCHAR(120) DEFAULT '',
                        tip_vfd_sau_driver VARCHAR(120) DEFAULT '',
                        cod_eroare_hmi VARCHAR(100) DEFAULT '',
                        mesaj_hmi TEXT DEFAULT '',
                        coduri_eroare_driver_json JSONB DEFAULT '[]'::jsonb,
                        coduri_driver_text TEXT DEFAULT '',
                        simptom TEXT DEFAULT '',
                        verificari_efectuate TEXT DEFAULT '',
                        solutie_aplicata TEXT DEFAULT '',
                        rezolvat BOOLEAN DEFAULT FALSE,
                        creat_la TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        actualizat_la TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS idx_def_masina_id ON defecte_interventii (masina_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_def_cod_hmi ON defecte_interventii (LOWER(cod_eroare_hmi))")
                c.execute("CREATE INDEX IF NOT EXISTS idx_def_coduri_driver ON defecte_interventii (LOWER(coduri_driver_text))")
        except Exception as e:
            logger.error(f"Eroare la verificarea schemei defecte_interventii: {e}")

    @staticmethod
    @st.cache_data(ttl=120)
    def get_all():
        DefecteRepository.ensure_schema()
        query = """
            SELECT id, masina_id, tip_control_cnc, tip_vfd_sau_driver,
                   cod_eroare_hmi, mesaj_hmi, coduri_eroare_driver_json,
                   coduri_driver_text, simptom, verificari_efectuate,
                   solutie_aplicata, rezolvat, creat_la, actualizat_la
            FROM defecte_interventii
            ORDER BY id DESC
        """
        return BaseRepository().fetch_all(query)

    @classmethod
    def insert(cls, data: dict):
        cls.ensure_schema()
        coduri_list, coduri_txt = _normalizeaza_coduri_driver(
            data.get("coduri_eroare_driver_json")
            if data.get("coduri_eroare_driver_json") is not None
            else data.get("coduri_driver_text", "")
        )

        query = """
            INSERT INTO defecte_interventii (
                masina_id, tip_control_cnc, tip_vfd_sau_driver,
                cod_eroare_hmi, mesaj_hmi, coduri_eroare_driver_json,
                coduri_driver_text, simptom, verificari_efectuate,
                solutie_aplicata, rezolvat
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("masina_id"),
            str(data.get("tip_control_cnc") or "").strip(),
            str(data.get("tip_vfd_sau_driver") or "").strip(),
            str(data.get("cod_eroare_hmi") or "").strip(),
            str(data.get("mesaj_hmi") or "").strip(),
            json.dumps(coduri_list, ensure_ascii=False),
            coduri_txt,
            str(data.get("simptom") or "").strip(),
            str(data.get("verificari_efectuate") or "").strip(),
            str(data.get("solutie_aplicata") or "").strip(),
            bool(data.get("rezolvat", False)),
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Defect salvat (HMI: {data.get('cod_eroare_hmi')} | Driver/VFD: {coduri_txt})")