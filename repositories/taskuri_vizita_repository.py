# -------------------------------------------------
# --- repositories/taskuri_vizita_repository.py ---
# -------------------------------------------------

import datetime
import logging
from typing import Any, Dict, List, Optional
import streamlit as st
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.TaskuriVizitaRepository")

OPTIUNI_STARE_TASK_VIZITA = [
    "Urgent",
    "De căutat",
    "De verificat",
    "De proiectat",
    "De ofertat",
    "În lucru",
    "Finalizat",
]


def normalizeaza_stare_task_vizita(val: Any) -> str:
    s = str(val or "").strip()
    mapa = {
        "urgent": "Urgent",
        "de cautat": "De căutat",
        "de căutat": "De căutat",
        "de verificat": "De verificat",
        "de proiectat": "De proiectat",
        "de ofertat": "De ofertat",
        "in lucru": "În lucru",
        "în lucru": "În lucru",
        "finalizat": "Finalizat",
        "finalizata": "Finalizat",
        "finalizată": "Finalizat",
    }
    return mapa.get(s.lower(), s if s in OPTIUNI_STARE_TASK_VIZITA else "Urgent")


def formateaza_ora_limita(val: Any) -> str:
    if isinstance(val, datetime.time):
        return val.strftime("%H:%M")
    if isinstance(val, datetime.datetime):
        return val.strftime("%H:%M")
    s = str(val or "").strip()
    if not s:
        return ""
    return s[:5]


def formateaza_termen_complet(data_val: Any, ora_val: Any = "") -> str:
    if not data_val:
        return "-"
    d_str = str(data_val)[:10]
    o_str = formateaza_ora_limita(ora_val)
    return f"{d_str} {o_str}".strip() if o_str else d_str


class TaskuriVizitaRepository(BaseRepository):
    _tabela_asigurata = False

    @classmethod
    def _asigura_tabela(cls) -> None:
        if cls._tabela_asigurata:
            return
        ddl = """
            CREATE TABLE IF NOT EXISTS taskuri_vizita (
                id SERIAL PRIMARY KEY,
                data_vizita DATE NOT NULL DEFAULT CURRENT_DATE,
                de_facut_pana_la DATE NULL,
                ora_limita VARCHAR(5) NULL,
                firma_id INTEGER NULL,
                firma VARCHAR(255) NOT NULL,
                masina VARCHAR(255) DEFAULT '',
                note_vizita TEXT NOT NULL,
                stare VARCHAR(60) NOT NULL DEFAULT 'Urgent',
                data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        cls().execute(ddl)
        for alter_sql in (
            "ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS de_facut_pana_la DATE NULL",
            "ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS ora_limita VARCHAR(5) NULL",
            "ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS masina VARCHAR(255) DEFAULT ''",
        ):
            try:
                cls().execute(alter_sql)
            except Exception:
                pass
        cls._tabela_asigurata = True

    @classmethod
    def insert(
        cls,
        data_vizita: datetime.date,
        firma: str,
        note_vizita: str,
        stare: str = "Urgent",
        firma_id: Optional[int] = None,
        masina: str = "",
        de_facut_pana_la: Optional[datetime.date] = None,
        ora_limita: Optional[Any] = None,
    ) -> Dict[str, Any]:
        cls._asigura_tabela()

        firma_curata = str(firma or "").strip()
        if not firma_curata:
            raise ValueError("Clientul / firma este obligatorie.")

        note_curate = str(note_vizita or "").strip()
        if not note_curate:
            raise ValueError("Câmpul «Note de vizită» nu poate fi gol.")

        stare_norm = normalizeaza_stare_task_vizita(stare)
        fid_val = int(firma_id) if firma_id is not None else None
        masina_curata = str(masina or "").strip()
        if masina_curata.startswith("--"):
            masina_curata = ""
        data_val = data_vizita if isinstance(data_vizita, datetime.date) else datetime.date.today()
        termen_val = de_facut_pana_la if isinstance(de_facut_pana_la, datetime.date) else None
        ora_val = formateaza_ora_limita(ora_limita) if termen_val else None

        row = cls().execute_returning(
            """
            INSERT INTO taskuri_vizita (
                data_vizita, de_facut_pana_la, ora_limita, firma_id, firma, masina, note_vizita, stare
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (data_val, termen_val, ora_val, fid_val, firma_curata, masina_curata, note_curate, stare_norm),
        )
        cls.get_all.clear()
        return dict(row) if row else {}

    @classmethod
    @st.cache_data(ttl=120)
    def get_all(cls_or_self=None) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else TaskuriVizitaRepository
        cls._asigura_tabela()
        rows = cls().fetch_all(
            """
            SELECT
                id,
                data_vizita,
                de_facut_pana_la,
                COALESCE(ora_limita, '') AS ora_limita,
                firma_id,
                COALESCE(firma, '') AS firma,
                COALESCE(masina, '') AS masina,
                COALESCE(note_vizita, '') AS note_vizita,
                COALESCE(NULLIF(TRIM(stare), ''), 'Urgent') AS stare,
                data_creare
            FROM taskuri_vizita
            ORDER BY
                CASE COALESCE(NULLIF(TRIM(stare), ''), 'Urgent')
                    WHEN 'Urgent' THEN 1
                    WHEN 'De căutat' THEN 2
                    WHEN 'De verificat' THEN 3
                    WHEN 'De proiectat' THEN 4
                    WHEN 'De ofertat' THEN 5
                    WHEN 'În lucru' THEN 6
                    WHEN 'Finalizat' THEN 7
                    ELSE 8
                END,
                de_facut_pana_la ASC NULLS LAST,
                COALESCE(NULLIF(TRIM(ora_limita), ''), '23:59') ASC,
                data_vizita DESC,
                id DESC
            """
        ) or []

        rez: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["stare"] = normalizeaza_stare_task_vizita(d.get("stare"))
            d["ora_limita"] = formateaza_ora_limita(d.get("ora_limita"))
            rez.append(d)
        return rez

    @classmethod
    def update(
        cls,
        task_id: int,
        note_vizita: str,
        stare: str,
        de_facut_pana_la: Optional[datetime.date] = None,
        ora_limita: Optional[Any] = None,
    ) -> None:
        cls._asigura_tabela()
        note_curate = str(note_vizita or "").strip()
        stare_norm = normalizeaza_stare_task_vizita(stare)
        termen_val = de_facut_pana_la if isinstance(de_facut_pana_la, datetime.date) else None
        ora_val = formateaza_ora_limita(ora_limita) if termen_val else None
        cls().execute(
            """
            UPDATE taskuri_vizita
            SET note_vizita = %s, stare = %s, de_facut_pana_la = %s, ora_limita = %s
            WHERE id = %s
            """,
            (note_curate, stare_norm, termen_val, ora_val, int(task_id)),
        )
        cls.get_all.clear()

    @classmethod
    def mark_completed(cls, task_id: int) -> None:
        cls._asigura_tabela()
        cls().execute(
            "UPDATE taskuri_vizita SET stare = 'Finalizat' WHERE id = %s",
            (int(task_id),),
        )
        cls.get_all.clear()

    @classmethod
    def delete(cls, task_id: int) -> None:
        cls._asigura_tabela()
        cls().execute("DELETE FROM taskuri_vizita WHERE id = %s", (int(task_id),))
        cls.get_all.clear()