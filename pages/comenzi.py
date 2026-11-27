# ----------------------------------
# -------pages/comenzi.py-----------
# ----------------------------------

import json
from typing import Any
import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.necesar_piese_repository import NecesarPieseRepository
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_repository import ReparatiiRepository

EDITOR_KEY = "comenzi_editor_clienti_stabil"

STARI_VALIDE_LOW = frozenset({
    "de comandat", "necesara", "necesare",
    "de căutat", "de cautat",
    "de ofertat",
    "comandată", "comandata",
    "în așteptare", "in asteptare",
    "anulată", "anulata",
})

STARI_DE_COMANDAT_RAW = frozenset({"de comandat", "necesara", "necesare"})

CHEI_FURNIZOR = (
    "furnizor",
    "nume_furnizor",
    "furnizor_principal",
    "supplier",
    "link_furnizor",
)

CHEI_DENUMIRE_COMP = (
    "Componenta / Cod / Parametri",
    "Componenta",
    "Piesa",
    "piesa",
    "denumire",
)


def _norm_text(val: Any, default: str = "") -> str:
    if val is None:
        return default
    text = " ".join(str(val).strip().lower().split())
    return text if text else default


def _clean_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _to_float(val: Any, default: float = 1.0) -> float:
    if val is None or isinstance(val, bool):
        return default
    try:
        num = float(val)
        return num if pd.notna(num) else default
    except (TypeError, ValueError):
        return default


def _to_int_or_none(val: Any) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        if pd.isna(val):
            return None
        s = str(val).strip()
        if not s:
            return None
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _parse_json_list(raw_val: Any) -> list[dict[str, Any]]:
    items = raw_val
    if isinstance(raw_val, str):
        s = raw_val.strip()
        if not s:
            return []
        try:
            items = json.loads(s)
        except Exception:
            return []
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _normalizeaza_stare_comanda_sigur(stare_raw: Any, fallback: str = "De comandat") -> str:
    txt = _clean_str(stare_raw)
    if not txt:
        return _normalizeaza_stare_comanda(fallback)
    if txt.lower() in STARI_DE_COMANDAT_RAW:
        return "De comandat"
    return _normalizeaza_stare_comanda(txt)


def _extrage_furnizor_piesa(piesa_row: dict[str, Any]) -> str:
    for k in CHEI_FURNIZOR:
        val = _clean_str(piesa_row.get(k))
        if val:
            return val
    return "Fără furnizor setat"


def _extrage_denumire_comp(item: dict[str, Any]) -> str:
    for k in CHEI_DENUMIRE_COMP:
        val = _clean_str(item.get(k))
        if val:
            return val
    return ""


def _actualizeaza_stare_in_raport_json(
    tabela: str,
    record_id: int,
    den_piesa: str,
    stare_noua: str,
) -> bool:
    if tabela not in ("reparatii", "reparatii_electronice"):
        return False
    camp_json = "piese_json" if tabela == "reparatii" else "componente_json"
    den_target = _norm_text(den_piesa)
    if not den_target:
        return False

    with db_cursor() as c:
        c.execute(f"SELECT {camp_json} FROM {tabela} WHERE id = %s", (int(record_id),))
        fetched = c.fetchone()
        if not fetched:
            return False
        row = fetched if isinstance(fetched, dict) else dict(fetched)
        items = _parse_json_list(row.get(camp_json))
        if not items:
            return False

        modificat = False
        for item in items:
            den_item_norm = _norm_text(_extrage_denumire_comp(item))
            if not den_item_norm:
                continue
            if den_item_norm == den_target or (
                den_target in den_item_norm or den_item_norm in den_target
            ):
                if tabela == "reparatii_electronice":
                    item["Stare"] = stare_noua
                elif tabela == "reparatii":
                    item["Tip"] = stare_noua
                item["stare_comandata"] = stare_noua
                modificat = True

        if modificat:
            c.execute(
                f"UPDATE {tabela} SET {camp_json} = %s WHERE id = %s",
                (json.dumps(items, ensure_ascii=False), int(record_id)),
            )
            if hasattr(c, "connection") and hasattr(c.connection, "commit"):
                c.connection.commit()
    return modificat


