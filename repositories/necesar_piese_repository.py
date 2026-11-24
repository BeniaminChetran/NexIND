# ------------------------------------------------
# --- repositories/necesar_piese_repository.py ---
# ------------------------------------------------

import logging
from typing import Any, Dict, List, Optional
import streamlit as st
from repositories.base_repository import BaseRepository
from repositories.piese_repository import PieseRepository, _normalizeaza_stare_comanda

logger = logging.getLogger("NexIndCMMS.NecesarPieseRepository")


class NecesarPieseRepository(BaseRepository):
    _tabela_asigurata = False

    @classmethod
    def _asigura_tabela(cls) -> None:
        if cls._tabela_asigurata:
            return
        ddl = """
            CREATE TABLE IF NOT EXISTS necesar_piese (
                id SERIAL PRIMARY KEY,
                piesa_id INTEGER NULL REFERENCES piese(id) ON DELETE SET NULL,
                denumire_piesa VARCHAR(255) NOT NULL,
                cod_producator VARCHAR(120) DEFAULT '',
                cantitate NUMERIC(12, 2) NOT NULL DEFAULT 1.00,
                firma_id INTEGER NULL,
                firma_client VARCHAR(255) NOT NULL,
                masina VARCHAR(255) DEFAULT '',
                observatii TEXT DEFAULT '',
                status_comanda VARCHAR(50) NOT NULL DEFAULT 'De căutat',
                data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        cls().execute(ddl)
        try:
            cls().execute("ALTER TABLE necesar_piese ADD COLUMN IF NOT EXISTS firma_id INTEGER NULL")
        except Exception:
            pass
        cls._tabela_asigurata = True

    @classmethod
    def _gaseste_piesa_catalog(cls, denumire: str, cod_producator: str = "") -> Optional[Dict[str, Any]]:
        den_norm = " ".join(str(denumire or "").strip().lower().split())
        cod_norm = " ".join(str(cod_producator or "").strip().lower().split())
        if not den_norm and not cod_norm:
            return None

        for p in PieseRepository.get_all() or []:
            p_den = " ".join(str(p.get("denumire") or "").strip().lower().split())
            p_cod = " ".join(str(p.get("cod_producator") or "").strip().lower().split())
            if den_norm and p_den == den_norm:
                return p
            if cod_norm and p_cod and p_cod == cod_norm:
                return p
        return None

    @classmethod
    def noteaza_piesa_pe_teren(
        cls,
        firma_client: str,
        denumire_piesa: str,
        cantitate: float,
        firma_id: Optional[int] = None,
        masina: str = "",
        cod_producator: str = "",
        observatii: str = "",
    ) -> Dict[str, Any]:
        cls._asigura_tabela()

        firma_curata = str(firma_client or "").strip()
        if not firma_curata:
            raise ValueError("Clientul / firma este obligatorie.")

        den_curata = " ".join(str(denumire_piesa or "").strip().split())
        if not den_curata:
            raise ValueError("Denumirea piesei este obligatorie.")

        cant_num = round(float(cantitate), 2)
        if cant_num <= 0:
            raise ValueError("Cantitatea trebuie să fie mai mare decât 0.")

        cod_curat = str(cod_producator or "").strip()
        masina_curata = str(masina or "").strip()
        if masina_curata.startswith("--"):
            masina_curata = ""
        obs_curata = str(observatii or "").strip()
        fid_val = int(firma_id) if firma_id is not None else None

        piesa_catalog = cls._gaseste_piesa_catalog(den_curata, cod_curat)
        existenta_in_catalog = piesa_catalog is not None

        if existenta_in_catalog:
            piesa_id = piesa_catalog.get("id")
            status_auto = "De ofertat"
        else:
            PieseRepository._asigura_coloane_piese()
            masina_catalog = masina_curata or "General"
            obs_catalog = f"Notat pe teren | Client: {firma_curata}"
            if obs_curata:
                obs_catalog = f"{obs_catalog} | {obs_curata}"

            inserted = cls().execute_returning(
                """
                INSERT INTO piese (
                    denumire, cod_producator, cod_comercial, masina_montaj,
                    subansamblu, parametri, pret_achizitie, valuta_achizitie,
                    link_furnizor, termen_livrare, stare_comandata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    den_curata,
                    cod_curat,
                    "",
                    masina_catalog,
                    "",
                    obs_catalog,
                    0.00,
                    "EUR",
                    "",
                    "1",
                    "De căutat",
                ),
            )
            PieseRepository.get_all.clear()
            piesa_id = inserted.get("id") if isinstance(inserted, dict) else None
            status_auto = "De căutat"

        row_necesar = cls().execute_returning(
            """
            INSERT INTO necesar_piese (
                piesa_id, denumire_piesa, cod_producator, cantitate,
                firma_id, firma_client, masina, observatii, status_comanda
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                piesa_id,
                den_curata,
                cod_curat,
                cant_num,
                fid_val,
                firma_curata,
                masina_curata,
                obs_curata,
                status_auto,
            ),
        )
        cls.get_all.clear()

        return {
            "record": dict(row_necesar) if row_necesar else {},
            "existenta_in_catalog": existenta_in_catalog,
            "status_comanda": status_auto,
            "piesa_id": piesa_id,
        }

    @classmethod
    @st.cache_data(ttl=120)
    def get_all(cls_or_self=None) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else NecesarPieseRepository
        cls._asigura_tabela()
        rows = cls().fetch_all(
            """
            SELECT
                np.id,
                np.piesa_id,
                np.denumire_piesa,
                COALESCE(np.cod_producator, '') AS cod_producator,
                COALESCE(np.cantitate, 1.00) AS cantitate,
                np.firma_id,
                COALESCE(np.firma_client, '') AS firma_client,
                COALESCE(np.masina, '') AS masina,
                COALESCE(np.observatii, '') AS observatii,
                COALESCE(NULLIF(TRIM(np.status_comanda), ''), 'De căutat') AS status_comanda,
                np.data_creare,
                p.link_furnizor AS furnizor_piesa
            FROM necesar_piese np
            LEFT JOIN piese p ON p.id = np.piesa_id
            ORDER BY np.data_creare DESC, np.id DESC
            """
        ) or []

        rez: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["status_comanda"] = _normalizeaza_stare_comanda(d.get("status_comanda"))
            rez.append(d)
        return rez

    @classmethod
    def update_status_comanda(cls, necesar_id: int, status_nou: str) -> None:
        cls._asigura_tabela()
        stare_norm = _normalizeaza_stare_comanda(status_nou)
        cls().execute(
            "UPDATE necesar_piese SET status_comanda = %s WHERE id = %s",
            (stare_norm, int(necesar_id)),
        )
        cls.get_all.clear()