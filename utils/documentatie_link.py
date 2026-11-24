
#----------------------------------------------
#---------utils/documentatie_link.py-----------
#-----------------------------------------------



import streamlit as st
from repositories.setari_repository import SetariRepository


def obtine_locatie_documentatie_url() -> str:
    """Returnează URL-ul valid salvat în setări pentru locația documentațiilor, sau '' dacă lipsește."""
    try:
        setari = SetariRepository.get_setari() or {}
    except Exception:
        setari = {}

    link = str(setari.get("locatie_documentatii_gdrive") or "").strip()
    if link.startswith(("http://", "https://")):
        return link
    return ""


def randeaza_banner_locatie_documentatie(
    eticheta: str = "📂 Deschide locația centrală a documentațiilor",
    mesaj_lipsa: str = "Locația documentațiilor nu este încă setată în Setări (`locatie_documentatii_gdrive`).",
) -> None:
    """Afișează link-ul către folderul/locația centrală de documentații salvată în DB."""
    url = obtine_locatie_documentatie_url()
    if url:
        st.link_button(eticheta, url=url, use_container_width=False)
    else:
        st.caption(f"ℹ️ {mesaj_lipsa}")