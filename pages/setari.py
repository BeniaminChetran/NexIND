import logging
import streamlit as st
from repositories.setari_repository import SetariRepository
from repositories.tarife_repository import TarifeRepository
from repositories.fraze_repository import FrazeRepository

logger = logging.getLogger("NexIndCMMS.Pages.Setari")

DEFAULT_COTA_TVA = 21.0
DEFAULT_VALABILITATE = "15 zile"
DEFAULT_TERMENI_PLATA = "5 zile de la emiterea facturii"
DEFAULT_INTOCMIT_DE = "Echipa Nexus Industrial"
DEFAULT_TEHNICIAN = "Tehnician Nexus"
DEFAULT_ADAOS_IMPLICIT = 35.0
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


def _get_setari_safe() -> dict:
    try:
        rez = SetariRepository.get_setari()
        return rez if isinstance(rez, dict) else {}
    except Exception as exc:
        logger.warning(f"Nu s-au putut încărca setările curente: {exc}")
        return {}


def _val_text_implicit(setari: dict, cheie: str, fallback: str) -> str:
    val = str(setari.get(cheie) or "").strip()
    return val if val else fallback


def _val_float_implicit(setari: dict, cheie: str, fallback: float) -> float:
    raw = setari.get(cheie)
    if raw is None or raw == "":
        return float(fallback)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(fallback)


