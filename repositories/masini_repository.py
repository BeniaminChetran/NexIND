#--------------------------------
#-----masini_repository.py-------
#--------------------------------

from datetime import date, timedelta
import json
import logging
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.MasiniRepository")

ALL_SISTEME_DEFAULT = "Electric,Mecanic,Hidraulic,Pneumatic,Vacuum,Auxiliare"

TIPURI_CONTROL_CNC = (
    "Fanuc",
    "Mitsubishi",
    "Siemens",
    "Heidenhain",
    "Fagor",
    "Mazatrol",
    "Beckhoff / TwinCAT",
    "Altele",
)


@st.cache_resource
def _asigura_schema_si_indexuri_masini_once() -> bool:
    ddl_si_indexuri = f"""
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS sisteme_active TEXT DEFAULT '{ALL_SISTEME_DEFAULT}';
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS verificari_custom_json JSONB DEFAULT '{{}}'::jsonb;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS componenta_sisteme_json JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS este_masina_noua BOOLEAN DEFAULT FALSE;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS prag_interventii INTEGER DEFAULT 20;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS offset_interventii INTEGER DEFAULT 0;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS grila_tarifare VARCHAR(20) DEFAULT 'AUTO';
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS fara_intretinere BOOLEAN DEFAULT FALSE;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS interval_intretinere_zile INTEGER DEFAULT 0;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS ultima_intretinere DATE;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS tip_control_cnc VARCHAR(120) DEFAULT '';
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS componente_electrice_json JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS gdrive_folder_url TEXT DEFAULT '';
        ALTER TABLE masini ADD COLUMN IF NOT EXISTS gdrive_folder_id VARCHAR(255) DEFAULT '';

        CREATE INDEX IF NOT EXISTS idx_masini_firma_id ON masini (firma_id);
        CREATE INDEX IF NOT EXISTS idx_masini_denumire ON masini (denumire);
        CREATE INDEX IF NOT EXISTS idx_masini_data_intretinere ON masini (data_intretinere);
    """
    with db_cursor() as c:
        c.execute(ddl_si_indexuri)

    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_mp_masina_id ON mentenanta_preventiva (masina_id)",
        "CREATE INDEX IF NOT EXISTS idx_re_masina_id ON reparatii_electronice (masina_id)",
        "CREATE INDEX IF NOT EXISTS idx_rep_masina_firma ON reparatii (masina, firma)",
    ):
        try:
            with db_cursor() as c:
                c.execute(idx_sql)
        except Exception:
            pass

    return True


def _goleste_cache_masini() -> None:
    if hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()
    if hasattr(MasiniRepository.get_by_firma, "clear"):
        MasiniRepository.get_by_firma.clear()


