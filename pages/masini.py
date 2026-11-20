#----------------------------------
#-------pages/masini.py------------
#----------------------------------

import streamlit as st
import pandas as pd
from datetime import datetime
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository, ALL_SISTEME_DEFAULT
from config import db_cursor

OPT_SISTEME = [
    ("Electric", "1. Sistem Electric, Electronică & Automatizare"),
    ("Mecanic", "2. Sistem Mecanic, Transmisii & Geometrie"),
    ("Hidraulic", "3. Sistem Hidraulic & Ungere"),
    ("Pneumatic", "4. Sistem Pneumatic"),
    ("Vacuum", "5. Sistem Vacuum"),
    ("Auxiliare", "6. Instalații Auxiliare (Răcire / Emulsie / Apă / Abur / Afumare)")
]
CODURI_SISTEME = [s[0] for s in OPT_SISTEME]
ETICHETE_SISTEME = {s[0]: s[1] for s in OPT_SISTEME}


def render_masini():
    st.subheader("🦾 Gestiune Mașini și Echipamente")
    is_unlocked = st.session_state.get("is_unlocked", False)

    firme_db = FirmeRepository.get_all()
    firme_dict = {f['nume_firma']: f['id'] for f in firme_db}

    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în modulul 'Firme'.")
        return

    # Banner global dacă există mașini care au atins/depășit pragul de intervenții
    masini_list = MasiniRepository.get_all()
    masini_prag_depasit = [
        m for m in masini_list
        if int(m.get("total_interventii", 0)) >= int(m.get("prag_interventii", 20))
    ]
    if masini_prag_depasit:
        nume_alert = ", ".join(
            f"{m['denumire']} ({m['total_interventii']}/{m['prag_interventii']})"
            for m in masini_prag_depasit
        )
        st.warning(f"🔔 **Atenție Grilă Tarifare:** Următoarele utilaje au atins sau depășit pragul de intervenții și pot trece la următoarea grilă de tarifare: **{nume_alert}**")

    c_sf1, c_sf2 = st.columns([3, 1.5], vertical_alignment="bottom")
    with c_sf1:
        sel_firma_nume = st.selectbox("Selectează Firma Proprietară", options=list(firme_dict.keys()), key="sel_firma_masini")
    with c_sf2:
        arata_toate_firmele = st.checkbox(
            "Afișează utilajele de la toate firmele",
            value=False,
            key="chk_toate_firmele_masini"
        )
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
                este_noua = st.checkbox("🆕 Mașină nouă (monitorizare prag intervenții pentru grila de tarifare)", value=True)
                prag_init = st.number_input(
                    "Prag intervenții (standard 20)",
                    value=20,
                    min_value=1,
                    max_value=500,
                    step=1,
                    disabled=not is_unlocked,
                    help="Valoarea implicită este 20. Deblochează din SistemAdmin → Deblocare pentru a o modifica."
                )
                defecte = st.text_area("Defecte (Memo)")
                reparatii = st.text_area("Remediații aferente (Memo)")
                piese_necesare = st.text_area("Piese Necesare")
            with col2:
                subansambluri = st.text_input("Subansambluri (separate prin virgulă)")
                erori = st.text_input("Erori (separate prin virgulă)")
                data_intretinere = st.date_input("Data Întreținere Planificată", value=datetime.today())
                tip_intretinere = st.selectbox("Tip Întreținere", options=["Lunară", "Trimestrială", "La 6 luni", "Anuală"])
                sisteme_sel = st.multiselect(
                    "Sisteme în dotare (pentru Fișa de Mentenanță Preventivă)",
                    options=CODURI_SISTEME,
                    default=CODURI_SISTEME,
                    format_func=lambda x: ETICHETE_SISTEME.get(x, x)
                )
                piese_inlocuite = st.text_area("Piese Înlocuite")
                tipuri_fluide = st.text_area("Tipuri de Fluide")

            if st.form_submit_button("💾 Salvează Mașina"):
                if denumire:
                    MasiniRepository.insert({
                        "firma_id": firma_id,
                        "denumire": denumire,
                        "tip_masina": tip_masina,
                        "serie": nr_serie,
                        "an_fabricatie": an_fabricatie,
                        "este_masina_noua": este_noua,
                        "prag_interventii": int(prag_init) if is_unlocked else 20,
                        "subansambluri": subansambluri,
                        "erori": erori,
                        "data_intretinere": data_intretinere.strftime("%Y-%m-%d"),
                        "tip_intretinere": tip_intretinere,
                        "sisteme_active": ",".join(sisteme_sel) if sisteme_sel else ALL_SISTEME_DEFAULT,
                        "defecte": defecte,
                        "remediu": reparatii,
                        "piese_necesare": piese_necesare,
                        "piese_inlocuite": piese_inlocuite,
                        "tipuri_fluide": tipuri_fluide
                    })
                    st.success(f"Mașina '{denumire}' a fost salvată cu succes!")
                    st.rerun()
                else:
                    st.error("Te rugăm să completezi cel puțin denumirea mașinii.")

    render_form_masina()
    st.markdown("---")

    if arata_toate_firmele:
        masini_afisate = masini_list
        st.subheader(f"📋 Mașini Înregistrate — Toate Firmele ({len(masini_afisate)})")
    else:
        masini_afisate = [m for m in masini_list if m.get("firma_id") == firma_id]
        st.subheader(f"📋 Mașini Înregistrate — {sel_firma_nume} ({len(masini_afisate)})")

    if masini_afisate:
        for m in masini_afisate:
            nume_f = next((n for n, fid in firme_dict.items() if fid == m.get('firma_id')), "Necunoscută")
            mid = m.get('id')
            sist_curente = [s.strip() for s in str(m.get('sisteme_active') or ALL_SISTEME_DEFAULT).split(",") if s.strip() in CODURI_SISTEME]
            if not sist_curente:
                sist_curente = CODURI_SISTEME

            total_int = int(m.get("total_interventii", 0))
            prag_int = int(m.get("prag_interventii", 20))
            este_noua_cur = bool(m.get("este_masina_noua", False))
            depasit = total_int >= prag_int
            grila_efectiva = MasiniRepository.determina_grila_efectiva(m)

            tag_noua = " | 🆕 Mașină nouă" if este_noua_cur else ""
            tag_grila = f" | 💶 {grila_efectiva}"
            tag_contor = f" | ⚠️ {total_int}/{prag_int} interv. (PRAG DEPĂȘIT)" if depasit else f" | 📊 {total_int}/{prag_int} interv."

            with st.expander(f"⚙️ {m['denumire']} (Firma: {nume_f}{tag_noua}{tag_grila}{tag_contor})"):
                if depasit:
                    st.error(f"🚨 **Prag atins/depășit ({total_int} din {prag_int} intervenții)!** Grilă efectivă curentă: **{grila_efectiva}**.")
                else:
                    ramase = prag_int - total_int
                    st.info(f"📈 **Contor intervenții:** {total_int} efectuate din pragul de {prag_int} (mai sunt **{ramase}** intervenții până la prag) | Grilă efectivă: **{grila_efectiva}**.")

                # SELECTOR GRILĂ TARIFARE PROTEJAT PRIN PAROLĂ
                st.markdown("#### 💶 Grilă Tarifare Echipament (Varianta A / Varianta B)")
                opt_grile_masina = ["AUTO", "Nivel A", "Nivel B"]
                etichete_grile = {
                    "AUTO": f"Automat (Nivel A până la {prag_int} interv., apoi Nivel B)",
                    "Nivel A": "Varianta 1 — Grila Nivel A (Multimarcă)",
                    "Nivel B": "Varianta 2 — Grila Nivel B (Expertiză CNC / >20h / SLA)"
                }
                grila_curenta = m.get("grila_tarifare") if m.get("grila_tarifare") in opt_grile_masina else "AUTO"

                cg1, cg2 = st.columns([3.2, 1.3], vertical_alignment="bottom")
                grila_aleasa = cg1.selectbox(
                    f"Mod alocare grilă (Activ acum: {grila_efectiva})",
                    options=opt_grile_masina,
                    index=opt_grile_masina.index(grila_curenta),
                    format_func=lambda x: etichete_grile[x],
                    disabled=not is_unlocked,
                    key=f"sel_grila_masina_{mid}",
                    help="Deblochează din SistemAdmin → Deblocare pentru a trece manual mașina din Varianta A în Varianta B."
                )
                if is_unlocked:
                    if cg2.button("💾 Aplică Grila", key=f"btn_save_grila_{mid}", use_container_width=True):
                        MasiniRepository.update_grila_tarifare(mid, grila_aleasa)
                        st.success(f"✅ Grila pentru '{m['denumire']}' a fost setată pe {grila_aleasa}!")
                        st.rerun()
                else:
                    cg2.caption("🔒 Blocat (necesită parolă)")

                with st.form(f"form_mod_masina_{mid}"):
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        m_den = st.text_input("Denumire Mașină", value=m.get('denumire', ''), key=f"m_den_{mid}")
                        m_tip = st.text_input("Tip Mașină", value=m.get('tip_masina', ''), key=f"m_tip_{mid}")
                        m_serie = st.text_input("Număr Serie", value=m.get('serie', ''), key=f"m_serie_{mid}")
                        m_sub = st.text_input("Subansambluri", value=m.get('subansambluri', ''), key=f"m_sub_{mid}")
                        m_noua = st.checkbox("🆕 Mașină nouă", value=este_noua_cur, key=f"m_noua_{mid}")
                    with mc2:
                        m_erori = st.text_input("Erori", value=m.get('erori', ''), key=f"m_erori_{mid}")
                        m_an = st.number_input("An Fabricație", value=int(m.get('an_fabricatie', 2020) or 2020), key=f"m_an_{mid}")
                        m_tip_int = st.text_input("Tip Întreținere", value=m.get('tip_intretinere', ''), key=f"m_tip_int_{mid}")
                        m_sist = st.multiselect(
                            "Sisteme active (Mentenanță Preventivă)",
                            options=CODURI_SISTEME,
                            default=sist_curente,
                            format_func=lambda x: ETICHETE_SISTEME.get(x, x),
                            key=f"m_sist_{mid}"
                        )
                        m_prag = st.number_input(
                            "Prag intervenții (protejat prin parolă)",
                            value=prag_int,
                            min_value=1,
                            max_value=500,
                            step=1,
                            disabled=not is_unlocked,
                            key=f"m_prag_{mid}",
                            help="Deblochează din SistemAdmin → Deblocare pentru a modifica pragul."
                        )

                    m_def = st.text_area("Defecte", value=m.get('defecte', ''), key=f"m_def_{mid}")

                    bt_s, bt_d = st.columns(2)
                    if bt_s.form_submit_button("💾 Salvează Modificările", key=f"m_sav_{mid}"):
                        MasiniRepository._ensure_sisteme_col()
                        sist_str = ",".join(m_sist) if m_sist else ALL_SISTEME_DEFAULT
                        prag_final = int(m_prag) if is_unlocked else prag_int
                        with db_cursor() as c:
                            c.execute("""
                                UPDATE masini
                                SET denumire=%s, tip_masina=%s, serie=%s, subansambluri=%s, erori=%s,
                                    an_fabricatie=%s, tip_intretinere=%s, defecte=%s, sisteme_active=%s,
                                    este_masina_noua=%s, prag_interventii=%s
                                WHERE id=%s
                            """, (m_den, m_tip, m_serie, m_sub, m_erori, m_an, m_tip_int, m_def, sist_str, m_noua, prag_final, mid))
                        st.success("Modificările mașinii au fost salvate!")
                        st.rerun()
                    if bt_d.form_submit_button("🗑️ Șterge Mașina", key=f"m_del_{mid}"):
                        with db_cursor() as c:
                            c.execute("DELETE FROM masini WHERE id=%s", (mid,))
                        st.success("Mașina a fost ștearsă!")
                        st.rerun()

                # TABEL COMPONENȚĂ SISTEME (Protejat prin parolă)
                st.markdown("#### 🧩 Tabel Componență Sisteme Utilaj")
                comp_lista = m.get("componenta_sisteme_json") or []
                df_comp = pd.DataFrame(comp_lista) if comp_lista else pd.DataFrame(
                    columns=["Sistem", "Element / Componentă", "Cod / Specificații", "Cantitate", "Observații"]
                )
                for col_req in ["Sistem", "Element / Componentă", "Cod / Specificații", "Cantitate", "Observații"]:
                    if col_req not in df_comp.columns:
                        df_comp[col_req] = ""

                if is_unlocked:
                    st.caption("🔓 Mod editare activ: poți adăuga rânduri noi jos (`+`) sau șterge rânduri bifând caseta din stânga și apăsând `Delete`.")
                    edited_comp = st.data_editor(
                        df_comp,
                        num_rows="dynamic",
                        hide_index=False,
                        column_config={
                            "Sistem": st.column_config.SelectboxColumn(
                                "Sistem",
                                options=CODURI_SISTEME,
                                default=sist_curente[0] if sist_curente else "Electric",
                                required=True
                            ),
                            "Element / Componentă": st.column_config.TextColumn("Element / Componentă", required=True, width="medium"),
                            "Cod / Specificații": st.column_config.TextColumn("Cod / Specificații", width="medium"),
                            "Cantitate": st.column_config.TextColumn("Cantitate", default="1", width="small"),
                            "Observații": st.column_config.TextColumn("Observații", width="medium"),
                        },
                        key=f"comp_editor_masina_{mid}",
                        use_container_width=True
                    )
                    if st.button("💾 Salvează Componența Sistemelor", key=f"save_comp_masina_{mid}", type="primary"):
                        clean_records = [
                            row for row in edited_comp.fillna("").to_dict(orient="records")
                            if str(row.get("Element / Componentă", "")).strip() != ""
                        ]
                        MasiniRepository.update_componenta_sisteme(mid, clean_records)
                        st.success("✅ Componența sistemelor pentru această mașină a fost salvată!")
                        st.rerun()
                else:
                    st.caption("🔒 Tabel protejat (doar vizualizare). Pentru a adăuga sau scoate elemente, deblochează din **SistemAdmin → Deblocare**.")
                    if df_comp.empty:
                        st.info("Nu sunt definite elemente în componența sistemelor acestui utilaj.")
                    else:
                        st.dataframe(df_comp, hide_index=True, use_container_width=True)
    else:
        if arata_toate_firmele:
            st.info("Nu există mașini înregistrate momentan.")
        else:
            st.info(f"Nu există mașini înregistrate pentru firma **{sel_firma_nume}**.")