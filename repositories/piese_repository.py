# --------------------------------
# -----piese_repository.py--------
# --------------------------------

import logging
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository[cite: 5]

logger = logging.getLogger("NexIndCMMS.PieseRepository")[cite: 5]

OPTIUNI_STARE_COMANDA = [
    "De căutat",
    "De ofertat",
    "De comandat",
    "Comandată",
    "În așteptare",
    "Anulată",
][cite: 5]


def _normalizeaza_stare_comanda(val) -> str:
    s = str(val or "").strip()[cite: 5]
    mapa = {
        "de cautat": "De căutat",
        "de căutat": "De căutat",
        "de ofertat": "De ofertat",
        "ofertare": "De ofertat",
        "de comandat": "De comandat",
        "comandat": "Comandată",
        "comandata": "Comandată",
        "comandată": "Comandată",
        "in asteptare": "În așteptare",
        "în așteptare": "În așteptare",
        "anulata": "Anulată",
        "anulată": "Anulată",
    }[cite: 5]
    return mapa.get(s.lower(), "De căutat")[cite: 5]


@st.cache_resource
def _asigura_coloane_piese_once() -> bool:
    ddl_si_indexuri = """
        ALTER TABLE piese ADD COLUMN IF NOT EXISTS termen_livrare VARCHAR(100) DEFAULT '1';
        ALTER TABLE piese ADD COLUMN IF NOT EXISTS stare_comandata VARCHAR(50) DEFAULT 'De căutat';
        CREATE INDEX IF NOT EXISTS idx_piese_denumire ON piese (denumire);
        CREATE INDEX IF NOT EXISTS idx_piese_cod_producator ON piese (cod_producator);
        CREATE INDEX IF NOT EXISTS idx_piese_stare_comandata ON piese (stare_comandata);
    """[cite: 5]
    with db_cursor() as cur:
        cur.execute(ddl_si_indexuri)
    return True


class PieseRepository(BaseRepository):
    @staticmethod
    def _asigura_coloane_piese():
        _asigura_coloane_piese_once()

    @classmethod
    def _goleste_cache_piese(cls):
        if hasattr(cls.get_all, "clear"):
            cls.get_all.clear()
        if hasattr(cls.get_filtrate, "clear"):
            cls.get_filtrate.clear()

    @classmethod
    @st.cache_data(ttl=300)
    def get_all(cls_or_self=None):
        cls = cls_or_self if isinstance(cls_or_self, type) else PieseRepository
        cls._asigura_coloane_piese()[cite: 5]
        query = """
            SELECT id, denumire, cod_producator, cod_comercial, masina_montaj,
                   subansamblu, parametri, pret_achizitie,
                   COALESCE(NULLIF(TRIM(valuta_achizitie), ''), 'RON') AS valuta_achizitie,
                   link_furnizor, COALESCE(termen_livrare, '1') AS termen_livrare,
                   COALESCE(NULLIF(TRIM(stare_comandata), ''), 'De căutat') AS stare_comandata
            FROM piese
            ORDER BY denumire
        """[cite: 5]
        rows = cls().fetch_all(query) or [][cite: 5]
        for r in rows:
            r["stare_comandata"] = _normalizeaza_stare_comanda(r.get("stare_comandata"))[cite: 5]
        return rows[cite: 5]

    @classmethod
    @st.cache_data(ttl=180)
    def get_filtrate(cls_or_self, select_masina_unica: str):
        cls = cls_or_self if isinstance(cls_or_self, type) else PieseRepository
        cls._asigura_coloane_piese()[cite: 5]
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
            """[cite: 5]
            params = (
                f"%{select_masina_unica.strip()}%",
                f"{select_masina_unica.strip()},%",
                f"%, {select_masina_unica.strip()}%",
            )[cite: 5]
            rows = cls().fetch_all(query, params) or [][cite: 5]
            for r in rows:
                r["stare_comandata"] = _normalizeaza_stare_comanda(r.get("stare_comandata"))[cite: 5]
            return rows[cite: 5]
        return cls.get_all()[cite: 5]

    @classmethod
    def insert(cls, data: dict):
        cls._asigura_coloane_piese()[cite: 5]
        valuta = str(data.get("valuta_achizitie") or "RON").strip().upper()[cite: 5]
        if valuta not in ("RON", "EUR"):
            valuta = "RON"[cite: 5]
        masina_val = str(data.get("masina_montaj") or "").strip() or "General"[cite: 5]
        stare_cmd = _normalizeaza_stare_comanda(data.get("stare_comandata"))[cite: 5]
        query = """
            INSERT INTO piese (
                denumire, cod_producator, cod_comercial, masina_montaj,
                subansamblu, parametri, pret_achizitie, valuta_achizitie,
                link_furnizor, termen_livrare, stare_comandata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """[cite: 5]
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
        )[cite: 5]
        cls().execute(query, params)[cite: 5]
        cls._goleste_cache_piese()
        logger.info(f"Piesă adăugată: {data['denumire']} ({masina_val}, {valuta}, {stare_cmd})")[cite: 5]

    @classmethod
    def update(cls, piesa_id: int, data: dict):
        cls._asigura_coloane_piese()[cite: 5]
        valuta = str(data.get("valuta_achizitie") or "RON").strip().upper()[cite: 5]
        if valuta not in ("RON", "EUR"):
            valuta = "RON"[cite: 5]
        masina_val = str(data.get("masina_montaj") or "").strip() or "General"[cite: 5]
        stare_cmd = _normalizeaza_stare_comanda(data.get("stare_comandata"))[cite: 5]
        query = """
            UPDATE piese
            SET denumire=%s, cod_producator=%s, cod_comercial=%s, masina_montaj=%s,
                subansamblu=%s, parametri=%s, pret_achizitie=%s, valuta_achizitie=%s,
                link_furnizor=%s, termen_livrare=%s, stare_comandata=%s
            WHERE id=%s
        """[cite: 5]
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
            int(piesa_id),
        )[cite: 5]
        cls().execute(query, params)[cite: 5]
        cls._goleste_cache_piese()
        logger.info(f"Piesa #{piesa_id} a fost actualizată ({masina_val}, {valuta}, {stare_cmd}).")[cite: 5]

    @classmethod
    def update_stare_comandata(cls, piesa_id: int, stare_noua: str):
        cls._asigura_coloane_piese()[cite: 5]
        stare_cmd = _normalizeaza_stare_comanda(stare_noua)[cite: 5]
        cls().execute(
            "UPDATE piese SET stare_comandata=%s WHERE id=%s",
            (stare_cmd, int(piesa_id)),
        )[cite: 5]
        cls._goleste_cache_piese()
        logger.info(f"Piesa #{piesa_id} -> stare comandă: {stare_cmd}")[cite: 5]

    @classmethod
    def delete(cls, piesa_id: int):
        query = "DELETE FROM piese WHERE id=%s"[cite: 5]
        cls().execute(query, (int(piesa_id),))[cite: 5]
        cls._goleste_cache_piese()
        logger.info(f"Piesa #{piesa_id} ștearsă.")[cite: 5]