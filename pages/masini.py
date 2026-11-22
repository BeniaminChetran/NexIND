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


def _parse_date_sigur(val, fallback: date) -> date:
    if isinstance(val, date):
        return val
    if val:
        try:
            return date.fromisoformat(str(val)[:10])
        except Exception:
            pass
    return fallback


def _actualizeaza_masina_db(masina_id: int, payload: dict):
    _asigura_coloane_masini()
    if hasattr(MasiniRepository, "update"):
        try:
            MasiniRepository.update(int(masina_id), payload)
            if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
                MasiniRepository.get_all.clear()
            return
        except Exception:
            pass

    with db_cursor() as c:
        c.execute(
            """
            UPDATE masini
            SET denumire = %s,
                tip_masina = %s,
                serie = %s,
                tip_intretinere = %s,
                data_intretinere = %s,
                fara_intretinere = %s,
                interval_intretinere_zile = %s,
                ultima_intretinere = %s
            WHERE id = %s
            """,
            (
                payload["denumire"],
                payload.get("tip_masina", ""),
                payload.get("serie", ""),
                payload.get("tip_intretinere", "Trimestrială"),
                payload.get("data_intretinere"),
                bool(payload.get("fara_intretinere", False)),
                int(payload.get("interval_intretinere_zile") or 0),
                payload.get("ultima_intretinere"),
                int(masina_id),
            ),
        )
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()