@st.cache_data(ttl=120)
def _incarca_catalog_piese() -> tuple[dict[str, str], dict[str, int | None], dict[str, str]]:
    piese_db = PieseRepository.get_all() or []
    furnizor_map: dict[str, str] = {}
    piesa_id_by_name: dict[str, int | None] = {}
    stare_catalog_by_name: dict[str, str] = {}

    for p in piese_db:
        if not isinstance(p, dict):
            continue
        den = _clean_str(p.get("denumire") or p.get("nume"))
        if not den:
            continue
        cheie = _norm_text(den)
        furnizor_map[cheie] = _extrage_furnizor_piesa(p)
        piesa_id_by_name[cheie] = _to_int_or_none(p.get("id"))
        stare_catalog_by_name[cheie] = _normalizeaza_stare_comanda_sigur(
            p.get("stare_comandata"), fallback="De comandat"
        )

    return furnizor_map, piesa_id_by_name, stare_catalog_by_name


@st.cache_data(ttl=120)
def _incarca_sursa_necesar(
    furnizor_map: dict[str, str],
    piesa_id_by_name: dict[str, int | None],
) -> list[dict[str, Any]]:
    necesar_rows = NecesarPieseRepository.get_all() or []
    randuri: list[dict[str, Any]] = []

    for np_row in necesar_rows:
        if not isinstance(np_row, dict):
            continue
        den_np = _clean_str(np_row.get("denumire_piesa"))
        if not den_np:
            continue
        cheie = _norm_text(den_np)
        rec_id = _to_int_or_none(np_row.get("id"))
        furnizor_np = _clean_str(np_row.get("furnizor_piesa")) or furnizor_map.get(
            cheie, "Fără furnizor setat"
        )
        randuri.append({
            "_uid": f"necesar_piese:{rec_id}:{_norm_text(den_np)}:{len(randuri)}",
            "_necesar_id": rec_id,
            "_piesa_id": _to_int_or_none(np_row.get("piesa_id")) or piesa_id_by_name.get(cheie),
            "_sursa_tbl": "necesar_piese",
            "_sursa_rec_id": rec_id,
            "Furnizor": furnizor_np,
            "Piesă": den_np,
            "Cantitate": _to_float(np_row.get("cantitate"), default=1.0),
            "Status Comandă": _normalizeaza_stare_comanda_sigur(
                np_row.get("status_comanda"), fallback="De comandat"
            ),
            "Sursă": "Teren / Necesar",
            "Firmă": _clean_str(np_row.get("firma_client"), default="-"),
            "Mașină": _clean_str(np_row.get("masina"), default="-"),
            "Raport": f"NP #{rec_id}" if rec_id is not None else "NP #-",
        })

    return randuri


@st.cache_data(ttl=120)
def _incarca_sursa_reparatii(
    furnizor_map: dict[str, str],
    piesa_id_by_name: dict[str, int | None],
    stare_catalog_by_name: dict[str, str],
) -> list[dict[str, Any]]:
    rapoarte = ReparatiiRepository.get_all() or []
    randuri: list[dict[str, Any]] = []

    for r in rapoarte:
        if not isinstance(r, dict):
            continue
        rec_id = _to_int_or_none(r.get("id"))
        piese_raw = r.get("piese_valide")
        if not piese_raw:
            piese_raw = r.get("piese_json")
        items = _parse_json_list(piese_raw)

        firma_txt = _clean_str(r.get("firma"), default="-")
        masina_txt = _clean_str(r.get("masina"), default="-")
        raport_txt = f"#{rec_id}" if rec_id is not None else "#-"

        for item in items:
            den_piesa = _clean_str(item.get("Piesa") or item.get("piesa") or item.get("denumire"))
            if not den_piesa:
                continue
            tip_piesa = _clean_str(item.get("Tip") or item.get("tip"))
            stare_item = _clean_str(item.get("stare_comandata") or item.get("Stare") or tip_piesa)
            if (
                stare_item.lower() not in STARI_VALIDE_LOW
                and tip_piesa.lower() not in STARI_VALIDE_LOW
            ):
                continue

            cant = item.get("Cantitate")
            if cant is None:
                cant = item.get("cantitate", 1.0)

            cheie = _norm_text(den_piesa)
            if stare_item:
                stare_curenta = _normalizeaza_stare_comanda_sigur(stare_item, fallback="De comandat")
            elif cheie in stare_catalog_by_name:
                stare_curenta = stare_catalog_by_name[cheie]
            else:
                stare_curenta = "De comandat"

            randuri.append({
                "_uid": f"reparatii:{rec_id}:{cheie}:{len(randuri)}",
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii",
                "_sursa_rec_id": rec_id,
                "Furnizor": furnizor_map.get(cheie, "Fără furnizor setat"),
                "Piesă": den_piesa,
                "Cantitate": _to_float(cant, default=1.0),
                "Status Comandă": stare_curenta,
                "Sursă": "Mașini",
                "Firmă": firma_txt,
                "Mașină": masina_txt,
                "Raport": raport_txt,
            })

    return randuri


