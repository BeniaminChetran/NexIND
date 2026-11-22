# --------------------------------
# -----piese_repository.py--------
# --------------------------------

import logging
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.PieseRepository")

OPTIUNI_STARE_COMANDA = [
    "De căutat",
    "De comandat",
    "Comandată",
    "Anulată",
]


def _normalizeaza_stare_comanda(val) -> str:
    s = str(val or "").strip()
    mapa = {
        "de cautat": "De căutat",
        "de căutat": "De căutat",
        "de comandat": "De comandat",
        "comandat": "Comandată",
        "comandata": "Comandată",
        "comandată": "Comandată",
        "anulata": "Anulată",
        "anulată": "Anulată",
    }
    return mapa.get(s.lower(), "De căutat")


class PieseRepository(BaseRepository):
    @staticmethod
    def _asigura_coloane_piese():
        try:
            BaseRepository().execute(
                "ALTER TABLE piese ADD COLUMN IF NOT EXISTS termen_livrare VARCHAR(100) DEFAULT '1'"
            )
        except Exception as e:
            logger.debug(f"Verificare coloană termen_livrare: {e}")
        try:
            BaseRepository().execute(
                "ALTER TABLE piese ADD COLUMN IF NOT EXISTS stare_comandata VARCHAR(50) DEFAULT 'De căutat'"
            )
        except Exception as e:
            logger.debug(f"Verificare coloană stare_comandata: {e}")

    @staticmethod
    @st.cache_data(ttl=300)
    def get_all(cls_or_self=None):
        PieseRepository._asigura_coloane_piese()
        query = """
            SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, 
                   subansamblu, parametri, pret_achizitie, 
                   COALESCE(NULLIF(TRIM(valuta_achizitie), ''), 'RON') AS valuta_achizitie, 
                   link_furnizor, COALESCE(termen_livrare, '1') AS termen_livrare,
                   COALESCE(NULLIF(TRIM(stare_comandata), ''), 'De căutat') AS stare_comandata
            FROM piese 
            ORDER BY denumire
        """
        rows = BaseRepository().fetch_all(query) or []
        for r in rows:
            r["stare_comandata"] = _normalizeaza_stare_comanda(r.get("stare_comandata"))
        return rows

    @classmethod
    def get_filtrate(cls, select_masina_unica: str):
        cls._asigura_coloane_piese()
        if select_masina_unica != "Toate mașinile / General":
            query = """
                SELECT id, denumire, cod_producator, cod_comercial, masina_montaj, 
                       subansamblu, parametri, pret_achizitie, 
                       COALESCE(NULLIF(TRIM(valuta_achizitie), ''), 'RON') AS valuta_achizitie, 
                       link_furnizor, COALESCE(termen_livrare, '1') AS termen_livrare,
                       COALESCE(NULLIF(TRIM(stare_comandata), ''), 'De căutat') AS stare_comandata
                FROM piese 
                WHERE LOWER(TRIM(masina_montaj)) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(masina_montaj) LIKE LOWER(%s)
                   OR LOWER(TRIM(masina_montaj)) = 'general'
                   OR masina_montaj = ''
                   OR masina_montaj IS NULL
                ORDER BY denumire
            """
            params = (
                f"%{select_masina_unica.strip()}%",
                f"{select_masina_unica.strip()},%",
                f"%, {select_masina_unica.strip()}%",
            )
            rows = cls().fetch_all(query, params) or []
            for r in rows:
                r["stare_comandata"] = _normalizeaza_stare_comanda(r.get("stare_comandata"))
            return rows
        else:
            return cls().get_all()

    @classmethod
    def insert(cls, data: dict):
        cls._asigura_coloane_piese()
        valuta = str(data.get("valuta_achizitie") or "RON").strip().upper()
        if valuta not in ("RON", "EUR"):
            valuta = "RON"
        masina_val = str(data.get("masina_montaj") or "").strip() or "General"
        stare_cmd = _normalizeaza_stare_comanda(data.get("stare_comandata"))
        query = """
            INSERT INTO piese (
                denumire, cod_producator, cod_comercial, masina_montaj, 
                subansamblu, parametri, pret_achizitie, valuta_achizitie, 
                link_furnizor, termen_livrare, stare_comandata
            ) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data["denumire"],
            data.get("cod_producator"),
            data.get("cod_comercial"),
            masina_val,
            data.get("subansamblu"),
            data.get("parametri", ""),
            data.get("pret_achizitie", 0.00),
            valuta,
            data.get("link_furnizor", ""),
            str(data.get("termen_livrare") or "1").strip(),
            stare_cmd,
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Piesă adăugată: {data['denumire']} ({masina_val}, {valuta}, {stare_cmd})")

    @classmethod
    def update(cls, piesa_id: int, data: dict):
        cls._asigura_coloane_piese()
        valuta = str(data.get("valuta_achizitie") or "RON").strip().upper()
        if valuta not in ("RON", "EUR"):
            valuta = "RON"
        masina_val = str(data.get("masina_montaj") or "").strip() or "General"
        stare_cmd = _normalizeaza_stare_comanda(data.get("stare_comandata"))
        query = """
            UPDATE piese 
            SET denumire=%s, cod_producator=%s, cod_comercial=%s, masina_montaj=%s,
                subansamblu=%s, parametri=%s, pret_achizitie=%s, valuta_achizitie=%s, 
                link_furnizor=%s, termen_livrare=%s, stare_comandata=%s
            WHERE id=%s
        """
        params = (
            data["denumire"],
            data.get("cod_producator"),
            data.get("cod_comercial"),
            masina_val,
            data.get("subansamblu"),
            data.get("parametri", ""),
            data.get("pret_achizitie", 0.00),
            valuta,
            data.get("link_furnizor", ""),
            str(data.get("termen_livrare") or "1").strip(),
            stare_cmd,
            piesa_id,
        )
        cls().execute(query, params)
        cls.get_all.clear()
        logger.info(f"Piesa #{piesa_id} a fost actualizată ({masina_val}, {valuta}, {stare_cmd}).")

    @classmethod
    def update_stare_comandata(cls, piesa_id: int, stare_noua: str):
        cls._asigura_coloane_piese()
        stare_cmd = _normalizeaza_stare_comanda(stare_noua)
        cls().execute(
            "UPDATE piese SET stare_comandata=%s WHERE id=%s",
            (stare_cmd, piesa_id),
        )
        cls.get_all.clear()
        logger.info(f"Piesa #{piesa_id} -> stare comandă: {stare_cmd}")

    @classmethod
    def delete(cls, piesa_id: int):
        query = "DELETE FROM piese WHERE id=%s"
        cls().execute(query, (piesa_id,))
        cls.get_all.clear()
        logger.info(f"Piesa #{piesa_id} ștearsă.")