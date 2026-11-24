

# ----------------------------------
# -------pages/comenzi.py-----------
# ----------------------------------

import json
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


def _extrage_furnizor_piesa(piesa_row: dict) -> str:
    for k in ("furnizor", "nume_furnizor", "furnizor_principal", "supplier", "link_furnizor"):
        val = str(piesa_row.get(k) or "").strip()
        if val:
            return val
    return "Fără furnizor setat"


def _actualizeaza_stare_in_raport_json(tabela: str, record_id: int, den_piesa: str, stare_noua: str) -> bool:
    camp_json = "piese_json" if tabela == "reparatii" else "componente_json"
    with db_cursor() as c:
        c.execute(f"SELECT {camp_json} FROM {tabela} WHERE id = %s", (int(record_id),))
        row = c.fetchone() or {}
        if not isinstance(row, dict):
            row = dict(row)
        raw_val = row.get(camp_json)
        items = raw_val
        if isinstance(raw_val, str):
            try:
                items = json.loads(raw_val)
            except Exception:
                items = []
        if not isinstance(items, list):
            return False

        modificat = False
        den_target = " ".join(str(den_piesa or "").strip().lower().split())
        for item in items:
            if not isinstance(item, dict):
                continue
            den_item = str(
                item.get("Componenta / Cod / Parametri")
                or item.get("Componenta")
                or item.get("Piesa")
                or item.get("piesa")
                or item.get("denumire")
                or ""
            ).strip()
            den_item_norm = " ".join(den_item.lower().split())
            if den_item_norm == den_target or (den_target and (den_target in den_item_norm or den_item_norm in den_target)):
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
def _incarca_date_comenzi_unificate() -> list[dict]:
    piese_db = PieseRepository.get_all() or []
    furnizor_map = {}
    piesa_id_by_name = {}
    stare_catalog_by_name = {}

    for p in piese_db:
        den = str(p.get("denumire") or p.get("nume") or "").strip()
        if den:
            cheie = " ".join(den.lower().split())
            furnizor_map[cheie] = _extrage_furnizor_piesa(p)
            piesa_id_by_name[cheie] = p.get("id")
            stare_catalog_by_name[cheie] = _normalizeaza_stare_comanda(p.get("stare_comandata"))

    randuri: list[dict] = []
    idx_counter = 0
    stari_valide_low = {
        "de comandat", "necesara", "necesare",
        "de căutat", "de cautat",
        "de ofertat",
        "comandată", "comandata",
        "în așteptare", "in asteptare",
        "anulată", "anulata",
    }

    # 1. Piese notate pe teren (`necesar_piese`)
    necesar_rows = NecesarPieseRepository.get_all() or []
    for np_row in necesar_rows:
        den_np = str(np_row.get("denumire_piesa") or "").strip()
        if not den_np:
            continue
        cheie = " ".join(den_np.lower().split())
        try:
            cant_num = float(np_row.get("cantitate") or 1.0)
        except Exception:
            cant_num = 1.0

        furnizor_np = str(np_row.get("furnizor_piesa") or "").strip() or furnizor_map.get(cheie, "Fără furnizor setat")
        idx_counter += 1
        randuri.append({
            "_row_id": idx_counter,
            "_necesar_id": np_row.get("id"),
            "_piesa_id": np_row.get("piesa_id") or piesa_id_by_name.get(cheie),
            "_sursa_tbl": "necesar_piese",
            "_sursa_rec_id": np_row.get("id"),
            "Furnizor": furnizor_np,
            "Piesă": den_np,
            "Cantitate": cant_num,
            "Status Comandă": _normalizeaza_stare_comanda(np_row.get("status_comanda")),
            "Sursă": "Teren / Necesar",
            "Firmă": str(np_row.get("firma_client") or "").strip() or "-",
            "Mașină": str(np_row.get("masina") or "").strip() or "-",
            "Raport": f"NP #{np_row.get('id')}",
        })

    # 2. Piese din rapoartele de Mașini (`reparatii`)
    rapoarte = ReparatiiRepository.get_all() or []
    for r in rapoarte:
        piese_raw = r.get("piese_valide")
        if not piese_raw:
            piese_raw = r.get("piese_json") or []
        if isinstance(piese_raw, str):
            try:
                piese_raw = json.loads(piese_raw)
            except Exception:
                piese_raw = []

        for item in piese_raw:
            if not isinstance(item, dict):
                continue
            den_piesa = str(item.get("Piesa") or item.get("piesa") or item.get("denumire") or "").strip()
            tip_piesa = str(item.get("Tip") or item.get("tip") or "").strip()
            stare_item = str(item.get("stare_comandata") or item.get("Stare") or tip_piesa or "").strip()
            if not den_piesa:
                continue
            if stare_item.lower() not in stari_valide_low and tip_piesa.lower() not in stari_valide_low:
                continue

            cant = item.get("Cantitate")
            if cant is None:
                cant = item.get("cantitate", 1)
            try:
                cant_num = float(cant)
            except Exception:
                cant_num = 1.0

            cheie = " ".join(den_piesa.lower().split())
            if stare_item.strip():
                stare_curenta = (
                    "De comandat"
                    if stare_item.lower() in ("de comandat", "necesara", "necesare")
                    else _normalizeaza_stare_comanda(stare_item)
                )
            elif cheie in stare_catalog_by_name:
                stare_curenta = stare_catalog_by_name[cheie]
            else:
                stare_curenta = "De comandat"

            furnizor = furnizor_map.get(cheie, "Fără furnizor setat")
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii",
                "_sursa_rec_id": r.get("id"),
                "Furnizor": furnizor,
                "Piesă": den_piesa,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Sursă": "Mașini",
                "Firmă": str(r.get("firma") or "").strip() or "-",
                "Mașină": str(r.get("masina") or "").strip() or "-",
                "Raport": f"#{r.get('id')}",
            })

    # 3. Componente din rapoartele de Reparații Electronice (`reparatii_electronice`)
    try:
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii_electronice ORDER BY id DESC")
            fise_el = [dict(row) for row in (c.fetchall() or [])]
    except Exception:
        fise_el = []

    for f_el in fise_el:
        comp_raw = f_el.get("componente_json") or []
        if isinstance(comp_raw, str):
            try:
                comp_raw = json.loads(comp_raw)
            except Exception:
                comp_raw = []

        for comp in comp_raw:
            if not isinstance(comp, dict):
                continue
            den_comp = str(
                comp.get("Componenta / Cod / Parametri")
                or comp.get("Componenta")
                or comp.get("piesa")
                or comp.get("denumire")
                or ""
            ).strip()
            stare_comp = str(comp.get("stare_comandata") or comp.get("Stare") or "").strip()
            if not den_comp or stare_comp.lower() not in stari_valide_low:
                continue

            cant_c = comp.get("Cantitate", 1.0)
            try:
                cant_num = float(cant_c)
            except Exception:
                cant_num = 1.0

            cheie = " ".join(den_comp.lower().split())
            stare_curenta = (
                "De comandat"
                if stare_comp.lower() in ("de comandat", "necesara", "necesare")
                else _normalizeaza_stare_comanda(stare_comp)
            )
            furnizor = furnizor_map.get(cheie, "Fără furnizor setat")
            idx_counter += 1
            randuri.append({
                "_row_id": idx_counter,
                "_necesar_id": None,
                "_piesa_id": piesa_id_by_name.get(cheie),
                "_sursa_tbl": "reparatii_electronice",
                "_sursa_rec_id": f_el.get("id"),
                "Furnizor": furnizor,
                "Piesă": den_comp,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Sursă": "Electronică",
                "Firmă": str(f_el.get("firma_nume") or "").strip() or "-",
                "Mașină": str(f_el.get("masina_nume") or f_el.get("piesa_subansamblu") or "").strip() or "-",
                "Raport": f"EL #{f_el.get('id')}",
            })

    return randuri


