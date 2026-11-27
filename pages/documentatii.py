# ----------------------------------
# ----documentatii.py---------------
# ----------------------------------

import streamlit as st
from config import db_cursor
from repositories.masini_repository import MasiniRepository
from repositories.setari_repository import SetariRepository


@st.cache_data(ttl=300)
def _obtine_url_locatie_centrala() -> str:
    try:
        setari = SetariRepository.get_setari() or {}
    except Exception:
        setari = {}
    url = str(setari.get("locatie_documentatii_gdrive") or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


@st.cache_data(ttl=180)
def _incarca_denumiri_masini_cached() -> list[str]:
    try:
        return [m["denumire"] for m in (MasiniRepository.get_all() or []) if m.get("denumire")]
    except Exception:
        return []


@st.cache_data(ttl=120)
def _incarca_defecte_masina_cached(masina: str) -> list[str]:
    with db_cursor() as cur_d:
        cur_d.execute(
            "SELECT DISTINCT defect FROM optimizari_interventie WHERE masina = %s ORDER BY defect",
            (masina,),
        )
        return [row["defect"] for row in (cur_d.fetchall() or []) if row.get("defect")]


@st.cache_data(ttl=120)
def _incarca_pasi_defect_cached(masina: str, defect: str) -> list[dict]:
    with db_cursor() as cur_p:
        cur_p.execute(
            "SELECT id, pas_numar, descriere_pas FROM optimizari_interventie "
            "WHERE masina = %s AND defect = %s ORDER BY pas_numar",
            (masina, defect),
        )
        return [dict(r) for r in (cur_p.fetchall() or [])]


def _invalideaza_cache_proceduri(masina: str, defect: str | None = None) -> None:
    _incarca_defecte_masina_cached.clear(masina)
    if defect:
        _incarca_pasi_defect_cached.clear(masina, defect)


def _reseteaza_stare_temporara() -> None:
    st.session_state["pasi_lucrare_t"] = []


def render_documentatii():
    col_t, col_l = st.columns([3.2, 1.8], vertical_alignment="center")
    with col_t:
        st.subheader("📊 Documentații / Proceduri de reparații")
    with col_l:
        url_doc = _obtine_url_locatie_centrala()
        if url_doc:
            st.link_button("📂 Locație Documentații", url=url_doc, use_container_width=False)

    @st.fragment
    def render_doc_fragment():
        st.session_state.setdefault("pasi_lucrare_t", [])
        masini_existente = _incarca_denumiri_masini_cached()

        if not masini_existente:
            st.warning("⚠️ Adăugați mașini în Tabul aferent.")
            return

        sel_opt_masina = st.selectbox(
            "Selectează Mașina",
            options=masini_existente,
            key="opt_m_sel_tab2",
            on_change=_reseteaza_stare_temporara,
        )

        try:
            defecte_existente = _incarca_defecte_masina_cached(sel_opt_masina)
        except Exception as e:
            st.error(f"Eroare la încărcarea defectelor: {e}")
            return

        optiuni_defecte = ["+ Defect nou (scrie mai jos)"] + defecte_existente
        sel_opt_defect_complet = st.selectbox(
            "Selectează sau creează Defectul / Procedura",
            options=optiuni_defecte,
            key="select_defect_unificat_tab2",
            on_change=_reseteaza_stare_temporara,
        )

        este_defect_nou = sel_opt_defect_complet == "+ Defect nou (scrie mai jos)"
        if este_defect_nou:
            def_final = st.text_input(
                "Introduceți descrierea pentru defectul / procedura nouă *",
                key="input_defect_nou_text_tab2",
            ).strip()
        else:
            def_final = sel_opt_defect_complet.strip()

        st.markdown("---")

        # Secțiunea de editare / ștergere pentru proceduri existente
        if not este_defect_nou and def_final:
            st.markdown(f"##### 🔎 Editare Pași de Reparație existenți pentru: **{def_final}**")
            try:
                pasii_db = _incarca_pasi_defect_cached(sel_opt_masina, def_final)
            except Exception as e:
                st.error(f"Eroare la încărcarea pașilor: {e}")
                pasii_db = []

            if pasii_db:
                # Cheie stabilă bazată pe indexul selecției, fără caractere speciale din textul defectului
                idx_defect = optiuni_defecte.index(sel_opt_defect_complet)
                with st.form(f"form_edita_pasi_{masini_existente.index(sel_opt_masina)}_{idx_defect}"):
                    pasi_editati_dict = {
                        pe["id"]: st.text_input(
                            f"Pasul {pe['pas_numar']}",
                            value=pe["descriere_pas"],
                            key=f"edit_pas_db_{pe['id']}",
                        )
                        for pe in pasii_db
                    }
                    col_ep1, col_ep2 = st.columns(2)
                    with col_ep1:
                        submit_update = st.form_submit_button("🔄 Actualizează Pașii")
                    with col_ep2:
                        submit_delete = st.form_submit_button("🗑️ Șterge Toată Procedura")

                if submit_update:
                    date_update = [
                        (val.strip(), pid)
                        for pid, val in pasi_editati_dict.items()
                        if val and val.strip()
                    ]
                    if len(date_update) != len(pasi_editati_dict):
                        st.warning("⚠️ Niciun pas existent nu poate fi lăsat gol.")
                    else:
                        try:
                            with db_cursor() as c:
                                c.executemany(
                                    "UPDATE optimizari_interventie SET descriere_pas = %s WHERE id = %s",
                                    date_update,
                                )
                            _invalideaza_cache_proceduri(sel_opt_masina, def_final)
                            st.success("Pașii au fost actualizați cu succes!")
                        except Exception as e:
                            st.error(f"Eroare la actualizarea pașilor: {e}")

                if submit_delete:
                    try:
                        with db_cursor() as c:
                            c.execute(
                                "DELETE FROM optimizari_interventie WHERE masina = %s AND defect = %s",
                                (sel_opt_masina, def_final),
                            )
                        _invalideaza_cache_proceduri(sel_opt_masina, def_final)
                        st.success("Procedura a fost ștearsă!")
                    except Exception as e:
                        st.error(f"Eroare la ștergerea procedurii: {e}")

            st.markdown("---")

        # Secțiunea de adăugare pași noi în memorie
        st.markdown(f"##### ➕ Adaugă Pași Noi pentru: **{def_final if def_final else 'Nedefinit'}**")

        with st.form("form_add_pas", clear_on_submit=True):
            desc_p_nou = st.text_area("Descriere pas remediu nou", key="desc_pas_nou_form_tab2")
            if st.form_submit_button("➕ Adaugă Pas în Memorie"):
                pas_curat = desc_p_nou.strip()
                if pas_curat:
                    st.session_state["pasi_lucrare_t"].append(pas_curat)
                    st.success("Pas adăugat în listă!")
                else:
                    st.warning("⚠️ Introduceți o descriere validă pentru pas.")

        # Afișare și salvare în lot (batch) a pașilor din memorie
        if st.session_state["pasi_lucrare_t"]:
            st.write("Pași adăugați pregătiți pentru salvare:")
            pasi_modificati = [
                st.text_input(f"Pas nou {idx + 1}", value=pval, key=f"pas_ed_{idx}")
                for idx, pval in enumerate(st.session_state["pasi_lucrare_t"])
            ]

            col_save, col_clear = st.columns([2, 1])
            with col_save:
                salveaza_click = st.button(
                    "💾 Salvează Toți Pașii Noi în Baza de Date",
                    type="primary",
                    key="btn_salveaza_toti_pasii_tab2",
                )
            with col_clear:
                if st.button("🧹 Golește Lista", key="btn_goleste_lista_tab2"):
                    _reseteaza_stare_temporara()

            if salveaza_click:
                pasi_valizi = [p.strip() for p in pasi_modificati if p and p.strip()]
                if not def_final:
                    st.error("Introduceți sau selectați un defect valid înainte de salvare.")
                elif not pasi_valizi:
                    st.error("Toți pașii din listă sunt goi. Completați cel puțin un pas valid.")
                else:
                    try:
                        with db_cursor() as c:
                            # Calculăm indexul de start direct în SQL și inserăm în lot cu executemany
                            c.execute(
                                "SELECT COALESCE(MAX(pas_numar), 0) AS max_p "
                                "FROM optimizari_interventie WHERE masina = %s AND defect = %s",
                                (sel_opt_masina, def_final),
                            )
                            row_max = c.fetchone()
                            start_nr = (row_max["max_p"] if row_max else 0) + 1

                            randuri_inserare = [
                                (sel_opt_masina, def_final, start_nr + idx, pval)
                                for idx, pval in enumerate(pasi_valizi)
                            ]
                            c.executemany(
                                "INSERT INTO optimizari_interventie (masina, defect, pas_numar, descriere_pas) "
                                "VALUES (%s, %s, %s, %s)",
                                randuri_inserare,
                            )

                        _reseteaza_stare_temporara()
                        _invalideaza_cache_proceduri(sel_opt_masina, def_final)
                        st.success("Pașii noi au fost salvați în Supabase!")
                    except Exception as e:
                        st.error(f"Eroare la salvarea în baza de date: {e}")

    render_doc_fragment()