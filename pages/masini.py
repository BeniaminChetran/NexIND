# ----------------------------------
# -------pages/masini.py------------
# ----------------------------------

from datetime import date, timedelta
import streamlit as st
from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository, ALL_SISTEME_DEFAULT


def _asigura_coloane_masini():
    try:
        with db_cursor() as c:
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS fara_intretinere BOOLEAN DEFAULT FALSE")
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS interval_intretinere_zile INTEGER DEFAULT 0")
            c.execute("ALTER TABLE masini ADD COLUMN IF NOT EXISTS ultima_intretinere DATE")
    except Exception:
        pass


def render_masini():
    st.subheader("⚙️ Gestiune Mașini / Utilaje")
    _asigura_coloane_masini()

    firme_db = FirmeRepository.get_all() or []
    if not firme_db:
        st.warning("⚠️ Adaugă mai întâi cel puțin o firmă din modulul **Firme**.")
        return

    firme_map = {f["nume_firma"]: f for f in firme_db if f.get("nume_firma")}
    opt_firme = ["-- Alege firma --"] + sorted(firme_map.keys(), key=lambda x: x.strip().lower())

    sel_firma = st.selectbox("1. Selectează Firma", options=opt_firme, key="masini_sel_firma")
    if sel_firma == "-- Alege firma --":
        st.info("ℹ️ Alege o firmă pentru a vedea sau adăuga utilaje.")
        return

    firma_obj = firme_map[sel_firma]
    firma_id = firma_obj["id"]

    st.markdown("---")
    st.markdown("#### ➕ Adaugă Mașină Nouă")

    fara_intretinere = st.checkbox(
        "🚫 Fără întreținere (utilajul nu necesită mentenanță periodică)",
        value=False,
        key="masini_chk_fara_intretinere",
    )

    with st.form("form_adauga_masina_noua", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            denumire = st.text_input("Denumire Mașină / Utilaj *")
            tip_masina = st.text_input("Producător / Model")
            serie = st.text_input("Serie Fabricație")
        with c2:
            tip_intretinere = st.selectbox(
                "Frecvență / Tip Întreținere",
                options=["Lunară", "Trimestrială", "Semestrială", "Anuală"],
                index=1,
            )
            if not fara_intretinere:
                interval_zile = st.number_input(
                    "Durata până la următoarea întreținere (zile)",
                    min_value=0,
                    step=15,
                    value=90,
                )
                data_intretinere = st.date_input(
                    "Data următoarei întrețineri",
                    value=date.today() + timedelta(days=90),
                )
            else:
                interval_zile = 0
                data_intretinere = None
                st.caption("ℹ️ Opțiunea **Fără întreținere** este activă — nu se setează dată de întreținere.")

        if st.form_submit_button("💾 Salvează Mașina", type="primary"):
            if not denumire.strip():
                st.error("⚠️ Completează denumirea mașinii.")
            else:
                payload = {
                    "firma_id": firma_id,
                    "denumire": denumire.strip(),
                    "tip_masina": tip_masina.strip(),
                    "serie": serie.strip(),
                    "tip_intretinere": tip_intretinere,
                    "data_intretinere": None if fara_intretinere else data_intretinere,
                    "fara_intretinere": bool(fara_intretinere),
                    "interval_intretinere_zile": 0 if fara_intretinere else int(interval_zile),
                    "sisteme_active": ALL_SISTEME_DEFAULT,
                }
                MasiniRepository.insert(payload)
                st.success(f"✅ Mașina **{denumire.strip()}** a fost adăugată.")
                st.rerun()

    st.markdown("---")
    st.markdown(f"#### 📋 Utilaje înregistrate — {sel_firma}")
    masini_firma = MasiniRepository.get_by_firma(firma_id) or []
    if not masini_firma:
        st.info("Nu există utilaje înregistrate pentru această firmă.")
        return

    for m in masini_firma:
        este_fara = bool(m.get("fara_intretinere", False))
        eticheta_int = "🚫 Fără întreținere" if este_fara else f"📅 Următoarea: {m.get('data_intretinere') or '-'}"
        with st.expander(f"⚙️ {m.get('denumire')} ({eticheta_int})"):
            st.write(
                f"**Model:** {m.get('tip_masina') or '-'} | **Serie:** {m.get('serie') or '-'} | "
                f"**Interval:** {m.get('interval_intretinere_zile') or 0} zile | "
                f"**Ultima întreținere:** {m.get('ultima_intretinere') or '-'}"
            )