# ----------------------------------
# -------pages/de_facut.py----------
# ----------------------------------

import datetime
import json
import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import (
    OPTIUNI_PRIORITATE_PIESA,
    OPTIUNI_STATUS_TEREN,
    NecesarPieseRepository,
    normalizeaza_prioritate_piesa,
)
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_repository import ReparatiiRepository
from repositories.taskuri_vizita_repository import (
    OPTIUNI_STARE_TASK_VIZITA,
    TaskuriVizitaRepository,
    normalizeaza_stare_task_vizita,
)


def _obtine_harta_firme() -> tuple[list[str], dict[str, int]]:
    firme_all = FirmeRepository.get_all() or []
    nume_to_id: dict[str, int] = {}
    for f in firme_all:
        nume = str(f.get("nume_firma") or "").strip()
        fid = f.get("id")
        if nume and fid is not None:
            nume_to_id[nume] = int(fid)
    return sorted(nume_to_id.keys()), nume_to_id


@st.cache_data(ttl=300)
def _incarca_optiuni_lookup_piese():
    piese_catalog = PieseRepository.get_all() or []
    optiuni = ["✍️ Piesă nouă (scriu manual)"]
    detalii = {}
    vazute = set()

    for p in piese_catalog:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or "").strip()
        mas = str(p.get("masina_montaj") or "").strip()
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + (f" ({mas})" if mas and mas != "General" else "")
        if eticheta in vazute:
            continue
        vazute.add(eticheta)
        optiuni.append(eticheta)
        detalii[eticheta] = {"denumire": den, "cod_producator": cod}

    return optiuni, detalii


@st.cache_data(ttl=120)
def incarca_memento_intretinere(zile_inainte: int = 14):
    zile = max(0, int(zile_inainte))
    try:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    m.id,
                    COALESCE(NULLIF(TRIM(f.nume_firma), ''), 'Fără firmă') AS firma,
                    m.denumire AS utilaj,
                    CAST(m.data_intretinere AS DATE) AS data_scadenta,
                    (CAST(m.data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                FROM masini m
                LEFT JOIN firme f ON f.id = m.firma_id
                WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                  AND m.data_intretinere IS NOT NULL
                  AND CAST(m.data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY CAST(m.data_intretinere AS DATE) ASC, firma ASC, m.denumire ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        with db_cursor() as c:
            c.execute("""
                SELECT
                    id,
                    'Fără firmă' AS firma,
                    denumire AS utilaj,
                    CAST(data_intretinere AS DATE) AS data_scadenta,
                    (CAST(data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                FROM masini
                WHERE COALESCE(fara_intretinere, FALSE) = FALSE
                  AND data_intretinere IS NOT NULL
                  AND CAST(data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY CAST(data_intretinere AS DATE) ASC, denumire ASC
            """, (zile,))
            return [dict(r) for r in (c.fetchall() or [])]


def _goleste_cache_de_facut():
    incarca_memento_intretinere.clear()
    _incarca_optiuni_lookup_piese.clear()
    try:
        PieseRepository.get_all.clear()
    except Exception:
        pass
    try:
        NecesarPieseRepository.get_all.clear()
    except Exception:
        pass
    try:
        TaskuriVizitaRepository.get_all.clear()
    except Exception:
        pass


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


def _colecteaza_piese_necesare() -> list[dict]:
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

    randuri = []
    idx_counter = 0
    stari_valide_low = {
        "de comandat", "necesara", "necesare",
        "de căutat", "de cautat",
        "de ofertat",
        "comandată", "comandata",
        "în așteptare", "in asteptare",
        "anulată", "anulata",
    }

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
            "Stare Piesă": normalizeaza_prioritate_piesa(np_row.get("prioritate_piesa")),
            "Piesă": den_np,
            "Cantitate": cant_num,
            "Status Comandă": _normalizeaza_stare_comanda(np_row.get("status_comanda")),
            "Furnizor": furnizor_np,
            "Sursă": "Teren / Necesar",
            "Firmă": str(np_row.get("firma_client") or "").strip(),
            "Mașină": str(np_row.get("masina") or "").strip() or "-",
            "Raport": f"NP #{np_row.get('id')}",
        })

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
                "Stare Piesă": "Normal",
                "Piesă": den_piesa,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Furnizor": furnizor,
                "Sursă": "Mașini",
                "Firmă": r.get("firma") or "",
                "Mașină": r.get("masina") or "",
                "Raport": f"#{r.get('id')}",
            })

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
                "Stare Piesă": "Normal",
                "Piesă": den_comp,
                "Cantitate": cant_num,
                "Status Comandă": stare_curenta,
                "Furnizor": furnizor,
                "Sursă": "Electronică",
                "Firmă": f_el.get("firma_nume") or "",
                "Mașină": f_el.get("masina_nume") or f_el.get("piesa_subansamblu") or "",
                "Raport": f"EL #{f_el.get('id')}",
            })

    # Ordonare: Urgent -> De comandat -> De ofertat -> De căutat -> restul
    ord_status = {
        "De comandat": 1,
        "De ofertat": 2,
        "De căutat": 3,
        "În așteptare": 4,
        "Comandată": 5,
        "Anulată": 6,
    }
    randuri.sort(
        key=lambda x: (
            0 if x.get("Stare Piesă") == "Urgent" else 1,
            ord_status.get(x.get("Status Comandă"), 9),
            str(x.get("Firmă") or "").lower(),
            str(x.get("Piesă") or "").lower(),
        )
    )
    return randuri


