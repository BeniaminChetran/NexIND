#----------------------------------
#-------pages/setari.py------------
#----------------------------------

import streamlit as st
from repositories.setari_repository import SetariRepository
from repositories.tarife_repository import TarifeRepository
from repositories.fraze_repository import FrazeRepository
from config import db_cursor


def _ensure_contact_cols():
    """Asigură existența coloanelor telefon_1, telefon_2, email_1, email_2 în tabela setari."""
    try:
        with db_cursor() as c:
            c.execute("""
                ALTER TABLE setari
                ADD COLUMN IF NOT EXISTS telefon_1 VARCHAR(50) DEFAULT '',
                ADD COLUMN IF NOT EXISTS telefon_2 VARCHAR(50) DEFAULT '',
                ADD COLUMN IF NOT EXISTS email_1 VARCHAR(150) DEFAULT '',
                ADD COLUMN IF NOT EXISTS email_2 VARCHAR(150) DEFAULT ''
            """)
    except Exception:
        pass

def _get_tarife_safe():
    if hasattr(TarifeRepository, "get_all"):
        return TarifeRepository.get_all()
    with db_cursor() as c:
        c.execute("SELECT * FROM tarife_implicite ORDER BY id ASC")
        return c.fetchall()


def _insert_tarif_safe(descriere: str, pret: float, moneda_um: str, nivel_grila: str = "Nivel A"):
    if hasattr(TarifeRepository, "insert"):
        return TarifeRepository.insert({
            "descriere": descriere,
            "pret": float(pret),
            "moneda_um": moneda_um,
            "nivel_grila": nivel_grila
        })
    with db_cursor() as c:
        c.execute(
            "INSERT INTO tarife_implicite (descriere, pret, moneda_um, nivel_grila) VALUES (%s, %s, %s, %s)",
            (descriere, float(pret), moneda_um, nivel_grila)
        )


def _update_pret_tarif_safe(tarif_id: int, nou_pret: float):
    if hasattr(TarifeRepository, "update_pret"):
        return TarifeRepository.update_pret(tarif_id, float(nou_pret))
    with db_cursor() as c:
        c.execute("UPDATE tarife_implicite SET pret = %s WHERE id = %s", (float(nou_pret), tarif_id))


def _delete_tarif_safe(tarif_id: int):
    if hasattr(TarifeRepository, "delete"):
        return TarifeRepository.delete(tarif_id)
    with db_cursor() as c:
        c.execute("DELETE FROM tarife_implicite WHERE id = %s", (tarif_id,))


def _trece_tarife_la_nivel_safe(nivel_tinta: str, sursa_nivel: str | None = None) -> int:
    if hasattr(TarifeRepository, "trece_la_nivel"):
        return TarifeRepository.trece_la_nivel(nivel_tinta, sursa_nivel=sursa_nivel)
    return 0


def _get_fraze_safe():
    if hasattr(FrazeRepository, "get_all"):
        return FrazeRepository.get_all()
    with db_cursor() as c:
        c.execute("SELECT * FROM fraze ORDER BY id ASC")
        return c.fetchall()


def _insert_fraza_safe(titlu: str, continut: str):
    if hasattr(FrazeRepository, "insert"):
        try:
            return FrazeRepository.insert(titlu, continut)
        except TypeError:
            return FrazeRepository.insert(continut)
    with db_cursor() as c:
        c.execute(
            "INSERT INTO fraze (titlu, continut) VALUES (%s, %s)",
            (titlu, continut)
        )


def _delete_fraza_safe(fraza_id: int):
    if hasattr(FrazeRepository, "delete"):
        return FrazeRepository.delete(fraza_id)
    with db_cursor() as c:
        c.execute("DELETE FROM fraze WHERE id = %s", (fraza_id,))

