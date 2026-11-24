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
                firma_id INTEGER NULL,
                firma VARCHAR(255) NOT NULL,
                note_vizita TEXT NOT NULL,
                stare VARCHAR(60) NOT NULL DEFAULT 'Urgent',
                data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        cls().execute(ddl)
        cls._tabela_asigurata = True

    @classmethod
    def insert(
        cls,
        data_vizita: datetime.date,
        firma: str,
        note_vizita: str,
        stare: str = "Urgent",
        firma_id: Optional[int] = None,
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
        data_val = data_vizita if isinstance(data_vizita, datetime.date) else datetime.date.today()

        row = cls().execute_returning(
            """
            INSERT INTO taskuri_vizita (data_vizita, firma_id, firma, note_vizita, stare)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (data_val, fid_val, firma_curata, note_curate, stare_norm),
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
                firma_id,
                COALESCE(firma, '') AS firma,
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
                data_vizita DESC,
                id DESC
            """
        ) or []

        rez: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["stare"] = normalizeaza_stare_task_vizita(d.get("stare"))
            rez.append(d)
        return rez

    @classmethod
    def update(cls, task_id: int, note_vizita: str, stare: str) -> None:
        cls._asigura_tabela()
        note_curate = str(note_vizita or "").strip()
        stare_norm = normalizeaza_stare_task_vizita(stare)
        cls().execute(
            "UPDATE taskuri_vizita SET note_vizita = %s, stare = %s WHERE id = %s",
            (note_curate, stare_norm, int(task_id)),
        )
        cls.get_all.clear()

    @classmethod
    def delete(cls, task_id: int) -> None:
        cls._asigura_tabela()
        cls().execute("DELETE FROM taskuri_vizita WHERE id = %s", (int(task_id),))
        cls.get_all.clear()