def render_setari():
    st.subheader("⚙️ Setări Generale Firmă, TVA & Configurări Documente")

    setari_curente = _get_setari_safe()
    parola_sistem = str(setari_curente.get("pass") or "").strip()
    acces_deblocat = bool(st.session_state.get("is_unlocked", False)) or (not parola_sistem)

    tab_firma, tab_tarife, tab_fraze, tab_securitate = st.tabs([
        "🏢 Date Firmă, TVA & Valori Implicite",
        "💰 Tarife Standard",
        "💬 Fraze Predefinite Oferte",
        "🔐 Securitate & Email",
    ])

    with tab_firma:
        with st.form("form_setari_firma"):
            st.markdown("##### Identificare Firmă Prestatoare & Fiscalitate")
            col1, col2 = st.columns(2)
            with col1:
                nume_firma_mea = st.text_input("Denumire Firmă", value=str(setari_curente.get("nume_firma_mea") or ""))
                cui_mea = st.text_input("CUI / CIF", value=str(setari_curente.get("cui_mea") or ""))
                reg_com_mea = st.text_input("Nr. Reg. Comerțului", value=str(setari_curente.get("reg_com_mea") or ""))
                cota_tva = st.number_input(
                    "Cotă TVA aplicabilă (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=_val_float_implicit(setari_curente, "cota_tva", DEFAULT_COTA_TVA),
                    step=1.0,
                    format="%.2f",
                )
            with col2:
                adresa_mea = st.text_input("Adresă Sediu Social", value=str(setari_curente.get("adresa_mea") or ""))
                banca_mea = st.text_input("Bancă", value=str(setari_curente.get("banca_mea") or ""))
                iban_mea = st.text_input("Cont IBAN", value=str(setari_curente.get("iban_mea") or ""))
                swep_mea = st.text_input("Cod SWIFT / BIC", value=str(setari_curente.get("swep_mea") or ""))

            st.markdown("---")
            st.markdown("##### Date de Contact Firmă (2 Telefoane & 2 Adrese de Email)")
            cc1, cc2 = st.columns(2)
            with cc1:
                telefon_1 = st.text_input("Telefon 1", value=str(setari_curente.get("telefon_1") or ""))
                telefon_2 = st.text_input("Telefon 2", value=str(setari_curente.get("telefon_2") or ""))
            with cc2:
                email_1 = st.text_input("Email 1", value=str(setari_curente.get("email_1") or ""))
                email_2 = st.text_input("Email 2", value=str(setari_curente.get("email_2") or ""))

            st.markdown("---")
            st.markdown("##### Valori Implicite pentru Oferte de Preț & Rapoarte Tehnice")
            co1, co2 = st.columns(2)
            with co1:
                valabilitate_implicita = st.text_input(
                    "Termen de valabilitate ofertă (implicit)",
                    value=_val_text_implicit(setari_curente, "valabilitate_implicita", DEFAULT_VALABILITATE),
                )
                intocmit_de_implicit = st.text_input(
                    "Întocmit de — Oferte de preț (implicit)",
                    value=_val_text_implicit(setari_curente, "intocmit_de_implicit", DEFAULT_INTOCMIT_DE),
                )
            with co2:
                termeni_plata_impliciti = st.text_input(
                    "Termeni de plată ofertă (impliciți)",
                    value=_val_text_implicit(setari_curente, "termeni_plata_impliciti", DEFAULT_TERMENI_PLATA),
                )
                tehnician_implicit = st.text_input(
                    "Tehnician implicit (Rapoarte Intervenție & Electronice)",
                    value=_val_text_implicit(setari_curente, "tehnician_implicit", DEFAULT_TEHNICIAN),
                )

            clauze_subsol_implicite = st.text_area(
                "Mențiuni / Clauze implicite subsol ofertă (folosește {MONEDA} pentru EUR/RON automat)",
                value=str(setari_curente.get("clauze_subsol_implicite") or ""),
                height=120,
            )

            if st.form_submit_button("💾 Salvează Setările", type="primary"):
                date_actualizate = {
                    **setari_curente,
                    "nume_firma_mea": nume_firma_mea.strip(),
                    "cui_mea": cui_mea.strip(),
                    "reg_com_mea": reg_com_mea.strip(),
                    "adresa_mea": adresa_mea.strip(),
                    "banca_mea": banca_mea.strip(),
                    "iban_mea": iban_mea.strip(),
                    "swep_mea": swep_mea.strip(),
                    "telefon_1": telefon_1.strip(),
                    "telefon_2": telefon_2.strip(),
                    "email_1": email_1.strip(),
                    "email_2": email_2.strip(),
                    "cota_tva": float(cota_tva),
                    "valabilitate_implicita": valabilitate_implicita.strip() or DEFAULT_VALABILITATE,
                    "termeni_plata_impliciti": termeni_plata_impliciti.strip() or DEFAULT_TERMENI_PLATA,
                    "intocmit_de_implicit": intocmit_de_implicit.strip() or DEFAULT_INTOCMIT_DE,
                    "tehnician_implicit": tehnician_implicit.strip() or DEFAULT_TEHNICIAN,
                    "clauze_subsol_implicite": clauze_subsol_implicite.strip(),
                }
                SetariRepository.save_setari(date_actualizate)
                st.success("✅ Setările au fost salvate!")
                st.rerun()

        st.markdown("---")
        st.markdown("##### 🔒 Adaos Comercial Implicit Piese (Client Standard)")
        if not acces_deblocat:
            st.info("🔐 Adaosul comercial implicit este protejat cu parolă. Mergi la **SistemAdmin → 🔑 Deblocare** pentru a-l modifica.")
        else:
            val_curenta_adaos = _val_float_implicit(setari_curente, "adaos_comercial_implicit", DEFAULT_ADAOS_IMPLICIT)
            ca1, ca2 = st.columns([3.0, 1.3], vertical_alignment="bottom")
            with ca1:
                nou_adaos_implicit = st.number_input(
                    "Adaos comercial implicit piese — Client Standard (%)",
                    min_value=0.0,
                    max_value=500.0,
                    value=val_curenta_adaos,
                    step=1.0,
                    format="%.2f",
                    key="num_adaos_comercial_implicit_db",
                )
            with ca2:
                if st.button("💾 Salvează Adaos", key="btn_save_adaos_imp", type="primary", use_container_width=True):
                    SetariRepository.save_setari({**setari_curente, "adaos_comercial_implicit": float(nou_adaos_implicit)})
                    st.success(f"✅ Adaosul comercial implicit a fost salvat ({nou_adaos_implicit:.2f}%)!")
                    st.rerun()

    with tab_tarife:
        st.markdown("##### Configurare Tarife & Activități Implicite (EUR sau RON)")
        with st.form("form_add_tarif"):
            ct1, ct2, ct3, ct4 = st.columns([2.8, 1.3, 1.3, 1.3], vertical_alignment="bottom")
            with ct1:
                desc_tarif = st.text_input("Descriere serviciu / activitate")
            with ct2:
                pret_tarif = st.number_input("Preț unitar", min_value=0.0, step=5.0, format="%.2f")
            with ct3:
                moneda_um = st.selectbox(
                    "Monedă / UM",
                    options=["EUR/ora", "EUR/km", "EUR/buc", "EUR/set", "RON/ora", "RON/km", "RON/buc", "RON/set"],
                )
            with ct4:
                nivel_nou_tarif = st.selectbox("Nivel Grilă", options=["Nivel A", "Nivel B", "Nivel C"])

            if st.form_submit_button("➕ Adaugă Tarif", type="primary"):
                if desc_tarif.strip():
                    TarifeRepository.insert({
                        "descriere": desc_tarif.strip(),
                        "pret": float(pret_tarif),
                        "moneda_um": moneda_um,
                        "nivel_grila": nivel_nou_tarif,
                    })
                    st.success(f"✅ Tarif adăugat pe {nivel_nou_tarif}!")
                    st.rerun()
                else:
                    st.warning("Introduceți descrierea tarifului.")

        tarife_list = TarifeRepository.get_all()
        if tarife_list:
            for t in tarife_list:
                tid = t["id"]
                niv_t = str(t.get("nivel_grila") or "Nivel A").strip()
                c_t1, c_t_niv, c_t2, c_t3, c_t4, c_t5 = st.columns([3.0, 1.0, 1.4, 1.2, 0.8, 0.8], vertical_alignment="center")
                c_t1.write(f"**{t['descriere']}**")
                c_t_niv.write(f"**{niv_t}**")
                nou_pret_t = c_t2.number_input(
                    "Preț",
                    value=float(t["pret"]),
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"edit_pret_tarif_{tid}",
                    label_visibility="collapsed",
                )
                c_t3.write(f"**{t['moneda_um']}**")
                if c_t4.button("💾", key=f"save_tarif_{tid}"):
                    TarifeRepository.update_pret(tid, nou_pret_t)
                    st.rerun()
                if c_t5.button("🗑️", key=f"del_tarif_{tid}"):
                    TarifeRepository.delete(tid)
                    st.rerun()
        else:
            st.info("Nu există tarife definite.")

    with tab_fraze:
        st.markdown("##### Clauze Standard Disponibile în Oferte")
        with st.form("form_add_fraza"):
            titlu_fraza = st.text_input("Titlu scurt")
            continut_fraza = st.text_area("Conținut complet clauză", height=80)
            if st.form_submit_button("➕ Salvează Clauză"):
                if titlu_fraza.strip() and continut_fraza.strip():
                    FrazeRepository.insert(titlu_fraza, continut_fraza)
                    st.success("Clauza a fost adăugată!")
                    st.rerun()
                else:
                    st.warning("Completați atât titlul, cât și conținutul clauzei.")

        fraze_list = FrazeRepository.get_all()
        if fraze_list:
            for fr in fraze_list:
                cf1, cf2 = st.columns([6, 1], vertical_alignment="center")
                cf1.markdown(f"**{fr.get('titlu', 'Clauză')}**: {fr.get('continut', '')}")
                if cf2.button("🗑️", key=f"del_fr_db_{fr['id']}"):
                    FrazeRepository.delete(fr["id"])
                    st.rerun()
        else:
            st.info("Nu există fraze salvate în baza de date.")

    with tab_securitate:
        with st.form("form_setari_email"):
            st.markdown("##### Configurare Server Email (SMTP) & Integrări")
            ce1, ce2 = st.columns(2)
            with ce1:
                smtp_server = st.text_input("Server SMTP", value=_val_text_implicit(setari_curente, "smtp_server", DEFAULT_SMTP_SERVER))
                smtp_port = st.number_input(
                    "Port SMTP",
                    value=int(_val_float_implicit(setari_curente, "smtp_port", DEFAULT_SMTP_PORT)),
                    step=1,
                )
                email_tehnician = st.text_input("Email Tehnician / Notificări", value=str(setari_curente.get("email_tehnician") or ""))
            with ce2:
                smtp_user = st.text_input("Utilizator SMTP (Email)", value=str(setari_curente.get("smtp_user") or ""))
                smtp_pass = st.text_input("Parolă SMTP / App Password", value=str(setari_curente.get("smtp_pass") or ""), type="password")
                google_sheet_url = st.text_input("URL Google Sheet Sync", value=str(setari_curente.get("google_sheet_url") or ""))

            if st.form_submit_button("💾 Salvează Configurări Email", type="primary"):
                SetariRepository.save_setari({
                    **setari_curente,
                    "smtp_server": smtp_server.strip() or DEFAULT_SMTP_SERVER,
                    "smtp_port": int(smtp_port),
                    "smtp_user": smtp_user.strip(),
                    "smtp_pass": smtp_pass,
                    "google_sheet_url": google_sheet_url.strip(),
                    "email_tehnician": email_tehnician.strip(),
                })
                st.success("✅ Configurările SMTP au fost salvate!")
                st.rerun()

        st.markdown("---")
        with st.form("form_schimba_parola"):
            st.markdown("##### Schimbare Parolă Deblocare Prețuri")
            noua_parola = st.text_input("Parolă nouă", type="password")
            if st.form_submit_button("🔑 Actualizează Parola"):
                if noua_parola.strip():
                    SetariRepository.update_pass(noua_parola.strip())
                    st.success("✅ Parola a fost actualizată!")
                else:
                    st.warning("Introduceți o parolă validă.")