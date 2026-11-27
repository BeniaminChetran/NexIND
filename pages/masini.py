# ----------------------------------
# -------pages/masini.py------------
# ----------------------------------

from datetime import date, timedelta
import streamlit as st

import config
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import ALL_SISTEME_DEFAULT, MasiniRepository
from utils.sectiune_masina_cmms import render_sectiune_cmms_masina

OPT_FRECVENTE = tuple(
    getattr(config, "OPT_FRECVENTE_INTRETINERE", ("Lunară", "Trimestrială", "Semestrială", "Anuală"))
)
FRECVENTA_IMPLICITA = getattr(config, "FRECVENTA_IMPLICITA", OPT_FRECVENTE[1] if len(OPT_FRECVENTE) > 1 else OPT_FRECVENTE[0])
INTERVAL_IMPLICIT_ZILE = int(getattr(config, "INTERVAL_IMPLICIT_ZILE", 90))
PAS_INTERVAL_ZILE = int(getattr(config, "PAS_INTERVAL_ZILE", 15))
PLACEHOLDER_FIRMA = getattr(config, "PLACEHOLDER_FIRMA", "-- Alege firma --")


def _parse_date_sigur(val, fallback: date) -> date:
    if isinstance(val, date):
        return val
    if val:
        try:
            return date.fromisoformat(str(val)[:10])
        except ValueError:
            pass
    return fallback


def _are_valoare_data(val) -> bool:
    if val is None:
        return False
    if isinstance(val, date):
        return True
    return str(val).strip() != ""


def _invalideaza_cache_masini(firma_id: int | None = None):
    if hasattr(MasiniRepository, "get_all") and hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()

    if hasattr(MasiniRepository, "get_by_firma") and hasattr(MasiniRepository.get_by_firma, "clear"):
        if firma_id is not None:
            try:
                MasiniRepository.get_by_firma.clear(int(firma_id))
                return
            except TypeError:
                pass
        MasiniRepository.get_by_firma.clear()


def _construieste_payload_masina(
    *,
    firma_id: int,
    denumire: str,
    tip_masina: str,
    serie: str,
    tip_intretinere: str,
    fara_intretinere: bool,
    interval_zile: int,
    data_intretinere: date | None,
    ultima_intretinere: date | None = None,
    include_sisteme: bool = False,
) -> dict:
    este_fara = bool(fara_intretinere)
    interval_curat = 0 if este_fara else max(0, int(interval_zile or 0))
    data_urmatoare = None if este_fara else data_intretinere

    payload = {
        "firma_id": int(firma_id),
        "denumire": denumire.strip(),
        "tip_masina": (tip_masina or "").strip(),
        "serie": (serie or "").strip(),
        "tip_intretinere": tip_intretinere,
        "data_intretinere": data_urmatoare,
        "fara_intretinere": este_fara,
        "interval_intretinere_zile": interval_curat,
        "ultima_intretinere": ultima_intretinere,
    }
    if include_sisteme:
        payload["sisteme_active"] = ALL_SISTEME_DEFAULT
    return payload


