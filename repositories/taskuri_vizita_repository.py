# -------------------------------------------------
# --- repositories/taskuri_vizita_repository.py ---
# -------------------------------------------------

import datetime
import logging
from typing import Any, Dict, List, Optional
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository[cite: 2]

logger = logging.getLogger("NexIndCMMS.TaskuriVizitaRepository")[cite: 2]

OPTIUNI_STARE_TASK_VIZITA = [
    "Urgent",
    "De căutat",
    "De verificat",
    "De proiectat",
    "De ofertat",
    "În lucru",
    "Finalizat",
][cite: 2]


def normalizeaza_stare_task_vizita(val: Any) -> str:
    s = str(val or "").strip()[cite: 2]
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
    }[cite: 2]
    return mapa.get(s.lower(), s if s in OPTIUNI_STARE_TASK_VIZITA else "Urgent")[cite: 2]


def formateaza_ora_limita(val: Any) -> str:
    if isinstance(val, datetime.time):
        return val.strftime("%H:%M")[cite: 2]
    if isinstance(val, datetime.datetime):
        return val.strftime("%H:%M")[cite: 2]
    s = str(val or "").strip()[cite: 2]
    if not s:
        return ""[cite: 2]
    return s[:5][cite: 2]


def formateaza_termen_complet(data_val: Any, ora_val: Any = "") -> str:
    if not data_val:
        return "-"[cite: 2]
    d_str = str(data_val)[:10][cite: 2]
    o_str = formateaza_ora_limita(ora_val)[cite: 2]
    return f"{d_str} {o_str}".strip() if o_str else d_str[cite: 2]


@st.cache_resource
def _asigura_tabela_taskuri_once() -> bool:
    ddl_si_indexuri = """
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
        );
        ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS de_facut_pana_la DATE NULL;
        ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS ora_limita VARCHAR(5) NULL;
        ALTER TABLE taskuri_vizita ADD COLUMN IF NOT EXISTS masina VARCHAR(255) DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_taskuri_vizita_stare ON taskuri_vizita (stare);
        CREATE INDEX IF NOT EXISTS idx_taskuri_vizita_termen ON taskuri_vizita (de_facut_pana_la);
    """[cite: 2]
    with db_cursor() as cur:
        cur.execute(ddl_si_indexuri)
    return True


class TaskuriVizitaRepository(BaseRepository):
    @classmethod
    def _asigura_tabela(cls) -> None:
        _asigura_tabela_taskuri_once()

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
        cls._asigura_tabela()[cite: 2]

        firma_curata = str(firma or "").strip()[cite: 2]
        if not firma_curata:
            raise ValueError("Clientul / firma este obligatorie.")[cite: 2]

        note_curate = str(note_vizita or "").strip()[cite: 2]
        if not note_curate:
            raise ValueError("Câmpul «Note de vizită» nu poate fi gol.")[cite: 2]

        stare_norm = normalizeaza_stare_task_vizita(stare)[cite: 2]
        fid_val = int(firma_id) if firma_id is not None else None[cite: 2]
        masina_curata = str(masina or "").strip()[cite: 2]
        if masina_curata.startswith("--"):
            masina_curata = ""[cite: 2]
        data_val = data_vizita if isinstance(data_vizita, datetime.date) else datetime.date.today()[cite: 2]
        termen_val = de_facut_pana_la if isinstance(de_facut_pana_la, datetime.date) else None[cite: 2]
        ora_val = formateaza_ora_limita(ora_limita) if termen_val else None[cite: 2]

        row = cls().execute_returning(
            """
            INSERT INTO taskuri_vizita (
                data_vizita, de_facut_pana_la, ora_limita, firma_id, firma, masina, note_vizita, stare
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (data_val, termen_val, ora_val, fid_val, firma_curata, masina_curata, note_curate, stare_norm),
        )[cite: 2]
        cls.get_all.clear()[cite: 2]
        return dict(row) if row else {}[cite: 2]

    @classmethod
    @st.cache_data(ttl=120)
    def get_all(cls_or_self=None) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else TaskuriVizitaRepository[cite: 2]
        cls._asigura_tabela()[cite: 2]
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
        ) or [][cite: 2]

        rez: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)[cite: 2]
            d["stare"] = normalizeaza_stare_task_vizita(d.get("stare"))[cite: 2]
            d["ora_limita"] = formateaza_ora_limita(d.get("ora_limita"))[cite: 2]
            rez.append(d)[cite: 2]
        return rez[cite: 2]

    @classmethod
    def update(
        cls,
        task_id: int,
        note_vizita: str,
        stare: str,
        de_facut_pana_la: Optional[datetime.date] = None,
        ora_limita: Optional[Any] = None,
    ) -> None:
        cls._asigura_tabela()[cite: 2]
        note_curate = str(note_vizita or "").strip()[cite: 2]
        stare_norm = normalizeaza_stare_task_vizita(stare)[cite: 2]
        termen_val = de_facut_pana_la if isinstance(de_facut_pana_la, datetime.date) else None[cite: 2]
        ora_val = formateaza_ora_limita(ora_limita) if termen_val else None[cite: 2]
        cls().execute(
            """
            UPDATE taskuri_vizita
            SET note_vizita = %s, stare = %s, de_facut_pana_la = %s, ora_limita = %s
            WHERE id = %s
            """,
            (note_curate, stare_norm, termen_val, ora_val, int(task_id)),
        )[cite: 2]
        cls.get_all.clear()[cite: 2]

    @classmethod
    def mark_completed(cls, task_id: int) -> None:
        cls._asigura_tabela()[cite: 2]
        cls().execute(
            "UPDATE taskuri_vizita SET stare = 'Finalizat' WHERE id = %s",
            (int(task_id),),
        )[cite: 2]
        cls.get_all.clear()[cite: 2]

    @classmethod
    def delete(cls, task_id: int) -> None:
        cls._asigura_tabela()[cite: 2]
        cls().execute("DELETE FROM taskuri_vizita WHERE id = %s", (int(task_id),))[cite: 2]
        cls.get_all.clear()[cite: 2]