@st.cache_data(ttl=120)
def _incarca_sursa_electronice(
    furnizor_map: dict[str, str],
    piesa_id_by_name: dict[str, int | None],
) -> list[dict[str, Any]]:
    try:
        with db_cursor() as c:
            c.execute(
                """
                SELECT id, firma_nume, masina_nume, piesa_subansamblu, componente_json
                FROM reparatii_electronice
                ORDER BY id DESC
                """
            )
            fetched = c.fetchall() or []
            fise_el = [row if isinstance(row, dict) else dict(row) for row in fetched]
    except Exception:
        fise_el = []

    randuri: list[dict[str, Any]] = []
    for f_el in fise_el:
        rec_id = _to_int_or_none(f_el.get("id"))
        items = _parse_json_list(f_el.get("componente_json"))
        firma_txt = _clean_str(f_el.get("firma_nume"), default="-")
        masina_txt = _clean_str(
            f_el.get("masina_nume") or f_el.get("piesa_subansamblu"), default="-"
        )
        raport_txt = f"EL #{rec_id}" if rec_id is not None else "EL #-"

        for comp in items:
            den_comp = _extrage_denumire_comp(comp)
            if not den_comp:
                continue
            stare_comp = _clean_str(comp.get("stare_comandata") or comp.get("Stare"))
            if stare_comp.lower() not in STARI_VALIDE_LOW:
                continue

            cant_c = comp.get("Cantitate")
            if cant_c is None:
                cant_c = comp.get("cantitate", 1.0)

            cheie = _norm_text(den_comp)
            randuri.append({
                "_uid": f"reparatii_electronice:{rec_id}:{cheie}:{len(randuri)}",
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii_electronice",
                "_sursa_rec_id": rec_id,
                "Furnizor": furnizor_map.get(cheie, "Fără furnizor setat"),
                "Piesă": den_comp,
                "Cantitate": _to_float(cant_c, default=1.0),
                "Status Comandă": _normalizeaza_stare_comanda_sigur(
                    stare_comp, fallback="De comandat"
                ),
                "Sursă": "Electronică",
                "Firmă": firma_txt,
                "Mașină": masina_txt,
                "Raport": raport_txt,
            })

    return randuri


def _incarca_date_comenzi_unificate() -> list[dict[str, Any]]:
    furnizor_map, piesa_id_by_name, stare_catalog_by_name = _incarca_catalog_piese()
    randuri: list[dict[str, Any]] = []
    randuri.extend(_incarca_sursa_necesar(furnizor_map, piesa_id_by_name))
    randuri.extend(
        _incarca_sursa_reparatii(furnizor_map, piesa_id_by_name, stare_catalog_by_name)
    )
    randuri.extend(_incarca_sursa_electronice(furnizor_map, piesa_id_by_name))

    for idx, r in enumerate(randuri, start=1):
        r["_row_id"] = idx
    return randuri


def _goleste_cache_comenzi() -> None:
    _incarca_date_comenzi_unificate.clear()
    _incarca_sursa_necesar.clear()
    _incarca_sursa_reparatii.clear()
    _incarca_sursa_electronice.clear()
    _incarca_catalog_piese.clear()
    for repo_cls in (PieseRepository, NecesarPieseRepository, ReparatiiRepository):
        get_all_fn = getattr(repo_cls, "get_all", None)
        clear_fn = getattr(get_all_fn, "clear", None)
        if callable(clear_fn):
            try:
                clear_fn()
            except Exception:
                pass


