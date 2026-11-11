#----------------------------------
#-------firme.py-------------------
#----------------------------------

import streamlit as st
from repositories.firme_repository import FirmeRepository
from config import db_cursor

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
            with c2:
                banca = st.text_input("Bancă")
                cont = st.text_input("Cont (IBAN)")
                nume_persoana = st.text_input("Persoană de Contact *")
                email = st.text_input("Adresă E-mail Contact")
                telefon = st.text_input("Telefon")
                
            if st.form_submit_button("💾 Salvează Firmă Nouă"):
                if nume_firma and nume_persoana:
                    with db_cursor() as c:
                        c.execute("""
                            INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon))
                    st.success(f"Firma **{nume_firma}** a fost salvată!")
                else:
                    st.error("Completați câmpurile obligatorii (*).")

    render_form_firme()
    st.markdown("---")
    
    @st.fragment
    def render_lista_firme():
        st.subheader("📋 Firme Înregistrate")
        firme_db = FirmeRepository.get_all()
        for f in firme_db:
            with st.expander(f"🏢 {f['nume_firma']} (CUI: {f.get('cui', 'N/A')}) - Contact: {f.get('nume_persoana', '')}"):
                with st.form(f"mod_firma_{f['id']}"):
                    mf_nume = st.text_input("Nume Firmă", value=f['nume_firma'], key=f"mf_n_{f['id']}")
                    mf_cui = st.text_input("CUI", value=f.get('cui', ''), key=f"mf_cui_{f['id']}")
                    mf_reg = st.text_input("Reg. Com.", value=f.get('reg_com', ''), key=f"mf_reg_{f['id']}")
                    mf_adr = st.text_input("Adresă", value=f.get('adresa', ''), key=f"mf_adr_{f['id']}")
                    mf_banca = st.text_input("Bancă", value=f.get('banca', ''), key=f"mf_b_{f['id']}")
                    mf_cont = st.text_input("Cont", value=f.get('cont', ''), key=f"mf_cont_{f['id']}")
                    mf_pers = st.text_input("Persoană Contact", value=f.get('nume_persoana', ''), key=f"mf_p_{f['id']}")
                    mf_email = st.text_input("Email", value=f.get('email', ''), key=f"mf_e_{f['id']}")
                    mf_tel = st.text_input("Telefon", value=f.get('telefon', ''), key=f"mf_t_{f['id']}")
                    
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        if st.form_submit_button("🔄 Modifică Tot", key=f"mod_f_{f['id']}"):
                            with db_cursor() as c:
                                c.execute("""
                                    UPDATE firme 
                                    SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s 
                                    WHERE id=%s
                                """, (mf_nume, mf_cui, mf_reg, mf_adr, mf_banca, mf_cont, mf_pers, mf_email, mf_tel, f['id']))
                            st.success("Firma a fost actualizată!")
                    with col_m2:
                        if st.form_submit_button("🗑️ Șterge Firma", key=f"del_f_{f['id']}"):
                            try:
                                with db_cursor() as c:
                                    c.execute("DELETE FROM firme WHERE id=%s", (f['id'],))
                                st.success("Firma a fost ștearsă!")
                            except Exception as e:
                                st.error(f"Eroare: {str(e)}")

    render_lista_firme()