# ==================================================================
# 7. PRIVIRE DE ANSAMBLU SUS ÎN PAGINĂ (TASK-URI URGENTE & PIESE PRIORITARE)
# ==================================================================
def render_privire_ansamblu_de_facut(piese_rows: list[dict]):
    taskuri = TaskuriVizitaRepository.get_all() or []
    taskuri_urgente = [t for t in taskuri if t.get("stare") == "Urgent"]
    taskuri_active = [t for t in taskuri if t.get("stare") != "Finalizat"]

    piese_urgente = [
        p for p in piese_rows
        if p.get("Stare Piesă") == "Urgent" and p.get("Status Comandă") not in ("Comandată", "Anulată")
    ]
    piese_de_comandat = [p for p in piese_rows if p.get("Status Comandă") == "De comandat"]
    piese_de_ofertat = [p for p in piese_rows if p.get("Status Comandă") == "De ofertat"]
    piese_de_cautat = [p for p in piese_rows if p.get("Status Comandă") == "De căutat"]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🚨 Task-uri Urgente", len(taskuri_urgente), delta=f"{len(taskuri_active)} active")
    m2.metric("🔥 Piese Urgente", len(piese_urgente))
    m3.metric("🛒 De comandat", len(piese_de_comandat))
    m4.metric("💶 De ofertat", len(piese_de_ofertat))
    m5.metric("🔎 De căutat", len(piese_de_cautat))

    c_ov1, c_ov2 = st.columns(2, gap="medium")
    with c_ov1:
        st.markdown("##### 🚨 Task-uri Urgente (Vizite Clienți)")
        if taskuri_urgente:
            df_tu = pd.DataFrame([
                {
                    "Firmă": t.get("firma") or "-",
                    "Mașină": t.get("masina") or "-",
                    "Până la": str(t.get("de_facut_pana_la") or "-"),
                    "Notiță": t.get("note_vizita") or "",
                }
                for t in taskuri_urgente[:10]
            ])
            st.dataframe(df_tu, hide_index=True, use_container_width=True)
        else:
            st.success("✅ Niciun task urgent în așteptare.")

    with c_ov2:
        st.markdown("##### 🔥 Piese Prioritare (Urgent → De comandat → De ofertat → De căutat)")
        piese_active_ord = [
            p for p in piese_rows
            if p.get("Status Comandă") in ("De comandat", "De ofertat", "De căutat")
        ]
        if piese_active_ord:
            df_po = pd.DataFrame([
                {
                    "Urgență": "🚨 Urgent" if p.get("Stare Piesă") == "Urgent" else "Normal",
                    "Status": p.get("Status Comandă"),
                    "Piesă": p.get("Piesă"),
                    "Cant.": p.get("Cantitate"),
                    "Firmă": p.get("Firmă") or "-",
                }
                for p in piese_active_ord[:12]
            ])
            st.dataframe(df_po, hide_index=True, use_container_width=True)
        else:
            st.success("✅ Nicio piesă în așteptare pentru comandă / ofertare / căutare.")


