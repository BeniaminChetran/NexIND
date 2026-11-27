# ----------------------------------
# -------pages/firme.py-------------
# ----------------------------------

from typing import Any

import pandas as pd
import streamlit as st

from repositories.firme_repository import FirmeRepository
from repositories.furnizori_repository import FurnizoriRepository

_MSG_KEY = "nomenclator_status_msg"


def _seteaza_mesaj(tip: str, text: str) -> None:
    st.session_state[_MSG_KEY] = (tip, text)


def _afiseaza_si_consuma_mesaj() -> None:
    payload = st.session_state.pop(_MSG_KEY, None)
    if not payload:
        return
    tip, text = payload
    if tip == "success":
        st.success(text)
    elif tip == "warning":
        st.warning(text)
    elif tip == "error":
        st.error(text)
    else:
        st.info(text)


def _val_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _val_int(val: Any, default: int = 0) -> int:
    try:
        if val is None or val == "":
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


@st.cache_data(ttl=120)
def _construieste_df_firme(rows_tuple: tuple[tuple[Any, ...], ...]) -> pd.DataFrame:
    records = [
        {
            "ID": r[0],
            "Firmă": r[1],
            "CUI": r[2],
            "Contact": r[3],
            "Telefon": r[4],
            "Email": r[5],
            "Adaos (%)": r[6],
            "Distanță (km)": r[7],
            "Adresă": r[8],
        }
        for r in rows_tuple
    ]
    return pd.DataFrame(records)


def _filtreaza_firme(rows: list[dict[str, Any]], cautare: str) -> list[dict[str, Any]]:
    if not cautare:
        return rows
    q = cautare.strip().lower()
    if not q:
        return rows
    rezultat: list[dict[str, Any]] = []
    for f in rows:
        contact = f.get("persoana_contact") or f.get("nume_persoana") or f.get("contact") or ""
        if (
            q in str(f.get("nume_firma") or "").lower()
            or q in str(f.get("cui") or "").lower()
            or q in str(contact).lower()
            or q in str(f.get("adresa") or "").lower()
        ):
            rezultat.append(f)
    return rezultat


def _render_sectiune_firme() -> None:
    st.markdown("#### 🏢 Nomenclator Firme (Clienți)")

    with st.form("form_adauga_firma_nomenclator", clear_on_submit=True):
        c1, c2, c3, c_dist = st.columns([2.0, 1.0, 1.0, 1.0])
        with c1:
            nume_firma = st.text_input("Denumire Firmă *", placeholder="ex: SC Exemplu SRL")
        with c2:
            cui = st.text_input("CUI / CIF", placeholder="RO12345678")
        with c3:
            adaos = st.number_input(
                "Adaos comercial (%)",
                min_value=0.0,
                max_value=500.0,
                value=20.0,
                step=1.0,
            )
        with c_dist:
            distanta_km = st.number_input(
                "Distanță sediu–client (km)",
                min_value=0.0,
                max_value=10000.0,
                value=0.0,
                step=1.0,
            )

        c4, c5, c6 = st.columns([1.4, 1.4, 1.4])
        with c4:
            persoana_contact = st.text_input("Persoană contact", placeholder="Nume Prenume")
        with c5:
            telefon = st.text_input("Telefon", placeholder="07xx...")
        with c6:
            email = st.text_input("Email", placeholder="contact@firma.ro")

        c7, c8 = st.columns([2.5, 1.5])
        with c7:
            adresa = st.text_input("Adresă", placeholder="Strada, Nr., Localitate, Județ")
        with c8:
            reg_com = st.text_input("Nr. Reg. Com.", placeholder="ex: J12/123/2020")

        if st.form_submit_button("💾 Salvează Firmă", type="primary"):
            if not nume_firma.strip():
                st.error("⚠️ Completează denumirea firmei.")
            else:
                payload = {
                    "nume_firma": nume_firma.strip(),
                    "cui": cui.strip(),
                    "reg_com": reg_com.strip(),
                    "adresa": adresa.strip(),
                    "persoana_contact": persoana_contact.strip(),
                    "telefon": telefon.strip(),
                    "email": email.strip(),
                    "adaos_comercial": _val_float(adaos, 20.0),
                    "distanta_km": _val_float(distanta_km, 0.0),
                }
                try:
                    if hasattr(FirmeRepository, "insert"):
                        FirmeRepository.insert(payload)
                    elif hasattr(FirmeRepository, "upsert"):
                        FirmeRepository.upsert(payload)
                    _seteaza_mesaj("success", f"✅ Firma **{nume_firma.strip()}** a fost salvată.")
                except (ValueError, RuntimeError) as exc:
                    st.error(f"⚠️ {exc}")

    try:
        toate_firmele = FirmeRepository.get_all() or []
    except Exception as exc:
        st.error(f"⚠️ Nu s-a putut încărca lista de firme: {exc}")
        return

    if not toate_firmele:
        st.info("Nu există firme înregistrate.")
        return

    cautare_f = st.text_input(
        "🔎 Caută firmă",
        placeholder="nume, CUI, contact, adresă...",
        key="nomenclator_cauta_firma",
    )
    firme_filtrate = _filtreaza_firme(toate_firmele, cautare_f)

    if not firme_filtrate:
        st.info("Nu s-au găsit firme pentru criteriul de căutare selectat.")
        return

    rows_tuple = tuple(
        (
            _val_int(f.get("id")),
            str(f.get("nume_firma") or ""),
            str(f.get("cui") or ""),
            str(f.get("persoana_contact") or f.get("nume_persoana") or f.get("contact") or ""),
            str(f.get("telefon") or ""),
            str(f.get("email") or ""),
            _val_float(f.get("adaos_comercial"), 0.0),
            _val_float(f.get("distanta_km"), 0.0),
            str(f.get("adresa") or ""),
        )
        for f in firme_filtrate
    )
    df_f = _construieste_df_firme(rows_tuple)
    st.dataframe(df_f, hide_index=True, use_container_width=True)


