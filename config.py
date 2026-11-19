#------------------------------
#----config.py-----------------
#------------------------------

import os
import logging
import streamlit as st
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

load_dotenv()

# Configurare Logging (înlocuiește print-urile)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NexIndCMMS")

# ------------------------------------------------------------------------------
# CONNECTION POOL SUPABASE
# ------------------------------------------------------------------------------
@st.cache_resource
def init_connection_pool():
    try:
        # Verifică întâi st.secrets, apoi fallback la os.getenv dacă este cazul
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

# ------------------------------------------------------------------------------
# CONTEXT MANAGER-E PENTRU BAZA DE DATE
# ------------------------------------------------------------------------------
@contextmanager
def get_connection():
    """Gestionează conexiunea din pool cu commit/rollback automat."""
    conn = db_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Eroare în transacția DB, rollback efectuat: {e}")
        raise e
    finally:
        db_pool.putconn(conn)

@contextmanager
def db_cursor(cursor_factory=psycopg2.extras.RealDictCursor):
    """Furnizează un cursor deschis pe o conexiune gestionată automat."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()