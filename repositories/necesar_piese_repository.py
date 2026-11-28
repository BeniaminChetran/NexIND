# ------------------------------------------------
# --- repositories/necesar_piese_repository.py ---
# ------------------------------------------------

import logging
from typing import Any, Dict, List, Optional
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository
from repositories.piese_repository import PieseRepository, _normalizeaza_stare_comanda

logger = logging.getLogger("NexIndCMMS.NecesarPieseRepository")

OPTIUNI_PRIORITATE_PIESA = ["Normal", "Urgent"]
OPTIUNI_STATUS_TEREN = ["De căutat", "De ofertat", "De comandat", "În așteptare", "Ofertată"]


def normalizeaza_prioritate_piesa(val: Any) -> str:
    s = str(val or "").strip().lower()
    if s in ("urgent", "urgentă", "urgenta", "ridicată", "ridicata", "high"):
        return "Urgent"
    return "Normal"


@st.cache_resource
def _asigura_tabela_necesar_once() -> bool:
    ddl_si_indexuri = """
        CREATE TABLE IF NOT EXISTS necesar_piese (
            id SERIAL PRIMARY KEY,
            piesa_id INTEGER NULL REFERENCES piese(id) ON DELETE SET NULL,
            denumire_piesa VARCHAR(255) NOT NULL,
            cod_producator VARCHAR(120) DEFAULT '',
            cantitate NUMERIC(12, 2) NOT NULL DEFAULT 1.00,
            firma_id INTEGER NULL,
            firma_client VARCHAR(255) NOT NULL,
            masina VARCHAR(255) DEFAULT '',
            prioritate_piesa VARCHAR(30) NOT NULL DEFAULT 'Normal',
            observatii TEXT DEFAULT '',
            status_comanda VARCHAR(50) NOT NULL DEFAULT 'De căutat',
            data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_ofertare TIMESTAMP NULL
        );
        ALTER TABLE necesar_piese ADD COLUMN IF NOT EXISTS firma_id INTEGER NULL;
        ALTER TABLE necesar_piese ADD COLUMN IF NOT EXISTS prioritate_piesa VARCHAR(30) NOT NULL DEFAULT 'Normal';
        ALTER TABLE necesar_piese ADD COLUMN IF NOT EXISTS data_ofertare TIMESTAMP NULL;
        CREATE INDEX IF NOT EXISTS idx_necesar_piese_status ON necesar_piese (status_comanda);
        CREATE INDEX IF NOT EXISTS idx_necesar_piese_prioritate ON necesar_piese (prioritate_piesa);
        CREATE INDEX IF NOT EXISTS idx_necesar_piese_firma ON necesar_piese (firma_id);
        CREATE INDEX IF NOT EXISTS idx_necesar_piese_data_ofertare ON necesar_piese (data_ofertare);
    """
    with db_cursor() as cur:
        cur.execute(ddl_si_indexuri)
    return True