def _salveaza_stari_modificate(
    df_editor_init: pd.DataFrame,
    edited_df: pd.DataFrame,
    meta_map: dict[str, dict[str, Any]],
) -> tuple[int, list[str]]:
    df_final = edited_df.copy()
    if "Status Comandă" in df_final.columns:
        df_final["Status Comandă"] = df_final["Status Comandă"].astype(object)

    state_ed = st.session_state.get(EDITOR_KEY)
    if isinstance(state_ed, dict):
        for idx_key, changes in (state_ed.get("edited_rows") or {}).items():
            try:
                idx = int(idx_key)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df_final) and isinstance(changes, dict):
                for col_name, new_val in changes.items():
                    if col_name in df_final.columns:
                        df_final.at[idx, col_name] = (
                            _normalizeaza_stare_comanda_sigur(new_val)
                            if col_name == "Status Comandă"
                            else new_val
                        )

    orig_map = {
        _clean_str(r.get("_uid")): _normalizeaza_stare_comanda_sigur(r.get("Status Comandă"))
        for _, r in df_editor_init.iterrows()
    }

    nr_mod = 0
    erori: list[str] = []

    for _, row in df_final.iterrows():
        uid = _clean_str(row.get("_uid"))
        if not uid:
            continue
        stare_noua = _normalizeaza_stare_comanda_sigur(row.get("Status Comandă"))
        stare_veche = _normalizeaza_stare_comanda_sigur(orig_map.get(uid))
        if stare_veche == stare_noua:
            continue

        meta = meta_map.get(uid) or {}
        sursa_tbl = _clean_str(meta.get("_sursa_tbl"))
        necesar_id = _to_int_or_none(meta.get("_necesar_id"))
        piesa_id = _to_int_or_none(meta.get("_piesa_id"))
        sursa_rec_id = _to_int_or_none(meta.get("_sursa_rec_id"))
        den_piesa = _clean_str(row.get("Piesă"))

        salvat = False
        try:
            if sursa_tbl == "necesar_piese":
                if necesar_id is not None:
                    NecesarPieseRepository.update_status_comanda(necesar_id, stare_noua)
                    salvat = True
                else:
                    erori.append(f"Necesar fără ID valid pentru '{den_piesa}'.")
            elif sursa_tbl in ("reparatii", "reparatii_electronice"):
                if sursa_rec_id is not None and _actualizeaza_stare_in_raport_json(
                    sursa_tbl, sursa_rec_id, den_piesa, stare_noua
                ):
                    salvat = True
                if piesa_id is not None:
                    PieseRepository.update_stare_comandata(piesa_id, stare_noua)
                    salvat = True
                if not salvat:
                    erori.append(
                        f"Nu s-a putut actualiza poziția '{den_piesa}' în {sursa_tbl}."
                    )
            else:
                erori.append(f"Sursă necunoscută '{sursa_tbl}' pentru '{den_piesa}'.")
        except Exception as e:
            erori.append(f"{sursa_tbl or 'înregistrare'} ({den_piesa}): {e}")

        if salvat:
            nr_mod += 1

    return nr_mod, erori


