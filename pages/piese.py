# ------------------------------------------------
# --- pages/piese.py ----------------------------
# ------------------------------------------------

import json
import pandas as pd
import streamlit as st

from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import NecesarPieseRepository
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_electronice_repository import ReparatiiElectroniceRepository
from repositories.reparatii_repository import ReparatiiRepository


COLOANE_MAPATE = {
    "denumire": "Denumire",
    "cod_producator": "Cod Producător",
    "cod_comercial": "Cod Comercial",
    "masina_montaj": "Mașină Montaj",
    "subansamblu": "Subansamblu",
    "parametri": "Proprietăți",
    "pret_achizitie": "Preț Achiziție",
    "valuta_achizitie": "Valută",
    "termen_livrare": "Termen Livrare (zile)",
    "stare_comandata": "Stare Comandată",
    "furnizor": "Furnizor",
    "link_furnizor": "Link Furnizor",
}

COLOANE_PRETINSE_FARA_ACCES = {
    "pret_achizitie",
    "Preț Achiziție",
    "valuta_achizitie",
    "Valută",
    "furnizor",
    "Furnizor",
    "link_furnizor",
    "Link Furnizor",
}


def _are_acces_preturi_si_furnizori() -> bool:
    rol = str(st.session_state.get("user_role") or st.session_state.get("rol") or "").strip().lower()
    if rol in ("tehnician", "operator", "vizitator", "guest"):
        return False
    return True


def _curata_cache_piese():
    for repo in (PieseRepository, NecesarPieseRepository, ReparatiiRepository, ReparatiiElectroniceRepository):
        try:
            repo.get_all.clear()
        except Exception:
            pass


def _cheie_unica_reper(denumire: str, cod_producator: str) -> tuple[str, str]:
    den_norm = " ".join(str(denumire or "").lower().split())
    cod_norm = " ".join(str(cod_producator or "").lower().split())
    return (den_norm, cod_norm)