def _sterge_masina_db(masina_id: int):
    if hasattr(MasiniRepository, "delete"):
        try:
            MasiniRepository.delete(int(masina_id))
            if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
                MasiniRepository.get_all.clear()
            return
        except Exception:
            pass

    with db_cursor() as c:
        c.execute("DELETE FROM masini WHERE id = %s", (int(masina_id),))
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()


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
        st.info("ℹ️ Alege o firmă pentru a vedea, edita sau adăuga utilaje.")
        return

    firma_obj = firme_map[sel_firma]
    firma_id = firma_obj["id"]

    st.markdown("---")
    st.markdown("#### ➕ Adaugă Mașină Nouă")

    fara_intretinere_nou = st.checkbox(
        "🚫 Fără întreținere (utilajul nu necesită mentenanță periodică)",
        value=False,
        key="masini_chk_fara_intretinere_nou",
    )

    with st.form("form_adauga_masina_noua", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            denumire_nou = st.text_input("Denumire Mașină / Utilaj *")
            tip_masina_nou = st.text_input("Producător / Model")
            serie_nou = st.text_input("Serie Fabricație")
        with c2:
            tip_intretinere_nou = st.selectbox(
                "Frecvență / Tip Întreținere",
                options=["Lunară", "Trimestrială", "Semestrială", "Anuală"],
                index=1,
            )
            if not fara_intretinere_nou:
                interval_zile_nou = st.number_input(
                    "Durata până la următoarea întreținere (zile)",
                    min_value=0,
                    step=15,
                    value=90,
                )
                data_intretinere_nou = st.date_input(
                    "Data următoarei întrețineri",
                    value=date.today() + timedelta(days=90),
                )
            else:
                interval_zile_nou = 0
                data_intretinere_nou = None
                st.caption("ℹ️ Opțiunea **Fără întreținere** este activă — nu se setează dată de întreținere.")

        if st.form_submit_button("💾 Salvează Mașina", type="primary"):
            if not denumire_nou.strip():
                st.error("⚠️ Completează denumirea mașinii.")
            else:
                payload = {
                    "firma_id": firma_id,
                    "denumire": denumire_nou.strip(),
                    "tip_masina": tip_masina_nou.strip(),
                    "serie": serie_nou.strip(),
                    "tip_intretinere": tip_intretinere_nou,
                    "data_intretinere": None if fara_intretinere_nou else data_intretinere_nou,
                    "fara_intretinere": bool(fara_intretinere_nou),
                    "interval_intretinere_zile": 0 if fara_intretinere_nou else int(interval_zile_nou),
                    "sisteme_active": ALL_SISTEME_DEFAULT,
                }
                MasiniRepository.insert(payload)
                if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
                    MasiniRepository.get_all.clear()
                st.success(f"✅ Mașina **{denumire_nou.strip()}** a fost adăugată.")
                st.rerun()

    st.markdown("---")
    st.markdown(f"#### 📋 Utilaje înregistrate — {sel_firma}")
    masini_firma = MasiniRepository.get_by_firma(firma_id) or []
    if not masini_firma:
        st.info("Nu există utilaje înregistrate pentru această firmă.")
        return

    opt_frecvente = ["Lunară", "Trimestrială", "Semestrială", "Anuală"]

    for m in masini_firma:
        mid = int(m["id"])
        este_fara = bool(m.get("fara_intretinere", False))
        eticheta_int = "🚫 Fără întreținere" if este_fara else f"📅 Următoarea: {m.get('data_intretinere') or '-'}"

        with st.expander(f"⚙️ {m.get('denumire')} ({eticheta_int})"):
            fara_int_edit = st.checkbox(
                "🚫 Fără întreținere",
                value=este_fara,
                key=f"chk_fara_int_edit_{mid}",
            )

            with st.form(f"form_editeaza_masina_{mid}"):
                e1, e2 = st.columns(2)
                with e1:
                    den_edit = st.text_input("Denumire Mașină / Utilaj *", value=str(m.get("denumire") or ""))
                    tip_edit = st.text_input("Producător / Model", value=str(m.get("tip_masina") or ""))
                    serie_edit = st.text_input("Serie Fabricație", value=str(m.get("serie") or ""))

                with e2:
                    frec_curenta = str(m.get("tip_intretinere") or "Trimestrială")
                    idx_frec = opt_frecvente.index(frec_curenta) if frec_curenta in opt_frecvente else 1
                    frec_edit = st.selectbox("Frecvență / Tip Întreținere", options=opt_frecvente, index=idx_frec)

                    int_curent = int(m.get("interval_intretinere_zile") or 0)
                    interval_edit = st.number_input(
                        "Durata până la următoarea întreținere (zile)",
                        min_value=0,
                        step=15,
                        value=int_curent if int_curent > 0 else 90,
                    )

                    ultima_raw = m.get("ultima_intretinere")
                    ultima_are_valoare = ultima_raw is not None and str(ultima_raw).strip() != ""
                    ultima_edit = st.date_input(
                        "Ultima întreținere",
                        value=_parse_date_sigur(ultima_raw, date.today()),
                    )

                    if not fara_int_edit:
                        data_urm_edit = st.date_input(
                            "Data următoarei întrețineri",
                            value=_parse_date_sigur(m.get("data_intretinere"), date.today() + timedelta(days=int(interval_edit) or 90)),
                        )
                    else:
                        data_urm_edit = None
                        st.caption("ℹ️ Mașina este marcată **Fără întreținere** — data următoarei întrețineri va fi golită.")

                b_save, b_del = st.columns([2, 1])
                salveaza_btn = b_save.form_submit_button("💾 Salvează Modificările", type="primary")
                sterge_btn = b_del.form_submit_button("🗑️ Șterge Mașina")

                if salveaza_btn:
                    if not den_edit.strip():
                        st.error("⚠️ Denumirea mașinii nu poate fi goală.")
                    else:
                        payload_edit = {
                            "firma_id": firma_id,
                            "denumire": den_edit.strip(),
                            "tip_masina": tip_edit.strip(),
                            "serie": serie_edit.strip(),
                            "tip_intretinere": frec_edit,
                            "fara_intretinere": bool(fara_int_edit),
                            "interval_intretinere_zile": 0 if fara_int_edit else int(interval_edit),
                            "data_intretinere": None if fara_int_edit else data_urm_edit,
                            "ultima_intretinere": ultima_edit if ultima_are_valoare else None,
                            "sisteme_active": m.get("sisteme_active") or ALL_SISTEME_DEFAULT,
                        }
                        _actualizeaza_masina_db(mid, payload_edit)
                        st.success(f"✅ Modificările pentru **{den_edit.strip()}** au fost salvate.")
                        st.rerun()

                if sterge_btn:
                    _sterge_masina_db(mid)
                    st.warning(f"🗑️ Mașina **{m.get('denumire')}** a fost ștearsă.")
                    st.rerun()