@st.cache_data(ttl=120)
def _construieste_df_furnizori(rows_tuple: tuple[tuple[Any, ...], ...]) -> pd.DataFrame:
    records = [
        {
            "ID": r[0],
            "Activ": r[1],
            "Furnizor": r[2],
            "CUI": r[3],
            "Contact": r[4],
            "Telefon": r[5],
            "Email": r[6],
            "Monedă": r[7],
            "Plată (zile)": r[8],
            "Site": r[9],
            "Observații": r[10],
        }
        for r in rows_tuple
    ]
    return pd.DataFrame(records)


def _filtreaza_furnizori(
    rows: list[dict[str, Any]],
    cautare: str,
    doar_activi: bool,
) -> list[dict[str, Any]]:
    q = cautare.strip().lower() if cautare else ""
    rezultat: list[dict[str, Any]] = []
    for fn in rows:
        activ = bool(fn.get("activ", True))
        if doar_activi and not activ:
            continue
        if q and not (
            q in str(fn.get("nume_furnizor") or "").lower()
            or q in str(fn.get("email") or "").lower()
            or q in str(fn.get("persoana_contact") or "").lower()
            or q in str(fn.get("observatii") or "").lower()
        ):
            continue
        rezultat.append(fn)
    return rezultat


def _render_sectiune_furnizori() -> None:
    st.markdown("#### 🏭 Nomenclator Furnizori")

    with st.expander("📥 Import Furnizori din Fișier (.csv, .txt, .json)", expanded=False):
        st.caption(
            "Format acceptat: coloane `nume_furnizor,cui,persoana_contact,telefon,email,site_web,"
            "termen_plata_zile,moneda_preferata,observatii` sau o denumire pe rând."
        )
        up_furn = st.file_uploader(
            "Alege fișier furnizori",
            type=["csv", "txt", "json"],
            key="up_nomenclator_furnizori",
        )
        if up_furn is not None and st.button("⬆️ Importă Furnizorii", type="primary", key="btn_import_furnizori"):
            try:
                nr_imp, errs = FurnizoriRepository.import_from_upload(up_furn)
                if nr_imp:
                    _seteaza_mesaj("success", f"✅ Importați/actualizați **{nr_imp}** furnizori.")
                if errs:
                    st.warning("⚠️ Unele rânduri nu au putut fi importate:\n" + "\n".join(errs[:10]))
                if nr_imp and not errs:
                    st.rerun()
            except Exception as exc:
                st.error(f"⚠️ Eroare la importul furnizorilor: {exc}")

    with st.form("form_adauga_furnizor_nomenclator", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns([2.0, 1.0, 1.0, 0.8])
        with f1:
            nume_furn = st.text_input("Denumire Furnizor *", placeholder="ex: TME / Farnell / Bosch Rexroth")
        with f2:
            cui_furn = st.text_input("CUI / VAT", placeholder="ex: RO... / PL...")
        with f3:
            termen_plata = st.number_input("Termen plată (zile)", min_value=0, max_value=365, value=15, step=1)
        with f4:
            moneda_pref = st.selectbox("Monedă", options=["EUR", "RON", "USD"], index=0)

        f5, f6, f7 = st.columns([1.4, 1.4, 1.4])
        with f5:
            contact_furn = st.text_input("Persoană contact", placeholder="Nume / Departament vânzări")
        with f6:
            tel_furn = st.text_input("Telefon", placeholder="+40...")
        with f7:
            email_furn = st.text_input("Email ofertare", placeholder="sales@furnizor.ro")

        f8, f9 = st.columns([1.5, 2.5])
        with f8:
            site_furn = st.text_input("Site / Portal", placeholder="https://...")
        with f9:
            obs_furn = st.text_input("Observații / Condiții livrare", placeholder="ex: transport gratuit peste 150 EUR")

        activ_furn = st.checkbox("Furnizor activ", value=True)

        if st.form_submit_button("💾 Salvează Furnizor", type="primary"):
            if not nume_furn.strip():
                st.error("⚠️ Completează denumirea furnizorului.")
            else:
                try:
                    FurnizoriRepository.upsert({
                        "nume_furnizor": nume_furn.strip(),
                        "cui": cui_furn.strip(),
                        "persoana_contact": contact_furn.strip(),
                        "telefon": tel_furn.strip(),
                        "email": email_furn.strip(),
                        "site_web": site_furn.strip(),
                        "termen_plata_zile": _val_int(termen_plata, 15),
                        "moneda_preferata": moneda_pref,
                        "observatii": obs_furn.strip(),
                        "activ": bool(activ_furn),
                    })
                    _seteaza_mesaj("success", f"✅ Furnizorul **{nume_furn.strip()}** a fost salvat.")
                except Exception as exc:
                    st.error(f"⚠️ Nu s-a putut salva furnizorul: {exc}")

    try:
        furnizori_rows = FurnizoriRepository.get_all(doar_activi=False) or []
    except Exception as exc:
        st.error(f"⚠️ Nu s-a putut încărca lista de furnizori: {exc}")
        return

    if not furnizori_rows:
        st.info("Nu există furnizori în tabela `furnizori`. Adaugă primul furnizor mai sus sau importă un fișier.")
        return

    fc1, fc2 = st.columns([3.0, 1.2], vertical_alignment="bottom")
    with fc1:
        cautare_fn = st.text_input(
            "🔎 Caută furnizor",
            placeholder="denumire, email, contact, observații...",
            key="nomenclator_cauta_furnizor",
        )
    with fc2:
        doar_act_fn = st.checkbox("Doar activi", value=False, key="nomenclator_doar_activi_furn")

    furn_filtrati = _filtreaza_furnizori(furnizori_rows, cautare_fn, doar_act_fn)

    if furn_filtrati:
        rows_fn_tuple = tuple(
            (
                _val_int(fn.get("id")),
                bool(fn.get("activ", True)),
                str(fn.get("nume_furnizor") or ""),
                str(fn.get("cui") or ""),
                str(fn.get("persoana_contact") or ""),
                str(fn.get("telefon") or ""),
                str(fn.get("email") or ""),
                str(fn.get("moneda_preferata") or "EUR"),
                _val_int(fn.get("termen_plata_zile"), 0),
                str(fn.get("site_web") or ""),
                str(fn.get("observatii") or ""),
            )
            for fn in furn_filtrati
        )
        df_fn = _construieste_df_furnizori(rows_fn_tuple)
        st.dataframe(df_fn, hide_index=True, use_container_width=True)

        mapa_edit_fn = {
            f"#{_val_int(fn.get('id'))} — {fn.get('nume_furnizor')}": fn
            for fn in furn_filtrati
        }
        with st.expander("✏️ Modifică sau Șterge un Furnizor", expanded=False):
            sel_fn_lbl = st.selectbox(
                "Selectează furnizorul",
                options=list(mapa_edit_fn.keys()),
                key="sel_edit_furnizor",
            )
            fn_sel = mapa_edit_fn[sel_fn_lbl]
            fn_id = _val_int(fn_sel.get("id"))

            with st.form(f"form_edit_furnizor_{fn_id}"):
                e1, e2, e3, e4 = st.columns([2.0, 1.0, 1.0, 0.8])
                with e1:
                    ed_nume = st.text_input("Denumire Furnizor *", value=str(fn_sel.get("nume_furnizor") or ""))
                with e2:
                    ed_cui = st.text_input("CUI / VAT", value=str(fn_sel.get("cui") or ""))
                with e3:
                    ed_termen = st.number_input(
                        "Termen plată (zile)",
                        min_value=0,
                        max_value=365,
                        value=_val_int(fn_sel.get("termen_plata_zile"), 0),
                        step=1,
                    )
                with e4:
                    mon_opts = ["EUR", "RON", "USD"]
                    cur_mon = str(fn_sel.get("moneda_preferata") or "EUR").upper()
                    ed_mon = st.selectbox(
                        "Monedă",
                        options=mon_opts,
                        index=mon_opts.index(cur_mon) if cur_mon in mon_opts else 0,
                    )

                e5, e6, e7 = st.columns([1.4, 1.4, 1.4])
                with e5:
                    ed_contact = st.text_input("Persoană contact", value=str(fn_sel.get("persoana_contact") or ""))
                with e6:
                    ed_tel = st.text_input("Telefon", value=str(fn_sel.get("telefon") or ""))
                with e7:
                    ed_email = st.text_input("Email ofertare", value=str(fn_sel.get("email") or ""))

                e8, e9 = st.columns([1.5, 2.5])
                with e8:
                    ed_site = st.text_input("Site / Portal", value=str(fn_sel.get("site_web") or ""))
                with e9:
                    ed_obs = st.text_input("Observații", value=str(fn_sel.get("observatii") or ""))

                ed_activ = st.checkbox("Furnizor activ", value=bool(fn_sel.get("activ", True)))

                b1, b2 = st.columns([2, 1])
                if b1.form_submit_button("💾 Salvează Modificările", type="primary"):
                    try:
                        FurnizoriRepository.update(fn_id, {
                            "nume_furnizor": ed_nume,
                            "cui": ed_cui,
                            "persoana_contact": ed_contact,
                            "telefon": ed_tel,
                            "email": ed_email,
                            "site_web": ed_site,
                            "termen_plata_zile": _val_int(ed_termen, 0),
                            "moneda_preferata": ed_mon,
                            "observatii": ed_obs,
                            "activ": bool(ed_activ),
                        })
                        _seteaza_mesaj("success", "✅ Furnizorul a fost actualizat.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"⚠️ {exc}")

                if b2.form_submit_button("🗑️ Șterge Furnizor"):
                    try:
                        FurnizoriRepository.delete(fn_id)
                        _seteaza_mesaj("warning", "🗑️ Furnizorul a fost șters.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"⚠️ Nu s-a putut șterge furnizorul: {exc}")
    else:
        st.info("Nu s-au găsit furnizori pentru filtrele selectate.")


def render_firme() -> None:
    st.subheader("📇 Nomenclator Firme & Furnizori")
    _afiseaza_si_consuma_mesaj()
    tab_firme, tab_furnizori = st.tabs(["🏢 Firme (Clienți)", "🏭 Furnizori"])
    with tab_firme:
        _render_sectiune_firme()
    with tab_furnizori:
        _render_sectiune_furnizori()