def _goleste_cache_comenzi():
    _incarca_date_comenzi_unificate.clear()
    try:
        PieseRepository.get_all.clear()
    except Exception:
        pass
    try:
        NecesarPieseRepository.get_all.clear()
    except Exception:
        pass


def render_comenzi():
    col_t, col_r = st.columns([5, 1])
    with col_t:
        st.subheader("📦 Comenzi — Către Furnizori & De la Clienți")
    with col_r:
        if st.button("🔄 Actualizează", use_container_width=True, key="btn_comenzi_refresh"):
            _goleste_cache_comenzi()
            st.rerun()

    randuri = _incarca_date_comenzi_unificate()
    if not randuri:
        st.info("Nu există piese înregistrate pentru comenzi către furnizori sau solicitări de la clienți.")
        return

    df = pd.DataFrame(randuri)

    # Filtre comune sus
    c1, c2, c3, c4 = st.columns([1.2, 1.4, 1.4, 1.5])
    with c1:
        filtru_sursa = st.selectbox(
            "Sursă",
            options=["Toate", "Teren / Necesar", "Mașini", "Electronică"],
            key="comenzi_filtru_sursa",
        )
    with c2:
        opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].unique().tolist())
        filtru_furn = st.selectbox("Furnizor", options=opt_furn, key="comenzi_filtru_furn")
    with c3:
        filtru_stare = st.selectbox(
            "Status Comandă",
            options=["Toate stările"] + OPTIUNI_STARE_COMANDA,
            key="comenzi_filtru_stare",
        )
    with c4:
        cautare_txt = st.text_input(
            "Caută piesă / client / mașină",
            placeholder="ex: rulment, firmă, cod...",
            key="comenzi_cautare_txt",
        ).strip().lower()

    df_f = df.copy()
    if filtru_sursa != "Toate":
        df_f = df_f[df_f["Sursă"] == filtru_sursa]
    if filtru_furn != "Toți furnizorii":
        df_f = df_f[df_f["Furnizor"] == filtru_furn]
    if filtru_stare != "Toate stările":
        df_f = df_f[df_f["Status Comandă"] == filtru_stare]
    if cautare_txt:
        mask = (
            df_f["Piesă"].str.lower().str.contains(cautare_txt, na=False)
            | df_f["Firmă"].str.lower().str.contains(cautare_txt, na=False)
            | df_f["Mașină"].str.lower().str.contains(cautare_txt, na=False)
            | df_f["Furnizor"].str.lower().str.contains(cautare_txt, na=False)
        )
        df_f = df_f[mask]

    if df_f.empty:
        st.info("Nu există înregistrări care să corespundă filtrelor curente.")
        return

    tab_furnizori, tab_clienti = st.tabs([
        "🏭 Către Furnizori (Centralizator Cantități)",
        "🏢 De la Clienți (Cereri & Status Comandă)",
    ])

    # ==================================================================
    # ZONA 1: CĂTRE FURNIZORI (CENTRALIZATOR MUTAT DE PE DASHBOARD)
    # ==================================================================
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
                "Cantitate": st.column_config.NumberColumn("Cantitate Totală", format="%.2f", width="small"),
            },
        )

    # ==================================================================
    # ZONA 2: DE LA CLIENȚI (SOLICITĂRI PER CLIENT & ACTUALIZARE STATUS)
    # ==================================================================
    with tab_clienti:
        st.markdown("##### 📋 Cereri / Necesar Piese De la Clienți")
        firme_disp = ["Toate firmele"] + sorted(
            [f for f in df_f["Firmă"].unique().tolist() if f and f != "-"]
        )
        sel_firma_cmd = st.selectbox(
            "Filtrează după client (firmă)",
            options=firme_disp,
            key="comenzi_clienti_sel_firma",
        )

        df_cli = df_f.copy()
        if sel_firma_cmd != "Toate firmele":
            df_cli = df_cli[df_cli["Firmă"] == sel_firma_cmd]

        if df_cli.empty:
            st.info("Nu există piese pentru clientul selectat.")
            return

        cols_afis = [
            "_row_id",
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
        editor_key = f"comenzi_editor_clienti_{sel_firma_cmd}_{filtru_stare}_{len(df_editor_init)}"

        edited_df = st.data_editor(
            df_editor_init,
            key=editor_key,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["_row_id", "Firmă", "Mașină", "Piesă", "Cantitate", "Furnizor", "Sursă", "Raport"],
            column_config={
                "_row_id": None,
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
            df_final = edited_df.copy()
            if "Status Comandă" in df_final.columns:
                df_final["Status Comandă"] = df_final["Status Comandă"].astype(object)

            state_ed = st.session_state.get(editor_key)
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
                                    _normalizeaza_stare_comanda(new_val) if col_name == "Status Comandă" else new_val
                                )

            meta_map = {}
            for _, r in df_cli.iterrows():
                k = int(r["_row_id"])
                if k not in meta_map:
                    nid_raw = r.get("_necesar_id")
                    pid_raw = r.get("_piesa_id")
                    sid_raw = r.get("_sursa_rec_id")
                    meta_map[k] = {
                        "_necesar_id": int(nid_raw) if pd.notna(nid_raw) and str(nid_raw).strip() != "" else None,
                        "_piesa_id": int(pid_raw) if pd.notna(pid_raw) and str(pid_raw).strip() != "" else None,
                        "_sursa_tbl": str(r.get("_sursa_tbl") or "").strip(),
                        "_sursa_rec_id": int(sid_raw) if pd.notna(sid_raw) and str(sid_raw).strip() != "" else None,
                    }

            orig_map = {
                int(r["_row_id"]): _normalizeaza_stare_comanda(r["Status Comandă"])
                for _, r in df_editor_init.iterrows()
            }
            nr_mod = 0
            erori = []

            for _, row in df_final.iterrows():
                rid = int(row["_row_id"])
                stare_noua = _normalizeaza_stare_comanda(row.get("Status Comandă"))
                stare_veche = _normalizeaza_stare_comanda(orig_map.get(rid))
                if stare_veche != stare_noua:
                    meta = meta_map.get(rid) or {}
                    sursa_tbl = str(meta.get("_sursa_tbl") or "").strip()
                    salvat = False

                    necesar_id = meta.get("_necesar_id")
                    if sursa_tbl == "necesar_piese" and necesar_id is not None:
                        try:
                            NecesarPieseRepository.update_status_comanda(int(necesar_id), stare_noua)
                            salvat = True
                        except Exception as e:
                            erori.append(f"Necesar #{necesar_id}: {e}")

                    piesa_id = meta.get("_piesa_id")
                    if sursa_tbl != "necesar_piese" and piesa_id is not None and pd.notna(piesa_id):
                        try:
                            PieseRepository.update_stare_comandata(int(piesa_id), stare_noua)
                            salvat = True
                        except Exception as e:
                            erori.append(f"Piesa #{piesa_id}: {e}")

                    sursa_rec_id = meta.get("_sursa_rec_id")
                    if sursa_tbl in ("reparatii", "reparatii_electronice") and sursa_rec_id is not None and pd.notna(sursa_rec_id):
                        try:
                            if _actualizeaza_stare_in_raport_json(
                                sursa_tbl,
                                int(sursa_rec_id),
                                str(row.get("Piesă") or ""),
                                stare_noua,
                            ):
                                salvat = True
                        except Exception as e:
                            erori.append(f"{sursa_tbl} #{sursa_rec_id}: {e}")

                    if salvat:
                        nr_mod += 1

            if editor_key in st.session_state:
                del st.session_state[editor_key]

            _goleste_cache_comenzi()
            if erori:
                st.error("⚠️ Erori la salvare:\n" + "\n".join(erori))
            elif nr_mod == 0:
                st.info("ℹ️ Nu există modificări nesalvate.")
            else:
                st.success(f"✅ Au fost actualizate **{nr_mod}** poziții.")
                st.rerun()