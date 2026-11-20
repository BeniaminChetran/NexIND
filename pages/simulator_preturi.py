#-----------------------------------------
#-------pages/simulator_preturi.py--------
#-----------------------------------------

import streamlit as st
import pandas as pd
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.tarife_repository import TarifeRepository
from repositories.setari_repository import SetariRepository
from pages.oferte import (
    obtine_curs_bnr,
    converteste_in_moneda_oferta,
    normalizeaza_um,
    este_ore_transport,
    MAX_ORE_TRANSPORT_ZI,
)

def render_simulator_preturi():
    st.subheader("🧮 Calculator Rapid Prețuri Vânzare (Piese & Servicii)")
    st.caption(
        "Simulează instantaneu prețul de vânzare pentru unul sau mai multe produse/servicii "
        "(cu adaosul comercial al clientului, grila utilajului, conversie EUR/RON la curs BNR și TVA), fără a salva o ofertă."
    )

    firme_list = FirmeRepository.get_all()
    firme_dict = {f["nume_firma"]: f for f in firme_list}
    piese_catalog = PieseRepository.get_all()
    tarife_disponibile = TarifeRepository.get_all()
    setari_firma = SetariRepository.get_setari()
    cota_tva_procent = float(setari_firma.get("cota_tva") if setari_firma.get("cota_tva") is not None else 21.0)

    if "sim_curs_bnr" not in st.session_state:
        st.session_state["sim_curs_bnr"] = obtine_curs_bnr()
    if "df_sim_cos" not in st.session_state:
        st.session_state["df_sim_cos"] = pd.DataFrame(
            columns=["Tip", "Descriere", "UM", "Cantitate", "Pret Achizitie/Baza", "Adaos %", "Pret Unitar", "Moneda"]
        )
    if "sim_editor_counter" not in st.session_state:
        st.session_state["sim_editor_counter"] = 0

    # 1. Parametri generali de calcul (Client / Adaos, Utilaj / Grilă, Monedă finală, Curs BNR)
    c_top1, c_top2, c_top3 = st.columns([2.2, 1.3, 1.5], vertical_alignment="bottom")
    with c_top1:
        opt_firme = ["-- Client Standard (Adaos manual) --"] + list(firme_dict.keys())
        sel_firma_sim = st.selectbox("Client (pentru preluare automată adaos & utilaje)", options=opt_firme, key="sim_sel_firma")
        if sel_firma_sim != "-- Client Standard (Adaos manual) --":
            client_obj = firme_dict[sel_firma_sim]
            adaos_implicit = float(client_obj.get("adaos_comercial", 20.0) or 20.0)
            masini_firma = MasiniRepository.get_by_firma(client_obj["id"])
        else:
            adaos_implicit = 20.0
            masini_firma = []

    with c_top2:
        adaos_sim = st.number_input(
            "Adaos comercial piese (%)",
            min_value=0.0,
            max_value=500.0,
            value=adaos_implicit,
            step=1.0,
            key=f"sim_adaos_{sel_firma_sim}"
        )

    with c_top3:
        moneda_finala = st.selectbox("Monedă afișare preț final", options=["EUR", "RON"], index=0, key="sim_moneda_finala")

    c_sub1, c_sub2, c_sub3 = st.columns([2.5, 1.5, 1.0], vertical_alignment="bottom")
    grila_activa = None
    with c_sub1:
        if masini_firma:
            masini_dict = {m["denumire"]: m for m in masini_firma}
            sel_m_sim = st.selectbox(
                "Utilaj client (detectează automat Grila A / B)",
                options=["-- Toate grilele --"] + list(masini_dict.keys()),
                key="sim_sel_masina"
            )
            if sel_m_sim != "-- Toate grilele --":
                grila_activa = MasiniRepository.determina_grila_efectiva(masini_dict[sel_m_sim])
                st.caption(f"💶 Grilă activă utilaj: **{grila_activa}**")
        else:
            st.caption("ℹ️ Selectează o firmă pentru a filtra automat după grila utilajului.")

    with c_sub2:
        curs_sim = st.number_input(
            "Curs BNR (1 EUR = X RON)",
            value=float(st.session_state["sim_curs_bnr"]),
            step=0.0001,
            format="%.4f",
            key="sim_input_curs"
        )
        st.session_state["sim_curs_bnr"] = curs_sim

    with c_sub3:
        if st.button("🔄 Curs BNR", key="sim_btn_bnr", use_container_width=True):
            obtine_curs_bnr.clear()
            st.session_state["sim_curs_bnr"] = obtine_curs_bnr()
            st.rerun()

    st.markdown("---")

    # 2. Verificare rapidă instantă (1 produs sau 1 serviciu) + adăugare în lista de simulare
    tab_piesa, tab_serviciu = st.tabs(["🔩 Verificare Rapidă Piesă (Catalog)", "🛠️ Verificare Rapidă Serviciu / Tarif"])

    with tab_piesa:
        piese_dict = {}
        for p in piese_catalog:
            val_p = str(p.get("valuta_achizitie") or "RON").strip().upper()
            if val_p not in ("RON", "EUR"):
                val_p = "RON"
            cod_p = str(p.get("cod_producator") or "").strip()
            nume_afis = f"{p['denumire']} ({cod_p})" if cod_p else p["denumire"]
            label_p = f"{nume_afis} | Achiziție: {float(p.get('pret_achizitie') or 0):.2f} {val_p}"
            piese_dict[label_p] = p

        cp1, cp2, cp3 = st.columns([3, 1, 1.2], vertical_alignment="bottom")
        with cp1:
            sel_p_sim = st.selectbox("Alege piesa din catalog", options=["-- Selectează piesa --"] + list(piese_dict.keys()), key="sim_sel_piesa")
        with cp2:
            cant_p_sim = st.number_input("Cantitate", min_value=0.01, value=1.0, step=1.0, key="sim_cant_piesa")
        with cp3:
            add_p_sim = st.button("➕ Adaugă în listă", key="sim_btn_add_piesa", use_container_width=True)

        if sel_p_sim != "-- Selectează piesa --":
            p_obj = piese_dict[sel_p_sim]
            val_src = str(p_obj.get("valuta_achizitie") or "RON").strip().upper()
            if val_src not in ("RON", "EUR"):
                val_src = "RON"
            pret_ach = float(p_obj.get("pret_achizitie") or 0.0)
            pret_vanz_src = round(pret_ach * (1.0 + adaos_sim / 100.0), 2)
            pret_unit_final = converteste_in_moneda_oferta(pret_vanz_src, val_src, moneda_finala, curs_sim)
            val_fara_tva = round(pret_unit_final * float(cant_p_sim), 2)
            val_cu_tva = round(val_fara_tva * (1.0 + cota_tva_procent / 100.0), 2)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Preț Achiziție", f"{pret_ach:,.2f} {val_src}")
            m2.metric(f"Preț Vânzare (+{adaos_sim:g}%)", f"{pret_unit_final:,.2f} {moneda_finala} / buc")
            m3.metric(f"Total ({cant_p_sim:g} buc) fără TVA", f"{val_fara_tva:,.2f} {moneda_finala}")
            m4.metric(f"Total cu TVA ({cota_tva_procent:g}%)", f"{val_cu_tva:,.2f} {moneda_finala}")

            if add_p_sim:
                cod_p = str(p_obj.get("cod_producator") or "").strip()
                desc_p = f"{p_obj['denumire']} ({cod_p})" if cod_p else str(p_obj["denumire"])
                rand_nou = pd.DataFrame([{
                    "Tip": "Piesă",
                    "Descriere": desc_p,
                    "UM": "buc",
                    "Cantitate": float(cant_p_sim),
                    "Pret Achizitie/Baza": pret_ach,
                    "Adaos %": float(adaos_sim),
                    "Pret Unitar": pret_vanz_src,
                    "Moneda": val_src
                }])
                st.session_state["df_sim_cos"] = pd.concat([st.session_state["df_sim_cos"], rand_nou], ignore_index=True)
                st.session_state["sim_editor_counter"] += 1
                st.toast(f"✅ Adăugat în simulare: {desc_p}")

    with tab_serviciu:
        opt_gr = ["Toate grilele", "Nivel A", "Nivel B"]
        idx_gr = opt_gr.index(grila_activa) if grila_activa in opt_gr else 0
        filtru_gr = st.radio("Grilă tarifare:", options=opt_gr, index=idx_gr, horizontal=True, key="sim_radio_grila")

        tarife_filt = (
            [t for t in tarife_disponibile if str(t.get("nivel_grila") or "Nivel A").strip() == filtru_gr]
            if filtru_gr != "Toate grilele"
            else tarife_disponibile
        )
        tarife_dict = {
            f"[{t.get('nivel_grila') or 'Nivel A'}] {t['descriere']} ({float(t['pret']):.2f} {t['moneda_um']})": t
            for t in tarife_filt
        }

        cs1, cs2, cs3 = st.columns([3, 1, 1.2], vertical_alignment="bottom")
        with cs1:
            sel_t_sim = st.selectbox("Alege serviciul / tariful", options=["-- Selectează serviciul --"] + list(tarife_dict.keys()), key="sim_sel_tarif")
        with cs2:
            cant_t_sim = st.number_input("Cantitate", min_value=0.01, value=1.0, step=0.5, key="sim_cant_tarif")
        with cs3:
            add_t_sim = st.button("➕ Adaugă în listă", key="sim_btn_add_tarif", use_container_width=True)

        if sel_t_sim != "-- Selectează serviciul --":
            t_obj = tarife_dict[sel_t_sim]
            pret_t_baza = round(float(t_obj["pret"]), 2)
            mon_um_brut = str(t_obj.get("moneda_um") or "RON").upper()
            mon_t_src = "EUR" if "EUR" in mon_um_brut else "RON"
            um_t = normalizeaza_um(mon_um_brut)

            pret_t_final = converteste_in_moneda_oferta(pret_t_baza, mon_t_src, moneda_finala, curs_sim)
            val_t_fara_tva = round(pret_t_final * float(cant_t_sim), 2)
            val_t_cu_tva = round(val_t_fara_tva * (1.0 + cota_tva_procent / 100.0), 2)

            if este_ore_transport(t_obj["descriere"]) and float(cant_t_sim) > MAX_ORE_TRANSPORT_ZI:
                st.warning(f"⚠️ Atenție: limita maximă pentru ore de transport este {int(MAX_ORE_TRANSPORT_ZI)} ore/zi.")

            ms1, ms2, ms3 = st.columns(3)
            ms1.metric(f"Tarif Unitar ({um_t})", f"{pret_t_final:,.2f} {moneda_finala}")
            ms2.metric(f"Total ({cant_t_sim:g} {um_t}) fără TVA", f"{val_t_fara_tva:,.2f} {moneda_finala}")
            ms3.metric(f"Total cu TVA ({cota_tva_procent:g}%)", f"{val_t_cu_tva:,.2f} {moneda_finala}")

            if add_t_sim:
                rand_t_nou = pd.DataFrame([{
                    "Tip": "Serviciu",
                    "Descriere": t_obj["descriere"],
                    "UM": um_t,
                    "Cantitate": float(cant_t_sim),
                    "Pret Achizitie/Baza": pret_t_baza,
                    "Adaos %": 0.0,
                    "Pret Unitar": pret_t_baza,
                    "Moneda": mon_t_src
                }])
                st.session_state["df_sim_cos"] = pd.concat([st.session_state["df_sim_cos"], rand_t_nou], ignore_index=True)
                st.session_state["sim_editor_counter"] += 1
                st.toast(f"✅ Adăugat în simulare: {t_obj['descriere']}")

    # 3. Coș de simulare multi-reper (poți combina piese + manoperă + transport și vezi totalul instant)
    st.markdown("---")
    c_cos1, c_cos2 = st.columns([4, 1], vertical_alignment="center")
    with c_cos1:
        st.markdown("##### 📋 Listă Simulare Multi-Reper (Combină produse și servicii)")
    with c_cos2:
        if st.button("🗑️ Golește lista", key="sim_btn_clear", use_container_width=True):
            st.session_state["df_sim_cos"] = pd.DataFrame(
                columns=["Tip", "Descriere", "UM", "Cantitate", "Pret Achizitie/Baza", "Adaos %", "Pret Unitar", "Moneda"]
            )
            st.session_state["sim_editor_counter"] += 1
            st.rerun()

    df_sim_editat = st.data_editor(
        st.session_state["df_sim_cos"],
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "Tip": st.column_config.SelectboxColumn("Tip", options=["Piesă", "Serviciu"], default="Piesă", width="small"),
            "Descriere": st.column_config.TextColumn("Denumire Produs / Serviciu", width="large"),
            "UM": st.column_config.SelectboxColumn("UM", options=["buc", "ore", "set", "ml", "kg", "km", "intervenție", "proiect"], default="buc", width="small"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, format="%.2f", default=1.0, width="small"),
            "Pret Achizitie/Baza": st.column_config.NumberColumn("Preț Bază", min_value=0.0, format="%.2f", default=0.0, width="small"),
            "Adaos %": st.column_config.NumberColumn("Adaos %", min_value=0.0, format="%.1f", default=0.0, width="small"),
            "Pret Unitar": st.column_config.NumberColumn("Preț Vânzare", min_value=0.0, format="%.2f", default=0.0, width="small"),
            "Moneda": st.column_config.SelectboxColumn("Moneda", options=["RON", "EUR"], default="EUR", width="small"),
        },
        key=f"sim_editor_{st.session_state['sim_editor_counter']}",
        use_container_width=True
    )

    if not df_sim_editat.empty:
        df_valid_sim = df_sim_editat[df_sim_editat["Descriere"].fillna("").astype(str).str.strip() != ""]
        sub_sim = 0.0
        for _, r in df_valid_sim.iterrows():
            c_val = float(pd.to_numeric(r.get("Cantitate"), errors="coerce") or 0.0)
            p_val = float(pd.to_numeric(r.get("Pret Unitar"), errors="coerce") or 0.0)
            m_val = str(r.get("Moneda") or "RON").strip().upper()
            p_conv = converteste_in_moneda_oferta(p_val, m_val, moneda_finala, curs_sim)
            sub_sim += round(c_val * p_conv, 2)

        sub_sim = round(sub_sim, 2)
        tva_sim = round(sub_sim * (cota_tva_procent / 100.0), 2)
        tot_sim = round(sub_sim + tva_sim, 2)

        st.success(
            f"💰 **TOTAL SIMULARE ({moneda_finala}):** **{sub_sim:,.2f} {moneda_finala}** fără TVA | "
            f"TVA ({cota_tva_procent:g}%): **{tva_sim:,.2f} {moneda_finala}** | "
            f"**TOTAL FINAL CU TVA: {tot_sim:,.2f} {moneda_finala}** (curs BNR: {curs_sim:.4f})"
        )
