#-------------------------------------------------
#-------helper incarcare icoana software----------
#-------------------------------------------------



from pathlib import Path
from PIL import Image
import streamlit as st


def _incarca_iconita(cale_relativa: str, fallback: str = "⚙️"):
    try:
        cale = Path(__file__).resolve().parent / cale_relativa
        if not cale.is_file():
            return fallback
        with Image.open(cale) as img:
            img.verify()
        with Image.open(cale) as img:
            return img.copy()
    except Exception:
        return fallback
from pathlib import Path
from PIL import Image


def incarca_iconita_app(nume_fisier: str = "logo.png", fallback: str = "⚙️"):
    try:
        cale = Path(__file__).resolve().parent.parent / nume_fisier
        if not cale.is_file():
            return fallback
        with Image.open(cale) as img:
            img.verify()
        with Image.open(cale) as img:
            return img.copy()
    except Exception:
        return fallback

st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    page_icon=_incarca_iconita("Nexind_android.png", fallback="⚙️"),
    layout="wide",
    initial_sidebar_state="collapsed",
)