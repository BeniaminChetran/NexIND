#----------------------------------
#-------masini.py------------------
#----------------------------------

import streamlit as st
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from config import db_cursor

def render_masini():
    st.subheader("🚗 Gestiune Mașini și Echipamente")
    
    firme_db = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f['id'] for f in firme_db}
    
    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în tabul 'Firme'.")
        return

    sel_firma_nume = st.selectbox("Selectează Firma Proprietară", options=list(firme_dict.keys()), key="sel_firma_masini")
    firma_id = firme_dict[sel_firma_nume]

    @st.fragment
    def render_form_masina():
        st.markdown("### ➕ Adaugă Mașină Nouă")
        with st.form("form_adauga_masina", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                denumire = st.text_input("Denumire Mașină *")
                tip_masina = st.text_input("Tip Mașină")
                nr_serie = st.text_input("Număr Serie")
                an_fabricatie = st.number_input("An Fabricație", value=2020, min_value=1950, max_value=2030, step=1)
                defecte = st.text_area("Defecte (Memo)")
                reparatii = st.text_area("Remediații aferente (Memo)")
                piese_necesare = st.text_area("Piese Necesare")
            with col2:
                subansambluri = st.text_input("Subansambluri (separate prin virgulă)")
                erori = st.text_input("Erori (separate prin virgulă)")
                data_intretinere = st.date_input("Data Întreținere Planificată", value=datetime.today())
                tip_intretinere = st.selectbox("Tip Întreținere", options=["Lunară", "Trimestrială", "Anuală", "La 6 luni"])
                piese_inlocuite = st.text_area("Piese Înlocuite")
                tipuri_fluide = st.text_area("Tipuri de Fluide")

            if st.form_submit_button("💾 Salvează Mașina"):
                if denumire:
                    MasiniRepository.insert({
                        "firma_id": firma_id,
                        "denumire": denumire,
                        "tip_masina": tip_masina,
                        "nr_serie": nr_serie,
                        "an_fabricatie": an_fabricatie,
                        "subansambluri": subansambluri,
                        "erori": erori,
                        "data_intretinere": data_intretinere.strftime("%Y-%m-%d"),
                        "tip_intretinere": tip_intretinere,
                        "defecte": defecte,
                        "reparatii": reparatii,
                        "piese_necesare": piese_necesare,
                        "piese_inlocuite": piese_inlocuite,
                        "tipuri_fluide": tipuri_fluide
                    })
                    st.success(f"Mașina '{denumire}' a fost salvată cu succes!")
                else:
                    st.error("Te rugăm să completezi cel puțin denumirea mașinii.")

    render_form_masina()
    st.markdown("---")
    
    @st.fragment
    def render_lista_masini():
        st.subheader("📋 Mașini Înregistrate")
        masini_list = MasiniRepository.get_all()
        if masini_list:
            for m in masini_list:
                nume_f = next((n for n, fid in firme_dict.items() if fid == m.get('firma_id')), "Necunoscută")
                mid = m.get('id')
                
                with st.expander(f"⚙️ {m['denumire']} (Firma: {nume_f})"):
                    with st.form(f"form_mod_masina_{mid}"):
                        mc1, mc2 = st.columns(2)
                        with mc1:
                            m_den = st.text_input("Denumire Mașină", value=m.get('denumire', ''), key=f"m_den_{mid}")
                            m_tip = st.text_input("Tip Mașină", value=m.get('tip_masina', ''), key=f"m_tip_{mid}")
                            m_serie = st.text_input("Număr Serie", value=m.get('nr_serie', ''), key=f"m_serie_{mid}")
                            m_sub = st.text_input("Subansambluri", value=m.get('subansambluri', ''), key=f"m_sub_{mid}")
                        with mc2:
                            m_erori = st.text_input("Erori", value=m.get('erori', ''), key=f"m_erori_{mid}")
                            m_an = st.number_input("An Fabricație", value=int(m.get('an_fabricatie', 2020) or 2020), key=f"m_an_{mid}")
                            m_tip_int = st.text_input("Tip Întreținere", value=m.get('tip_intretinere', ''), key=f"m_tip_int_{mid}")
                        
                        m_def = st.text_area("Defecte", value=m.get('defecte', ''), key=f"m_def_{mid}")
                        
                        bt_s, bt_d = st.columns(2)
                        if bt_s.form_submit_button("💾 Salvează Modificările", key=f"m_sav_{mid}"):
                            with db_cursor() as c:
                                c.execute("""
                                    UPDATE masini SET denumire=%s, tip_masina=%s, nr_serie=%s, subansambluri=%s, erori=%s, an_fabricatie=%s, tip_intretinere=%s, defecte=%s 
                                    WHERE id=%s
                                """, (m_den, m_tip, m_serie, m_sub, m_erori, m_an, m_tip_int, m_def, mid))
                            st.success("Modificările mașinii au fost salvate!")
                        if bt_d.form_submit_button("🗑️ Șterge Mașina", key=f"m_del_{mid}"):
                            with db_cursor() as c:
                                c.execute("DELETE FROM masini WHERE id=%s", (mid,))
                            st.success("Mașina a fost ștearsă!")
        else:
            st.info("Nu există mașini înregistrate momentan.")

    render_lista_masini()