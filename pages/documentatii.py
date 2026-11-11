#----------------------------------
#----documentatii.py---------------
#----------------------------------

import streamlit as st
from repositories.masini_repository import MasiniRepository
from config import db_cursor

def render_documentatii():
    st.subheader("📊 Documentații / Proceduri de reparații")
    
    @st.fragment
    def render_doc_fragment():
        masini_existente = [m['denumire'] for m in MasiniRepository.get_all()]
        
        if not masini_existente:
            st.warning("⚠️ Adăugați mașini în Tabul aferent.")
            return

        sel_opt_masina = st.selectbox("Selectează Mașina", options=masini_existente, key="opt_m_sel_tab2")
        
        with db_cursor() as cur_d:
            cur_d.execute("SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s", (sel_opt_masina,))
            defecte_existente = [row['defect'] for row in cur_d.fetchall() if row['defect']]
        
        opțiuni_defecte = ["+ Defect nou (scrie mai jos)"] + defecte_existente
        sel_opt_defect_complet = st.selectbox("Selectează sau creează Defectul / Procedura", options=opțiuni_defecte, key="select_defect_unificat_tab2")
        
        if sel_opt_defect_complet == "+ Defect nou (scrie mai jos)":
            def_final = st.text_input("Introduceți descrierea pentru defectul / procedura nouă *", key="input_defect_nou_text_tab2")
        else:
            def_final = sel_opt_defect_complet
            
        st.markdown("---")
        
        if sel_opt_defect_complet != "+ Defect nou (scrie mai jos)" and sel_opt_defect_complet:
            st.markdown(f"##### 🔎 Editare Pași de Reparație existenți pentru: **{sel_opt_defect_complet}**")
            with db_cursor() as cur_p:
                cur_p.execute("SELECT id, pas_numar, descriere_pas FROM optimizari_interventie WHERE masina = %s AND defect = %s ORDER BY pas_numar", (sel_opt_masina, sel_opt_defect_complet))
                pasii_db = cur_p.fetchall()
            
            with st.form(f"form_edita_pasi_{sel_opt_masina}_{sel_opt_defect_complet}"):
                pasi_editati_dict = {pe['id']: st.text_input(f"Pasul {pe['pas_numar']}", value=pe['descriere_pas'], key=f"edit_pas_db_{pe['id']}") for pe in pasii_db}
                col_ep1, col_ep2 = st.columns(2)
                with col_ep1:
                    if st.form_submit_button("🔄 Actualizează Pașii"):
                        with db_cursor() as c:
                            for pid_pas, val_noua in pasi_editati_dict.items():
                                c.execute("UPDATE optimizari_interventie SET descriere_pas = %s WHERE id = %s", (val_noua, pid_pas))
                        st.success("Pașii au fost actualizați cu succes!")
                with col_ep2:
                    if st.form_submit_button("🗑️ Șterge Toată Procedura"):
                        with db_cursor() as c:
                            c.execute("DELETE FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, sel_opt_defect_complet))
                        st.success("Procedura a fost ștearsă!")
            st.markdown("---")
            
        st.markdown(f"##### ➕ Adaugă Pași Noi pentru: **{def_final if def_final else 'Nefinit'}**")
        if "pasi_lucrare_t" not in st.session_state:
            st.session_state["pasi_lucrare_t"] = []
            
        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou", key="desc_pas_nou_form_tab2")
            if st.form_submit_button("➕ Adaugă Pas în Memorie"):
                if desc_p_nou:
                    st.session_state["pasi_lucrare_t"].append(desc_p_nou)
                    st.success("Pas adăugat în listă!")
                    
        if st.session_state["pasi_lucrare_t"]:
            st.write("Pași adăugați pregătiți pentru salvare:")
            pasi_modificati = [st.text_input(f"Pas nou {idx+1}", value=pval, key=f"pas_ed_{idx}") for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])]
            if st.button("💾 Salvează Toți Pașii Noi în Baza de Date", type="primary", key="btn_salveaza_toti_pasii_tab2"):
                if def_final and def_final.strip() != "":
                    with db_cursor() as cur_mx:
                        cur_mx.execute("SELECT MAX(pas_numar) as max_p FROM optimizari_interventie WHERE masina = %s AND defect = %s", (sel_opt_masina, def_final))
                        max_p = cur_mx.fetchone()
                    
                    start_nr = (max_p['max_p'] if max_p and max_p['max_p'] else 0) + 1
                    with db_cursor() as c:
                        for idx, pval in enumerate(pasi_modificati):
                            c.execute("INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) VALUES (%s, %s, %s, %s)", (sel_opt_masina, def_final, start_nr + idx, pval))
                    st.session_state["pasi_lucrare_t"] = []
                    st.success("Pașii noi au fost salvați în Supabase!")
                else:
                    st.error("Introduceți sau selectați un defect valid înainte de salvare.")

    render_doc_fragment()