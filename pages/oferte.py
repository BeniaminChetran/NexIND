# ----------------------------------
# -------pages/masuratori.py--------
# ----------------------------------

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.masuratori_repository import MasuratoriRepository
from utils.context_selectie import aplica_context_la_tab, seteaza_context_selectie


@dataclass(frozen=True)
class ConfigMasuratori:
    zecimale: int = 3
    max_parametri_eticheta: int = 3
    grafic_inaltime: int = 450
    grafic_linie_latime: float = 2.5
    grafic_marker_marime: int = 8
    focus_max_incercari: int = 8
    focus_interval_ms: int = 60
    focus_delay_initial_ms: int = 50
    subansamblu_implicit: str = "General"
    eticheta_masuratoare_noua: str = "➕ Măsurătoare nouă"
    eticheta_alege_parametru: str = "— Alege parametru existent —"
    unitate_alta: str = "Altul"
    unitati_masura: tuple[str, ...] = (
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
    )
    paleta_culori: tuple[str, ...] = (
        "#00E5FF",
        "#FF5252",
        "#69F0AE",
        "#FFD740",
        "#E040FB",
        "#FF9100",
        "#448AFF",
        "#FF80AB",
        "#B2FF59",
        "#18FFFF",
        "#EA80FC",
        "#FFE57F",
    )
    label_valoare: str = "Valoare Măsurată (cu semn +/-)"

    @property
    def pas_numeric(self) -> float:
        return 10 ** (-self.zecimale)

    @property
    def format_input(self) -> str:
        return f"%.{self.zecimale}f"

    @property
    def format_cu_semn(self) -> str:
        return f"{{:+.{self.zecimale}f}}"

    @property
    def format_hover(self) -> str:
        return f":+.{self.zecimale}f"


CFG = ConfigMasuratori()


def _chei_masina(m_id: int) -> dict[str, str]:
    return {
        "extra_sub": f"_mas_extra_sub_{m_id}",
        "sub_selectat": f"_mas_sub_sel_{m_id}",
        "sub_nou_input": f"mas_nou_sub_{m_id}",
        "derulare_selectat": f"mas_sel_derulare_{m_id}",
        "param_dd": f"mas_param_dd_{m_id}",
        "param_edit": f"mas_param_edit_{m_id}",
        "unit_sel": f"mas_unit_sel_{m_id}",
        "unit_custom": f"mas_unit_custom_{m_id}",
        "focus_token": f"_mas_focus_val_{m_id}",
        "sub_input_form": f"mas_sub_form_{m_id}",
        "val_input_form": f"mas_val_form_{m_id}",
        "grafic_multisel": f"mas_grafic_sel_{m_id}",
    }


def _curata_text(val: Any) -> str:
    return str(val or "").strip()


def _cheie_canonica(val: Any) -> str:
    return _curata_text(val).lower()