def _extrage_lista_dict_din_camp(val_raw) -> list[dict]:
    if not val_raw:
        return []
    if isinstance(val_raw, str):
        txt = val_raw.strip()
        if not txt:
            return []
        try:
            parsed = json.loads(txt)
        except Exception:
            return []
    else:
        parsed = val_raw

    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _sincronizeaza_din_toate_sectiunile() -> dict:
    """Importă piesele din Rapoarte Service, Reparații Electronice și Necesar Teren fără duplicate (denumire + cod_producator)."""
    piese_existente = PieseRepository.get_all() or []
    chei_existente: set[tuple[str, str]] = set()
    for p in piese_existente:
        den_ex = str(p.get("denumire") or "").strip()
        if not den_ex:
            continue
        cod_ex = str(p.get("cod_producator") or p.get("cod_comercial") or "").strip()
        chei_existente.add(_cheie_unica_reper(den_ex, cod_ex))

    adaugate_service = 0
    adaugate_el = 0
    adaugate_teren = 0

    def _insereaza_daca_nou(
        den: str,
        cod: str = "",
        masina: str = "General",
        subansamblu: str = "",
        parametri: str = "",
        stare_raw=None,
    ) -> bool:
        den_clean = " ".join(str(den or "").split()).strip()
        if not den_clean:
            return False
        cod_clean = " ".join(str(cod or "").split()).strip()
        cheie = _cheie_unica_reper(den_clean, cod_clean)
        if cheie in chei_existente:
            return False

        PieseRepository.insert({
            "denumire": den_clean,
            "cod_producator": cod_clean,
            "cod_comercial": cod_clean,
            "masina_montaj": str(masina or "General").strip() or "General",
            "subansamblu": str(subansamblu or "").strip(),
            "parametri": str(parametri or "").strip(),
            "pret_achizitie": 0.0,
            "valuta_achizitie": "RON",
            "termen_livrare": "1",
            "stare_comandata": _normalizeaza_stare_comanda(stare_raw or "De căutat"),
        })
        chei_existente.add(cheie)
        return True

    # 1. Din Rapoarte de Service (ReparatiiRepository)
    rapoarte_service = ReparatiiRepository.get_all() or []
    campuri_lista_service = (
        "piese_json",
        "piese_schimbate_json",
        "piese_necesare_json",
        "componente_json",
        "piese",
        "piese_schimbate",
        "piese_necesare",
    )
    for rep in rapoarte_service:
        if not isinstance(rep, dict):
            continue
        masina_srv = str(
            rep.get("masina_nume")
            or rep.get("masina")
            or rep.get("utilaj")
            or rep.get("echipament")
            or "General"
        ).strip() or "General"
        subansamblu_srv = str(rep.get("subansamblu") or rep.get("piesa_subansamblu") or "").strip()

        gasit_in_lista = False
        for camp in campuri_lista_service:
            lista_items = _extrage_lista_dict_din_camp(rep.get(camp))
            if not lista_items:
                continue
            gasit_in_lista = True
            for item in lista_items:
                den = (
                    item.get("denumire")
                    or item.get("denumire_piesa")
                    or item.get("Denumire")
                    or item.get("piesa")
                    or item.get("Piesa")
                    or item.get("Componenta / Cod / Parametri")
                    or item.get("Componenta")
                    or ""
                )
                cod = (
                    item.get("cod_producator")
                    or item.get("cod")
                    or item.get("Cod")
                    or item.get("cod_comercial")
                    or ""
                )
                prop = (
                    item.get("parametri")
                    or item.get("Parametri")
                    or item.get("Proprietati")
                    or item.get("observatii")
                    or item.get("Observatii")
                    or ""
                )
                stare = item.get("stare_comandata") or item.get("status_comanda") or item.get("Stare")
                if _insereaza_daca_nou(den, cod, masina_srv, subansamblu_srv, prop, stare):
                    adaugate_service += 1

        # Fallback dacă raportul are piese salvate ca text simplu separat prin virgulă / linie nouă
        if not gasit_in_lista:
            for camp_txt in ("piese_schimbate", "piese_necesare", "denumire_piesa"):
                val_txt = rep.get(camp_txt)
                if isinstance(val_txt, str) and val_txt.strip() and not val_txt.strip().startswith(("[", "{")):
                    cod_rep = str(rep.get("cod_producator") or rep.get("cod_piesa") or "").strip()
                    parti = [x.strip() for x in val_txt.replace(";", "\n").splitlines() if x.strip()]
                    for p_txt in parti:
                        cod_curent = cod_rep if len(parti) == 1 else ""
                        if _insereaza_daca_nou(p_txt, cod_curent, masina_srv, subansamblu_srv, ""):
                            adaugate_service += 1

    # 2. Din Reparații Electronice (ReparatiiElectroniceRepository)
    fise_el = ReparatiiElectroniceRepository.get_all() or []
    for f in fise_el:
        if not isinstance(f, dict):
            continue
        subansamblu_el = str(f.get("piesa_subansamblu") or "").strip()
        masina_el = str(f.get("masina_nume") or "General").strip() or "General"
        comp_list = _extrage_lista_dict_din_camp(f.get("componente_json"))

        for comp in comp_list:
            den = (
                comp.get("Componenta / Cod / Parametri")
                or comp.get("Componenta")
                or comp.get("denumire")
                or ""
            )
            cod = comp.get("Cod") or comp.get("cod_producator") or ""
            prop = comp.get("Parametri") or comp.get("Proprietati") or comp.get("Observatii") or ""
            stare = comp.get("Stare") or comp.get("stare_comandata")
            if _insereaza_daca_nou(den, cod, masina_el, subansamblu_el, prop, stare):
                adaugate_el += 1

    # 3. Din Necesar Piese Teren (NecesarPieseRepository)
    necesar_rows = NecesarPieseRepository.get_all() or []
    for nr in necesar_rows:
        if not isinstance(nr, dict):
            continue
        den = nr.get("denumire_piesa") or nr.get("denumire") or ""
        cod = nr.get("cod_producator") or ""
        mas = nr.get("masina") or "General"
        obs = nr.get("observatii") or ""
        stare = nr.get("status_comanda") or nr.get("stare_comandata")
        if _insereaza_daca_nou(den, cod, mas, "", obs, stare):
            adaugate_teren += 1

    if adaugate_service or adaugate_el or adaugate_teren:
        _curata_cache_piese()

    return {
        "service": adaugate_service,
        "electronica": adaugate_el,
        "teren": adaugate_teren,
    }


def _este_gol(val) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    return str(val).strip() == ""


