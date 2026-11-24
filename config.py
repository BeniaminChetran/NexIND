# ------------------------------
# ----config.py-----------------
# ------------------------------

import os
import logging
from contextlib import contextmanager
import streamlit as st
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()[cite: 1]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)[cite: 1]
logger = logging.getLogger("NexIndCMMS")[cite: 1]


@st.cache_resource
def init_connection_pool():
    try:
        db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")[cite: 1]
        if not db_url:
            raise ValueError("DATABASE_URL nu este setat în st.secrets sau variabilele de mediu.")[cite: 1]

        pool = ThreadedConnectionPool(1, 20, db_url)[cite: 1]
        logger.info("Connection Pool inițializat cu succes.")[cite: 1]
        return pool[cite: 1]
    except Exception as e:
        logger.error(f"Eroare critică la inițializarea Connection Pool: {e}")[cite: 1]
        st.error(f"Eroare critică la inițializarea Connection Pool Supabase: {e}")[cite: 1]
        st.stop()[cite: 1]


db_pool = init_connection_pool()[cite: 1]


def _preia_conexiune_valida():
    conn = db_pool.getconn()[cite: 1]
    if conn is None or conn.closed:
        if conn is not None:
            try:
                db_pool.putconn(conn, close=True)[cite: 1]
            except Exception:
                pass
        conn = db_pool.getconn()[cite: 1]
    return conn


@contextmanager
def get_connection():
    """Gestionează conexiunea din pool cu commit/rollback automat."""
    conn = _preia_conexiune_valida()
    try:
        yield conn[cite: 1]
        if conn and not conn.closed:
            conn.commit()[cite: 1]
    except psycopg2.OperationalError as e:
        try:
            if conn and not conn.closed:
                conn.rollback()[cite: 1]
        except Exception:
            pass
        logger.warning(f"Conexiune DB întreruptă, va fi închisă la eliberare: {e}")
        if conn is not None:
            try:
                db_pool.putconn(conn, close=True)[cite: 1]
                conn = None
            except Exception:
                pass
        raise
    except Exception as e:
        try:
            if conn and not conn.closed:
                conn.rollback()[cite: 1]
        except Exception:
            pass
        logger.error(f"Eroare în transacția DB, rollback efectuat: {e}")[cite: 1]
        raise
    finally:
        if conn is not None:
            try:
                db_pool.putconn(conn, close=bool(conn.closed))[cite: 1]
            except Exception:
                pass


@contextmanager
def db_cursor(cursor_factory=psycopg2.extras.RealDictCursor):
    """Furnizează un cursor deschis pe o conexiune gestionată automat."""
    with get_connection() as conn:[cite: 1]
        cur = conn.cursor(cursor_factory=cursor_factory)[cite: 1]
        try:
            yield cur[cite: 1]
        finally:
            cur.close()[cite: 1]