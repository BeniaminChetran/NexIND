# ----------------------------------
# -------pages/firme.py-------------
# ----------------------------------

import pandas as pd
import streamlit as st

from repositories.firme_repository import FirmeRepository
from repositories.furnizori_repository import FurnizoriRepository


def _clear_firme_cache() -> None:
    fn = getattr(FirmeRepository.get_all, "clear", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def _render_sectiune_firme() -> None:
    st.markdown("#### 🏢 Nomenclator Firme (Clienți)")

    with st.form("form_adauga_firma_nomenclator", clear_on_submit=True):
        c1, c2, c3 = st.columns([2.0, 1.0, 1.0])
        with c1:
            nume_firma = st.text_input("Denumire Firmă *", placeholder="ex: SC Exemplu SRL")
        with c2:
            cui = st.text_input("CUI / CIF", placeholder="RO12345678")
        with c3:
            adaos = st.number_input("Adaos comercial (%)", min_value=0.0, max_value=500.0, value=20.0, step=1.0)

        c4, c5, c6 = st.columns([1.4, 1.4, 1.4])
        with c4:
            persoana_contact = st.text_input("Persoană contact", placeholder="Nume Prenume")
        with c5:
            telefon = st.text_input("Telefon", placeholder="07xx...")
        with c6:
            email = st.text_input("Email", placeholder="contact@firma.ro")

        adresa = st.text_input("Adresă", placeholder="Strada, Nr., Localitate, Județ")
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
                    "adaos_comercial": float(adaos),
                }
                if hasattr(FirmeRepository, "insert"):
                    FirmeRepository.insert(payload)
                elif hasattr(FirmeRepository, "upsert"):
                    FirmeRepository.upsert(payload)
                _clear_firme_cache()
                st.success(f"✅ Firma **{nume_firma.strip()}** a fost salvată.")
                st.rerun()

    firme_rows = FirmeRepository.get_all() or []
    if not firme_rows:
        st.info("Nu există firme înregistrate.")
        return

    cautare_f = st.text_input("🔎 Caută firmă", placeholder="nume, CUI, contact...", key="nomenclator_cauta_firma").strip().lower()
    if cautare_f:
        firme_rows = [
            f for f in firme_rows
            if cautare_f in str(f.get("nume_firma") or "").lower()
            or cautare_f in str(f.get("cui") or "").lower()
            or cautare_f in str(f.get("persoana_contact") or "").lower()
        ]

    df_f = pd.DataFrame([
        {
            "ID": int(f.get("id") or 0),
            "Firmă": str(f.get("nume_firma") or ""),
            "CUI": str(f.get("cui") or ""),
            "Contact": str(f.get("persoana_contact") or f.get("contact") or ""),
            "Telefon": str(f.get("telefon") or ""),
            "Email": str(f.get("email") or ""),
            "Adaos (%)": float(f.get("adaos_comercial") or 0.0),
            "Adresă": str(f.get("adresa") or ""),
        }
        for f in firme_rows
    ])
    st.dataframe(df_f, hide_index=True, use_container_width=True)