def _normalizare_valoare_payload(col_db: str, val, orig_val=None):
    if col_db == "denumire":
        return "" if _este_gol(val) else str(val).strip()
    if col_db == "masina_montaj":
        txt = "" if _este_gol(val) else str(val).strip()
        return txt or "General"
    if col_db == "valuta_achizitie":
        txt = "" if _este_gol(val) else str(val).strip().upper()
        return txt or "RON"
    if col_db == "termen_livrare":
        txt = "" if _este_gol(val) else str(val).strip()
        return txt or "1"
    if col_db == "stare_comandata":
        return _normalizeaza_stare_comanda("" if _este_gol(val) else val)
    if col_db == "pret_achizitie":
        if _este_gol(val):
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(orig_val or 0.0)

    if isinstance(orig_val, (int, float)) and not isinstance(orig_val, bool):
        if _este_gol(val):
            return 0 if isinstance(orig_val, int) else 0.0
        try:
            return int(val) if isinstance(orig_val, int) and str(val).strip().isdigit() else float(val)
        except (TypeError, ValueError):
            return orig_val

    return "" if _este_gol(val) else str(val).strip()


def _valori_diferite(a, b) -> bool:
    if _este_gol(a) and _este_gol(b):
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a or 0.0) - float(b or 0.0)) > 1e-6
        except (TypeError, ValueError):
            pass
    return str(a if a is not None else "") != str(b if b is not None else "")