# ==================================================================
# 1, 2, 2.1, 3. NOTARE RAPIDĂ PIESE PE TEREN
# ==================================================================
def render_notare_rapida_teren():
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []
    optiuni_piese, detalii_piese = _incarca_optiuni_lookup_piese()

    with st.expander("📝 Notare Rapidă Piese pe Teren (Client obligatoriu • Mașină opțională)", expanded=False):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
            return

        # 2.1 Client/Firmă și Mașină pe același rând (păstrate după salvare)
        c_fm1, c_fm2 = st.columns([1.5, 1.5])
        with c_fm1:
            firma_teren = st.selectbox(
                "Client / Firmă *",
                options=firme_nume,
                key="df_teren_firma_sel",
            )
        fid_teren = nume_to_id.get(firma_teren)
        masini_firma = [
            str(m.get("denumire") or "").strip()
            for m in masini_all
            if str(m.get("denumire") or "").strip()
            and (fid_teren is None or m.get("firma_id") == fid_teren)
        ]
        opt_masini_teren = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma))
        if st.session_state.get("df_teren_masina_sel") not in opt_masini_teren:
            st.session_state["df_teren_masina_sel"] = "-- Fără mașină (opțional) --"

        with c_fm2:
            masina_teren = st.selectbox(
                "Mașină (opțional)",
                options=opt_masini_teren,
                key="df_teren_masina_sel",
            )

        if st.session_state.get("df_teren_lookup_piesa") not in optiuni_piese:
            st.session_state["df_teren_lookup_piesa"] = optiuni_piese[0]

        piesa_aleasa_lookup = st.selectbox(
            "Alege piesă din DB (sau «Piesă nouă»)",
            options=optiuni_piese,
            key="df_teren_lookup_piesa",
        )

        este_piesa_noua = piesa_aleasa_lookup == "✍️ Piesă nouă (scriu manual)"
        piesa_din_db = detalii_piese.get(piesa_aleasa_lookup, {})
        den_implicit = "" if este_piesa_noua else str(piesa_din_db.get("denumire") or "")
        cod_implicit = "" if este_piesa_noua else str(piesa_din_db.get("cod_producator") or "")

        # Sincronizare câmpuri la schimbarea lookup-ului
        if st.session_state.get("_df_last_lookup") != piesa_aleasa_lookup:
            st.session_state["_df_last_lookup"] = piesa_aleasa_lookup
            st.session_state["df_teren_den_manual"] = den_implicit
            st.session_state["df_teren_cod_manual"] = cod_implicit
            st.session_state["df_teren_status_sel"] = "De căutat" if este_piesa_noua else "De ofertat"

        st.session_state.setdefault("df_teren_den_manual", "")
        st.session_state.setdefault("df_teren_cod_manual", "")
        st.session_state.setdefault("df_teren_cant_num", 1.0)
        st.session_state.setdefault("df_teren_prio_sel", "Normal")
        st.session_state.setdefault("df_teren_status_sel", "De căutat")
        st.session_state.setdefault("df_teren_obs_txt", "")

        with st.form("form_notare_rapida_teren_df", clear_on_submit=False):
            c_t1, c_t2 = st.columns([2.3, 1.5])
            with c_t1:
                piesa_teren = st.text_input(
                    "Denumire piesă *",
                    key="df_teren_den_manual",
                    disabled=not este_piesa_noua,
                    placeholder="scrie denumirea piesei noi...",
                )
            with c_t2:
                cod_teren = st.text_input(
                    "Cod producător (opțional)",
                    key="df_teren_cod_manual",
                    placeholder="ex: cod reper notat la client",
                )

            c_t3, c_t4, c_t5 = st.columns([1.1, 1.3, 1.5])
            with c_t3:
                cant_teren = st.number_input(
                    "Cantitate *",
                    min_value=0.01,
                    step=1.0,
                    format="%.2f",
                    key="df_teren_cant_num",
                )
            with c_t4:
                prioritate_teren = st.selectbox(
                    "Stare piesă *",
                    options=OPTIUNI_PRIORITATE_PIESA,
                    key="df_teren_prio_sel",
                )
            with c_t5:
                status_teren = st.selectbox(
                    "Status Comandă *",
                    options=OPTIUNI_STATUS_TEREN,
                    key="df_teren_status_sel",
                )

            obs_teren = st.text_area(
                "Observații / detalii notate la client (opțional)",
                placeholder="ex: cerută la vizită, verificare ofertă, detalii montaj...",
                height=90,
                key="df_teren_obs_txt",
            )
            salveaza_teren = st.form_submit_button("➕ Notează Piesa pentru Comandă", type="primary")

        if salveaza_teren:
            try:
                den_finala = den_implicit if not este_piesa_noua else piesa_teren
                rez = NecesarPieseRepository.noteaza_piesa_pe_teren(
                    firma_client=firma_teren,
                    firma_id=fid_teren,
                    denumire_piesa=den_finala,
                    cantitate=cant_teren,
                    masina=masina_teren,
                    cod_producator=cod_teren,
                    prioritate_piesa=prioritate_teren,
                    status_comanda=status_teren,
                    observatii=obs_teren,
                )
                _goleste_cache_de_facut()

                # 2. Golește toate câmpurile (inclusiv DBlookup), păstrând Firma și Mașina selectate
                st.session_state["df_teren_lookup_piesa"] = "✍️ Piesă nouă (scriu manual)"
                st.session_state["_df_last_lookup"] = "✍️ Piesă nouă (scriu manual)"
                st.session_state["df_teren_den_manual"] = ""
                st.session_state["df_teren_cod_manual"] = ""
                st.session_state["df_teren_cant_num"] = 1.0
                st.session_state["df_teren_prio_sel"] = "Normal"
                st.session_state["df_teren_status_sel"] = "De căutat"
                st.session_state["df_teren_obs_txt"] = ""

                mesaj_cat = (
                    "existentă în catalog"
                    if rez.get("existenta_in_catalog")
                    else "adăugată și în catalogul `piese`"
                )
                st.success(
                    f"✅ Salvat **{str(den_finala).strip()}** (cant. **{float(cant_teren):g}**, "
                    f"stare: **{prioritate_teren}**, status: **{status_teren}**, {mesaj_cat}). "
                    f"Pregătit pentru următoarea piesă la **{firma_teren}**"
                    f"{f' — {masina_teren}' if not masina_teren.startswith('--') else ''}."
                )
                st.rerun()
            except ValueError as ve:
                st.error(f"⚠️ {ve}")


