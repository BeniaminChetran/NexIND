#--------------------------------
#-------base_repository.py-------
#--------------------------------

import logging
from typing import Any, List, Optional, Tuple
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.BaseRepository")

class BaseRepository:
    def fetch_all(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> List[dict]:
        with db_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def fetch_one(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[dict]:
        with db_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def execute(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        with db_cursor() as cur:
            cur.execute(query, params)
            return cur.rowcount

    def execute_returning(self, query: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[dict]:
        with db_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()