def _get_setari_safe():
    """Încarcă setările din baza de date în siguranță, fără să crape dacă tabelul lipsește."""
    try:
        if hasattr(SetariRepository, "get_all"):
            rez = SetariRepository.get_all()
            if isinstance(rez, dict):
                return rez
        if hasattr(SetariRepository, "get_setari"):
            rez = SetariRepository.get_setari()
            if isinstance(rez, dict):
                return rez
    except Exception as e:
        logger.warning(f"Nu s-au putut încărca setările curent: {e}")
    return {}

def render_setari():
    st.subheader("⚙️ Setări Generale Firmă, TVA & Configurări Documente")

    setari_curente = _get_setari_safe()
    parola_sistem = str(setari_curente.get("pass") or "").strip()
    acces_deblocat = bool(st.session_state.get("is_unlocked", False)) or (not parola_sistem)

    tab_firma, tab_tarife, tab_fraze, tab_securitate = st.tabs([
        "🏢 Date Firmă, TVA & Valori Implicite",
        "💰 Tarife Standard",
        "💬 Fraze Predefinite Oferte",
        "🔐 Securitate & Email"
    ])

    # ---------------------------------------------------------
    # TAB 1: DATE FIRMĂ, TVA & VALORI IMPLICITE (OFERTE + RAPOARTE)
    # ---------------------------------------------------------
    with tab_firma:
        with st.form("form_setari_firma"):
            st.markdown("##### Identificare Firmă Prestatoare & Fiscalitate")
            col1, col2 = st.columns(2)
            with col1:
                nume_firma_mea = st.text_input("Denumire Firmă", value=setari_curente.get("nume_firma_mea", ""))
                cui_mea = st.text_input("CUI / CIF", value=setari_curente.get("cui_mea", ""))
                reg_com_mea = st.text_input("Nr. Reg. Comerțului", value=setari_curente.get("reg_com_mea", ""))
                cota_tva = st.number_input(
                    "Cotă TVA aplicabilă (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(setari_curente.get("cota_tva") if setari_curente.get("cota_tva") is not None else 21.0),
                    step=1.0,
                    format="%.2f"
                )
            with col2:
                adresa_mea = st.text_input("Adresă Sediu Social", value=setari_curente.get("adresa_mea", ""))
                banca_mea = st.text_input("Bancă", value=setari_curente.get("banca_mea", ""))
                iban_mea = st.text_input("Cont IBAN", value=setari_curente.get("iban_mea", ""))
                swep_mea = st.text_input("Cod SWIFT / BIC", value=setari_curente.get("swep_mea", ""))

            st.markdown("---")
            st.markdown("##### Date de Contact Firmă (2 Telefoane & 2 Adrese de Email)")
            cc1, cc2 = st.columns(2)
            with cc1:
                telefon_1 = st.text_input(
                    "Telefon 1",
                    value=setari_curente.get("telefon_1", ""),
                    placeholder="ex: +40 7xx xxx xxx"
                )
                telefon_2 = st.text_input(
                    "Telefon 2",
                    value=setari_curente.get("telefon_2", ""),
                    placeholder="ex: +40 7xx xxx xxx"
                )
            with cc2:
                email_1 = st.text_input(
                    "Email 1",
                    value=setari_curente.get("email_1", ""),
                    placeholder="ex: contact@nexind.ro"
                )
                email_2 = st.text_input(
                    "Email 2",
                    value=setari_curente.get("email_2", ""),
                    placeholder="ex: oferte@nexind.ro"
                )

            st.markdown("---")
            st.markdown("##### Valori Implicite pentru Oferte de Preț & Rapoarte Tehnice")
            co1, co2 = st.columns(2)
            with co1:
                valabilitate_implicita = st.text_input(
                    "Termen de valabilitate ofertă (implicit)",
                    value=setari_curente.get("valabilitate_implicita") or "15 zile"
                )
                intocmit_de_implicit = st.text_input(
                    "Întocmit de — Oferte de preț (implicit)",
                    value=setari_curente.get("intocmit_de_implicit") or "Echipa Nexus Industrial"
                )
            with co2:
                termeni_plata_impliciti = st.text_input(
                    "Termeni de plată ofertă (impliciți)",
                    value=setari_curente.get("termeni_plata_impliciti") or "5 zile de la emiterea facturii",
                    help="Poți separa mai multe tranșe prin virgulă sau ';' (ex: 30% avans, 30% la livrare, 40% la PIF)."
                )
                tehnician_implicit = st.text_input(
                    "Tehnician implicit (Rapoarte Intervenție & Electronice)",
                    value=setari_curente.get("tehnician_implicit") or "Tehnician Nexus"
                )

            clauze_subsol_implicite = st.text_area(
                "Mențiuni / Clauze implicite subsol ofertă (folosește {MONEDA} pentru EUR/RON automat)",
                value=str(setari_curente.get("clauze_subsol_implicite") or ""),
                height=120,
                help="Acest text se încarcă automat la orice ofertă nouă. Folosește {MONEDA} acolo unde dorești să apară EUR sau RON."
            )

            submitted_firma = st.form_submit_button("💾 Salvează Setările", type="primary")
            if submitted_firma:
                date_actualizate = dict(setari_curente)
                date_actualizate.update({
                    "nume_firma_mea": nume_firma_mea,
                    "cui_mea": cui_mea,
                    "reg_com_mea": reg_com_mea,
                    "adresa_mea": adresa_mea,
                    "banca_mea": banca_mea,
                    "iban_mea": iban_mea,
                    "swep_mea": swep_mea,
                    "telefon_1": telefon_1.strip(),
                    "telefon_2": telefon_2.strip(),
                    "email_1": email_1.strip(),
                    "email_2": email_2.strip(),
                    "cota_tva": float(cota_tva),
                    "valabilitate_implicita": valabilitate_implicita.strip() or "15 zile",
                    "termeni_plata_impliciti": termeni_plata_impliciti.strip() or "5 zile de la emiterea facturii",
                    "intocmit_de_implicit": intocmit_de_implicit.strip() or "Echipa Nexus Industrial",
                    "tehnician_implicit": tehnician_implicit.strip() or "Tehnician Nexus",
                    "clauze_subsol_implicite": clauze_subsol_implicite.strip(),
                })
                SetariRepository.save_setari(date_actualizate)
                st.success("✅ Setările firmei, contactele, TVA-ul și valorile implicite au fost salvate!")
                st.rerun()

        # ---------------------------------------------------------
        # SECȚIUNE PROTEJATĂ CU PAROLĂ: ADAOS COMERCIAL IMPLICIT
        # ---------------------------------------------------------
        st.markdown("---")
        st.markdown("##### 🔒 Adaos Comercial Implicit Piese (Client Standard)")

        if not acces_deblocat:
            st.info("🔐 Adaosul comercial implicit este protejat cu parolă. Mergi la **SistemAdmin → 🔑 Deblocare** pentru a-l vizualiza sau modifica.")
        else:
            val_curenta_adaos = float(
                setari_curente.get("adaos_comercial_implicit")
                if setari_curente.get("adaos_comercial_implicit") is not None
                else 35.0
            )
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
                    help="Se citește din baza de date (setari.adaos_comercial_implicit) și se aplică în Calculatorul Rapid de Prețuri."
                )
            with ca2:
                if st.button("💾 Salvează Adaos", key="btn_save_adaos_imp", type="primary", use_container_width=True):
                    date_actualizate = dict(setari_curente)
                    date_actualizate["adaos_comercial_implicit"] = float(nou_adaos_implicit)
                    SetariRepository.save_setari(date_actualizate)
                    st.success(f"✅ Adaosul comercial implicit a fost salvat în baza de date ({nou_adaos_implicit:.2f}%)!")
                    st.rerun()

    # ---------------------------------------------------------
    # TAB 2: TARIFE STANDARD (NIVEL A / NIVEL B / NIVEL C)
    # ---------------------------------------------------------
    with tab_tarife:
        st.markdown("##### Configurare Tarife & Activități Implicite (EUR sau RON)")
        st.caption("💡 Poți defini tarife în **EUR** sau **RON**, pe **Nivel A**, **Nivel B** sau **Nivel C**, cu prețuri modificate independent pe fiecare nivel.")

        with st.form("form_add_tarif"):
            ct1, ct2, ct3, ct4 = st.columns([2.8, 1.3, 1.3, 1.3], vertical_alignment="bottom")
            with ct1:
                desc_tarif = st.text_input("Descriere serviciu / activitate", placeholder="ex: Manoperă service / Ora de transport")
            with ct2:
                pret_tarif = st.number_input("Preț unitar", min_value=0.0, step=5.0, format="%.2f")
            with ct3:
                moneda_um = st.selectbox(
                    "Monedă / UM",
                    options=[
                        "EUR/ora", "EUR/km", "EUR/buc", "EUR/set",
                        "RON/ora", "RON/km", "RON/buc", "RON/set"
                    ]
                )
            with ct4:
                nivel_nou_tarif = st.selectbox("Nivel Grilă", options=["Nivel A", "Nivel B", "Nivel C"])

            if st.form_submit_button("➕ Adaugă Tarif", type="primary"):
                if desc_tarif.strip():
                    _insert_tarif_safe(desc_tarif.strip(), pret_tarif, moneda_um, nivel_nou_tarif)
                    st.success(f"✅ Tarif adăugat pe {nivel_nou_tarif} ({pret_tarif:.2f} {moneda_um})!")
                    st.rerun()
                else:
                    st.warning("Introduceți descrierea tarifului.")

        st.markdown("---")
        st.markdown("###### 🔄 Trecere Tarife pe Nivel (4 Nivele: Toate, Nivel A, Nivel B, Nivel C)")
        ct_tr1, ct_tr2, ct_tr3 = st.columns([2.0, 2.0, 1.5], vertical_alignment="bottom")
        with ct_tr1:
            sursa_nivel_sel = st.selectbox(
                "Preia tarifele inițiale din:",
                options=["Toate existentele", "Nivel A", "Nivel B", "Nivel C"],
                key="sel_sursa_nivel_tarife"
            )
        with ct_tr2:
            nivel_tinta_sel = st.selectbox(
                "Trece toate tarifele la nivelul:",
                options=["Toate", "Nivel A", "Nivel B", "Nivel C"],
                key="sel_tinta_nivel_tarife"
            )
        with ct_tr3:
            if st.button("🚀 Aplică Trecerea", key="btn_trece_tarife_nivel", type="primary", use_container_width=True):
                sursa_arg = None if sursa_nivel_sel == "Toate existentele" else sursa_nivel_sel
                nr_create = _trece_tarife_la_nivel_safe(nivel_tinta_sel, sursa_nivel=sursa_arg)
                st.success(f"✅ Operațiune finalizată pentru **{nivel_tinta_sel}** ({nr_create} tarife noi create; prețurile pot fi ajustate separat pe fiecare nivel).")
                st.rerun()

        tarife_list = _get_tarife_safe()
        if tarife_list:
            st.markdown("###### Tarife active în sistem (modificarea prețului afectează doar nivelul rândului respectiv):")
            filtru_nivel_afisaj = st.radio(
                "Filtrează lista afișată după nivel:",
                options=["Toate", "Nivel A", "Nivel B", "Nivel C"],
                horizontal=True,
                key="radio_filtru_nivel_setari"
            )
            tarife_de_afisat = (
                tarife_list
                if filtru_nivel_afisaj == "Toate"
                else [t for t in tarife_list if str(t.get("nivel_grila") or "Nivel A").strip() == filtru_nivel_afisaj]
            )

            for t in tarife_de_afisat:
                tid = t['id']
                niv_t = str(t.get('nivel_grila') or 'Nivel A').strip()
                c_t1, c_t_niv, c_t2, c_t3, c_t4, c_t5 = st.columns([3.0, 1.0, 1.4, 1.2, 0.8, 0.8], vertical_alignment="center")
                c_t1.write(f"**{t['descriere']}**")
                c_t_niv.write(f"**{niv_t}**")
                nou_pret_t = c_t2.number_input(
                    "Preț",
                    value=float(t['pret']),
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"edit_pret_tarif_{tid}",
                    label_visibility="collapsed"
                )
                c_t3.write(f"**{t['moneda_um']}**")
                if c_t4.button("💾", key=f"save_tarif_{tid}", help="Salvează prețul modificat doar pentru acest nivel"):
                    _update_pret_tarif_safe(tid, nou_pret_t)
                    st.toast(f"✅ Preț actualizat ({niv_t}): {t['descriere']} -> {nou_pret_t:.2f} {t['moneda_um']}")
                    st.rerun()
                if c_t5.button("🗑️", key=f"del_tarif_{tid}", help="Șterge tarif"):
                    _delete_tarif_safe(tid)
                    st.rerun()
        else:
            st.info("Nu există tarife definite.")

    # ---------------------------------------------------------
    # TAB 3: FRAZE PREDEFINITE OFERTE
    # ---------------------------------------------------------
    with tab_fraze:
        st.markdown("##### Clauze Standard Disponibile în Oferte")
        with st.form("form_add_fraza"):
            titlu_fraza = st.text_input("Titlu scurt (pentru identificare)", placeholder="ex: Garanție 12 luni")
            continut_fraza = st.text_area("Conținut complet clauză", height=80, placeholder="Textul exact care va apărea în ofertă...")
            if st.form_submit_button("➕ Salvează Clauză"):
                if titlu_fraza.strip() and continut_fraza.strip():
                    _insert_fraza_safe(titlu_fraza.strip(), continut_fraza.strip())
                    st.success("Clauza a fost adăugată!")
                    st.rerun()
                else:
                    st.warning("Completați atât titlul, cât și conținutul clauzei.")

        fraze_list = _get_fraze_safe()
        if fraze_list:
            for fr in fraze_list:
                cf1, cf2 = st.columns([6, 1], vertical_alignment="center")
                with cf1:
                    st.markdown(f"**{fr.get('titlu', 'Clauză')}**: {fr.get('continut', '')}")
                with cf2:
                    if st.button("🗑️", key=f"del_fr_db_{fr['id']}", help="Șterge clauza"):
                        _delete_fraza_safe(fr['id'])
                        st.rerun()
        else:
            st.info("Nu există fraze salvate în baza de date.")

    # ---------------------------------------------------------
    # TAB 4: SECURITATE & EMAIL SMTP
    # ---------------------------------------------------------
    with tab_securitate:
        with st.form("form_setari_email"):
            st.markdown("##### Configurare Server Email (SMTP) & Integrări")
            ce1, ce2 = st.columns(2)
            with ce1:
                smtp_server = st.text_input("Server SMTP", value=setari_curente.get("smtp_server", "smtp.gmail.com"))
                smtp_port = st.number_input("Port SMTP", value=int(setari_curente.get("smtp_port") or 587), step=1)
                email_tehnician = st.text_input("Email Tehnician / Notificări", value=setari_curente.get("email_tehnician", ""))
            with ce2:
                smtp_user = st.text_input("Utilizator SMTP (Email)", value=setari_curente.get("smtp_user", ""))
                smtp_pass = st.text_input("Parolă SMTP / App Password", value=setari_curente.get("smtp_pass", ""), type="password")
                google_sheet_url = st.text_input("URL Google Sheet Sync", value=setari_curente.get("google_sheet_url", ""))

            if st.form_submit_button("💾 Salvează Configurări Email", type="primary"):
                date_actualizate = dict(setari_curente)
                date_actualizate.update({
                    "smtp_server": smtp_server,
                    "smtp_port": int(smtp_port),
                    "smtp_user": smtp_user,
                    "smtp_pass": smtp_pass,
                    "google_sheet_url": google_sheet_url,
                    "email_tehnician": email_tehnician
                })
                SetariRepository.save_setari(date_actualizate)
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
