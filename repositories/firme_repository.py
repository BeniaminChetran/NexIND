# --------------------------------
# -----firme_repository.py--------
# --------------------------------

import logging
import math
from typing import Any

import streamlit as st

from repositories.base_repository import BaseRepository
from repositories.setari_repository import SetariRepository

logger = logging.getLogger("NexIndCMMS.FirmeRepository")

_COLOANE_SELECT = (
    "id, nume_firma, cui, reg_com, adresa, banca, cont, "
    "nume_persoana, email, telefon, adaos_comercial, distanta_km"
)


def _curata_text(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _rezolva_adaos(data: dict[str, Any]) -> float:
    val = data.get("adaos_comercial")
    if val is not None and str(val).strip() != "":
        try:
            parsed = float(val)
            if math.isfinite(parsed) and parsed >= 0.0:
                return parsed
        except (TypeError, ValueError):
            pass

    setari = SetariRepository.get_setari() or {}
    imp = setari.get("adaos_comercial_implicit")
    try:
        parsed_imp = float(imp) if imp is not None and str(imp).strip() != "" else 35.0
        return parsed_imp if math.isfinite(parsed_imp) and parsed_imp >= 0.0 else 35.0
    except (TypeError, ValueError):
        return 35.0


def _rezolva_distanta_km(data: dict[str, Any]) -> float:
    val = data.get("distanta_km")
    if val is None or str(val).strip() == "":
        return 0.0
    try:
        parsed = float(val)
        if not math.isfinite(parsed) or parsed < 0.0:
            return 0.0
        return parsed
    except (TypeError, ValueError):
        return 0.0


def _rezolva_persoana_contact(data: dict[str, Any]) -> str | None:
    return _curata_text(data.get("persoana_contact")) or _curata_text(data.get("nume_persoana"))


class FirmeRepository(BaseRepository):
    @classmethod
    @st.cache_data(ttl=300)
    def get_all(cls, _self=None) -> list[dict[str, Any]]:
        query = f"""
            SELECT {_COLOANE_SELECT}
            FROM firme
            ORDER BY nume_firma
        """
        rows = cls().fetch_all(query) or []
        return list(rows)

    @classmethod
    def insert(cls, data: dict[str, Any]) -> None:
        nume = _curata_text(data.get("nume_firma"))
        if not nume:
            logger.error("Tentativă de inserare firmă fără nume.")
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")

        adaos_val = _rezolva_adaos(data)
        distanta_val = _rezolva_distanta_km(data)
        persoana_val = _rezolva_persoana_contact(data)

        query = """
            INSERT INTO firme (
                nume_firma, cui, reg_com, adresa, banca, cont,
                nume_persoana, email, telefon, adaos_comercial, distanta_km
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            nume,
            _curata_text(data.get("cui")),
            _curata_text(data.get("reg_com")),
            _curata_text(data.get("adresa")),
            _curata_text(data.get("banca")),
            _curata_text(data.get("cont")),
            persoana_val,
            _curata_text(data.get("email")),
            _curata_text(data.get("telefon")),
            adaos_val,
            distanta_val,
        )
        try:
            cls().execute(query, params)
        except Exception as exc:
            logger.exception("Eroare la inserarea firmei '%s': %s", nume, exc)
            raise RuntimeError(f"Nu s-a putut salva firma '{nume}'.") from exc

        cls.get_all.clear()
        logger.info("Firma nouă adăugată cu succes: %s", nume)

    @classmethod
    def update(cls, firma_id: int, data: dict[str, Any]) -> None:
        if not firma_id or int(firma_id) <= 0:
            raise ValueError("ID-ul firmei este obligatoriu pentru actualizare.")

        nume = _curata_text(data.get("nume_firma"))
        if not nume:
            raise ValueError("Câmpul 'nume_firma' este obligatoriu.")

        adaos_val = _rezolva_adaos(data)
        distanta_val = _rezolva_distanta_km(data)
        persoana_val = _rezolva_persoana_contact(data)

        query = """
            UPDATE firme
            SET nume_firma=%s,
                cui=%s,
                reg_com=%s,
                adresa=%s,
                banca=%s,
                cont=%s,
                nume_persoana=%s,
                email=%s,
                telefon=%s,
                adaos_comercial=%s,
                distanta_km=%s
            WHERE id=%s
        """
        params = (
            nume,
            _curata_text(data.get("cui")),
            _curata_text(data.get("reg_com")),
            _curata_text(data.get("adresa")),
            _curata_text(data.get("banca")),
            _curata_text(data.get("cont")),
            persoana_val,
            _curata_text(data.get("email")),
            _curata_text(data.get("telefon")),
            adaos_val,
            distanta_val,
            int(firma_id),
        )
        try:
            cls().execute(query, params)
        except Exception as exc:
            logger.exception("Eroare la actualizarea firmei #%s: %s", firma_id, exc)
            raise RuntimeError(f"Nu s-a putut actualiza firma #{firma_id}.") from exc

        cls.get_all.clear()
        logger.info("Firma #%s a fost actualizată.", firma_id)

    @classmethod
    def delete(cls, firma_id: int) -> None:
        if not firma_id or int(firma_id) <= 0:
            raise ValueError("ID-ul firmei este invalid pentru ștergere.")

        query = "DELETE FROM firme WHERE id=%s"
        try:
            cls().execute(query, (int(firma_id),))
        except Exception as exc:
            logger.exception("Eroare la ștergerea firmei #%s: %s", firma_id, exc)
            raise RuntimeError(
                f"Nu s-a putut șterge firma #{firma_id}. Verifică dacă este folosită în alte înregistrări."
            ) from exc

        cls.get_all.clear()
        logger.warning("Firma #%s a fost ștearsă din baza de date.", firma_id)