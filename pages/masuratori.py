# ----------------------------------
# -------pages/masuratori.py--------
# ----------------------------------

from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

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

_PALETA_CULORI_PARAMETRI = [
    "#00E5FF",  # cyan electric
    "#FF5252",  # roșu coral
    "#69F0AE",  # verde mentă
    "#FFD740",  # galben ambră
    "#E040FB",  # mov magenta
    "#FF9100",  # portocaliu intens
    "#448AFF",  # albastru cobalt
    "#FF80AB",  # roz aprins
    "#B2FF59",  # verde lime
    "#18FFFF",  # turcoaz
    "#EA80FC",  # lavandă
    "#FFE57F",  # galben deschis
]

_VALOARE_LABEL = "Valoare Măsurată (cu semn +/-)"


def _focalizeaza_valoare_masurata(trigger_id: str) -> None:
    """Setează focusul în browser pe câmpul Valoare Măsurată la schimbarea parametrului."""
    if not trigger_id:
        return
    components.html(
        f"""
        <script>
        (function() {{
            const token = {trigger_id!r};
            const targetLabel = {_VALOARE_LABEL!r};
            function tryFocus(attempt) {{
                const doc = window.parent ? window.parent.document : document;
                const inputs = Array.from(doc.querySelectorAll('input'));
                const match = inputs.find((el) => el.getAttribute('aria-label') === targetLabel);
                if (match && typeof match.focus === 'function') {{
                    match.focus();
                    if (typeof match.select === 'function') {{
                        match.select();
                    }}
                    return;
                }}
                if (attempt < 8) {{
                    setTimeout(() => tryFocus(attempt + 1), 60);
                }}
            }}
            setTimeout(() => tryFocus(0), 50);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _invalideaza_cache_masuratori() -> None:
    clear_fn = getattr(MasuratoriRepository.get_by_masina, "clear", None)
    if callable(clear_fn):
        try:
            clear_fn()
        except Exception:
            pass


def _construieste_masuratori_in_derulare(masuratori_db: list[dict]) -> list[dict]:
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


def _colecteaza_parametri(
    masuratori_db: list[dict],
    subansamblu_filtru: str | None = None,
) -> list[str]:
    prioritari: list[str] = []
    alti: list[str] = []
    vazute: set[str] = set()
    filtru_low = str(subansamblu_filtru or "").strip().lower()

    for m_row in masuratori_db:
        param = str(m_row.get("parametru") or "").strip()
        if not param:
            continue
        low = param.lower()
        if low in vazute:
            continue
        vazute.add(low)
        sub_row = str(m_row.get("subansamblu") or "").strip().lower()
        if filtru_low and sub_row == filtru_low:
            prioritari.append(param)
        else:
            alti.append(param)

    return prioritari + alti


def _gaseste_unitate_parametru(
    masuratori_db: list[dict],
    parametru_nume: str | None,
    subansamblu_nume: str | None = None,
) -> str | None:
    """Returnează unitatea de măsură cunoscută pentru parametrul selectat."""
    param_low = str(parametru_nume or "").strip().lower()
    if not param_low:
        return None
    sub_low = str(subansamblu_nume or "").strip().lower()

    # 1. Caută prioritar pe același subansamblu
    if sub_low:
        for m_row in masuratori_db:
            if (
                str(m_row.get("parametru") or "").strip().lower() == param_low
                and str(m_row.get("subansamblu") or "").strip().lower() == sub_low
            ):
                unit = str(m_row.get("unitate_masura") or "").strip()
                if unit:
                    return unit

    # 2. Altfel caută pe orice înregistrare a parametrului pe mașină
    for m_row in masuratori_db:
        if str(m_row.get("parametru") or "").strip().lower() == param_low:
            unit = str(m_row.get("unitate_masura") or "").strip()
            if unit:
                return unit

    return None


def _persista_subansamblu_pe_masina(
    m_id: int,
    masina_obj_val: dict,
    subansambluri: list[str],
    extra_key: str,
    sub_nou: str,
) -> None:
    lista_noua_str = ", ".join(subansambluri)
    with db_cursor() as c:
        c.execute(
            "UPDATE masini SET subansambluri = %s WHERE id = %s",
            (lista_noua_str, m_id),
        )
    masina_obj_val["subansambluri"] = lista_noua_str
    extra_curent = list(st.session_state.get(extra_key, []))
    if sub_nou not in extra_curent:
        extra_curent.append(sub_nou)
        st.session_state[extra_key] = extra_curent


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
        sub_state_key = f"_mas_sub_curent_{m_id}"
        sub_nou_key = f"mas_nou_sub_{m_id}"
        sel_derulare_key = f"mas_sel_derulare_{m_id}"
        last_derulare_key = f"_mas_last_derulare_{m_id}"
        sub_widget_key = f"mas_sub_box_{m_id}"
        param_dropdown_key = f"mas_param_dd_{m_id}"
        last_param_dd_key = f"_mas_last_param_dd_{m_id}"
        param_edit_key = f"mas_param_edit_{m_id}"
        unit_select_key = f"mas_unit_sel_{m_id}"
        unit_custom_key = f"mas_unit_custom_{m_id}"
        focus_token_key = f"_mas_focus_val_{m_id}"

        masuratori_db = MasuratoriRepository.get_by_masina(m_id) or []
        sesiuni_derulare = _construieste_masuratori_in_derulare(masuratori_db)
        subansambluri_existente = _colecteaza_subansambluri(
            masina_obj_val=masina_obj_val,
            masuratori_db=masuratori_db,
            extra_list=st.session_state.get(extra_key, []),
        )
        opt_sub = subansambluri_existente if subansambluri_existente else ["General"]

        st.markdown(f"### ➕ Introducere Măsurătoare Nouă ({m_nume})")

        # 1. Selectare măsurătoare deja în derulare
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
            if sub_din_derulare in opt_sub:
                st.session_state[sub_state_key] = sub_din_derulare
                st.session_state.pop(sub_widget_key, None)
            st.session_state[focus_token_key] = f"derulare_{sel_derulare}_{datetime.now().timestamp()}"

        if st.session_state.get(sub_state_key) not in opt_sub:
            st.session_state[sub_state_key] = opt_sub[0]

        idx_sub = opt_sub.index(st.session_state[sub_state_key])

        # 2. Selectare sau creare subansamblu nou de măsurat
        c_sub1, c_sub2, c_sub3 = st.columns([2.2, 2.0, 1.1], vertical_alignment="bottom")
        with c_sub1:
            subansamblu_ales = st.selectbox(
                "Subansamblu de măsurat",
                options=opt_sub,
                index=idx_sub,
                key=sub_widget_key,
            )
            st.session_state[sub_state_key] = subansamblu_ales
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
                            m_id=m_id,
                            masina_obj_val=masina_obj_val,
                            subansambluri=subansambluri_existente,
                            extra_key=extra_key,
                            sub_nou=subansamblu_nou,
                        )
                    st.session_state[sub_state_key] = subansamblu_nou
                    st.session_state.pop(sub_widget_key, None)
                    st.toast(f"✅ Subansamblul '{subansamblu_nou}' este pregătit pentru măsurare.")

        sub_activ_implicit = subansamblu_nou or subansamblu_ales

        # 3. Dropdown parametru existent (scrie direct în editbox și setează unitatea de măsură)
        parametri_existenti = _colecteaza_parametri(
            masuratori_db=masuratori_db,
            subansamblu_filtru=sub_activ_implicit,
        )
        opt_parametri = ["— Alege parametru existent —"] + parametri_existenti

        parametru_dd = st.selectbox(
            "Parametru existent (opțional — sau scrie direct mai jos)",
            options=opt_parametri,
            key=param_dropdown_key,
        )

        st.session_state.setdefault(param_edit_key, "")
        st.session_state.setdefault(unit_select_key, _UNITATI_MASURA[0])

        if parametru_dd != st.session_state.get(last_param_dd_key):
            st.session_state[last_param_dd_key] = parametru_dd
            if not parametru_dd.startswith("—"):
                st.session_state[param_edit_key] = parametru_dd
                unit_cunoscuta = _gaseste_unitate_parametru(
                    masuratori_db=masuratori_db,
                    parametru_nume=parametru_dd,
                    subansamblu_nume=sub_activ_implicit,
                )
                if unit_cunoscuta:
                    if unit_cunoscuta in _UNITATI_MASURA:
                        st.session_state[unit_select_key] = unit_cunoscuta
                    else:
                        st.session_state[unit_select_key] = "Altul"
                        st.session_state[unit_custom_key] = unit_cunoscuta
                st.session_state[focus_token_key] = f"param_{parametru_dd}_{datetime.now().timestamp()}"

        with st.form(f"form_adauga_masuratoare_{m_id}", clear_on_submit=False):
            f_col1, f_col2 = st.columns([1.15, 1.0])

            with f_col1:
                subansamblu_input = st.text_input(
                    "Subansamblu activ pentru măsurătoare",
                    value=sub_activ_implicit,
                    help="Poți ajusta direct sau folosi subansamblul selectat / creat mai sus.",
                )
                parametru_input = st.text_input(
                    "Parametru măsurat (ex: Temperatură, Joc axial, Presiune, Vibrații)",
                    key=param_edit_key,
                )
                unitate_input = st.selectbox(
                    "Unitate de Măsură",
                    options=_UNITATI_MASURA,
                    key=unit_select_key,
                )
                if unitate_input == "Altul":
                    unitate_custom = st.text_input(
                        "Specifică unitatea de măsură",
                        key=unit_custom_key,
                    )
                    if unitate_custom:
                        unitate_input = unitate_custom

            with f_col2:
                st.markdown("##### 🎯 Valoare & Salvare Rapidă")
                valoare_input = st.number_input(
                    _VALOARE_LABEL,
                    format="%.3f",
                    step=0.001,
                    help="Introdu valoarea măsurată (cu semn +/-) și apasă Salvează Măsurătoarea.",
                )
                btn_salveaza = st.form_submit_button(
                    "💾 Salvează Măsurătoarea",
                    type="primary",
                    use_container_width=True,
                )

            if btn_salveaza:
                if not subansamblu_input.strip():
                    st.error("Te rugăm să selectezi sau să completezi subansamblul.")
                elif not parametru_input.strip():
                    st.warning("⚠️ Nu ai selectat și nici nu ai completat parametrul măsurat.")
                else:
                    sub_curat = subansamblu_input.strip()
                    param_curat = parametru_input.strip()

                    MasuratoriRepository.insert({
                        "firma_id": firma_id_val,
                        "masina_id": m_id,
                        "subansamblu": sub_curat,
                        "parametru": param_curat,
                        "valoare": valoare_input,
                        "unitate_masura": unitate_input,
                        "data_masurare": datetime.now(),
                    })

                    if sub_curat.lower() not in [s.lower() for s in subansambluri_existente]:
                        subansambluri_existente.append(sub_curat)
                        _persista_subansamblu_pe_masina(
                            m_id=m_id,
                            masina_obj_val=masina_obj_val,
                            subansambluri=subansambluri_existente,
                            extra_key=extra_key,
                            sub_nou=sub_curat,
                        )

                    _invalideaza_cache_masuratori()
                    st.session_state[sub_state_key] = sub_curat
                    st.session_state.pop(sub_widget_key, None)
                    masuratori_db = MasuratoriRepository.get_by_masina(m_id) or []
                    st.success(
                        f"Măsurătoarea pentru '{param_curat}' ({valoare_input:+.3f} {unitate_input}) "
                        f"pe subansamblul '{sub_curat}' a fost salvată!"
                    )

        focus_token = st.session_state.pop(focus_token_key, None)
        if focus_token:
            _focalizeaza_valoare_masurata(focus_token)

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
            df_filtrat = (
                df_masuratori[df_masuratori["eticheta_parametru"].isin(sel_param_grafic)]
                .sort_values("data_masurare")
            )

            color_map = {
                param_lbl: _PALETA_CULORI_PARAMETRI[i % len(_PALETA_CULORI_PARAMETRI)]
                for i, param_lbl in enumerate(parametri_unic)
            }

            fig = px.line(
                df_filtrat,
                x="data_masurare",
                y="valoare",
                color="eticheta_parametru",
                color_discrete_map=color_map,
                markers=True,
                title=f"Evoluția în Timp a Parametrilor Tehnici ({m_nume})",
                labels={
                    "data_masurare": "Timp (Data & Ora)",
                    "valoare": "Valoare Măsurată",
                    "eticheta_parametru": "Parametru / Subansamblu",
                },
                hover_data={"valoare": ":+.3f", "unitate_masura": True, "subansamblu": True},
            )

            fig.update_traces(line=dict(width=2.5), marker=dict(size=8))

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