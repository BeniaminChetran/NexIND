# ----------------------------------
# -------pages/masuratori.py--------
# ----------------------------------

from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.masuratori_repository import MasuratoriRepository
from utils.context_selectie import aplica_context_la_tab, seteaza_context_selectie

_UNITATI_MASURA = [
    "°C",
    "bar",
    "mm",
    "mm/s",
    "RPM",
    "V",
    "A",
    "Hz",
    "dB",
    "kW",
    "Ohm",
    "%",
    "Altul",
]


def _invalideaza_cache_masuratori() -> None:
    clear_fn = getattr(MasuratoriRepository.get_by_masina, "clear", None)
    if callable(clear_fn):
        try:
            clear_fn()
        except Exception:
            pass


def _construieste_masuratori_in_derulare(masuratori_db: list[dict]) -> list[dict]:
    """
    Grupează măsurătorile existente ale mașinii în sesiuni/serii în derulare
    (pe subansamblu și dată) astfel încât utilizatorul să poată selecta ușor o măsurătoare începută.
    """
    if not masuratori_db:
        return []

    grupuri: dict[str, dict] = {}
    for m in masuratori_db:
        sub = str(m.get("subansamblu") or "General").strip() or "General"
        param = str(m.get("parametru") or "").strip()
        dt_str = str(m.get("data_masurare") or "")[:10]
        cheie = f"{sub.lower()}__{dt_str}"

        if cheie not in grupuri:
            grupuri[cheie] = {
                "cheie": cheie,
                "subansamblu": sub,
                "data_str": dt_str,
                "nr_citiri": 0,
                "parametri": [],
                "ultima_valoare": None,
            }
        g = grupuri[cheie]
        g["nr_citiri"] += 1
        if param and param not in g["parametri"]:
            g["parametri"].append(param)
        if g["ultima_valoare"] is None:
            try:
                val_f = float(m.get("valoare"))
                unit_s = str(m.get("unitate_masura") or "").strip()
                g["ultima_valoare"] = f"{val_f:+.3f} {unit_s}".strip()
            except (TypeError, ValueError):
                g["ultima_valoare"] = None

    rezultat = []
    for idx, g in enumerate(grupuri.values(), start=1):
        param_txt = ", ".join(g["parametri"][:3]) if g["parametri"] else "fără parametri"
        ult_txt = f" | Ultima: {g['ultima_valoare']}" if g["ultima_valoare"] else ""
        data_txt = f" ({g['data_str']})" if g["data_str"] else ""
        g["eticheta"] = (
            f"#{idx} — {g['subansamblu']}{data_txt} • {param_txt} "
            f"[{g['nr_citiri']} citiri{ult_txt}]"
        )
        rezultat.append(g)
    return rezultat


def _colecteaza_subansambluri(
    masina_obj_val: dict,
    masuratori_db: list[dict],
    extra_list: list[str],
) -> list[str]:
    subansambluri: list[str] = []
    vazute: set[str] = set()

    def _adauga(val: str | None) -> None:
        txt = str(val or "").strip()
        if not txt:
            return
        low = txt.lower()
        if low not in vazute:
            vazute.add(low)
            subansambluri.append(txt)

    if masina_obj_val.get("subansambluri"):
        for s in str(masina_obj_val["subansambluri"]).split(","):
            _adauga(s)

    for m_row in masuratori_db:
        _adauga(m_row.get("subansamblu"))

    for s_ext in extra_list:
        _adauga(s_ext)

    return subansambluri


def _persista_subansamblu_pe_masina(
    masina_obj_val: dict,
    subansambluri: list[str],
    extra_key: str,
    sub_nou: str,
) -> None:
    lista_noua_str = ", ".join(subansambluri)
    with db_cursor() as c:
        c.execute(
            "UPDATE masini SET subansambluri = %s WHERE id = %s",
            (lista_noua_str, masina_obj_val["id"]),
        )
    masina_obj_val["subansambluri"] = lista_noua_str
    st.session_state.setdefault(extra_key, [])
    if sub_nou not in st.session_state[extra_key]:
        st.session_state[extra_key].append(sub_nou)