def _construieste_df_catalog(piese_filtrate: list[dict]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Construiește DataFrame-ul cu toate coloanele din DB și returnează maparea {coloana_ui: coloana_db}."""
    toate_coloane_db: list[str] = []
    for row in piese_filtrate:
        for k in row.keys():
            if k not in toate_coloane_db:
                toate_coloane_db.append(k)

    ordonate_db: list[str] = []
    if "id" in toate_coloane_db:
        ordonate_db.append("id")
    for k in COLOANE_MAPATE.keys():
        if k in toate_coloane_db and k not in ordonate_db:
            ordonate_db.append(k)
    for k in toate_coloane_db:
        if k not in ordonate_db:
            ordonate_db.append(k)

    ui_to_db: dict[str, str] = {}
    col_ui_list: list[str] = []
    for col_db in ordonate_db:
        if col_db == "id":
            col_ui = "id"
        elif col_db in COLOANE_MAPATE:
            col_ui = COLOANE_MAPATE[col_db]
        else:
            col_ui = col_db
        if col_ui in ui_to_db:
            col_ui = f"{col_ui} ({col_db})"
        ui_to_db[col_ui] = col_db
        col_ui_list.append(col_ui)

    randuri_ui: list[dict] = []
    for r in piese_filtrate:
        item: dict = {}
        for col_ui, col_db in ui_to_db.items():
            val = r.get(col_db)
            if col_db == "id" and val is not None:
                try:
                    item[col_ui] = int(val)
                except (TypeError, ValueError):
                    item[col_ui] = val
            elif col_db == "pret_achizitie":
                item[col_ui] = float(val or 0.0)
            elif col_db == "valuta_achizitie":
                item[col_ui] = str(val or "RON").strip().upper() or "RON"
            elif col_db == "masina_montaj":
                item[col_ui] = str(val or "General").strip() or "General"
            elif col_db == "termen_livrare":
                item[col_ui] = str(val or "1").strip() or "1"
            elif col_db == "stare_comandata":
                item[col_ui] = _normalizeaza_stare_comanda(val)
            elif col_db in ("denumire", "cod_producator", "cod_comercial", "subansamblu", "parametri", "furnizor", "link_furnizor"):
                item[col_ui] = "" if _este_gol(val) else str(val).strip()
            else:
                item[col_ui] = None if _este_gol(val) else val
        item["Șterge"] = False
        randuri_ui.append(item)

    df_init = pd.DataFrame(randuri_ui, columns=col_ui_list + ["Șterge"])
    return df_init, ui_to_db


def _configurare_coloane_editor(col_ui_list: list[str], ui_to_db: dict[str, str]) -> dict:
    cfg: dict = {
        "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
        "Șterge": st.column_config.CheckboxColumn("🗑️ Șterge", default=False, width="small"),
    }
    for col_ui in col_ui_list:
        if col_ui == "id":
            continue
        col_db = ui_to_db[col_ui]
        if col_db == "denumire":
            cfg[col_ui] = st.column_config.TextColumn("Denumire *", width="large", required=True)
        elif col_db == "parametri":
            cfg[col_ui] = st.column_config.TextColumn("Proprietăți / Parametri", width="large")
        elif col_db == "pret_achizitie":
            cfg[col_ui] = st.column_config.NumberColumn("Preț Achiziție", min_value=0.0, format="%.2f", width="small")
        elif col_db == "valuta_achizitie":
            cfg[col_ui] = st.column_config.SelectboxColumn("Valută", options=["RON", "EUR", "USD"], width="small")
        elif col_db == "stare_comandata":
            cfg[col_ui] = st.column_config.SelectboxColumn("Stare Comandată", options=OPTIUNI_STARE_COMANDA, width="medium")
        elif col_db == "termen_livrare":
            cfg[col_ui] = st.column_config.TextColumn("Termen (zile)", width="small")
        else:
            cfg[col_ui] = st.column_config.TextColumn(col_ui, width="medium")
    return cfg


@st.fragment
def render_catalog_general_piese(acces_permis: bool):
    st.subheader("📦 Catalog General Piese (Adăugare, Editare & Ștergere)")
    st.caption(
        "Sunt afișate **toate coloanele** din baza de date. Poți **edita** orice celulă, "
        "**adăuga** rânduri direct în tabel (din ultimul rând gol) sau **șterge** repere (prin bifa `🗑️ Șterge` sau ștergere rând în tabel), "
        "apoi apeși **Salvează Modificările**."
    )

    c_sync, c_rem = st.columns([1.8, 3.2], vertical_alignment="center")
    with c_sync:
        if st.button("🔄 Actualizează / Importă Piese", key="btn_sync_toate_sectiunile", use_container_width=True):
            rez = _sincronizeaza_din_toate_sectiunile()
            total_imp = rez["service"] + rez["electronica"] + rez["teren"]
            if total_imp == 0:
                st.info("ℹ️ Nu au fost găsite repere noi (toate există deja în catalog după denumire și cod producător).")
            else:
                st.success(
                    f"✅ Importate **{total_imp}** repere noi: "
                    f"**{rez['service']}** din rapoarte service, "
                    f"**{rez['electronica']}** din reparații electronice, "
                    f"**{rez['teren']}** din note teren."
                )
                st.rerun()

    with c_rem:
        if st.session_state.get("piese_auto_sync_done", False):
            st.info(
                "💡 **Reminder:** Sincronizarea automată a rulat deja la prima deschidere din această sesiune. "
                "Dacă ai adăugat piese între timp în **Raport Service**, **Electronică** sau **Teren**, "
                "apasă **«🔄 Actualizează / Importă Piese»** pentru a actualiza tabelul."
            )

    piese_all = PieseRepository.get_all() or []
    if not piese_all:
        st.info("Nu există piese în catalog. Poți importa din celelalte secțiuni sau adăuga din tab-ul «Adaugă Piesă Nouă».")
        return

    df_raw = pd.DataFrame(piese_all)

    f1, f2, f3 = st.columns([2.2, 1.5, 1.5])
    with f1:
        q_cautare = st.text_input(
            "Caută în toate coloanele",
            placeholder="ex: releu, 24V, encoder, cod, furnizor...",
            key="piese_cat_search",
        ).strip().lower()
    with f2:
        opt_mas = ["Toate mașinile"] + sorted({
            str(p.get("masina_montaj") or "General").strip()
            for p in piese_all
            if str(p.get("masina_montaj") or "").strip()
        })
        sel_mas = st.selectbox("Mașină montaj", options=opt_mas, key="piese_cat_masina")
    with f3:
        opt_stari = ["Toate stările"] + OPTIUNI_STARE_COMANDA
        sel_stare = st.selectbox("Stare comandă", options=opt_stari, key="piese_cat_stare")

    df_f = df_raw.copy()
    if sel_mas != "Toate mașinile" and "masina_montaj" in df_f.columns:
        df_f = df_f[df_f["masina_montaj"].fillna("General").astype(str).str.strip() == sel_mas]
    if sel_stare != "Toate stările" and "stare_comandata" in df_f.columns:
        df_f = df_f[df_f["stare_comandata"].apply(_normalizeaza_stare_comanda) == sel_stare]
    if q_cautare:
        mask = pd.Series(False, index=df_f.index)
        for col in df_f.columns:
            mask = mask | df_f[col].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
        df_f = df_f[mask]

    piese_filtrate = df_f.to_dict(orient="records")
    if not piese_filtrate:
        st.info("Nicio piesă nu corespunde filtrelor.")
        return

    df_init, ui_to_db = _construieste_df_catalog(piese_filtrate)
    col_ui_list = [c for c in df_init.columns if c != "Șterge"]

    disabled_cols = ["id"]
    if not acces_permis:
        for col_ui in col_ui_list:
            if col_ui in COLOANE_PRETINSE_FARA_ACCES or ui_to_db.get(col_ui) in COLOANE_PRETINSE_FARA_ACCES:
                disabled_cols.append(col_ui)

    editor_key = f"editor_piese_general_{sel_mas}_{sel_stare}_{len(df_init)}"
    edited = st.data_editor(
        df_init,
        key=editor_key,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        disabled=disabled_cols,
        column_config=_configurare_coloane_editor(col_ui_list, ui_to_db),
    )

    if st.button("💾 Salvează Modificările în Catalogul de Piese", type="primary", key="btn_save_piese_general"):
        df_final = edited.copy() if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)
        state_ed = st.session_state.get(editor_key) if isinstance(st.session_state.get(editor_key), dict) else {}

        for idx_str, changes in (state_ed.get("edited_rows") or {}).items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df_final) and isinstance(changes, dict):
                for col_name, new_val in changes.items():
                    if col_name in df_final.columns:
                        df_final.at[idx, col_name] = new_val

        orig_map: dict[int, dict] = {}
        ids_prezente_in_editor: set[int] = set()
        chei_curente_in_catalog: set[tuple[str, str]] = {
            _cheie_unica_reper(p.get("denumire") or "", p.get("cod_producator") or p.get("cod_comercial") or "")
            for p in piese_all
            if str(p.get("denumire") or "").strip()
        }

        for _, r in df_init.iterrows():
            if not _este_gol(r.get("id")):
                try:
                    orig_map[int(r["id"])] = r.to_dict()
                except (TypeError, ValueError):
                    pass

        nr_mod = 0
        nr_del = 0
        nr_add = 0
        erori_validare = 0

        for _, row in df_final.iterrows():
            raw_id = row.get("id")
            if not _este_gol(raw_id):
                try:
                    pid = int(raw_id)
                except (TypeError, ValueError):
                    pid = None
            else:
                pid = None

            if pid is not None:
                ids_prezente_in_editor.add(pid)

            bifata_stergere = bool(row.get("Șterge", False))

            if pid is not None and bifata_stergere:
                PieseRepository.delete(pid)
                nr_del += 1
                continue

            # Rând nou adăugat direct în tabel (fără ID)
            if pid is None:
                if bifata_stergere:
                    continue
                payload_nou: dict = {}
                for col_ui in col_ui_list:
                    col_db = ui_to_db[col_ui]
                    if col_db == "id":
                        continue
                    if not acces_permis and col_db in COLOANE_PRETINSE_FARA_ACCES:
                        continue
                    payload_nou[col_db] = _normalizare_valoare_payload(col_db, row.get(col_ui))

                are_continut = any(
                    not _este_gol(v)
                    for k, v in payload_nou.items()
                    if k not in ("masina_montaj", "valuta_achizitie", "termen_livrare", "stare_comandata")
                )
                if not are_continut and not payload_nou.get("denumire"):
                    continue

                if not payload_nou.get("denumire"):
                    erori_validare += 1
                    st.warning("⚠️ Un rând nou adăugat în tabel nu are «Denumire» și nu a fost salvat.")
                    continue

                cheie_noua = _cheie_unica_reper(
                    payload_nou.get("denumire") or "",
                    payload_nou.get("cod_producator") or payload_nou.get("cod_comercial") or "",
                )
                if cheie_noua in chei_curente_in_catalog:
                    erori_validare += 1
                    st.warning(
                        f"⚠️ Reperul «{payload_nou['denumire']}» (cod: «{payload_nou.get('cod_producator') or '-'}») "
                        "există deja în catalog și nu a fost duplicat."
                    )
                    continue

                PieseRepository.insert(payload_nou)
                chei_curente_in_catalog.add(cheie_noua)
                nr_add += 1
                continue

            # Rând existent
            orig = orig_map.get(pid)
            if orig is None:
                continue

            payload_upd: dict = {}
            schimbat = False

            for col_ui in col_ui_list:
                col_db = ui_to_db[col_ui]
                if col_db == "id":
                    continue
                if not acces_permis and col_db in COLOANE_PRETINSE_FARA_ACCES:
                    continue
                orig_val = orig.get(col_ui)
                nou_val_norm = _normalizare_valoare_payload(col_db, row.get(col_ui), orig_val=orig_val)
                orig_val_norm = _normalizare_valoare_payload(col_db, orig_val, orig_val=orig_val)
                payload_upd[col_db] = nou_val_norm
                if _valori_diferite(nou_val_norm, orig_val_norm):
                    schimbat = True

            if not payload_upd.get("denumire"):
                erori_validare += 1
                st.warning(f"⚠️ Reperul ID {pid} nu poate avea «Denumire» goală; modificarea a fost ignorată.")
                continue

            if schimbat:
                PieseRepository.update(pid, payload_upd)
                nr_mod += 1

        for pid_orig in orig_map.keys():
            if pid_orig not in ids_prezente_in_editor:
                PieseRepository.delete(pid_orig)
                nr_del += 1

        _curata_cache_piese()
        if editor_key in st.session_state:
            del st.session_state[editor_key]

        if nr_mod == 0 and nr_del == 0 and nr_add == 0:
            if erori_validare == 0:
                st.info("ℹ️ Nu există modificări nesalvate.")
        else:
            st.success(
                f"✅ Salvat: **{nr_add}** adăugate, **{nr_mod}** actualizate, **{nr_del}** șterse."
            )
            st.rerun()


@st.fragment
def render_adaugare_piesa_noua(masini_all: list[dict], acces_permis: bool):
    st.subheader("➕ Adaugă Piesă Nouă în Catalog")
    opt_masini = ["General"] + sorted({
        str(m.get("denumire") or "").strip()
        for m in (masini_all or [])
        if str(m.get("denumire") or "").strip()
    })

    with st.form("form_adauga_piesa_catalog_unic", clear_on_submit=True):
        c1, c2, c3 = st.columns([2.0, 1.3, 1.3])
        with c1:
            den = st.text_input("Denumire piesă *")
        with c2:
            cod_p = st.text_input("Cod producător")
        with c3:
            cod_c = st.text_input("Cod comercial")

        c4, c5, c6 = st.columns([1.5, 1.5, 2.0])
        with c4:
            mas = st.selectbox("Mașină montaj", options=opt_masini)
        with c5:
            sub = st.text_input("Subansamblu")
        with c6:
            prop = st.text_input("Proprietăți / parametri")

        c7, c8, c9, c10 = st.columns([1.1, 0.9, 1.1, 1.5])
        with c7:
            pret = st.number_input("Preț achiziție", min_value=0.0, value=0.0, step=1.0, format="%.2f", disabled=not acces_permis)
            
            
def render_piese():
    st.title("🔩 Gestiune Piese")

    if not st.session_state.get("piese_auto_sync_done", False):
        try:
            rez = _sincronizeaza_din_toate_sectiunile()
            st.session_state["piese_auto_sync_done"] = True
            total_imp = rez["service"] + rez["electronica"] + rez["teren"]
            if total_imp > 0:
                st.toast(
                    f"Sincronizate automat {total_imp} repere noi "
                    f"({rez['service']} service, {rez['electronica']} electronică, {rez['teren']} teren)."
                )
        except Exception as exc:
            st.session_state["piese_auto_sync_done"] = True
            st.warning(f"⚠️ Sincronizarea automată a pieselor a întâmpinat o problemă: {exc}")

    acces_permis = _are_acces_preturi_si_furnizori()
    masini_all = MasiniRepository.get_all() or []

    tab_catalog, tab_nou = st.tabs([
        "📦 Catalog General Piese",
        "➕ Adaugă Piesă Nouă",
    ])

    with tab_catalog:
        render_catalog_general_piese(acces_permis)

    with tab_nou:
        render_adaugare_piesa_noua(masini_all, acces_permis)