def _salveaza_masina_noua_cb(firma_id: int):
    denumire = (st.session_state.get("nou_den") or "").strip()
    if not denumire:
        st.session_state["masini_feedback"] = ("error", "⚠️ Completează denumirea mașinii.")
        return

    este_fara = bool(st.session_state.get("masini_chk_fara_intretinere_nou", False))
    tip_int = st.session_state.get("nou_tip_int", FRECVENTA_IMPLICITA)
    interval_zile = int(st.session_state.get("nou_interval_zile", INTERVAL_IMPLICIT_ZILE) or 0)
    data_urm = st.session_state.get("nou_data_int")

    payload = _construieste_payload_masina(
        firma_id=firma_id,
        denumire=denumire,
        tip_masina=st.session_state.get("nou_tip_masina", ""),
        serie=st.session_state.get("nou_serie", ""),
        tip_intretinere=tip_int,
        fara_intretinere=este_fara,
        interval_zile=interval_zile,
        data_intretinere=data_urm,
        include_sisteme=True,
    )

    try:
        MasiniRepository.insert(payload)
        _invalideaza_cache_masini(firma_id)
        st.session_state["masini_feedback"] = ("success", f"✅ Mașina **{denumire}** a fost adăugată.")
        # Resetăm câmpurile formularului fără st.rerun()
        st.session_state["nou_den"] = ""
        st.session_state["nou_tip_masina"] = ""
        st.session_state["nou_serie"] = ""
        st.session_state["nou_tip_int"] = FRECVENTA_IMPLICITA
        st.session_state["nou_interval_zile"] = INTERVAL_IMPLICIT_ZILE
        st.session_state["nou_data_int"] = date.today() + timedelta(days=INTERVAL_IMPLICIT_ZILE)
    except Exception as exc:
        st.session_state["masini_feedback"] = ("error", f"❌ Eroare la adăugare: {exc}")


def _actualizeaza_masina_cb(masina_id: int, firma_id: int, ultima_are_valoare: bool):
    key_prefix = f"m_{firma_id}_{masina_id}"
    denumire = (st.session_state.get(f"{key_prefix}_den") or "").strip()
    if not denumire:
        st.session_state["masini_feedback"] = ("error", "⚠️ Denumirea mașinii nu poate fi goală.")
        return

    este_fara = bool(st.session_state.get(f"chk_fara_int_edit_{firma_id}_{masina_id}", False))
    interval_val = int(st.session_state.get(f"{key_prefix}_interval", INTERVAL_IMPLICIT_ZILE) or 0)
    ultima_val = st.session_state.get(f"{key_prefix}_ultima")
    data_urm_val = st.session_state.get(f"{key_prefix}_data_urm")

    payload_update = _construieste_payload_masina(
        firma_id=firma_id,
        denumire=denumire,
        tip_masina=st.session_state.get(f"{key_prefix}_tip", ""),
        serie=st.session_state.get(f"{key_prefix}_serie", ""),
        tip_intretinere=st.session_state.get(f"{key_prefix}_frec", FRECVENTA_IMPLICITA),
        fara_intretinere=este_fara,
        interval_zile=interval_val,
        data_intretinere=data_urm_val,
        ultima_intretinere=ultima_val if ultima_are_valoare else None,
        include_sisteme=False,
    )

    try:
        if not hasattr(MasiniRepository, "update"):
            raise RuntimeError("MasiniRepository.update nu este implementată.")
        MasiniRepository.update(int(masina_id), payload_update)
        _invalideaza_cache_masini(firma_id)
        st.session_state["masini_feedback"] = ("success", f"✅ Modificările pentru **{denumire}** au fost salvate.")
    except Exception as exc:
        st.session_state["masini_feedback"] = ("error", f"❌ Eroare la actualizare: {exc}")


def _sterge_masina_cb(masina_id: int, firma_id: int, denumire_afisata: str):
    try:
        if not hasattr(MasiniRepository, "delete"):
            raise RuntimeError("MasiniRepository.delete nu este implementată.")
        MasiniRepository.delete(int(masina_id))
        _invalideaza_cache_masini(firma_id)

        # Curățăm selecția dacă utilajul șters era cel deschis
        if st.session_state.get(f"masina_activa_{firma_id}") == int(masina_id):
            st.session_state[f"masina_activa_{firma_id}"] = None

        st.session_state["masini_feedback"] = ("warning", f"🗑️ Mașina **{denumire_afisata}** a fost ștearsă.")
        st.session_state["masini_needs_rerun"] = True
    except Exception as exc:
        st.session_state["masini_feedback"] = ("error", f"❌ Eroare la ștergere: {exc}")


def _afiseaza_feedback():
    feedback = st.session_state.pop("masini_feedback", None)
    if not feedback:
        return
    nivel, mesaj = feedback
    if nivel == "success":
        st.success(mesaj)
    elif nivel == "warning":
        st.warning(mesaj)
    else:
        st.error(mesaj)