# ==================================================================
# 4. TABEL PIESE DE COMANDAT / NECESARE (Furnizor după Status Comandă și înainte de Sursă)
# ==================================================================
def render_tabel_piese_de_comandat(randuri: list[dict]):
    with st.expander("🛒 Piese De Comandat / Necesare & Furnizori", expanded=False):
        st.caption(
            "Schimbă direct în tabel **Stare Piesă** (`Normal` / `Urgent`) sau **Status Comandă** "
            "(`De căutat`, `De ofertat`, `De comandat`, `Comandată`, `În așteptare`, `Anulată`) "
            "și apasă **💾 Actualizează Stările în Tabel**."
        )

        if not randuri:
            st.info("Nu există piese marcate ca necesare / de comandat / de căutat / de ofertat.")
            return

        df = pd.DataFrame(randuri)

        c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1.4])
        with c1:
            filtru_sursa = st.selectbox(
                "Filtrează după sursă",
                options=["Toate", "Teren / Necesar", "Mașini", "Electronică"],
                key="df_piese_cmd_sursa",
            )
        with c2:
            opt_furn = ["Toți furnizorii"] + sorted(df["Furnizor"].unique().tolist())
            filtru_furn = st.selectbox(
                "Filtrează după furnizor",
                options=opt_furn,
                key="df_piese_cmd_furn",
            )
        with c3:
            filtru_stare = st.selectbox(
                "Filtrează după status",
                options=["Toate stările"] + OPTIUNI_STARE_COMANDA,
                key="df_piese_cmd_stare",
            )
        with c4:
            cautare_piesa = st.text_input(
                "Caută piesă / cod",
                placeholder="ex: L6376PD, SFH6106...",
                key="df_piese_cmd_cautare",
            ).strip().lower()

        df_f = df.copy()
        if filtru_sursa != "Toate":
            df_f = df_f[df_f["Sursă"] == filtru_sursa]
        if filtru_furn != "Toți furnizorii":
            df_f = df_f[df_f["Furnizor"] == filtru_furn]
        if filtru_stare != "Toate stările":
            df_f = df_f[df_f["Status Comandă"] == filtru_stare]
        if cautare_piesa:
            df_f = df_f[df_f["Piesă"].str.lower().str.contains(cautare_piesa, na=False)]

        if df_f.empty:
            st.info("Nu există piese care să corespundă filtrelor selectate.")
            return

        # 4. Ordinea coloanelor: Furnizor după Status Comandă și înainte de Sursă
        cols_afis = [
            "_row_id",
            "Stare Piesă",
            "Piesă",
            "Cantitate",
            "Status Comandă",
            "Furnizor",
            "Sursă",
            "Firmă",
            "Mașină",
            "Raport",
        ]
        df_editor_init = df_f[cols_afis].reset_index(drop=True)
        editor_dash_key = f"df_editor_stare_piese_{filtru_sursa}_{filtru_furn}_{filtru_stare}"

        edited_df = st.data_editor(
            df_editor_init,
            key=editor_dash_key,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["_row_id", "Piesă", "Cantitate", "Furnizor", "Sursă", "Firmă", "Mașină", "Raport"],
            column_config={
                "_row_id": None,
                "Stare Piesă": st.column_config.SelectboxColumn(
                    "Stare Piesă",
                    options=OPTIUNI_PRIORITATE_PIESA,
                    required=True,
                    width="small",
                ),
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
                "Firmă": st.column_config.TextColumn("Firmă", width="small"),
                "Mașină": st.column_config.TextColumn("Mașină", width="small"),
                "Raport": st.column_config.TextColumn("Raport", width="small"),
            },
        )

        if st.button("💾 Actualizează Stările în Tabel", type="primary", key="btn_df_update_stare_piese"):
            df_final = edited_df.copy()
            if "Status Comandă" in df_final.columns:
                df_final["Status Comandă"] = df_final["Status Comandă"].astype(object)
            if "Stare Piesă" in df_final.columns:
                df_final["Stare Piesă"] = df_final["Stare Piesă"].astype(object)

            state_ed = st.session_state.get(editor_dash_key)
            if isinstance(state_ed, dict):
                for idx_key, changes in (state_ed.get("edited_rows") or {}).items():
                    try:
                        idx = int(idx_key)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= idx < len(df_final) and isinstance(changes, dict):
                        for col_name, new_val in changes.items():
                            if col_name in df_final.columns:
                                if col_name == "Status Comandă":
                                    df_final.at[idx, col_name] = _normalizeaza_stare_comanda(new_val)
                                elif col_name == "Stare Piesă":
                                    df_final.at[idx, col_name] = normalizeaza_prioritate_piesa(new_val)
                                else:
                                    df_final.at[idx, col_name] = new_val

            meta_map = {}
            for _, r in df_f.iterrows():
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

            orig_status_map = {
                int(r["_row_id"]): _normalizeaza_stare_comanda(r["Status Comandă"])
                for _, r in df_editor_init.iterrows()
            }
            orig_prio_map = {
                int(r["_row_id"]): normalizeaza_prioritate_piesa(r["Stare Piesă"])
                for _, r in df_editor_init.iterrows()
            }
            nr_mod = 0
            erori_salvare = []

            for _, row in df_final.iterrows():
                rid = int(row["_row_id"])
                stare_noua = _normalizeaza_stare_comanda(row.get("Status Comandă"))
                stare_veche = orig_status_map.get(rid)
                prio_noua = normalizeaza_prioritate_piesa(row.get("Stare Piesă"))
                prio_veche = orig_prio_map.get(rid)

                if stare_veche != stare_noua or prio_veche != prio_noua:
                    meta = meta_map.get(rid) or {}
                    salvat_ceva = False
                    sursa_tbl = str(meta.get("_sursa_tbl") or "").strip()

                    necesar_id = meta.get("_necesar_id")
                    if sursa_tbl == "necesar_piese" and necesar_id is not None:
                        try:
                            if stare_veche != stare_noua:
                                NecesarPieseRepository.update_status_comanda(int(necesar_id), stare_noua)
                            if prio_veche != prio_noua:
                                NecesarPieseRepository.update_prioritate_piesa(int(necesar_id), prio_noua)
                            salvat_ceva = True
                        except Exception as e:
                            erori_salvare.append(f"Necesar #{necesar_id} ({row.get('Piesă')}): {e}")

                    piesa_id = meta.get("_piesa_id")
                    if piesa_id is not None and pd.notna(piesa_id) and stare_veche != stare_noua:
                        try:
                            PieseRepository.update_stare_comandata(int(piesa_id), stare_noua)
                            salvat_ceva = True
                        except Exception as e:
                            erori_salvare.append(f"Piesa #{piesa_id} ({row.get('Piesă')}): {e}")

                    sursa_rec_id = meta.get("_sursa_rec_id")
                    if sursa_tbl in ("reparatii", "reparatii_electronice") and sursa_rec_id is not None and pd.notna(sursa_rec_id) and stare_veche != stare_noua:
                        try:
                            if _actualizeaza_stare_in_raport_json(
                                sursa_tbl,
                                int(sursa_rec_id),
                                str(row.get("Piesă") or ""),
                                stare_noua,
                            ):
                                salvat_ceva = True
                        except Exception as e:
                            erori_salvare.append(f"{sursa_tbl} #{sursa_rec_id} ({row.get('Piesă')}): {e}")

                    if salvat_ceva:
                        nr_mod += 1

            if editor_dash_key in st.session_state:
                del st.session_state[editor_dash_key]

            _goleste_cache_de_facut()
            if erori_salvare:
                st.error("⚠️ Au apărut erori la salvare:\n" + "\n".join(erori_salvare))
            elif nr_mod == 0:
                st.info("ℹ️ Nu există modificări nesalvate la statusul comenzii.")
            else:
                st.success(f"✅ Stările au fost actualizate în baza de date pentru **{nr_mod}** poziții.")
                st.rerun()