class MasiniRepository(BaseRepository):
    @staticmethod
    def _ensure_sisteme_col():
        _asigura_schema_si_indexuri_masini_once()

    @staticmethod
    def _parse_json(val, default):
        if val is None:
            return default
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return default

    @classmethod
    @st.cache_data(ttl=180)
    def get_all(cls_or_self=None):
        cls = cls_or_self if isinstance(cls_or_self, type) else MasiniRepository
        cls._ensure_sisteme_col()
        query = """
            WITH cnt_rep AS (
                SELECT COALESCE(firma, '') AS firma_txt, COALESCE(masina, '') AS masina_txt, COUNT(*) AS cnt
                FROM reparatii
                GROUP BY COALESCE(firma, ''), COALESCE(masina, '')
            ),
            cnt_mp AS (
                SELECT masina_id, COUNT(*) AS cnt
                FROM mentenanta_preventiva
                WHERE masina_id IS NOT NULL
                GROUP BY masina_id
            ),
            cnt_re AS (
                SELECT masina_id, COUNT(*) AS cnt
                FROM reparatii_electronice
                WHERE masina_id IS NOT NULL
                GROUP BY masina_id
            )
            SELECT m.id, m.firma_id, m.denumire, m.tip_masina, m.serie, m.an_fabricatie,
                   m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare,
                   m.piese_inlocuite, m.tipuri_fluide, m.data_intretinere, m.tip_intretinere,
                   COALESCE(NULLIF(TRIM(m.sisteme_active), ''), %s) AS sisteme_active,
                   COALESCE(m.verificari_custom_json, '{}'::jsonb) AS verificari_custom_json,
                   COALESCE(m.componenta_sisteme_json, '[]'::jsonb) AS componenta_sisteme_json,
                   COALESCE(m.este_masina_noua, FALSE) AS este_masina_noua,
                   COALESCE(m.prag_interventii, 20) AS prag_interventii,
                   COALESCE(m.offset_interventii, 0) AS offset_interventii,
                   COALESCE(NULLIF(TRIM(m.grila_tarifare), ''), 'AUTO') AS grila_tarifare,
                   (
                       COALESCE(cr.cnt, 0) +
                       COALESCE(cmp.cnt, 0) +
                       COALESCE(cre.cnt, 0) +
                       COALESCE(m.offset_interventii, 0)
                   ) AS total_interventii
            FROM masini m
            LEFT JOIN firme f ON m.firma_id = f.id
            LEFT JOIN cnt_rep cr ON cr.masina_txt = m.denumire AND (f.nume_firma IS NULL OR cr.firma_txt = f.nume_firma)
            LEFT JOIN cnt_mp cmp ON cmp.masina_id = m.id
            LEFT JOIN cnt_re cre ON cre.masina_id = m.id
            ORDER BY m.denumire
        """
        rows = cls().fetch_all(query, (ALL_SISTEME_DEFAULT,)) or []
        for r in rows:
            r["verificari_custom_json"] = cls._parse_json(r.get("verificari_custom_json"), {})
            r["componenta_sisteme_json"] = cls._parse_json(r.get("componenta_sisteme_json"), [])
            r["total_interventii"] = max(0, int(r.get("total_interventii") or 0))
            r["prag_interventii"] = int(r.get("prag_interventii") or 20)
        return rows

    @classmethod
    @st.cache_data(ttl=180)
    def get_by_firma(cls_or_self, firma_id: int):
        cls = cls_or_self if isinstance(cls_or_self, type) else MasiniRepository
        cls._ensure_sisteme_col()
        query = """
            WITH cnt_rep AS (
                SELECT COALESCE(firma, '') AS firma_txt, COALESCE(masina, '') AS masina_txt, COUNT(*) AS cnt
                FROM reparatii
                GROUP BY COALESCE(firma, ''), COALESCE(masina, '')
            ),
            cnt_mp AS (
                SELECT masina_id, COUNT(*) AS cnt
                FROM mentenanta_preventiva
                WHERE masina_id IS NOT NULL
                GROUP BY masina_id
            ),
            cnt_re AS (
                SELECT masina_id, COUNT(*) AS cnt
                FROM reparatii_electronice
                WHERE masina_id IS NOT NULL
                GROUP BY masina_id
            )
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina, m.serie, m.an_fabricatie,
                   m.data_intretinere, m.tip_intretinere, m.tipuri_fluide,
                   COALESCE(NULLIF(TRIM(m.sisteme_active), ''), %s) AS sisteme_active,
                   COALESCE(m.verificari_custom_json, '{}'::jsonb) AS verificari_custom_json,
                   COALESCE(m.componenta_sisteme_json, '[]'::jsonb) AS componenta_sisteme_json,
                   COALESCE(m.este_masina_noua, FALSE) AS este_masina_noua,
                   COALESCE(m.prag_interventii, 20) AS prag_interventii,
                   COALESCE(m.offset_interventii, 0) AS offset_interventii,
                   COALESCE(NULLIF(TRIM(m.grila_tarifare), ''), 'AUTO') AS grila_tarifare,
                   (
                       COALESCE(cr.cnt, 0) +
                       COALESCE(cmp.cnt, 0) +
                       COALESCE(cre.cnt, 0) +
                       COALESCE(m.offset_interventii, 0)
                   ) AS total_interventii
            FROM masini m
            JOIN firme f ON m.firma_id = f.id
            LEFT JOIN cnt_rep cr ON cr.masina_txt = m.denumire AND cr.firma_txt = f.nume_firma
            LEFT JOIN cnt_mp cmp ON cmp.masina_id = m.id
            LEFT JOIN cnt_re cre ON cre.masina_id = m.id
            WHERE f.id = %s
            ORDER BY m.denumire
        """
        rows = cls().fetch_all(query, (ALL_SISTEME_DEFAULT, int(firma_id))) or []
        for r in rows:
            r["verificari_custom_json"] = cls._parse_json(r.get("verificari_custom_json"), {})
            r["componenta_sisteme_json"] = cls._parse_json(r.get("componenta_sisteme_json"), [])
            r["total_interventii"] = max(0, int(r.get("total_interventii") or 0))
            r["prag_interventii"] = int(r.get("prag_interventii") or 20)
        return rows

    @classmethod
    def update_grila_tarifare(cls, masina_id: int, grila_noua: str):
        cls._ensure_sisteme_col()
        cls().execute(
            "UPDATE masini SET grila_tarifare = %s WHERE id = %s",
            (grila_noua, int(masina_id)),
        )
        _goleste_cache_masini()
        logger.info(f"Grila tarifară pentru mașina #{masina_id} a fost schimbată în {grila_noua}")

    @staticmethod
    def determina_grila_efectiva(masina_obj: dict) -> str:
        mod = str(masina_obj.get("grila_tarifare") or "AUTO").strip()
        if mod in ("Nivel A", "Nivel B"):
            return mod
        total_int = int(masina_obj.get("total_interventii", 0))
        prag_int = int(masina_obj.get("prag_interventii", 20))
        return "Nivel B" if total_int >= prag_int else "Nivel A"

    @classmethod
    def update_verificari_custom(cls, masina_id: int, verificari_dict: dict):
        cls._ensure_sisteme_col()
        cls().execute(
            "UPDATE masini SET verificari_custom_json = %s::jsonb WHERE id = %s",
            (json.dumps(verificari_dict, ensure_ascii=False), int(masina_id)),
        )
        _goleste_cache_masini()
        logger.info(f"Verificările tehnice personalizate au fost actualizate pentru mașina #{masina_id}")

    @classmethod
    def update_componenta_sisteme(cls, masina_id: int, componenta_list: list):
        cls._ensure_sisteme_col()
        cls().execute(
            "UPDATE masini SET componenta_sisteme_json = %s::jsonb WHERE id = %s",
            (json.dumps(componenta_list, ensure_ascii=False), int(masina_id)),
        )
        _goleste_cache_masini()
        logger.info(f"Componența sistemelor a fost actualizată pentru mașina #{masina_id}")

    @classmethod
    def insert(cls, data: dict):
        cls._ensure_sisteme_col()
        query = """
            INSERT INTO masini (
                firma_id, denumire, tip_masina, serie, an_fabricatie, subansambluri, erori,
                defecte, remediu, piese_necesare, piese_inlocuite, tipuri_fluide,
                data_intretinere, tip_intretinere, sisteme_active,
                verificari_custom_json, componenta_sisteme_json,
                este_masina_noua, prag_interventii, offset_interventii, grila_tarifare
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
        """
        params = (
            data["firma_id"],
            data["denumire"],
            data.get("tip_masina"),
            data.get("serie") or data.get("nr_serie"),
            data.get("an_fabricatie"),
            data.get("subansambluri"),
            data.get("erori"),
            data.get("defecte"),
            data.get("remediu") or data.get("reparatii"),
            data.get("piese_necesare"),
            data.get("piese_inlocuite"),
            data.get("tipuri_fluide"),
            data.get("data_intretinere"),
            data.get("tip_intretinere"),
            data.get("sisteme_active") or ALL_SISTEME_DEFAULT,
            json.dumps(data.get("verificari_custom_json") or {}, ensure_ascii=False),
            json.dumps(data.get("componenta_sisteme_json") or [], ensure_ascii=False),
            bool(data.get("este_masina_noua", False)),
            int(data.get("prag_interventii", 20) or 20),
            int(data.get("offset_interventii", 0) or 0),
            data.get("grila_tarifare") or "AUTO",
        )
        cls().execute(query, params)
        _goleste_cache_masini()
        logger.info(f"Mașină adăugată: {data['denumire']}")

    @classmethod
    def delete(cls, masina_id: int):
        query = "DELETE FROM masini WHERE id=%s"
        cls().execute(query, (int(masina_id),))
        _goleste_cache_masini()
        logger.info(f"Mașina #{masina_id} a fost ștearsă")