def _focalizeaza_valoare_masurata(trigger_id: str, cfg: ConfigMasuratori = CFG) -> None:
    if not trigger_id:
        return
    components.html(
        f"""
        <script>
        (function() {{
            const token = {trigger_id!r};
            const targetLabel = {cfg.label_valoare!r};
            const maxAttempts = {cfg.focus_max_incercari!r};
            const intervalMs = {cfg.focus_interval_ms!r};
            const initialDelayMs = {cfg.focus_delay_initial_ms!r};
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
                if (attempt < maxAttempts) {{
                    setTimeout(() => tryFocus(attempt + 1), intervalMs);
                }}
            }}
            setTimeout(() => tryFocus(0), initialDelayMs);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _invalideaza_cache_masuratori() -> None:
    clear_fn = getattr(MasuratoriRepository.get_by_masina, "clear", None)
    if callable(clear_fn):
        clear_fn()


def _parseaza_subansambluri_string(raw_str: Any) -> list[str]:
    txt = _curata_text(raw_str)
    if not txt:
        return []
    return [_curata_text(item) for item in txt.split(",") if _curata_text(item)]


@st.cache_data(show_spinner=False)
def _analizeaza_masuratori(
    m_id: int,
    subansambluri_masina_raw: str,
    extra_subansambluri: tuple[str, ...],
    masuratori_db: list[dict[str, Any]],
    cfg: ConfigMasuratori = CFG,
) -> dict[str, Any]:
    subansambluri: list[str] = []
    vazute_sub: set[str] = set()

    def _adauga_sub(val: Any) -> None:
        curat = _curata_text(val)
        cheie = _cheie_canonica(curat)
        if curat and cheie not in vazute_sub:
            vazute_sub.add(cheie)
            subansambluri.append(curat)

    for s_item in _parseaza_subansambluri_string(subansambluri_masina_raw):
        _adauga_sub(s_item)
    for m_row in masuratori_db:
        _adauga_sub(m_row.get("subansamblu"))
    for s_ext in extra_subansambluri:
        _adauga_sub(s_ext)

    if not subansambluri:
        subansambluri = [cfg.subansamblu_implicit]

    grupuri: dict[str, dict[str, Any]] = {}
    unitati_dupa_sub_param: dict[tuple[str, str], str] = {}
    unitati_dupa_param: dict[str, str] = {}
    parametri_toti: list[str] = []
    vazute_param: set[str] = set()
    sub_la_parametri: dict[str, list[str]] = {}

    fmt_val = cfg.format_cu_semn

    for m_row in masuratori_db:
        sub = _curata_text(m_row.get("subansamblu")) or cfg.subansamblu_implicit
        sub_low = _cheie_canonica(sub)
        param = _curata_text(m_row.get("parametru"))
        param_low = _cheie_canonica(param)
        unit = _curata_text(m_row.get("unitate_masura"))
        dt_str = _curata_text(m_row.get("data_masurare"))[:10]

        if param and param_low not in vazute_param:
            vazute_param.add(param_low)
            parametri_toti.append(param)

        if param:
            sub_la_parametri.setdefault(sub_low, [])
            if param_low not in [_cheie_canonica(p) for p in sub_la_parametri[sub_low]]:
                sub_la_parametri[sub_low].append(param)

        if unit and param_low:
            unitati_dupa_param.setdefault(param_low, unit)
            unitati_dupa_sub_param.setdefault((sub_low, param_low), unit)

        cheie_grup = f"{sub_low}__{dt_str}"
        if cheie_grup not in grupuri:
            grupuri[cheie_grup] = {
                "cheie": cheie_grup,
                "subansamblu": sub,
                "data_str": dt_str,
                "nr_citiri": 0,
                "parametri": [],
                "ultima_valoare": None,
            }

        g = grupuri[cheie_grup]
        g["nr_citiri"] += 1
        if param and param not in g["parametri"]:
            g["parametri"].append(param)
        if g["ultima_valoare"] is None:
            try:
                val_f = float(m_row.get("valoare"))
                g["ultima_valoare"] = f"{fmt_val.format(val_f)} {unit}".strip()
            except (TypeError, ValueError):
                g["ultima_valoare"] = None

    sesiuni_derulare: list[dict[str, Any]] = []
    for idx, g in enumerate(grupuri.values(), start=1):
        param_txt = (
            ", ".join(g["parametri"][: cfg.max_parametri_eticheta])
            if g["parametri"]
            else "fără parametri"
        )
        ult_txt = f" | Ultima: {g['ultima_valoare']}" if g["ultima_valoare"] else ""
        data_txt = f" ({g['data_str']})" if g["data_str"] else ""
        g["eticheta"] = (
            f"#{idx} — {g['subansamblu']}{data_txt} • {param_txt} "
            f"[{g['nr_citiri']} citiri{ult_txt}]"
        )
        sesiuni_derulare.append(g)

    return {
        "subansambluri": subansambluri,
        "sesiuni_derulare": sesiuni_derulare,
        "parametri_toti": parametri_toti,
        "sub_la_parametri": sub_la_parametri,
        "unitati_dupa_sub_param": unitati_dupa_sub_param,
        "unitati_dupa_param": unitati_dupa_param,
    }


def _parametri_ordonati_pentru_subansamblu(
    analiza: dict[str, Any],
    subansamblu_activ: str,
) -> list[str]:
    sub_low = _cheie_canonica(subansamblu_activ)
    prioritari_low = set(analiza["sub_la_parametri"].get(sub_low, []))
    prioritari = [p for p in analiza["parametri_toti"] if _cheie_canonica(p) in prioritari_low]
    alti = [p for p in analiza["parametri_toti"] if _cheie_canonica(p) not in prioritari_low]
    return prioritari + alti


def _gaseste_unitate(
    analiza: dict[str, Any],
    parametru_nume: str | None,
    subansamblu_nume: str | None = None,
) -> str | None:
    p_low = _cheie_canonica(parametru_nume)
    if not p_low:
        return None
    s_low = _cheie_canonica(subansamblu_nume)
    if s_low and (s_low, p_low) in analiza["unitati_dupa_sub_param"]:
        return analiza["unitati_dupa_sub_param"][(s_low, p_low)]
    return analiza["unitati_dupa_param"].get(p_low)


def _persista_subansamblu_daca_lipseste(
    m_id: int,
    subansambluri_curente: list[str],
    sub_nou: str,
    extra_key: str,
    cfg: ConfigMasuratori = CFG,
) -> list[str]:
    sub_curat = _curata_text(sub_nou)
    if not sub_curat:
        return subansambluri_curente

    cheie_noua = _cheie_canonica(sub_curat)
    exista_deja = any(_cheie_canonica(s) == cheie_noua for s in subansambluri_curente)
    if exista_deja:
        return subansambluri_curente

    lista_actualizata = [*subansambluri_curente, sub_curat]
    with db_cursor() as c:
        c.execute(
            "UPDATE masini SET subansambluri = %s WHERE id = %s",
            (", ".join(lista_actualizata), m_id),
        )

    extra_existent = list(st.session_state.get(extra_key, []))
    if cheie_noua not in {_cheie_canonica(x) for x in extra_existent}:
        extra_existent.append(sub_curat)
        st.session_state[extra_key] = extra_existent

    _invalideaza_cache_masuratori()
    return lista_actualizata


def _on_change_derulare(
    m_id: int,
    sesiuni_map: dict[str, str],
    subansambluri_valide: list[str],
    cfg: ConfigMasuratori = CFG,
) -> None:
    keys = _chei_masina(m_id)
    ales = st.session_state.get(keys["derulare_selectat"])
    if not ales or ales == cfg.eticheta_masuratoare_noua:
        return
    sub_tinta = sesiuni_map.get(ales)
    if sub_tinta and sub_tinta in subansambluri_valide:
        st.session_state[keys["sub_selectat"]] = sub_tinta
        st.session_state[keys["sub_input_form"]] = sub_tinta


def _on_click_creeaza_subansamblu(
    m_id: int,
    subansambluri_curente: list[str],
    cfg: ConfigMasuratori = CFG,
) -> None:
    keys = _chei_masina(m_id)
    sub_nou = _curata_text(st.session_state.get(keys["sub_nou_input"]))
    if not sub_nou:
        return
    lista_noua = _persista_subansamblu_daca_lipseste(
        m_id=m_id,
        subansambluri_curente=subansambluri_curente,
        sub_nou=sub_nou,
        extra_key=keys["extra_sub"],
        cfg=cfg,
    )
    st.session_state[keys["sub_selectat"]] = sub_nou
    st.session_state[keys["sub_input_form"]] = sub_nou
    st.session_state[keys["sub_nou_input"]] = ""
    if sub_nou in lista_noua:
        st.toast(f"✅ Subansamblul '{sub_nou}' este pregătit pentru măsurare.")


def _on_change_parametru_dd(
    m_id: int,
    analiza: dict[str, Any],
    subansamblu_activ: str,
    cfg: ConfigMasuratori = CFG,
) -> None:
    keys = _chei_masina(m_id)
    ales = _curata_text(st.session_state.get(keys["param_dd"]))
    if not ales or ales == cfg.eticheta_alege_parametru:
        return

    st.session_state[keys["param_edit"]] = ales
    unit_cunoscuta = _gaseste_unitate(analiza, ales, subansamblu_activ)
    if unit_cunoscuta:
        if unit_cunoscuta in cfg.unitati_masura:
            st.session_state[keys["unit_sel"]] = unit_cunoscuta
        else:
            st.session_state[keys["unit_sel"]] = cfg.unitate_alta
            st.session_state[keys["unit_custom"]] = unit_cunoscuta

    st.session_state[keys["focus_token"]] = f"{m_id}:{ales}:{datetime.now().timestamp()}"


@st.cache_data(show_spinner=False)
def _construieste_grafic_si_tabel(
    m_id: int,
    m_nume: str,
    masuratori_db: list[dict[str, Any]],
    parametri_selectati: tuple[str, ...],
    cfg: ConfigMasuratori = CFG,
) -> tuple[Any, pd.DataFrame | None]:
    if not masuratori_db or not parametri_selectati:
        return None, None

    df = pd.DataFrame(masuratori_db)
    df["data_masurare"] = pd.to_datetime(df["data_masurare"], errors="coerce")
    df["valoare"] = pd.to_numeric(df["valoare"], errors="coerce")
    df = df.dropna(subset=["data_masurare", "valoare"])
    if df.empty:
        return None, None

    df["eticheta_parametru"] = (
        df["subansamblu"].map(_curata_text)
        + " - "
        + df["parametru"].map(_curata_text)
        + " ("
        + df["unitate_masura"].map(_curata_text)
        + ")"
    )

    toti_parametri = list(dict.fromkeys(df["eticheta_parametru"].tolist()))
    df_filtrat = (
        df[df["eticheta_parametru"].isin(parametri_selectati)]
        .sort_values("data_masurare")
    )
    if df_filtrat.empty:
        return None, None

    paleta = cfg.paleta_culori
    color_map = {
        lbl: paleta[i % len(paleta)]
        for i, lbl in enumerate(toti_parametri)
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
        hover_data={
            "valoare": cfg.format_hover,
            "unitate_masura": True,
            "subansamblu": True,
        },
    )

    fig.update_traces(
        line=dict(width=cfg.grafic_linie_latime),
        marker=dict(size=cfg.grafic_marker_marime),
    )
    fig.update_layout(
        xaxis=dict(autorange=True, title="Timp Scurs"),
        yaxis=dict(autorange=True, title="Valoare Parametru"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        height=cfg.grafic_inaltime,
    )

    df_tabel = df_filtrat[
        ["data_masurare", "subansamblu", "parametru", "valoare", "unitate_masura"]
    ].copy()
    df_tabel.columns = ["Data & Ora", "Subansamblu", "Parametru", "Valoare Măsurată", "Unitate"]
    df_tabel["Valoare Măsurată"] = df_tabel["Valoare Măsurată"].map(cfg.format_cu_semn.format)
    return fig, df_tabel


def render_masuratori(cfg: ConfigMasuratori = CFG) -> None:
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
        sel_firma_nume = st.selectbox(
            "1. Alege Firma",
            options=opt_firme,
            key="masuratori_sel_firma",
        )
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

        sel_masina_nume = st.selectbox(
            "2. Alege Mașina",
            options=opt_masini,
            key="masuratori_sel_masina",
        )
        masina_obj = masini_dict[sel_masina_nume]

    seteaza_context_selectie(firma=sel_firma_nume, masina=sel_masina_nume)
    st.markdown("---")

    @st.fragment
    def render_form_si_grafic(firma_id_val: int, masina_obj_val: dict[str, Any]) -> None:
        m_id = masina_obj_val["id"]
        m_nume = masina_obj_val["denumire"]
        keys = _chei_masina(m_id)

        masuratori_db = MasuratoriRepository.get_by_masina(m_id) or []
        extra_sub = tuple(st.session_state.get(keys["extra_sub"], ()))
        analiza = _analizeaza_masuratori(
            m_id=m_id,
            subansambluri_masina_raw=masina_obj_val.get("subansambluri") or "",
            extra_subansambluri=extra_sub,
            masuratori_db=masuratori_db,
            cfg=cfg,
        )

        subansambluri_opt = analiza["subansambluri"]
        sesiuni_derulare = analiza["sesiuni_derulare"]
        sesiuni_map = {s["eticheta"]: s["subansamblu"] for s in sesiuni_derulare}

        st.session_state.setdefault(keys["sub_selectat"], subansambluri_opt[0])
        if st.session_state[keys["sub_selectat"]] not in subansambluri_opt:
            st.session_state[keys["sub_selectat"]] = subansambluri_opt[0]

        st.session_state.setdefault(keys["sub_input_form"], st.session_state[keys["sub_selectat"]])
        st.session_state.setdefault(keys["param_edit"], "")
        st.session_state.setdefault(keys["unit_sel"], cfg.unitati_masura[0])

        st.markdown(f"### ➕ Introducere Măsurătoare Nouă ({m_nume})")

        op_derulare = [cfg.eticheta_masuratoare_noua, *sesiuni_map.keys()]
        sel_derulare = st.selectbox(
            "Măsurători deja în derulare (pentru această mașină)",
            options=op_derulare,
            key=keys["derulare_selectat"],
            on_change=_on_change_derulare,
            args=(m_id, sesiuni_map, subansambluri_opt, cfg),
            help="Alege o măsurătoare în derulare pentru a continua măsurătorile pe subansamblul ei sau lasă 'Măsurătoare nouă'.",
        )

        if sel_derulare != cfg.eticheta_masuratoare_noua and sel_derulare in sesiuni_map:
            ses_info = next((s for s in sesiuni_derulare if s["eticheta"] == sel_derulare), None)
            if ses_info:
                st.info(
                    f"📌 Continui măsurătoarea în derulare: **{ses_info['subansamblu']}** "
                    f"({ses_info['nr_citiri']} citiri înregistrate)."
                )

        c_sub1, c_sub2, c_sub3 = st.columns([2.2, 2.0, 1.1], vertical_alignment="bottom")
        with c_sub1:
            subansamblu_ales = st.selectbox(
                "Subansamblu de măsurat",
                options=subansambluri_opt,
                key=keys["sub_selectat"],
            )
        with c_sub2:
            subansamblu_nou = st.text_input(
                "Sau creează subansamblu nou de măsurat",
                placeholder="ex: Axă Z, Pompă hidraulică, Tablou PLC...",
                key=keys["sub_nou_input"],
            )
        with c_sub3:
            st.button(
                "➕ Creează subansamblu",
                key=f"btn_creeaza_sub_{m_id}",
                use_container_width=True,
                on_click=_on_click_creeaza_subansamblu,
                args=(m_id, subansambluri_opt, cfg),
            )

        sub_activ_implicit = _curata_text(subansamblu_nou) or subansamblu_ales
        if not st.session_state.get(keys["sub_input_form"]) and sub_activ_implicit:
            st.session_state[keys["sub_input_form"]] = sub_activ_implicit

        parametri_ordonati = _parametri_ordonati_pentru_subansamblu(analiza, sub_activ_implicit)
        opt_parametri = [cfg.eticheta_alege_parametru, *parametri_ordonati]

        st.selectbox(
            "Parametru existent (opțional — sau scrie direct în câmpul de parametru)",
            options=opt_parametri,
            key=keys["param_dd"],
            on_change=_on_change_parametru_dd,
            args=(m_id, analiza, sub_activ_implicit, cfg),
        )

        with st.form(f"form_adauga_masuratoare_{m_id}", clear_on_submit=False):
            f_col1, f_col2 = st.columns([1.15, 1.0])

            with f_col1:
                subansamblu_input = st.text_input(
                    "Subansamblu activ pentru măsurătoare",
                    key=keys["sub_input_form"],
                    help="Poți ajusta direct sau folosi subansamblul selectat / creat mai sus.",
                )
                valoare_input = st.number_input(
                    cfg.label_valoare,
                    format=cfg.format_input,
                    step=cfg.pas_numeric,
                    key=keys["val_input_form"],
                    help="Introdu valoarea măsurată (cu semn +/-) și apasă Salvează Măsurătoarea.",
                )
                btn_salveaza = st.form_submit_button(
                    "💾 Salvează Măsurătoarea",
                    type="primary",
                    use_container_width=True,
                )

            with f_col2:
                parametru_input = st.text_input(
                    "Parametru măsurat (ex: Temperatură, Joc axial, Presiune, Vibrații)",
                    key=keys["param_edit"],
                )
                unitate_input = st.selectbox(
                    "Unitate de Măsură",
                    options=cfg.unitati_masura,
                    key=keys["unit_sel"],
                )
                if unitate_input == cfg.unitate_alta:
                    unitate_custom = _curata_text(
                        st.text_input("Specifică unitatea de măsură", key=keys["unit_custom"])
                    )
                    if unitate_custom:
                        unitate_input = unitate_custom

            if btn_salveaza:
                sub_curat = _curata_text(subansamblu_input)
                param_curat = _curata_text(parametru_input)

                if not sub_curat:
                    st.error("Te rugăm să selectezi sau să completezi subansamblul.")
                elif not param_curat:
                    st.warning("⚠️ Nu ai selectat și nici nu ai completat parametrul măsurat.")
                else:
                    MasuratoriRepository.insert({
                        "firma_id": firma_id_val,
                        "masina_id": m_id,
                        "subansamblu": sub_curat,
                        "parametru": param_curat,
                        "valoare": valoare_input,
                        "unitate_masura": unitate_input,
                        "data_masurare": datetime.now(),
                    })
                    _persista_subansamblu_daca_lipseste(
                        m_id=m_id,
                        subansambluri_curente=subansambluri_opt,
                        sub_nou=sub_curat,
                        extra_key=keys["extra_sub"],
                        cfg=cfg,
                    )
                    _invalideaza_cache_masuratori()
                    st.session_state[keys["sub_selectat"]] = sub_curat
                    masuratori_db = MasuratoriRepository.get_by_masina(m_id) or []
                    st.success(
                        f"Măsurătoarea pentru '{param_curat}' "
                        f"({cfg.format_cu_semn.format(valoare_input)} {unitate_input}) "
                        f"pe subansamblul '{sub_curat}' a fost salvată!"
                    )

        focus_token = st.session_state.pop(keys["focus_token"], None)
        if focus_token:
            _focalizeaza_valoare_masurata(focus_token, cfg=cfg)

        st.markdown("---")
        st.markdown(f"### 📈 Grafic Evoluție Parametri Măsurați — **{m_nume}**")

        if not masuratori_db:
            st.info("Nu există încă măsurători înregistrate pentru această mașină.")
            return

        etichete_disponibile = list(
            dict.fromkeys(
                f"{_curata_text(r.get('subansamblu'))} - {_curata_text(r.get('parametru'))} "
                f"({_curata_text(r.get('unitate_masura'))})"
                for r in masuratori_db
            )
        )

        sel_param_grafic = st.multiselect(
            "Filtrează Parametrii pe Grafic",
            options=etichete_disponibile,
            default=etichete_disponibile,
            key=keys["grafic_multisel"],
        )

        fig, df_tabel = _construieste_grafic_si_tabel(
            m_id=m_id,
            m_nume=m_nume,
            masuratori_db=masuratori_db,
            parametri_selectati=tuple(sel_param_grafic),
            cfg=cfg,
        )

        if fig is not None and df_tabel is not None:
            st.plotly_chart(fig, use_container_width=True, key=f"grafic_masuratori_{m_id}")
            st.markdown("#### 📋 Tabel Istoric Măsurători")
            st.dataframe(df_tabel, use_container_width=True)

    render_form_si_grafic(firma_id, masina_obj)