def _randare_formular_adaugare(firma_id: int):
    st.markdown("#### ➕ Adaugă Mașină Nouă")

    st.session_state.setdefault("nou_den", "")
    st.session_state.setdefault("nou_tip_masina", "")
    st.session_state.setdefault("nou_serie", "")
    st.session_state.setdefault("nou_tip_int", FRECVENTA_IMPLICITA)
    st.session_state.setdefault("nou_interval_zile", INTERVAL_IMPLICIT_ZILE)
    st.session_state.setdefault("nou_data_int", date.today() + timedelta(days=INTERVAL_IMPLICIT_ZILE))

    fara_intretinere_nou = st.checkbox(
        "🚫 Fără întreținere (utilajul nu necesită mentenanță periodică)",
        value=False,
        key="masini_chk_fara_intretinere_nou",
    )

    with st.form("form_adauga_masina_noua"):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Denumire Mașină / Utilaj *", key="nou_den")
            st.text_input("Producător / Model", key="nou_tip_masina")
            st.text_input("Serie Fabricație", key="nou_serie")
        with c2:
            st.selectbox(
                "Frecvență / Tip Întreținere",
                options=list(OPT_FRECVENTE),
                key="nou_tip_int",
            )
            if not fara_intretinere_nou:
                st.number_input(
                    "Durata până la următoarea întreținere (zile)",
                    min_value=0,
                    step=PAS_INTERVAL_ZILE,
                    key="nou_interval_zile",
                )
                st.date_input(
                    "Data următoarei întrețineri",
                    key="nou_data_int",
                )
            else:
                st.caption("ℹ️ Opțiunea **Fără întreținere** este activă — nu se setează dată de întreținere.")

        st.form_submit_button(
            "💾 Salvează Mașina",
            type="primary",
            on_click=_salveaza_masina_noua_cb,
            args=(firma_id,),
        )


def _randare_detalii_utilaj(m: dict, firma_id: int):
    mid = int(m["id"])
    key_prefix = f"m_{firma_id}_{mid}"
    este_fara = bool(m.get("fara_intretinere", False))
    denumire_curenta = str(m.get("denumire") or "")

    fara_int_edit = st.checkbox(
        "🚫 Fără întreținere",
        value=este_fara,
        key=f"chk_fara_int_edit_{firma_id}_{mid}",
    )

    int_curent = int(m.get("interval_intretinere_zile") or 0)
    interval_default = int_curent if int_curent > 0 else INTERVAL_IMPLICIT_ZILE
    ultima_raw = m.get("ultima_intretinere")
    ultima_are_valoare = _are_valoare_data(ultima_raw)

    st.session_state.setdefault(f"{key_prefix}_den", denumire_curenta)
    st.session_state.setdefault(f"{key_prefix}_tip", str(m.get("tip_masina") or ""))
    st.session_state.setdefault(f"{key_prefix}_serie", str(m.get("serie") or ""))

    frec_curenta = str(m.get("tip_intretinere") or FRECVENTA_IMPLICITA)
    frec_valida = frec_curenta if frec_curenta in OPT_FRECVENTE else FRECVENTA_IMPLICITA
    st.session_state.setdefault(f"{key_prefix}_frec", frec_valida)
    st.session_state.setdefault(f"{key_prefix}_interval", interval_default)
    st.session_state.setdefault(f"{key_prefix}_ultima", _parse_date_sigur(ultima_raw, date.today()))
    st.session_state.setdefault(
        f"{key_prefix}_data_urm",
        _parse_date_sigur(
            m.get("data_intretinere"),
            date.today() + timedelta(days=interval_default),
        ),
    )

    with st.form(f"form_editeaza_masina_{firma_id}_{mid}"):
        e1, e2 = st.columns(2)
        with e1:
            st.text_input("Denumire Mașină / Utilaj *", key=f"{key_prefix}_den")
            st.text_input("Producător / Model", key=f"{key_prefix}_tip")
            st.text_input("Serie Fabricație", key=f"{key_prefix}_serie")

        with e2:
            st.selectbox(
                "Frecvență / Tip Întreținere",
                options=list(OPT_FRECVENTE),
                key=f"{key_prefix}_frec",
            )
            st.number_input(
                "Durata până la următoarea întreținere (zile)",
                min_value=0,
                step=PAS_INTERVAL_ZILE,
                key=f"{key_prefix}_interval",
            )
            st.date_input(
                "Ultima întreținere",
                key=f"{key_prefix}_ultima",
            )

            if not fara_int_edit:
                st.date_input(
                    "Data următoarei întrețineri",
                    key=f"{key_prefix}_data_urm",
                )
            else:
                st.caption("ℹ️ Mașina este marcată **Fără întreținere** — data următoarei întrețineri va fi golită.")

        b_save, b_del = st.columns([2, 1])
        b_save.form_submit_button(
            "💾 Salvează Modificările",
            type="primary",
            on_click=_actualizeaza_masina_cb,
            args=(mid, firma_id, ultima_are_valoare),
        )
        b_del.form_submit_button(
            "🗑️ Șterge Mașina",
            on_click=_sterge_masina_cb,
            args=(mid, firma_id, denumire_curenta),
        )

    render_sectiune_cmms_masina(
        firma_id=firma_id,
        masina_obj=m,
    )


