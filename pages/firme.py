#----------------------------------
#-------firme.py-------------------
#----------------------------------

import streamlit as st
from repositories.firme_repository import FirmeRepository


def render_firme():
    st.subheader("📇 Gestiune Firme și Persoane de Contact")

    @st.fragment
    def render_form_firme():
        with st.form("form_firme", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                nume_firma = st.text_input("Nume Firmă / Client *")
                cui = st.text_input("CUI")
                reg_com = st.text_input("Nr. Reg. Com.")
                adresa = st.text_input("Adresă Sediu")
                adaos_comercial = st.number_input("Adaos Comercial implicit (%)", value=20.0, step=0.5, format="%.2f")
            with c2:
                banca = st.text_input("Bancă")
                cont = st.text_input("Cont (IBAN)")
                nume_persoana = st.text_input("Persoană de Contact *")
                email = st.text_input("Adresă E-mail Contact")
                telefon = st.text_input("Telefon")

            if st.form_submit_button("💾 Salvează Firmă Nouă"):
                if nume_firma and nume_persoana:
                    try:
                        FirmeRepository.insert({
                            "nume_firma": nume_firma,
                            "cui": cui,
                            "reg_com": reg_com,
                            "adresa": adresa,
                            "banca": banca,
                            "cont": cont,
                            "nume_persoana": nume_persoana,
                            "email": email,
                            "telefon": telefon,
                            "adaos_comercial": adaos_comercial
                        })
                        st.toast(f"✅ Firma {nume_firma} a fost salvată!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Eroare la salvarea firmei: {str(e)}")
                else:
                    st.error("Completați câmpurile obligatorii (*).")

    render_form_firme()
    st.markdown("---")

    @st.fragment
    def render_lista_firme():
        st.subheader("📋 Firme Înregistrate")
        firme_db = FirmeRepository.get_all()
        for f in firme_db:
            with st.expander(f"🏢 {f['nume_firma']} (CUI: {f.get('cui', 'N/A')}) - Adaos: {f.get('adaos_comercial', 20.0)}%"):
                with st.form(f"mod_firma_{f['id']}"):
                    mf_nume = st.text_input("Nume Firmă", value=f['nume_firma'], key=f"mf_n_{f['id']}")
                    mf_cui = st.text_input("CUI", value=f.get('cui', ''), key=f"mf_cui_{f['id']}")
                    mf_reg = st.text_input("Reg. Com.", value=f.get('reg_com', ''), key=f"mf_reg_{f['id']}")
                    mf_adr = st.text_input("Adresă", value=f.get('adresa', ''), key=f"mf_adr_{f['id']}")
                    mf_adaos = st.number_input("Adaos Comercial (%)", value=float(f.get('adaos_comercial', 20.0) or 20.0), step=0.5, format="%.2f", key=f"mf_adaos_{f['id']}")
                    mf_banca = st.text_input("Bancă", value=f.get('banca', ''), key=f"mf_b_{f['id']}")
                    mf_cont = st.text_input("Cont", value=f.get('cont', ''), key=f"mf_cont_{f['id']}")
                    mf_pers = st.text_input("Persoană Contact", value=f.get('nume_persoana', ''), key=f"mf_p_{f['id']}")
                    mf_email = st.text_input("Email", value=f.get('email', ''), key=f"mf_e_{f['id']}")
                    mf_tel = st.text_input("Telefon", value=f.get('telefon', ''), key=f"mf_t_{f['id']}")

                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        if st.form_submit_button("🔄 Modifică Tot", key=f"mod_f_{f['id']}"):
                            try:
                                FirmeRepository.update(f['id'], {
                                    "nume_firma": mf_nume,
                                    "cui": mf_cui,
                                    "reg_com": mf_reg,
                                    "adresa": mf_adr,
                                    "banca": mf_banca,
                                    "cont": mf_cont,
                                    "nume_persoana": mf_pers,
                                    "email": mf_email,
                                    "telefon": mf_tel,
                                    "adaos_comercial": mf_adaos
                                })
                                st.toast("✅ Firma a fost actualizată!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Eroare la actualizare: {str(e)}")
                    with col_m2:
                        if st.form_submit_button("🗑️ Șterge Firma", key=f"del_f_{f['id']}"):
                            try:
                                FirmeRepository.delete(f['id'])
                                st.toast("🗑️ Firma a fost ștearsă!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Eroare: {str(e)}")

    render_lista_firme()