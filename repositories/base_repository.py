# --------------------------------
# -------base_repository.py-------
# --------------------------------

import logging
from typing import Any, Iterable, List, Optional, Tuple
from config import db_cursor[cite: 3]

logger = logging.getLogger("NexIndCMMS.BaseRepository")[cite: 3]


class BaseRepository:
    def fetch_all(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> List[dict]:
        with db_cursor() as cur:[cite: 3]
            cur.execute(query, params)[cite: 3]
            return cur.fetchall()[cite: 3]

    def fetch_one(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[dict]:
        with db_cursor() as cur:[cite: 3]
            cur.execute(query, params)[cite: 3]
            return cur.fetchone()[cite: 3]

    def execute(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        with db_cursor() as cur:[cite: 3]
            cur.execute(query, params)[cite: 3]
            return cur.rowcount[cite: 3]

    def execute_returning(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[dict]:
        with db_cursor() as cur:[cite: 3]
            cur.execute(query, params)[cite: 3]
            return cur.fetchone()[cite: 3]

    def executemany(self, query: str, seq_of_params: Iterable[Tuple[Any, ...]]) -> int:
        with db_cursor() as cur:
            cur.executemany(query, seq_of_params)
            return cur.rowcount