def _randare_lista_utilaje(firma_id: int, sel_firma: str):
    st.markdown(f"#### 📋 Utilaje înregistrate — {sel_firma}")
    masini_firma = MasiniRepository.get_by_firma(firma_id) or []
    if not masini_firma:
        st.info("Nu există utilaje înregistrate pentru această firmă.")
        return

    activ_key = f"masina_activa_{firma_id}"
    masina_activa_id = st.session_state.get(activ_key)

    for m in masini_firma:
        mid = int(m["id"])
        este_fara = bool(m.get("fara_intretinere", False))
        eticheta_int = "🚫 Fără întreținere" if este_fara else f"📅 Următoarea: {m.get('data_intretinere') or '-'}"
        este_deschis = masina_activa_id == mid

        with st.expander(f"⚙️ {m.get('denumire')} ({eticheta_int})", expanded=este_deschis):
            if st.button(
                "🔼 Închide detaliile" if este_deschis else "✏️ Editează / Vezi CMMS",
                key=f"btn_toggle_{firma_id}_{mid}",
            ):
                st.session_state[activ_key] = None if este_deschis else mid
                st.rerun()

            # Încărcăm formularul greu și secțiunea CMMS doar când utilajul este deschis
            if este_deschis:
                _randare_detalii_utilaj(m, firma_id)


def render_masini():
    st.subheader("⚙️ Gestiune Mașini / Utilaje")
    _afiseaza_feedback()

    firme_db = FirmeRepository.get_all() or []
    if not firme_db:
        st.warning("⚠️ Adaugă mai întâi cel puțin o firmă din modulul **Firme**.")
        return

    firme_map = {f["nume_firma"]: f for f in firme_db if f.get("nume_firma")}
    opt_firme = [PLACEHOLDER_FIRMA] + sorted(firme_map.keys(), key=lambda x: x.strip().lower())

    sel_firma = st.selectbox("1. Selectează Firma", options=opt_firme, key="masini_sel_firma")
    if sel_firma == PLACEHOLDER_FIRMA:
        st.info("ℹ️ Alege o firmă pentru a vedea, edita sau adăuga utilaje.")
        return

    firma_id = int(firme_map[sel_firma]["id"])

    st.markdown("---")
    _randare_formular_adaugare(firma_id)

    st.markdown("---")
    _randare_lista_utilaje(firma_id, sel_firma)

    # Singurul rerun păstrat: doar când ștergerea schimbă lista și trebuie reîmprospătată structura
    if st.session_state.pop("masini_needs_rerun", False):
        st.rerun()