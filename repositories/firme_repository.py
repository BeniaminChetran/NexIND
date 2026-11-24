#--------------------------------
#-----firme_repository.py--------
#--------------------------------

import logging
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository[cite: 9]
from repositories.setari_repository import SetariRepository[cite: 9]

logger = logging.getLogger("NexIndCMMS.FirmeRepository")[cite: 9]


@st.cache_resource
def _asigura_indexuri_firme_once() -> bool:
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_firme_nume_firma ON firme (nume_firma);
            CREATE INDEX IF NOT EXISTS idx_firme_cui ON firme (cui);
            """
        )
    return True


def _rezolva_adaos(data: dict) -> float:
    val = data.get("adaos_comercial")[cite: 9]
    if val is not None and str(val).strip() != "":
        return float(val)[cite: 9]
    setari = SetariRepository.get_setari() or {}[cite: 9]
    imp = setari.get("adaos_comercial_implicit")[cite: 9]
    try:
        return float(imp) if imp is not None and str(imp).strip() != "" else 35.0[cite: 9]
    except (TypeError, ValueError):
        return 35.0[cite: 9]


class FirmeRepository(BaseRepository):
    @classmethod
    @st.cache_data(ttl=300)
    def get_all(cls_or_self=None):
        _asigura_indexuri_firme_once()
        query = """
            SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon, adaos_comercial
            FROM firme
            ORDER BY nume_firma
        """[cite: 9]
        return BaseRepository().fetch_all(query)[cite: 9]

    @classmethod
    def insert(cls, data: dict):
        _asigura_indexuri_firme_once()
        nume = data.get("nume_firma")[cite: 9]
        if not nume or not str(nume).strip():
            logger.error("Tentativă de inserare firmă fără nume.")[cite: 9]
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")[cite: 9]

        adaos_val = _rezolva_adaos(data)[cite: 9]

        query = """
            INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon, adaos_comercial)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """[cite: 9]
        params = (
            nume.strip(),
            data.get("cui"),
            data.get("reg_com"),
            data.get("adresa"),
            data.get("banca"),
            data.get("cont"),
            data.get("nume_persoana"),
            data.get("email"),
            data.get("telefon"),
            adaos_val,
        )[cite: 9]
        cls().execute(query, params)[cite: 9]
        cls.get_all.clear()[cite: 9]
        logger.info(f"Firma nouă adăugată cu succes: {nume}")[cite: 9]

    @classmethod
    def update(cls, firma_id: int, data: dict):
        _asigura_indexuri_firme_once()
        if not firma_id:
            raise ValueError("ID-ul firmei este obligatoriu pentru actualizare.")[cite: 9]

        nume = data.get("nume_firma")[cite: 9]
        if not nume or not str(nume).strip():
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")[cite: 9]

        adaos_val = _rezolva_adaos(data)[cite: 9]

        query = """
            UPDATE firme
            SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s, adaos_comercial=%s
            WHERE id=%s
        """[cite: 9]
        params = (
            nume.strip(),
            data.get("cui"),
            data.get("reg_com"),
            data.get("adresa"),
            data.get("banca"),
            data.get("cont"),
            data.get("nume_persoana"),
            data.get("email"),
            data.get("telefon"),
            adaos_val,
            firma_id,
        )[cite: 9]
        cls().execute(query, params)[cite: 9]
        cls.get_all.clear()[cite: 9]
        logger.info(f"Firma #{firma_id} a fost actualizată.")[cite: 9]

    @classmethod
    def delete(cls, firma_id: int):
        if not firma_id:
            raise ValueError("ID-ul firmei este invalid pentru ștergere.")[cite: 9]
        query = "DELETE FROM firme WHERE id=%s"[cite: 9]
        cls().execute(query, (firma_id,))[cite: 9]
        cls.get_all.clear()[cite: 9]
        logger.warning(f"Firma #{firma_id} a fost ștearsă din baza de date.")[cite: 9]