def render_comenzi() -> None:
    col_t, col_r = st.columns([5, 1])
    with col_t:
        st.subheader("📦 Comenzi — Către Furnizori & De la Clienți")
    with col_r:
        if st.button("🔄 Actualizează", use_container_width=True, key="btn_comenzi_refresh"):
            _goleste_cache_comenzi()
            if EDITOR_KEY in st.session_state:
                del st.session_state[EDITOR_KEY]

    randuri = _incarca_date_comenzi_unificate()
    if not randuri:
        st.info(
            "Nu există piese înregistrate pentru comenzi către furnizori sau solicitări de la clienți."
        )
        return

    df = pd.DataFrame(randuri)

    c1, c2, c3, c4 = st.columns([1.2, 1.4, 1.4, 1.5])
    with c1:
        filtru_sursa = st.selectbox(
            "Sursă",
            options=["Toate", "Teren / Necesar", "Mașini", "Electronică"],
            key="comenzi_filtru_sursa",
        )
    with c2:
        opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].dropna().unique().tolist())
        filtru_furn = st.selectbox("Furnizor", options=opt_furn, key="comenzi_filtru_furn")
    with c3:
        filtru_stare = st.selectbox(
            "Status Comandă",
            options=["Toate stările"] + OPTIUNI_STARE_COMANDA,
            key="comenzi_filtru_stare",
        )
    with c4:
        cautare_txt = _norm_text(
            st.text_input(
                "Caută piesă / client / mașină",
                placeholder="ex: rulment, firmă, cod...",
                key="comenzi_cautare_txt",
            )
        )

    mask = pd.Series(True, index=df.index)
    if filtru_sursa != "Toate":
        mask &= df["Sursă"] == filtru_sursa
    if filtru_furn != "Toți furnizorii":
        mask &= df["Furnizor"] == filtru_furn
    if filtru_stare != "Toate stările":
        mask &= df["Status Comandă"] == filtru_stare
    if cautare_txt:
        mask &= (
            df["Piesă"].str.lower().str.contains(cautare_txt, case=False, regex=False, na=False)
            | df["Firmă"].str.lower().str.contains(cautare_txt, case=False, regex=False, na=False)
            | df["Mașină"].str.lower().str.contains(cautare_txt, case=False, regex=False, na=False)
            | df["Furnizor"].str.lower().str.contains(cautare_txt, case=False, regex=False, na=False)
        )

    df_f = df[mask]
    if df_f.empty:
        st.info("Nu există înregistrări care să corespundă filtrelor curente.")
        return

    tab_furnizori, tab_clienti = st.tabs([
        "🏭 Către Furnizori (Centralizator Cantități)",
        "🏢 De la Clienți (Cereri & Status Comandă)",
    ])

    with tab_furnizori:
        st.markdown("##### 📊 Centralizator Cantități Către Furnizori")
        st.caption(
            "Cantitățile sunt însumate pe **Status Comandă**, **Furnizor** și **Piesă**, "
            "incluzând cererile cumulate de la mai mulți clienți sau rapoarte."
        )

        df_sum = (
            df_f.groupby(["Status Comandă", "Furnizor", "Piesă"], as_index=False)["Cantitate"]
            .sum()
            .sort_values(["Status Comandă", "Furnizor", "Piesă"])
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Repere unice centralizate", len(df_sum))
        m2.metric("Cantitate totală cumulată", f"{df_sum['Cantitate'].sum():.2f}")
        m3.metric("Furnizori vizați", df_sum["Furnizor"].nunique())

        st.dataframe(
            df_sum,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Status Comandă": st.column_config.TextColumn("Status Comandă", width="medium"),
                "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                "Piesă": st.column_config.TextColumn("Piesă", width="large"),
                "Cantitate": st.column_config.NumberColumn(
                    "Cantitate Totală", format="%.2f", width="small"
                ),
            },
        )

    with tab_clienti:
        st.markdown("##### 📋 Cereri / Necesar Piese De la Clienți")
        firme_disp = ["Toate firmele"] + sorted(
            [f for f in df_f["Firmă"].dropna().unique().tolist() if f and f != "-"]
        )
        sel_firma_cmd = st.selectbox(
            "Filtrează după client (firmă)",
            options=firme_disp,
            key="comenzi_clienti_sel_firma",
        )

        df_cli = df_f[df_f["Firmă"] == sel_firma_cmd] if sel_firma_cmd != "Toate firmele" else df_f
        if df_cli.empty:
            st.info("Nu există piese pentru clientul selectat.")
            return

        cols_afis = [
            "_uid",
            "Firmă",
            "Mașină",
            "Piesă",
            "Cantitate",
            "Status Comandă",
            "Furnizor",
            "Sursă",
            "Raport",
        ]
        df_editor_init = df_cli[cols_afis].reset_index(drop=True)

        edited_df = st.data_editor(
            df_editor_init,
            key=EDITOR_KEY,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["_uid", "Firmă", "Mașină", "Piesă", "Cantitate", "Furnizor", "Sursă", "Raport"],
            column_config={
                "_uid": None,
                "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
                "Mașină": st.column_config.TextColumn("Mașină", width="medium"),
                "Piesă": st.column_config.TextColumn("Piesă", width="large"),
                "Cantitate": st.column_config.NumberColumn("Cantitate", format="%.2f", width="small"),
                "Status Comandă": st.column_config.SelectboxColumn(
                    "Status Comandă",
                    options=OPTIUNI_STARE_COMANDA,
                    required=True,
                    width="medium",
                ),
                "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                "Sursă": st.column_config.TextColumn("Sursă", width="small"),
                "Raport": st.column_config.TextColumn("Raport", width="small"),
            },
        )

        if st.button("💾 Actualizează Stările Comenzilor", type="primary", key="btn_comenzi_save_stari"):
            meta_map: dict[str, dict[str, Any]] = {}
            for _, r in df_cli.iterrows():
                uid = _clean_str(r.get("_uid"))
                if uid and uid not in meta_map:
                    meta_map[uid] = {
                        "_necesar_id": r.get("_necesar_id"),
                        "_piesa_id": r.get("_piesa_id"),
                        "_sursa_tbl": r.get("_sursa_tbl"),
                        "_sursa_rec_id": r.get("_sursa_rec_id"),
                    }

            nr_mod, erori = _salveaza_stari_modificate(df_editor_init, edited_df, meta_map)

            if EDITOR_KEY in st.session_state:
                del st.session_state[EDITOR_KEY]

            if nr_mod > 0:
                _goleste_cache_comenzi()

            if erori:
                st.error("⚠️ Erori la salvare:\n" + "\n".join(erori))
            elif nr_mod == 0:
                st.info("ℹ️ Nu există modificări nesalvate.")
            else:
                st.success(f"✅ Au fost actualizate **{nr_mod}** poziții.")