def asigura_coloane_mentenanta_masini():
    _asigura_schema_si_indexuri_masini_once()


def calculeaza_urmatoarea_data_intretinere(
    data_efectuare: date,
    interval_zile: int | None,
    fallback_zile: int = 90,
) -> date:
    zile = int(interval_zile or 0)
    if zile <= 0:
        zile = int(fallback_zile or 90)
    return data_efectuare + timedelta(days=zile)


def scoate_masina_din_intretinere(masina_id: int):
    asigura_coloane_mentenanta_masini()
    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET fara_intretinere = TRUE,
                data_intretinere = NULL
            WHERE id = %s
            """,
            (int(masina_id),),
        )
    _goleste_cache_masini()


def activeaza_si_programeaza_intretinere(
    masina_id: int,
    data_programata: date,
    interval_zile: int = 0,
    ultima_intretinere: date | None = None,
):
    asigura_coloane_mentenanta_masini()
    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET fara_intretinere = FALSE,
                data_intretinere = %s,
                interval_intretinere_zile = %s,
                ultima_intretinere = COALESCE(%s, ultima_intretinere)
            WHERE id = %s
            """,
            (
                data_programata,
                max(0, int(interval_zile or 0)),
                ultima_intretinere,
                int(masina_id),
            ),
        )
    _goleste_cache_masini()