def _render_sectiune_furnizori() -> None:
    st.markdown("#### 🏭 Nomenclator Furnizori")

    with st.expander("📥 Import Furnizori din Fișier (.csv, .txt, .json)", expanded=False):
        st.caption("Format acceptat: coloane `nume_furnizor,cui,persoana_contact,telefon,email,site_web,termen_plata_zile,moneda_preferata,observatii` sau o denumire pe rând.")
        up_furn = st.file_uploader("Alege fișier furnizori", type=["csv", "txt", "json"], key="up_nomenclator_furnizori")
        if up_furn is not None and st.button("⬆️ Importă Furnizorii", type="primary", key="btn_import_furnizori"):
            nr_imp, errs = FurnizoriRepository.import_from_upload(up_furn)
            if nr_imp:
                st.success(f"✅ Importați/actualizați **{nr_imp}** furnizori.")
            if errs:
                st.warning("⚠️ Unele rânduri nu au putut fi importate:\n" + "\n".join(errs[:10]))
            if nr_imp:
                st.rerun()

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
                FurnizoriRepository.upsert({
                    "nume_furnizor": nume_furn.strip(),
                    "cui": cui_furn.strip(),
                    "persoana_contact": contact_furn.strip(),
                    "telefon": tel_furn.strip(),
                    "email": email_furn.strip(),
                    "site_web": site_furn.strip(),
                    "termen_plata_zile": int(termen_plata),
                    "moneda_preferata": moneda_pref,
                    "observatii": obs_furn.strip(),
                    "activ": bool(activ_furn),
                })
                st.success(f"✅ Furnizorul **{nume_furn.strip()}** a fost salvat.")
                st.rerun()

    furnizori_rows = FurnizoriRepository.get_all(doar_activi=False)
    if not furnizori_rows:
        st.info("Nu există furnizori în tabela `furnizori`. Adaugă primul furnizor mai sus sau importă un fișier.")
        return

    fc1, fc2 = st.columns([3.0, 1.2], vertical_alignment="bottom")
    with fc1:
        cautare_fn = st.text_input(
            "🔎 Caută furnizor",
            placeholder="denumire, email, contact, observații...",
            key="nomenclator_cauta_furnizor",
        ).strip().lower()
    with fc2:
        doar_act_fn = st.checkbox("Doar activi", value=False, key="nomenclator_doar_activi_furn")

    furn_filtrati = [
        fn for fn in furnizori_rows
        if (not doar_act_fn or bool(fn.get("activ", True)))
        and (
            not cautare_fn
            or cautare_fn in str(fn.get("nume_furnizor") or "").lower()
            or cautare_fn in str(fn.get("email") or "").lower()
            or cautare_fn in str(fn.get("persoana_contact") or "").lower()
            or cautare_fn in str(fn.get("observatii") or "").lower()
        )
    ]

    df_fn = pd.DataFrame([
        {
            "ID": int(fn["id"]),
            "Activ": bool(fn.get("activ", True)),
            "Furnizor": str(fn.get("nume_furnizor") or ""),
            "CUI": str(fn.get("cui") or ""),
            "Contact": str(fn.get("persoana_contact") or ""),
            "Telefon": str(fn.get("telefon") or ""),
            "Email": str(fn.get("email") or ""),
            "Monedă": str(fn.get("moneda_preferata") or "EUR"),
            "Plată (zile)": int(fn.get("termen_plata_zile") or 0),
            "Site": str(fn.get("site_web") or ""),
            "Observații": str(fn.get("observatii") or ""),
        }
        for fn in furn_filtrati
    ])
    st.dataframe(df_fn, hide_index=True, use_container_width=True)

    if furn_filtrati:
        mapa_edit_fn = {
            f"#{fn['id']} — {fn['nume_furnizor']}": fn
            for fn in furn_filtrati
        }
        with st.expander("✏️ Modifică sau Șterge un Furnizor", expanded=False):
            sel_fn_lbl = st.selectbox("Selectează furnizorul", options=list(mapa_edit_fn.keys()), key="sel_edit_furnizor")
            fn_sel = mapa_edit_fn[sel_fn_lbl]
            fn_id = int(fn_sel["id"])

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
                        value=int(fn_sel.get("termen_plata_zile") or 0),
                        step=1,
                    )
                with e4:
                    mon_opts = ["EUR", "RON", "USD"]
                    cur_mon = str(fn_sel.get("moneda_preferata") or "EUR").upper()
                    ed_mon = st.selectbox("Monedă", options=mon_opts, index=mon_opts.index(cur_mon) if cur_mon in mon_opts else 0)

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
                            "termen_plata_zile": int(ed_termen),
                            "moneda_preferata": ed_mon,
                            "observatii": ed_obs,
                            "activ": bool(ed_activ),
                        })
                        st.success("✅ Furnizorul a fost actualizat.")
                        st.rerun()
                    except ValueError as ve:
                        st.error(f"⚠️ {ve}")

                if b2.form_submit_button("🗑️ Șterge Furnizor"):
                    FurnizoriRepository.delete(fn_id)
                    st.warning("🗑️ Furnizorul a fost șters.")
                    st.rerun()


def render_firme():
    st.subheader("📇 Nomenclator Firme & Furnizori")
    tab_firme, tab_furnizori = st.tabs(["🏢 Firme (Clienți)", "🏭 Furnizori"])
    with tab_firme:
        _render_sectiune_firme()
    with tab_furnizori:
        _render_sectiune_furnizori()