def render_masuratori():
    st.subheader("📏 Înregistrare Parametri Tehnici & Grafic Evoluție")

    firme_db = FirmeRepository.get_all() or []
    firme_dict = {f["nume_firma"]: f["id"] for f in firme_db}

    if not firme_dict:
        st.warning("⚠️ Adăugați mai întâi cel puțin o firmă în baza de date.")
        return

    opt_firme = list(firme_dict.keys())
    aplica_context_la_tab(
        tab_prefix="mas_f",
        optiuni_firme=opt_firme,
        default_firma=opt_firme[0],
        key_firma="masuratori_sel_firma",
    )

    col1, col2 = st.columns(2)
    with col1:
        sel_firma_nume = st.selectbox("1. Alege Firma", options=opt_firme, key="masuratori_sel_firma")
        firma_id = firme_dict[sel_firma_nume]

    masini_db = MasiniRepository.get_by_firma(firma_id) or []
    masini_dict = {m["denumire"]: m for m in masini_db}

    with col2:
        if not masini_dict:
            seteaza_context_selectie(firma=sel_firma_nume, masina=None)
            st.warning("⚠️ Nu există mașini înregistrate pentru această firmă.")
            return

        opt_masini = list(masini_dict.keys())
        aplica_context_la_tab(
            tab_prefix=f"mas_m_{firma_id}",
            optiuni_firme=opt_firme,
            default_firma=sel_firma_nume,
            key_firma="masuratori_sel_firma",
            optiuni_masini=opt_masini,
            default_masina=opt_masini[0],
            key_masina="masuratori_sel_masina",
        )
        if st.session_state.get("masuratori_sel_masina") not in opt_masini:
            st.session_state["masuratori_sel_masina"] = opt_masini[0]

        sel_masina_nume = st.selectbox("2. Alege Mașina", options=opt_masini, key="masuratori_sel_masina")
        masina_obj = masini_dict[sel_masina_nume]

    seteaza_context_selectie(firma=sel_firma_nume, masina=sel_masina_nume)
    st.markdown("---")

    @st.fragment
    def render_form_si_grafic(firma_id_val: int, masina_obj_val: dict):
        m_id = masina_obj_val["id"]
        m_nume = masina_obj_val["denumire"]
        extra_key = f"mas_sub_extra_{m_id}"
        pending_sub_key = f"_mas_pending_sub_{m_id}"
        sub_select_key = f"mas_sel_sub_{m_id}"
        sub_nou_key = f"mas_nou_sub_{m_id}"
        sel_derulare_key = f"mas_sel_derulare_{m_id}"
        last_derulare_key = f"_mas_last_derulare_{m_id}"

        masuratori_db = MasuratoriRepository.get_by_masina(m_id) or []
        sesiuni_derulare = _construieste_masuratori_in_derulare(masuratori_db)
        subansambluri_existente = _colecteaza_subansambluri(
            masina_obj_val=masina_obj_val,
            masuratori_db=masuratori_db,
            extra_list=st.session_state.get(extra_key, []),
        )

        st.markdown(f"### ➕ Introducere Măsurătoare Nouă ({m_nume})")

        op_derulare = ["➕ Măsurătoare nouă"] + [s["eticheta"] for s in sesiuni_derulare]
        sel_derulare = st.selectbox(
            "Măsurători deja în derulare (pentru această mașină)",
            options=op_derulare,
            key=sel_derulare_key,
            help="Alege o măsurătoare în derulare pentru a continua măsurătorile pe subansamblul ei sau lasă 'Măsurătoare nouă'.",
        )

        sub_din_derulare = None
        if sel_derulare != "➕ Măsurătoare nouă":
            match_ses = next((s for s in sesiuni_derulare if s["eticheta"] == sel_derulare), None)
            if match_ses:
                sub_din_derulare = match_ses["subansamblu"]
                st.info(
                    f"📌 Continui măsurătoarea în derulare: **{match_ses['subansamblu']}** "
                    f"({match_ses['nr_citiri']} citiri înregistrate)."
                )

        if sub_din_derulare and st.session_state.get(last_derulare_key) != sel_derulare:
            st.session_state[last_derulare_key] = sel_derulare
            if sub_din_derulare in subansambluri_existente:
                st.session_state[pending_sub_key] = sub_din_derulare

        opt_sub = subansambluri_existente if subansambluri_existente else ["General"]

        # Aplicăm valoarea pregătită ÎNAINTE de instanțierea widget-ului `sub_select_key`
        pending_sub = st.session_state.pop(pending_sub_key, None)
        if pending_sub and pending_sub in opt_sub:
            st.session_state[sub_select_key] = pending_sub
        elif st.session_state.get(sub_select_key) not in opt_sub:
            st.session_state[sub_select_key] = opt_sub[0]

        c_sub1, c_sub2, c_sub3 = st.columns([2.2, 2.0, 1.1], vertical_alignment="bottom")
        with c_sub1:
            subansamblu_ales = st.selectbox(
                "Subansamblu de măsurat",
                options=opt_sub,
                key=sub_select_key,
            )
        with c_sub2:
            subansamblu_nou = st.text_input(
                "Sau creează subansamblu nou de măsurat",
                placeholder="ex: Axă Z, Pompă hidraulică, Tablou PLC...",
                key=sub_nou_key,
            ).strip()
        with c_sub3:
            if st.button("➕ Creează subansamblu", key=f"btn_creeaza_sub_{m_id}", use_container_width=True):
                if not subansamblu_nou:
                    st.warning("Introdu numele subansamblului nou.")
                else:
                    if subansamblu_nou.lower() not in [s.lower() for s in subansambluri_existente]:
                        subansambluri_existente.append(subansamblu_nou)
                        _persista_subansamblu_pe_masina(
                            masina_obj_val=masina_obj_val,
                            subansambluri=subansambluri_existente,
                            extra_key=extra_key,
                            sub_nou=subansamblu_nou,
                        )
                    st.session_state[pending_sub_key] = subansamblu_nou
                    st.toast(f"✅ Subansamblul '{subansamblu_nou}' este pregătit pentru măsurare.")
                    st.rerun(scope="fragment")

        sub_activ_implicit = subansamblu_nou or subansamblu_ales

        with st.form(f"form_adauga_masuratoare_{m_id}", clear_on_submit=False):
            f_col1, f_col2 = st.columns(2)

            with f_col1:
                subansamblu_input = st.text_input(
                    "Subansamblu activ pentru măsurătoare",
                    value=sub_activ_implicit,
                    help="Poți ajusta direct sau folosi subansamblul selectat / creat mai sus.",
                )
                parametru_input = st.text_input(
                    "Parametru măsurat (ex: Temperatură, Joc axial, Presiune, Vibrații)"
                )

            with f_col2:
                valoare_input = st.number_input(
                    "Valoare Măsurată (cu semn +/-)",
                    format="%.3f",
                    step=0.001,
                    help="Acceptă valori pozitive sau negative (ex: +23.450 sau -0.125)",
                )

                unitate_input = st.selectbox("Unitate de Măsură", options=_UNITATI_MASURA)
                if unitate_input == "Altul":
                    unitate_custom = st.text_input("Specifică unitatea de măsură")
                    if unitate_custom:
                        unitate_input = unitate_custom

            btn_salveaza = st.form_submit_button("💾 Salvează Măsurătoarea", type="primary")

            if btn_salveaza:
                if not subansamblu_input.strip() or not parametru_input.strip():
                    st.error("Te rugăm să completezi subansamblul și denumirea parametrului.")
                else:
                    sub_curat = subansamblu_input.strip()

                    MasuratoriRepository.insert({
                        "firma_id": firma_id_val,
                        "masina_id": m_id,
                        "subansamblu": sub_curat,
                        "parametru": parametru_input.strip(),
                        "valoare": valoare_input,
                        "unitate_masura": unitate_input,
                        "data_masurare": datetime.now(),
                    })

                    if sub_curat.lower() not in [s.lower() for s in subansambluri_existente]:
                        subansambluri_existente.append(sub_curat)
                        _persista_subansamblu_pe_masina(
                            masina_obj_val=masina_obj_val,
                            subansambluri=subansambluri_existente,
                            extra_key=extra_key,
                            sub_nou=sub_curat,
                        )

                    _invalideaza_cache_masuratori()
                    st.session_state[pending_sub_key] = sub_curat
                    st.success(
                        f"Măsurătoarea pentru '{parametru_input}' ({valoare_input:+.3f} {unitate_input}) "
                        f"pe subansamblul '{sub_curat}' a fost salvată!"
                    )
                    st.rerun(scope="fragment")

        st.markdown("---")
        st.markdown(f"### 📈 Grafic Evoluție Parametri Măsurați — **{m_nume}**")

        if not masuratori_db:
            st.info("Nu există încă măsurători înregistrate pentru această mașină.")
            return

        df_masuratori = pd.DataFrame(masuratori_db)
        df_masuratori["data_masurare"] = pd.to_datetime(df_masuratori["data_masurare"])
        df_masuratori["valoare"] = df_masuratori["valoare"].astype(float)
        df_masuratori["eticheta_parametru"] = (
            df_masuratori["subansamblu"].astype(str)
            + " - "
            + df_masuratori["parametru"].astype(str)
            + " ("
            + df_masuratori["unitate_masura"].astype(str)
            + ")"
        )

        parametri_unic = list(df_masuratori["eticheta_parametru"].unique())
        sel_param_grafic = st.multiselect(
            "Filtrează Parametrii pe Grafic",
            options=parametri_unic,
            default=parametri_unic,
        )

        if sel_param_grafic:
            df_filtrat = df_masuratori[df_masuratori["eticheta_parametru"].isin(sel_param_grafic)]

            fig = px.line(
                df_filtrat,
                x="data_masurare",
                y="valoare",
                color="eticheta_parametru",
                markers=True,
                title=f"Evoluția în Timp a Parametrilor Tehnici ({m_nume})",
                labels={
                    "data_masurare": "Timp (Data & Ora)",
                    "valoare": "Valoare Măsurată",
                    "eticheta_parametru": "Parametru / Subansamblu",
                },
                hover_data={"valoare": ":+.3f", "unitate_masura": True, "subansamblu": True},
            )

            fig.update_layout(
                xaxis=dict(autorange=True, title="Timp Scurs"),
                yaxis=dict(autorange=True, title="Valoare Parametru"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                template="plotly_dark",
                height=450,
            )

            st.plotly_chart(fig, use_container_width=True, key=f"grafic_masuratori_{m_id}")

            st.markdown("#### 📋 Tabel Istoric Măsurători")
            df_afisare = df_filtrat[["data_masurare", "subansamblu", "parametru", "valoare", "unitate_masura"]].copy()
            df_afisare.columns = ["Data & Ora", "Subansamblu", "Parametru", "Valoare Măsurată", "Unitate"]
            df_afisare["Valoare Măsurată"] = df_afisare["Valoare Măsurată"].map("{:+.3f}".format)
            st.dataframe(df_afisare, use_container_width=True)

    render_form_si_grafic(firma_id, masina_obj)