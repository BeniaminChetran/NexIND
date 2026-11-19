#--------------------------------
#-----masini_repository.py-------
#--------------------------------

import json
import logging
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.MasiniRepository")

ALL_SISTEME_DEFAULT = "Electric,Mecanic,Hidraulic,Pneumatic,Vacuum,Auxiliare"


class MasiniRepository(BaseRepository):
    @staticmethod
    def _ensure_sisteme_col():
        try:
            with db_cursor() as c:
                c.execute(f"""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS sisteme_active TEXT DEFAULT '{ALL_SISTEME_DEFAULT}'
                """)
                c.execute("""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS verificari_custom_json JSONB DEFAULT '{}'::jsonb
                """)
                c.execute("""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS componenta_sisteme_json JSONB DEFAULT '[]'::jsonb
                """)
                c.execute("""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS este_masina_noua BOOLEAN DEFAULT FALSE
                """)
                c.execute("""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS prag_interventii INTEGER DEFAULT 20
                """)
                c.execute("""
                    ALTER TABLE masini
                    ADD COLUMN IF NOT EXISTS offset_interventii INTEGER DEFAULT 0
                """)
        except Exception as e:
            logger.debug(f"Verificare coloane masini: {e}")

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
    def get_all(cls):
        cls._ensure_sisteme_col()
        query = """
            SELECT m.id, m.firma_id, m.denumire, m.tip_masina, m.serie, m.an_fabricatie,
                   m.subansambluri, m.erori, m.defecte, m.remediu, m.piese_necesare,
                   m.piese_inlocuite, m.tipuri_fluide, m.data_intretinere, m.tip_intretinere,
                   COALESCE(NULLIF(TRIM(m.sisteme_active), ''), %s) AS sisteme_active,
                   COALESCE(m.verificari_custom_json, '{}'::jsonb) AS verificari_custom_json,
                   COALESCE(m.componenta_sisteme_json, '[]'::jsonb) AS componenta_sisteme_json,
                   COALESCE(m.este_masina_noua, FALSE) AS este_masina_noua,
                   COALESCE(m.prag_interventii, 20) AS prag_interventii,
                   COALESCE(m.offset_interventii, 0) AS offset_interventii,
                   (
                       COALESCE((SELECT COUNT(*) FROM reparatii r WHERE r.masina = m.denumire AND (f.nume_firma IS NULL OR r.firma = f.nume_firma)), 0) +
                       COALESCE((SELECT COUNT(*) FROM mentenanta_preventiva mp WHERE mp.masina_id = m.id), 0) +
                       COALESCE((SELECT COUNT(*) FROM reparatii_electronice re WHERE re.masina_id = m.id), 0) +
                       COALESCE(m.offset_interventii, 0)
                   ) AS total_interventii
            FROM masini m
            LEFT JOIN firme f ON m.firma_id = f.id
            ORDER BY m.denumire
        """
        rows = cls().fetch_all(query, (ALL_SISTEME_DEFAULT,))
        for r in rows:
            r["verificari_custom_json"] = cls._parse_json(r.get("verificari_custom_json"), {})
            r["componenta_sisteme_json"] = cls._parse_json(r.get("componenta_sisteme_json"), [])
            r["total_interventii"] = max(0, int(r.get("total_interventii") or 0))
            r["prag_interventii"] = int(r.get("prag_interventii") or 20)
        return rows

    @classmethod
    def get_by_firma(cls, firma_id: int):
        cls._ensure_sisteme_col()
        query = """
            SELECT m.id, m.denumire, m.subansambluri, m.erori, m.tip_masina, m.serie, m.an_fabricatie,
                   m.data_intretinere, m.tip_intretinere, m.tipuri_fluide,
                   COALESCE(NULLIF(TRIM(m.sisteme_active), ''), %s) AS sisteme_active,
                   COALESCE(m.verificari_custom_json, '{}'::jsonb) AS verificari_custom_json,
                   COALESCE(m.componenta_sisteme_json, '[]'::jsonb) AS componenta_sisteme_json,
                   COALESCE(m.este_masina_noua, FALSE) AS este_masina_noua,
                   COALESCE(m.prag_interventii, 20) AS prag_interventii,
                   COALESCE(m.offset_interventii, 0) AS offset_interventii,
                   (
                       COALESCE((SELECT COUNT(*) FROM reparatii r WHERE r.masina = m.denumire AND r.firma = f.nume_firma), 0) +
                       COALESCE((SELECT COUNT(*) FROM mentenanta_preventiva mp WHERE mp.masina_id = m.id), 0) +
                       COALESCE((SELECT COUNT(*) FROM reparatii_electronice re WHERE re.masina_id = m.id), 0) +
                       COALESCE(m.offset_interventii, 0)
                   ) AS total_interventii
            FROM masini m
            JOIN firme f ON m.firma_id = f.id
            WHERE f.id = %s 
            ORDER BY m.denumire
        """
        rows = cls().fetch_all(query, (ALL_SISTEME_DEFAULT, firma_id))
        for r in rows:
            r["verificari_custom_json"] = cls._parse_json(r.get("verificari_custom_json"), {})
            r["componenta_sisteme_json"] = cls._parse_json(r.get("componenta_sisteme_json"), [])
            r["total_interventii"] = max(0, int(r.get("total_interventii") or 0))
            r["prag_interventii"] = int(r.get("prag_interventii") or 20)
        return rows

    @classmethod
    def update_verificari_custom(cls, masina_id: int, verificari_dict: dict):
        cls._ensure_sisteme_col()
        with db_cursor() as c:
            c.execute(
                "UPDATE masini SET verificari_custom_json = %s::jsonb WHERE id = %s",
                (json.dumps(verificari_dict, ensure_ascii=False), masina_id)
            )
        logger.info(f"Verificările tehnice personalizate au fost actualizate pentru mașina #{masina_id}")

    @classmethod
    def update_componenta_sisteme(cls, masina_id: int, componenta_list: list):
        cls._ensure_sisteme_col()
        with db_cursor() as c:
            c.execute(
                "UPDATE masini SET componenta_sisteme_json = %s::jsonb WHERE id = %s",
                (json.dumps(componenta_list, ensure_ascii=False), masina_id)
            )
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
                este_masina_noua, prag_interventii, offset_interventii
            ) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
        """
        params = (
            data['firma_id'], data['denumire'], data.get('tip_masina'),
            data.get('serie') or data.get('nr_serie'),
            data.get('an_fabricatie'), data.get('subansambluri'), data.get('erori'),
            data.get('defecte'), data.get('remediu') or data.get('reparatii'),
            data.get('piese_necesare'),
            data.get('piese_inlocuite'), data.get('tipuri_fluide'), data.get('data_intretinere'),
            data.get('tip_intretinere'),
            data.get('sisteme_active') or ALL_SISTEME_DEFAULT,
            json.dumps(data.get('verificari_custom_json') or {}, ensure_ascii=False),
            json.dumps(data.get('componenta_sisteme_json') or [], ensure_ascii=False),
            bool(data.get('este_masina_noua', False)),
            int(data.get('prag_interventii', 20) or 20),
            int(data.get('offset_interventii', 0) or 0),
        )
        cls().execute(query, params)
        logger.info(f"Mașină adăugată: {data['denumire']}")

    @classmethod
    def delete(cls, masina_id: int):
        query = "DELETE FROM masini WHERE id=%s"
        cls().execute(query, (masina_id,))
        logger.info(f"Mașina #{masina_id} a fost ștearsă.")