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
        db_url = st.secrets["DATABASE_URL"]
        pool = ThreadedConnectionPool(1, 20, db_url)
        logger.info("Connection Pool inițializat cu succes.")
        return pool
    except Exception as e:
        logger.error(f"Eroare critică la inițializarea Connection Pool: {e}")
        st.error(f"Eroare critică la inițializarea Connection Pool Supabase: {e}")
        st.stop()

db_pool = init_connection_pool()

from contextlib import contextmanager

@contextmanager
def db_cursor():
    conn = db_pool.getconn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Eroare în transacția DB, rollback efectuat: {e}")
        raise e
    finally:
        cur.close()
        db_pool.putconn(conn)