def finalizeaza_si_replanifica_intretinere(
    masina_id: int,
    data_finalizare: date,
    urmatoarea_data: date,
    interval_zile: int = 0,
):
    asigura_coloane_mentenanta_masini()
    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET fara_intretinere = FALSE,
                ultima_intretinere = %s,
                data_intretinere = %s,
                interval_intretinere_zile = CASE
                    WHEN %s > 0 THEN %s
                    ELSE COALESCE(interval_intretinere_zile, 0)
                END
            WHERE id = %s
            """,
            (
                data_finalizare,
                urmatoarea_data,
                int(interval_zile or 0),
                int(interval_zile or 0),
                int(masina_id),
            ),
        )
    _goleste_cache_masini()


class MasiniRepositoryExt(BaseRepository):
    @classmethod
    def ensure_electric_cnc_cols(cls):
        _asigura_schema_si_indexuri_masini_once()

    @classmethod
    def update_control_si_componente_electrice(
        cls,
        masina_id: int,
        tip_control_cnc: str,
        componente_electrice: list[dict],
        gdrive_folder_url: str = "",
        gdrive_folder_id: str = "",
    ):
        cls.ensure_electric_cnc_cols()
        clean_comp = [
            {
                "rol": str(row.get("Rol / Tip") or "").strip(),
                "producator_model": str(row.get("Producător / Model") or "").strip(),
                "axa_zona": str(row.get("Axă / Zonă / Detalii") or "").strip(),
                "observatii": str(row.get("Observații") or "").strip(),
            }
            for row in (componente_electrice or [])
            if any(
                str(row.get(k) or "").strip()
                for k in ("Rol / Tip", "Producător / Model", "Axă / Zonă / Detalii", "Observații")
            )
        ]
        cls().execute(
            """
            UPDATE masini
            SET tip_control_cnc = %s,
                componente_electrice_json = %s::jsonb,
                gdrive_folder_url = %s,
                gdrive_folder_id = %s
            WHERE id = %s
            """,
            (
                str(tip_control_cnc or "").strip(),
                json.dumps(clean_comp, ensure_ascii=False),
                str(gdrive_folder_url or "").strip(),
                str(gdrive_folder_id or "").strip(),
                int(masina_id),
            ),
        )
        _goleste_cache_masini()
        logger.info(f"Actualizat control CNC ({tip_control_cnc}) și componente electrice pentru mașina #{masina_id}.")