class NecesarPieseRepository(BaseRepository):
    @classmethod
    def _asigura_tabela(cls) -> None:
        _asigura_tabela_necesar_once()

    @classmethod
    def _gaseste_piesa_catalog(cls, denumire: str, cod_producator: str = "") -> Optional[Dict[str, Any]]:
        den_norm = " ".join(str(denumire or "").strip().lower().split())
        cod_norm = " ".join(str(cod_producator or "").strip().lower().split())
        if not den_norm and not cod_norm:
            return None

        row = cls().fetch_one(
            """
            SELECT id, denumire, cod_producator, link_furnizor
            FROM piese
            WHERE (%s <> '' AND LOWER(TRIM(COALESCE(denumire, ''))) = %s)
               OR (%s <> '' AND LOWER(TRIM(COALESCE(cod_producator, ''))) = %s)
            ORDER BY id ASC
            LIMIT 1
            """,
            (den_norm, den_norm, cod_norm, cod_norm),
        )
        return dict(row) if row else None

    @classmethod
    def noteaza_piesa_pe_teren(
        cls,
        firma_client: str,
        denumire_piesa: str,
        cantitate: float,
        firma_id: Optional[int] = None,
        masina: str = "",
        cod_producator: str = "",
        prioritate_piesa: str = "Normal",
        status_comanda: Optional[str] = None,
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
        prio_norm = normalizeaza_prioritate_piesa(prioritate_piesa)
        obs_curata = str(observatii or "").strip()
        fid_val = int(firma_id) if firma_id is not None else None

        piesa_catalog = cls._gaseste_piesa_catalog(den_curata, cod_curat)
        existenta_in_catalog = piesa_catalog is not None

        if status_comanda and str(status_comanda).strip():
            status_final = _normalizeaza_stare_comanda(status_comanda)
        else:
            status_final = "De ofertat" if existenta_in_catalog else "De căutat"

        if existenta_in_catalog:
            piesa_id = piesa_catalog.get("id")
            if not cod_curat:
                cod_curat = str(piesa_catalog.get("cod_producator") or "").strip()
        else:
            PieseRepository._asigura_coloane_piese()
            masina_catalog = masina_curata or "General"
            obs_catalog = f"Notat pe teren | Client: {firma_curata} | Prioritate: {prio_norm}"
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
                    status_final,
                ),
            )
            if hasattr(PieseRepository, "_goleste_cache_piese"):
                PieseRepository._goleste_cache_piese()
            elif hasattr(PieseRepository.get_all, "clear"):
                PieseRepository.get_all.clear()
            piesa_id = inserted.get("id") if isinstance(inserted, dict) else None

        data_ofertare_val = "CURRENT_TIMESTAMP" if status_final == "Ofertată" else "NULL"

        row_necesar = cls().execute_returning(
            f"""
            INSERT INTO necesar_piese (
                piesa_id, denumire_piesa, cod_producator, cantitate,
                firma_id, firma_client, masina, prioritate_piesa, observatii, status_comanda, data_ofertare
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {data_ofertare_val})
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
                prio_norm,
                obs_curata,
                status_final,
            ),
        )
        cls.get_all.clear()

        return {
            "record": dict(row_necesar) if row_necesar else {},
            "existenta_in_catalog": existenta_in_catalog,
            "prioritate_piesa": prio_norm,
            "status_comanda": status_final,
            "piesa_id": piesa_id,
        }

    @classmethod
    @st.cache_data(ttl=120)
    def get_all(cls_or_self=None, include_ofertate: bool = True) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else NecesarPieseRepository
        cls._asigura_tabela()

        filtru_sql = "" if include_ofertate else "WHERE LOWER(TRIM(COALESCE(np.status_comanda, ''))) <> 'ofertată'"

        rows = cls().fetch_all(
            f"""
            SELECT
                np.id,
                np.piesa_id,
                np.denumire_piesa,
                COALESCE(np.cod_producator, '') AS cod_producator,
                COALESCE(np.cantitate, 1.00) AS cantitate,
                np.firma_id,
                COALESCE(np.firma_client, '') AS firma_client,
                COALESCE(np.masina, '') AS masina,
                COALESCE(NULLIF(TRIM(np.prioritate_piesa), ''), 'Normal') AS prioritate_piesa,
                COALESCE(np.observatii, '') AS observatii,
                COALESCE(NULLIF(TRIM(np.status_comanda), ''), 'De căutat') AS status_comanda,
                np.data_creare,
                np.data_ofertare,
                COALESCE(NULLIF(TRIM(p.link_furnizor), ''), '') AS furnizor_piesa,
                COALESCE(p.pret_achizitie, 0.00) AS pret_catalog,
                COALESCE(NULLIF(TRIM(p.valuta_achizitie), ''), 'RON') AS valuta_catalog
            FROM necesar_piese np
            LEFT JOIN piese p ON p.id = np.piesa_id
            {filtru_sql}
            ORDER BY
                CASE WHEN LOWER(TRIM(COALESCE(np.prioritate_piesa, 'Normal'))) = 'urgent' THEN 0 ELSE 1 END,
                CASE COALESCE(NULLIF(TRIM(np.status_comanda), ''), 'De căutat')
                    WHEN 'De ofertat' THEN 1
                    WHEN 'De căutat' THEN 2
                    WHEN 'De comandat' THEN 3
                    WHEN 'În așteptare' THEN 4
                    WHEN 'Comandată' THEN 5
                    WHEN 'Ofertată' THEN 6
                    WHEN 'Anulată' THEN 7
                    ELSE 8
                END,
                np.data_creare DESC,
                np.id DESC
            """
        ) or []

        rez: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["prioritate_piesa"] = normalizeaza_prioritate_piesa(d.get("prioritate_piesa"))
            d["status_comanda"] = _normalizeaza_stare_comanda(d.get("status_comanda"))
            rez.append(d)
        return rez

    @classmethod
    def update_status_comanda(cls, necesar_id: int, status_nou: str) -> None:
        cls._asigura_tabela()
        stare_norm = _normalizeaza_stare_comanda(status_nou)
        if stare_norm == "Ofertată":
            cls().execute(
                """
                UPDATE necesar_piese
                SET status_comanda = %s,
                    data_ofertare = COALESCE(data_ofertare, CURRENT_TIMESTAMP)
                WHERE id = %s
                """,
                (stare_norm, int(necesar_id)),
            )
        else:
            cls().execute(
                """
                UPDATE necesar_piese
                SET status_comanda = %s,
                    data_ofertare = NULL
                WHERE id = %s
                """,
                (stare_norm, int(necesar_id)),
            )
        cls.get_all.clear()

    @classmethod
    def update_prioritate_piesa(cls, necesar_id: int, prioritate_noua: str) -> None:
        cls._asigura_tabela()
        prio_norm = normalizeaza_prioritate_piesa(prioritate_noua)
        cls().execute(
            "UPDATE necesar_piese SET prioritate_piesa = %s WHERE id = %s",
            (prio_norm, int(necesar_id)),
        )
        cls.get_all.clear()

    @classmethod
    def marcheaza_ofertat(cls, necesar_id: int, observatie_suplimentara: str = "") -> None:
        cls._asigura_tabela()
        obs_extra = str(observatie_suplimentara or "").strip()
        if obs_extra:
            cls().execute(
                """
                UPDATE necesar_piese
                SET status_comanda = 'Ofertată',
                    data_ofertare = COALESCE(data_ofertare, CURRENT_TIMESTAMP),
                    observatii = CASE
                        WHEN COALESCE(TRIM(observatii), '') = '' THEN %s
                        ELSE observatii || ' | ' || %s
                    END
                WHERE id = %s
                """,
                (obs_extra, obs_extra, int(necesar_id)),
            )
        else:
            cls().execute(
                """
                UPDATE necesar_piese
                SET status_comanda = 'Ofertată',
                    data_ofertare = COALESCE(data_ofertare, CURRENT_TIMESTAMP)
                WHERE id = %s
                """,
                (int(necesar_id),),
            )
        cls.get_all.clear()