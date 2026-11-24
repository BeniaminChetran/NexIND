# ------------------------------
# ----config.py-----------------
# ------------------------------

import os
import logging
import streamlit as st
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NexIndCMMS")


@st.cache_resource
def init_connection_pool():
    try:
        db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL nu este setat în st.secrets sau variabilele de mediu.")

        pool = ThreadedConnectionPool(1, 20, db_url)
        logger.info("Connection Pool inițializat cu succes.")
        return pool
    except Exception as e:
        logger.error(f"Eroare critică la inițializarea Connection Pool: {e}")
        st.error(f"Eroare critică la inițializarea Connection Pool Supabase: {e}")
        st.stop()


db_pool = init_connection_pool()


def _preia_conexiune_valida():
    conn = db_pool.getconn()
    if conn is None or conn.closed:
        if conn is not None:
            try:
                db_pool.putconn(conn, close=True)
            except Exception:
                pass
        conn = db_pool.getconn()
    return conn


@contextmanager
def get_connection():
    """Gestionează conexiunea din pool cu commit/rollback automat."""
    conn = _preia_conexiune_valida()
    try:
        yield conn
        if conn and not conn.closed:
            conn.commit()
    except psycopg2.OperationalError as e:
        try:
            if conn and not conn.closed:
                conn.rollback()
        except Exception:
            pass
        logger.warning(f"Conexiune DB întreruptă, va fi închisă la eliberare: {e}")
        if conn is not None:
            try:
                db_pool.putconn(conn, close=True)
                conn = None
            except Exception:
                pass
        raise
    except Exception as e:
        try:
            if conn and not conn.closed:
                conn.rollback()
        except Exception:
            pass
        logger.error(f"Eroare în transacția DB, rollback efectuat: {e}")
        raise
    finally:
        if conn is not None:
            try:
                db_pool.putconn(conn, close=bool(conn.closed))
            except Exception:
                pass


@contextmanager
def db_cursor(cursor_factory=psycopg2.extras.RealDictCursor):
    """Furnizează un cursor deschis pe o conexiune gestionată automat."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()