# ==================================================================
# 2.2, 2.3, 5, 6. NOTIȚE & TASK-URI VIZITĂ CLIENT (TOATĂ LĂȚIMEA PAGINII)
# ==================================================================
def render_notite_vizita_de_facut():
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []

    with st.expander("📋 Notițe & Task-uri Vizită Client", expanded=False):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            # 2.3 Firmă și Mașină în afara form-ului, ca să rămână selectate după salvare
            cf1, cf2 = st.columns([1.5, 1.5])
            with cf1:
                firma_viz = st.selectbox(
                    "Firmă (Client) *",
                    options=firme_nume,
                    key="df_nota_firma_sel",
                )
            fid_viz = nume_to_id.get(firma_viz)
            masini_firma_v = [
                str(m.get("denumire") or "").strip()
                for m in masini_all
                if str(m.get("denumire") or "").strip()
                and (fid_viz is None or m.get("firma_id") == fid_viz)
            ]
            opt_masini_viz = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma_v))
            if st.session_state.get("df_nota_masina_sel") not in opt_masini_viz:
                st.session_state["df_nota_masina_sel"] = "-- Fără mașină (opțional) --"

            with cf2:
                masina_viz = st.selectbox(
                    "Mașină (opțional)",
                    options=opt_masini_viz,
                    key="df_nota_masina_sel",
                )

            with st.form("form_adauga_notita_vizita_df", clear_on_submit=True):
                # 5. Controale pentru Data vizitei, De făcut până la data, Stare
                cn1, cn2, cn3 = st.columns([1.2, 1.3, 1.3])
                with cn1:
                    data_viz = st.date_input("Data vizitei *", value=datetime.date.today())
                with cn2:
                    are_termen = st.checkbox("Setează termen limită", value=True)
                    de_facut_pana = st.date_input(
                        "De făcut până la data",
                        value=datetime.date.today() + datetime.timedelta(days=3),
                    )
                with cn3:
                    stare_viz = st.selectbox(
                        "Stare *",
                        options=OPTIUNI_STARE_TASK_VIZITA,
                        index=0,
                    )

                # 6. Note de vizită mai mare, pe rând nou
                note_viz = st.text_area(
                    "Note de vizită *",
                    placeholder="ex: De verificat senzor presiune linie 2, de proiectat suport motor, detalii constatate la client...",
                    height=130,
                )
                salveaza_nota = st.form_submit_button("💾 Salvează Notița", type="primary")

            if salveaza_nota:
                try:
                    TaskuriVizitaRepository.insert(
                        data_vizita=data_viz,
                        de_facut_pana_la=(de_facut_pana if are_termen else None),
                        firma=firma_viz,
                        firma_id=fid_viz,
                        masina=masina_viz,
                        note_vizita=note_viz,
                        stare=stare_viz,
                    )
                    _goleste_cache_de_facut()
                    st.success(
                        f"✅ Notiță salvată pentru **{firma_viz}**"
                        f"{f' ({masina_viz})' if not masina_viz.startswith('--') else ''} — Stare: **{stare_viz}**."
                    )
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

        st.markdown("---")
        taskuri = TaskuriVizitaRepository.get_all() or []
        if not taskuri:
            st.info("Nu există notițe sau task-uri de vizită înregistrate.")
            return

        df_t = pd.DataFrame(taskuri)

        ft1, ft2, ft3 = st.columns([1.4, 1.4, 1.4])
        with ft1:
            firme_filtrare = ["Toate firmele"] + sorted(df_t["firma"].unique().tolist())
            sel_firma_t = st.selectbox("Filtrează după firmă", options=firme_filtrare, key="df_task_filtru_firma")
        with ft2:
            sel_stare_t = st.selectbox(
                "Filtrează după stare",
                options=["Active (fără Finalizat)", "Toate stările"] + OPTIUNI_STARE_TASK_VIZITA,
                key="df_task_filtru_stare",
            )
        with ft3:
            cautare_t = st.text_input(
                "Caută în note",
                placeholder="cuvânt cheie...",
                key="df_task_cautare",
            ).strip().lower()

        df_tf = df_t.copy()
        if sel_firma_t != "Toate firmele":
            df_tf = df_tf[df_tf["firma"] == sel_firma_t]
        if sel_stare_t == "Active (fără Finalizat)":
            df_tf = df_tf[df_tf["stare"] != "Finalizat"]
        elif sel_stare_t != "Toate stările":
            df_tf = df_tf[df_tf["stare"] == sel_stare_t]
        if cautare_t:
            df_tf = df_tf[df_tf["note_vizita"].str.lower().str.contains(cautare_t, na=False)]

        if df_tf.empty:
            st.info("Nu există notițe pentru filtrele selectate.")
            return

        df_t_init = pd.DataFrame([
            {
                "id": int(r["id"]),
                "Data": str(r["data_vizita"]),
                "De făcut până la": r["de_facut_pana_la"] if pd.notna(r["de_facut_pana_la"]) else None,
                "Firmă": str(r["firma"]),
                "Mașină": str(r.get("masina") or "-"),
                "Note de vizită": str(r["note_vizita"]),
                "Stare": normalizeaza_stare_task_vizita(r["stare"]),
                "Șterge": False,
            }
            for _, r in df_tf.iterrows()
        ])

        editor_task_key = f"df_editor_taskuri_{sel_firma_t}_{sel_stare_t}_{len(df_t_init)}"
        edited_t = st.data_editor(
            df_t_init,
            key=editor_task_key,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["id", "Data", "Firmă", "Mașină"],
            column_config={
                "id": None,
                "Data": st.column_config.TextColumn("Data", width="small"),
                "De făcut până la": st.column_config.DateColumn("De făcut până la", width="small"),
                "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
                "Mașină": st.column_config.TextColumn("Mașină", width="medium"),
                "Note de vizită": st.column_config.TextColumn("Note de vizită", width="large", required=True),
                "Stare": st.column_config.SelectboxColumn(
                    "Stare",
                    options=OPTIUNI_STARE_TASK_VIZITA,
                    required=True,
                    width="medium",
                ),
                "Șterge": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
            },
        )

        if st.button("💾 Salvează Modificările Notițe", type="primary", key="btn_df_save_taskuri"):
            df_t_final = edited_t.copy()
            state_t = st.session_state.get(editor_task_key)
            if isinstance(state_t, dict):
                for idx_key, changes in (state_t.get("edited_rows") or {}).items():
                    try:
                        idx = int(idx_key)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= idx < len(df_t_final) and isinstance(changes, dict):
                        for col_name, new_val in changes.items():
                            if col_name in df_t_final.columns:
                                df_t_final.at[idx, col_name] = new_val

            orig_t_map = {int(r["id"]): r for _, r in df_t_init.iterrows()}
            nr_mod_t = 0
            nr_del_t = 0

            for _, row in df_t_final.iterrows():
                tid = int(row["id"])
                if bool(row.get("Șterge", False)):
                    TaskuriVizitaRepository.delete(tid)
                    nr_del_t += 1
                    continue

                orig = orig_t_map.get(tid)
                if orig is None:
                    continue

                nota_noua = str(row.get("Note de vizită") or "").strip()
                stare_noua = normalizeaza_stare_task_vizita(row.get("Stare"))
                termen_raw = row.get("De făcut până la")
                termen_nou = termen_raw if isinstance(termen_raw, datetime.date) else None
                termen_vechi = orig["De făcut până la"] if isinstance(orig["De făcut până la"], datetime.date) else None

                if (
                    nota_noua != str(orig["Note de vizită"]).strip()
                    or stare_noua != normalizeaza_stare_task_vizita(orig["Stare"])
                    or termen_nou != termen_vechi
                ) and nota_noua:
                    TaskuriVizitaRepository.update(tid, nota_noua, stare_noua, de_facut_pana_la=termen_nou)
                    nr_mod_t += 1

            if editor_task_key in st.session_state:
                del st.session_state[editor_task_key]

            if nr_mod_t == 0 and nr_del_t == 0:
                st.info("ℹ️ Nu există modificări nesalvate la notițe.")
            else:
                st.success(f"✅ Notițe actualizate: **{nr_mod_t}** modificate, **{nr_del_t}** șterse.")
                st.rerun()


# ==================================================================
# 8. MEMENTO SCADENȚE ÎNTREȚINERE (MUTAT DIN DASHBOARD)
# ==================================================================
def render_memento_intretinere_de_facut():
    st.subheader("📅 Întrețineri Scadente")
    col_z, col_info = st.columns([1.4, 3.6], vertical_alignment="bottom")
    with col_z:
        zile_avans = st.selectbox(
            "Anunță-mă cu cel puțin:",
            options=[3, 7, 14, 21, 30, 60],
            index=2,
            format_func=lambda x: f"{x} zile înainte",
            key="df_memento_intretinere_zile",
        )

    alerta_rows = incarca_memento_intretinere(zile_avans)
    with col_info:
        if alerta_rows:
            st.warning(
                f"⏰ Ai **{len(alerta_rows)}** utilaje cu întreținerea scadentă în următoarele **{zile_avans}** zile (sau deja depășite)."
            )
        else:
            st.success(f"✅ Nicio întreținere scadentă în următoarele **{zile_avans}** zile.")

    if alerta_rows:
        df_m = pd.DataFrame([
            {
                "Firmă": r.get("firma") or "Fără firmă",
                "Utilaj": r.get("utilaj") or "",
                "Data scadentă": str(r.get("data_scadenta") or ""),
                "Zile rămase": int(r.get("zile_ramase") or 0),
                "Status memento": (
                    "🚨 Depășită" if int(r.get("zile_ramase") or 0) < 0
                    else ("⚠️ Azi" if int(r.get("zile_ramase") or 0) == 0 else "🔔 În curând")
                ),
            }
            for r in alerta_rows
        ])
        df_m = df_m[["Firmă", "Utilaj", "Data scadentă", "Zile rămase", "Status memento"]]
        st.dataframe(df_m, hide_index=True, use_container_width=True)


def render_de_facut():
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.title("✅ De făcut & Activități Teren")
    with col_refresh:
        if st.button("🔄 Actualizează", use_container_width=True, key="btn_df_refresh_unic"):
            _goleste_cache_de_facut()
            st.rerun()

    piese_rows = _colecteaza_piese_necesare()

    # 7. Privire de ansamblu sus în pagină
    render_privire_ansamblu_de_facut(piese_rows)

    st.markdown("---")
    # 1, 2, 3. Notare rapidă piese
    render_notare_rapida_teren()

    # 4. Piese de comandat / necesare & furnizori
    render_tabel_piese_de_comandat(piese_rows)

    # 5, 6. Notițe & task-uri vizită client pe toată lățimea paginii
    render_notite_vizita_de_facut()

    st.markdown("---")
    # 8. Memento scadențe întreținere
    render_memento_intretinere_de_facut()