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
from repositories.setari_repository import SetariRepository
from repositories.taskuri_vizita_repository import (
    OPTIUNI_STARE_TASK_VIZITA,
    TaskuriVizitaRepository,
    formateaza_ora_limita,
    formateaza_termen_complet,
    normalizeaza_stare_task_vizita,
)

try:
    from repositories.cereri_oferta_repository import (
        OPTIUNI_STATUS_CERERE_OFERTA,
        CereriOfertaRepository,
        normalizeaza_status_cerere_oferta,
    )

    _HAS_CERERI_REPO = True
except Exception:
    OPTIUNI_STATUS_CERERE_OFERTA = [
        "Trimis - aștept",
        "Primită - de făcut către client",
        "Ofertat la client",
        "Închisă",
    ]
    CereriOfertaRepository = None
    _HAS_CERERI_REPO = False

    def normalizeaza_status_cerere_oferta(val):
        s = str(val or "").strip()
        return s if s in OPTIUNI_STATUS_CERERE_OFERTA else "Trimis - aștept"


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
            c.execute(
                """
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
            """,
                (zile,),
            )
            return [dict(r) for r in (c.fetchall() or [])]
    except Exception:
        with db_cursor() as c:
            c.execute(
                """
                SELECT
                    id,
                    'Fără firmă' AS firma,
                    denumire AS utilaj,
                    CAST(data_intretinere AS DATE) AS data_scadenta,
                    (CAST(m.data_intretinere AS DATE) - CURRENT_DATE) AS zile_ramase
                FROM masini m
                WHERE COALESCE(m.fara_intretinere, FALSE) = FALSE
                  AND m.data_intretinere IS NOT NULL
                  AND CAST(m.data_intretinere AS DATE) <= (CURRENT_DATE + make_interval(days => %s))
                ORDER BY CAST(m.data_intretinere AS DATE) ASC, m.denumire ASC
            """,
                (zile,),
            )
            return [dict(r) for r in (c.fetchall() or [])]


def _goleste_cache_de_facut():
    incarca_memento_intretinere.clear()
    _incarca_optiuni_lookup_piese.clear()
    for repo in (PieseRepository, NecesarPieseRepository, TaskuriVizitaRepository, CereriOfertaRepository):
        if repo is None:
            continue
        for method_name in ("get_all", "get_cereri", "get_linii_by_cerere"):
            fn = getattr(repo, method_name, None)
            if fn is not None and hasattr(fn, "clear"):
                try:
                    fn.clear()
                except Exception:
                    pass


def _extrage_furnizor_piesa(piesa_row: dict) -> str:
    for k in ("furnizor", "nume_furnizor", "furnizor_principal", "supplier", "link_furnizor"):
        val = str(piesa_row.get(k) or "").strip()
        if val:
            return val
    return "Fără furnizor setat"


def _extrage_piese_inlocuitoare(row_dict: dict) -> str:
    for k in ("piese_inlocuitoare", "echivalente", "cod_echivalent", "piese_echivalente", "inlocuitor"):
        val = str(row_dict.get(k) or "").strip()
        if val:
            return val
    return "-"


def _extrage_link_gdrive(piesa_row: dict) -> str:
    try:
        setari = SetariRepository.get_setari() or {}
    except Exception:
        setari = {}

    link_setari = str(setari.get("locatie_documentatii_gdrive") or "").strip()
    if link_setari.startswith(("http://", "https://")):
        return link_setari

    for k in ("link_gdrive", "gdrive_url", "gdrive_link", "url_documentatie", "documentatie_url", "link_doc"):
        val = str(piesa_row.get(k) or "").strip()
        if val.startswith(("http://", "https://")):
            return val

    return ""


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
    gdrive_by_name = {}
    inloc_by_name = {}

    for p in piese_db:
        den = str(p.get("denumire") or p.get("nume") or "").strip()
        if den:
            cheie = " ".join(den.lower().split())
            furnizor_map[cheie] = _extrage_furnizor_piesa(p)
            piesa_id_by_name[cheie] = p.get("id")
            stare_catalog_by_name[cheie] = _normalizeaza_stare_comanda(p.get("stare_comandata"))
            gdrive_by_name[cheie] = _extrage_link_gdrive(p)
            inloc_by_name[cheie] = _extrage_piese_inlocuitoare(p)

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
        link_gd = gdrive_by_name.get(cheie) or _extrage_link_gdrive(np_row)
        piese_inloc_np = _extrage_piese_inlocuitoare(np_row)
        if piese_inloc_np == "-":
            piese_inloc_np = inloc_by_name.get(cheie, "-")

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
            "Piese înlocuitoare": piese_inloc_np,
            "Doc GDrive": link_gd,
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
            link_gd = gdrive_by_name.get(cheie) or _extrage_link_gdrive({})
            piese_inloc = _extrage_piese_inlocuitoare(item)
            if piese_inloc == "-":
                piese_inloc = inloc_by_name.get(cheie, "-")

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
                "Piese înlocuitoare": piese_inloc,
                "Doc GDrive": link_gd,
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
            link_gd = gdrive_by_name.get(cheie) or _extrage_link_gdrive({})
            piese_inloc = _extrage_piese_inlocuitoare(comp)
            if piese_inloc == "-":
                piese_inloc = inloc_by_name.get(cheie, "-")

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
                "Piese înlocuitoare": piese_inloc,
                "Doc GDrive": link_gd,
                "Raport": f"EL #{f_el.get('id')}",
            })

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
            for t in taskuri_urgente[:8]:
                termen_txt = formateaza_termen_complet(t.get("de_facut_pana_la"), t.get("ora_limita"))
                st.markdown(
                    f"""
                    <div style="background:#FEF2F2;border-left:5px solid #DC2626;padding:8px 12px;margin-bottom:6px;border-radius:4px;">
                        <div style="color:#B91C1C;font-size:1.12rem;font-weight:700;">
                            🚨 {t.get('firma') or '-'} {f"• {t.get('masina')}" if t.get('masina') else ""}
                        </div>
                        <div style="color:#7F1D1D;font-size:1.05rem;margin-top:2px;">{t.get('note_vizita') or ''}</div>
                        <div style="color:#991B1B;font-size:0.95rem;margin-top:2px;">⏰ Până la: <b>{termen_txt}</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ Niciun task urgent în așteptare.")

    with c_ov2:
        st.markdown("##### 🔥 Piese Prioritare (Urgent / De ofertat / De căutat)")
        piese_active_ord = [
            p for p in piese_rows
            if p.get("Stare Piesă") == "Urgent" or p.get("Status Comandă") in ("De comandat", "De ofertat", "De căutat")
        ]
        if piese_active_ord:
            df_po = pd.DataFrame([
                {
                    "Stare Piesă": p.get("Stare Piesă"),
                    "Status": p.get("Status Comandă"),
                    "Piesă": p.get("Piesă"),
                    "Cant.": p.get("Cantitate"),
                    "Firmă": p.get("Firmă") or "-",
                    "Doc GDrive": p.get("Doc GDrive") or None,
                }
                for p in piese_active_ord[:12]
            ])

            def _stil_rand_ov(row):
                if row.get("Stare Piesă") == "Urgent":
                    return ["background-color: #FEE2E2; color: #991B1B; font-weight: 700;"] * len(row)
                if row.get("Status") == "De ofertat":
                    return ["background-color: #FEF9C3; color: #854D0E; font-weight: 600;"] * len(row)
                if row.get("Status") == "De căutat":
                    return ["background-color: #DBEAFE; color: #1E40AF; font-weight: 600;"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_po.style.apply(_stil_rand_ov, axis=1),
                column_config={
                    "Doc GDrive": st.column_config.LinkColumn("Doc GDrive", display_text="📂 GDrive"),
                },
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("✅ Nicio piesă în așteptare.")


def _randeaza_lista_carduri_taskuri(task_list: list[dict], nivel: str):
    if nivel == "urgent":
        bg = "#FEF2F2"
        border = "#DC2626"
        text_col = "#991B1B"
        title_size = "1.18rem"
        body_size = "1.08rem"
        badge = "🚨 URGENT"
    else:
        bg = "#FEF9C3"
        border = "#D97706"
        text_col = "#854D0E"
        title_size = "1.02rem"
        body_size = "0.98rem"
        badge = "🟡 NORMAL"

    for t in task_list:
        tid = int(t["id"])
        termen_str = formateaza_termen_complet(t.get("de_facut_pana_la"), t.get("ora_limita"))
        masina_str = f" — <i>{t.get('masina')}</i>" if t.get("masina") else ""

        c_card, c_done, c_del = st.columns([6.2, 1.1, 0.9], vertical_alignment="center")
        with c_card:
            st.markdown(
                f"""
                <div style="background:{bg};border-left:5px solid {border};padding:10px 14px;border-radius:6px;margin-bottom:6px;">
                    <div style="color:{text_col};font-size:{title_size};font-weight:700;">
                        {badge} • {t.get('firma') or '-'}{masina_str}
                    </div>
                    <div style="color:{text_col};font-size:{body_size};margin-top:4px;">
                        {t.get('note_vizita') or ''}
                    </div>
                    <div style="color:{text_col};font-size:0.88rem;opacity:0.9;margin-top:4px;">
                        📅 Vizită: {str(t.get('data_vizita') or '')[:10]} &nbsp;|&nbsp;
                        ⏰ Termen: <b>{termen_str}</b> &nbsp;|&nbsp;
                        Stare: <b>{t.get('stare')}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c_done:
            if t.get("stare") != "Finalizat":
                if st.button("✅ Completed", key=f"btn_done_task_{nivel}_{tid}", use_container_width=True):
                    if hasattr(TaskuriVizitaRepository, "mark_completed"):
                        TaskuriVizitaRepository.mark_completed(tid)
                    else:
                        TaskuriVizitaRepository.update(
                            tid,
                            str(t.get("note_vizita") or ""),
                            "Finalizat",
                            de_facut_pana_la=t.get("de_facut_pana_la"),
                        )
                    _goleste_cache_de_facut()
                    st.rerun()
        with c_del:
            if st.button("🗑️ Șterge", key=f"btn_del_task_{nivel}_{tid}", use_container_width=True):
                TaskuriVizitaRepository.delete(tid)
                _goleste_cache_de_facut()
                st.rerun()


def render_notite_vizita_de_facut():
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []

    with st.expander("📋 Notițe & Task-uri Vizită Client", expanded=True):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            cf1, cf2 = st.columns([1.5, 1.5])
            with cf1:
                firma_viz = st.selectbox("Firmă (Client) *", options=firme_nume, key="df_nota_firma_sel")
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
                masina_viz = st.selectbox("Mașină (opțional)", options=opt_masini_viz, key="df_nota_masina_sel")

            with st.form("form_adauga_notita_vizita_df", clear_on_submit=True):
                cn1, cn2, cn3, cn4 = st.columns([1.15, 1.25, 1.0, 1.3], vertical_alignment="bottom")
                with cn1:
                    data_viz = st.date_input("Data vizitei *", value=datetime.date.today())
                with cn2:
                    de_facut_pana = st.date_input(
                        "De făcut până la *",
                        value=datetime.date.today() + datetime.timedelta(days=3),
                    )
                with cn3:
                    ora_limita_inp = st.time_input("Ora due date", value=datetime.time(17, 0))
                with cn4:
                    stare_viz = st.selectbox("Stare *", options=OPTIUNI_STARE_TASK_VIZITA, index=0)

                note_viz = st.text_area(
                    "Note de vizită *",
                    placeholder="ex: De verificat senzor presiune linie 2, de proiectat suport motor...",
                    height=130,
                )
                salveaza_nota = st.form_submit_button("💾 Salvează Notița", type="primary")

            if salveaza_nota:
                try:
                    TaskuriVizitaRepository.insert(
                        data_vizita=data_viz,
                        de_facut_pana_la=de_facut_pana,
                        ora_limita=ora_limita_inp,
                        firma=firma_viz,
                        firma_id=fid_viz,
                        masina=masina_viz,
                        note_vizita=note_viz,
                        stare=stare_viz,
                    )
                    _goleste_cache_de_facut()
                    st.success(f"✅ Notiță salvată pentru **{firma_viz}** — Stare: **{stare_viz}**.")
                    st.rerun()
                except TypeError:
                    TaskuriVizitaRepository.insert(
                        data_vizita=data_viz,
                        de_facut_pana_la=de_facut_pana,
                        firma=firma_viz,
                        firma_id=fid_viz,
                        masina=masina_viz,
                        note_vizita=note_viz,
                        stare=stare_viz,
                    )
                    _goleste_cache_de_facut()
                    st.success(f"✅ Notiță salvată pentru **{firma_viz}** — Stare: **{stare_viz}**.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

        st.markdown("---")
        taskuri = TaskuriVizitaRepository.get_all() or []
        if not taskuri:
            st.info("Nu există notițe sau task-uri de vizită înregistrate.")
            return

        taskuri_urgente = [t for t in taskuri if t.get("stare") == "Urgent"]
        taskuri_normale = [t for t in taskuri if t.get("stare") not in ("Urgent", "Finalizat")]

        st.markdown("#### 🚨 Task-uri Urgente")
        if taskuri_urgente:
            _randeaza_lista_carduri_taskuri(taskuri_urgente, nivel="urgent")
        else:
            st.caption("Nu există task-uri urgente active.")

        st.markdown("#### 🟡 Task-uri Nivel Normal")
        if taskuri_normale:
            _randeaza_lista_carduri_taskuri(taskuri_normale, nivel="normal")
        else:
            st.caption("Nu există task-uri normale active.")

        st.markdown("---")
        st.markdown("#### ✏️ Editare Rapidă în Tabel")
        df_t = pd.DataFrame(taskuri)
        df_t_init = pd.DataFrame([
            {
                "id": int(r["id"]),
                "Data": str(r["data_vizita"]),
                "De făcut până la": r["de_facut_pana_la"] if pd.notna(r["de_facut_pana_la"]) else None,
                "Ora limită": formateaza_ora_limita(r.get("ora_limita")),
                "Stare": normalizeaza_stare_task_vizita(r["stare"]),
                "Firmă": str(r["firma"]),
                "Mașină": str(r.get("masina") or "-"),
                "Note de vizită": str(r["note_vizita"]),
                "Completed": r["stare"] == "Finalizat",
                "Șterge": False,
            }
            for _, r in df_t.iterrows()
        ])

        editor_task_key = f"df_editor_taskuri_{len(df_t_init)}"
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
                "Ora limită": st.column_config.TextColumn("Ora (HH:MM)", width="small"),
                "Stare": st.column_config.SelectboxColumn("Stare", options=OPTIUNI_STARE_TASK_VIZITA, required=True, width="medium"),
                "Firmă": st.column_config.TextColumn("Firmă", width="medium"),
                "Mașină": st.column_config.TextColumn("Mașină", width="medium"),
                "Note de vizită": st.column_config.TextColumn("Note de vizită", width="large", required=True),
                "Completed": st.column_config.CheckboxColumn("✅ Completed", default=False, width="small"),
                "Șterge": st.column_config.CheckboxColumn("🗑️ Șterge", default=False, width="small"),
            },
        )

        if st.button("💾 Salvează Modificările din Tabel", type="primary", key="btn_df_save_taskuri"):
            orig_t_map = {int(r["id"]): r for _, r in df_t_init.iterrows()}
            nr_mod_t = 0
            nr_del_t = 0

            for _, row in edited_t.iterrows():
                tid = int(row["id"])
                if bool(row.get("Șterge", False)):
                    TaskuriVizitaRepository.delete(tid)
                    nr_del_t += 1
                    continue

                orig = orig_t_map.get(tid)
                if orig is None:
                    continue

                nota_noua = str(row.get("Note de vizită") or "").strip()
                stare_noua = "Finalizat" if bool(row.get("Completed", False)) else normalizeaza_stare_task_vizita(row.get("Stare"))
                termen_raw = row.get("De făcut până la")
                termen_nou = termen_raw if isinstance(termen_raw, datetime.date) else None
                termen_vechi = orig["De făcut până la"] if isinstance(orig["De făcut până la"], datetime.date) else None
                ora_noua = formateaza_ora_limita(row.get("Ora limită"))
                ora_veche = formateaza_ora_limita(orig.get("Ora limită"))

                if (
                    nota_noua != str(orig["Note de vizită"]).strip()
                    or stare_noua != normalizeaza_stare_task_vizita(orig["Stare"])
                    or termen_nou != termen_vechi
                    or ora_noua != ora_veche
                ) and nota_noua:
                    try:
                        TaskuriVizitaRepository.update(
                            tid,
                            nota_noua,
                            stare_noua,
                            de_facut_pana_la=termen_nou,
                            ora_limita=ora_noua,
                        )
                    except TypeError:
                        TaskuriVizitaRepository.update(tid, nota_noua, stare_noua, de_facut_pana_la=termen_nou)
                    nr_mod_t += 1

            if editor_task_key in st.session_state:
                del st.session_state[editor_task_key]

            _goleste_cache_de_facut()
            if nr_mod_t == 0 and nr_del_t == 0:
                st.info("ℹ️ Nu există modificări nesalvate la notițe.")
            else:
                st.success(f"✅ Actualizate: **{nr_mod_t}** modificate, **{nr_del_t}** șterse.")
                st.rerun()


def render_notare_rapida_teren():
    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []
    optiuni_piese, detalii_piese = _incarca_optiuni_lookup_piese()

    with st.expander("📝 Notare Rapidă Piese pe Teren (Client obligatoriu • Mașină opțională)", expanded=False):
        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
            return

        c_fm1, c_fm2 = st.columns([1.5, 1.5])
        with c_fm1:
            firma_teren = st.selectbox("Client / Firmă *", options=firme_nume, key="df_teren_firma_sel")
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
            masina_teren = st.selectbox("Mașină (opțional)", options=opt_masini_teren, key="df_teren_masina_sel")

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
                prioritate_teren = st.selectbox("Stare piesă *", options=OPTIUNI_PRIORITATE_PIESA, key="df_teren_prio_sel")
            with c_t5:
                status_teren = st.selectbox("Status Comandă *", options=OPTIUNI_STATUS_TEREN, key="df_teren_status_sel")

            obs_teren = st.text_area(
                "Observații / detalii notate la client (opțional)",
                placeholder="ex: cerută la vizită, verificare ofertă...",
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

                st.session_state["df_teren_lookup_piesa"] = "✍️ Piesă nouă (scriu manual)"
                st.session_state["_df_last_lookup"] = "✍️ Piesă nouă (scriu manual)"
                st.session_state["df_teren_den_manual"] = ""
                st.session_state["df_teren_cod_manual"] = ""
                st.session_state["df_teren_cant_num"] = 1.0
                st.session_state["df_teren_prio_sel"] = "Normal"
                st.session_state["df_teren_status_sel"] = "De căutat"
                st.session_state["df_teren_obs_txt"] = ""

                mesaj_cat = "existentă în catalog" if rez.get("existenta_in_catalog") else "adăugată și în catalogul `piese`"
                st.success(
                    f"✅ Salvat **{str(den_finala).strip()}** ({mesaj_cat}). "
                    f"Pregătit pentru următoarea piesă la **{firma_teren}**."
                )
                st.rerun()
            except ValueError as ve:
                st.error(f"⚠️ {ve}")


def render_tabel_piese_de_comandat(randuri: list[dict]):
    with st.expander("🛒 Piese De Comandat / Necesare & Furnizori", expanded=False):
        st.markdown(
            "🔴 **Urgent** &nbsp;|&nbsp; 🟡 **De ofertat** &nbsp;|&nbsp; 🔵 **De căutat** — "
            "Schimbă direct **Stare Piesă** sau **Status Comandă** și apasă **💾 Actualizează Stările în Tabel**."
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
            filtru_furn = st.selectbox("Filtrează după furnizor", options=opt_furn, key="df_piese_cmd_furn")
        with c3:
            filtru_stare = st.selectbox("Filtrează după status", options=["Toate stările"] + OPTIUNI_STARE_COMANDA, key="df_piese_cmd_stare")
        with c4:
            cautare_piesa = st.text_input("Caută piesă / cod", placeholder="ex: L6376PD, SFH6106...", key="df_piese_cmd_cautare").strip().lower()

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

        df_color = df_f[[
            "Stare Piesă",
            "Piesă",
            "Cantitate",
            "Status Comandă",
            "Furnizor",
            "Sursă",
            "Firmă",
            "Mașină",
            "Piese înlocuitoare",
            "Doc GDrive",
        ]].reset_index(drop=True)
        df_color["Doc GDrive"] = df_color["Doc GDrive"].apply(lambda x: x if str(x or "").startswith(("http://", "https://")) else None)

        def _stil_rand_piese(row):
            if row.get("Stare Piesă") == "Urgent":
                return ["background-color: #FEE2E2; color: #991B1B; font-weight: 700;"] * len(row)
            if row.get("Status Comandă") == "De ofertat":
                return ["background-color: #FEF9C3; color: #854D0E; font-weight: 600;"] * len(row)
            if row.get("Status Comandă") == "De căutat":
                return ["background-color: #DBEAFE; color: #1E40AF; font-weight: 600;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_color.style.apply(_stil_rand_piese, axis=1),
            column_config={
                "Doc GDrive": st.column_config.LinkColumn("Doc GDrive", display_text="📂 GDrive"),
            },
            hide_index=True,
            use_container_width=True,
        )

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
            "Piese înlocuitoare",
            "Doc GDrive",
            "Raport",
        ]
        df_editor_init = df_f[cols_afis].reset_index(drop=True)
        df_editor_init["Doc GDrive"] = df_editor_init["Doc GDrive"].apply(lambda x: x if str(x or "").startswith(("http://", "https://")) else None)
        editor_dash_key = f"df_editor_stare_piese_{filtru_sursa}_{filtru_furn}_{filtru_stare}"

        edited_df = st.data_editor(
            df_editor_init,
            key=editor_dash_key,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            disabled=["_row_id", "Piesă", "Cantitate", "Furnizor", "Sursă", "Firmă", "Mașină", "Piese înlocuitoare", "Doc GDrive", "Raport"],
            column_config={
                "_row_id": None,
                "Stare Piesă": st.column_config.SelectboxColumn("Stare Piesă", options=OPTIUNI_PRIORITATE_PIESA, required=True, width="small"),
                "Piesă": st.column_config.TextColumn("Piesă", width="large"),
                "Cantitate": st.column_config.NumberColumn("Cantitate", format="%.2f", width="small"),
                "Status Comandă": st.column_config.SelectboxColumn("Status Comandă", options=OPTIUNI_STARE_COMANDA, required=True, width="medium"),
                "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                "Sursă": st.column_config.TextColumn("Sursă", width="small"),
                "Firmă": st.column_config.TextColumn("Firmă", width="small"),
                "Mașină": st.column_config.TextColumn("Mașină", width="small"),
                "Piese înlocuitoare": st.column_config.TextColumn("Piese înlocuitoare", width="medium"),
                "Doc GDrive": st.column_config.LinkColumn("Doc GDrive", display_text="📂 GDrive", width="small"),
                "Raport": st.column_config.TextColumn("Raport", width="small"),
            },
        )

        if st.button("💾 Actualizează Stările în Tabel", type="primary", key="btn_df_update_stare_piese"):
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

            orig_status_map = {int(r["_row_id"]): _normalizeaza_stare_comanda(r["Status Comandă"]) for _, r in df_editor_init.iterrows()}
            orig_prio_map = {int(r["_row_id"]): normalizeaza_prioritate_piesa(r["Stare Piesă"]) for _, r in df_editor_init.iterrows()}
            nr_mod = 0
            erori_salvare = []

            for _, row in edited_df.iterrows():
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
                            if _actualizeaza_stare_in_raport_json(sursa_tbl, int(sursa_rec_id), str(row.get("Piesă") or ""), stare_noua):
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
                st.info("ℹ️ Nu există modificări nesalvate.")
            else:
                st.success(f"✅ Stările au fost actualizate în baza de date pentru **{nr_mod}** poziții.")
                st.rerun()


def render_cereri_oferta_furnizori_de_facut():
    if not _HAS_CERERI_REPO or CereriOfertaRepository is None:
        with st.expander("📨 Cereri Ofertă Furnizori (RFQ) & Analiză Prețuri", expanded=False):
            st.info("Adaugă fișierul `repositories/cereri_oferta_repository.py` pentru a activa cererile către furnizori și analiza ofertelor primite.")
        return

    firme_nume, nume_to_id = _obtine_harta_firme()
    masini_all = MasiniRepository.get_all() or []
    piese_catalog = PieseRepository.get_all() or []
    necesar_rows = NecesarPieseRepository.get_all() or []

    with st.expander("📨 Cereri Ofertă Furnizori (RFQ) • Analiză Prețuri & Legătură Client / Mașină", expanded=False):
        st.markdown("##### 1. Creează Cerere de Ofertă către Furnizori")

        if not firme_nume:
            st.warning("⚠️ Nu există firme înregistrate în baza de date.")
        else:
            cf_a, cf_b, cf_c = st.columns([1.4, 1.4, 1.2])
            with cf_a:
                firma_rfq = st.selectbox("Client / Firmă *", options=firme_nume, key="df_rfq_firma_sel")
            fid_rfq = nume_to_id.get(firma_rfq)

            masini_firma_rfq = [
                m for m in masini_all
                if str(m.get("denumire") or "").strip() and (fid_rfq is None or m.get("firma_id") == fid_rfq)
            ]
            mapa_masini_rfq = {str(m.get("denumire")).strip(): m for m in masini_firma_rfq}
            opt_masini_rfq = ["-- Fără mașină (opțional) --"] + sorted(mapa_masini_rfq.keys())
            with cf_b:
                masina_rfq = st.selectbox("Mașină (opțional)", options=opt_masini_rfq, key="df_rfq_masina_sel")
            mid_rfq = mapa_masini_rfq.get(masina_rfq, {}).get("id") if not masina_rfq.startswith("--") else None

            with cf_c:
                termen_rfq = st.date_input(
                    "Termen răspuns furnizor",
                    value=datetime.date.today() + datetime.timedelta(days=2),
                    key="df_rfq_termen_data",
                )

            furnizori_cunoscuti = sorted({
                _extrage_furnizor_piesa(p)
                for p in piese_catalog
                if _extrage_furnizor_piesa(p) and _extrage_furnizor_piesa(p) != "Fără furnizor setat"
            })
            furn_col1, furn_col2 = st.columns([2.2, 1.8])
            with furn_col1:
                furn_selectati = st.multiselect("Furnizori din catalog (opțional)", options=furnizori_cunoscuti, key="df_rfq_furn_multi")
            with furn_col2:
                furn_manual = st.text_input("Furnizori suplimentari (separați prin virgulă)", placeholder="ex: Furnizor A, Furnizor B", key="df_rfq_furn_manual")

            piese_din_necesar_client = [
                np_r for np_r in necesar_rows
                if str(np_r.get("firma_client") or "").strip().lower() == str(firma_rfq or "").strip().lower()
            ]
            opt_piese_nec = {
                f"{r.get('denumire_piesa')} (cant. {r.get('cantitate')})": r
                for r in piese_din_necesar_client
                if str(r.get("denumire_piesa") or "").strip()
            }
            piese_nec_alese = st.multiselect("Preia piese din necesarul clientului (opțional)", options=list(opt_piese_nec.keys()), key="df_rfq_piese_nec_multi")

            with st.form("form_creeaza_cerere_rfq", clear_on_submit=True):
                cp1, cp2, cp3, cp4 = st.columns([2.2, 1.3, 0.9, 1.4])
                with cp1:
                    piesa_extra_den = st.text_input("Sau adaugă piesă manuală în cerere", placeholder="ex: Rulment 6206 / Electrovana")
                with cp2:
                    piesa_extra_cod = st.text_input("Cod producător", placeholder="opțional")
                with cp3:
                    piesa_extra_cant = st.number_input("Cant.", min_value=0.01, value=1.0, step=1.0, format="%.2f")
                with cp4:
                    piesa_extra_inloc = st.text_input("Piese înlocuitoare", placeholder="ex: SKF 6206, FAG 6206")

                obs_rfq = st.text_area("Observații cerere ofertă", height=70, placeholder="detalii tehnice, coduri...")
                btn_creeaza_rfq = st.form_submit_button("📤 Creează Cererea de Ofertă", type="primary")

            if btn_creeaza_rfq:
                linii_de_trimis = []
                for lbl_n in piese_nec_alese:
                    nr = opt_piese_nec.get(lbl_n) or {}
                    linii_de_trimis.append({
                        "piesa_id": nr.get("piesa_id"),
                        "denumire_piesa": nr.get("denumire_piesa"),
                        "cod_producator": nr.get("cod_producator", ""),
                        "piese_inlocuitoare": _extrage_piese_inlocuitoare(nr) if _extrage_piese_inlocuitoare(nr) != "-" else "",
                        "cantitate": float(nr.get("cantitate") or 1.0),
                        "pret_unitar": 0.0,
                        "moneda": "EUR",
                        "termen_livrare_zile": "",
                    })

                if str(piesa_extra_den or "").strip():
                    linii_de_trimis.append({
                        "piesa_id": None,
                        "denumire_piesa": str(piesa_extra_den).strip(),
                        "cod_producator": str(piesa_extra_cod or "").strip(),
                        "piese_inlocuitoare": str(piesa_extra_inloc or "").strip(),
                        "cantitate": float(piesa_extra_cant or 1.0),
                        "pret_unitar": 0.0,
                        "moneda": "EUR",
                        "termen_livrare_zile": "",
                    })

                furn_finale = list(dict.fromkeys(
                    list(furn_selectati or [])
                    + [x.strip() for x in str(furn_manual or "").split(",") if x.strip()]
                ))

                try:
                    cer_noua = CereriOfertaRepository.creeaza_cerere(
                        firma_nume=firma_rfq,
                        firma_id=fid_rfq,
                        masina_nume=masina_rfq,
                        masina_id=mid_rfq,
                        termen_raspuns=termen_rfq,
                        observatii=obs_rfq,
                        linii_piese=linii_de_trimis,
                        furnizori_selectati=furn_finale,
                    )
                    _goleste_cache_de_facut()
                    st.success(f"✅ Cererea **{cer_noua.get('cod_cerere')}** a fost creată cu status **Trimis - aștept**.")
                    st.rerun()
                except ValueError as ve:
                    st.error(f"⚠️ {ve}")

        st.markdown("---")
        st.markdown("##### 2. Tabel Cereri de Ofertă către Furnizori")

        cereri_all = CereriOfertaRepository.get_cereri() or []
        if not cereri_all:
            st.info("Nu există cereri de ofertă către furnizori înregistrate.")
            return

        filtru_st_cer = st.selectbox("Filtrează după starea cererii", options=["Toate"] + OPTIUNI_STATUS_CERERE_OFERTA, key="df_rfq_filtru_status")
        cereri_filtrate = [
            c for c in cereri_all
            if filtru_st_cer == "Toate" or normalizeaza_status_cerere_oferta(c.get("status_cerere")) == filtru_st_cer
        ]

        df_cer = pd.DataFrame([
            {
                "id": int(c["id"]),
                "Cod Cerere": str(c.get("cod_cerere") or ""),
                "Stare Cerere": normalizeaza_status_cerere_oferta(c.get("status_cerere")),
                "Client": str(c.get("firma_nume") or ""),
                "Mașină": str(c.get("masina_nume") or "-"),
                "Data Trimitere": str(c.get("data_trimitere") or "")[:10],
                "Termen Răspuns": str(c.get("termen_raspuns") or "-")[:10],
                "Ofertă Client ID": str(c.get("oferta_client_id") or "-"),
                "Observații": str(c.get("observatii") or ""),
            }
            for c in cereri_filtrate
        ])

        def _stil_status_cerere(row):
            st_v = row.get("Stare Cerere")
            if st_v == "Primită - de făcut către client":
                return ["background-color: #FEF9C3; color: #854D0E; font-weight: 700;"] * len(row)
            if st_v == "Trimis - aștept":
                return ["background-color: #DBEAFE; color: #1E40AF; font-weight: 600;"] * len(row)
            if st_v == "Ofertat la client":
                return ["background-color: #DCFCE7; color: #166534; font-weight: 600;"] * len(row)
            return [""] * len(row)

        st.dataframe(df_cer.drop(columns=["id"]).style.apply(_stil_status_cerere, axis=1), hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("##### 3. Analiză Oferte Primite de la Furnizori & Legătură cu Oferta către Client")

        mapa_cereri = {
            f"{c.get('cod_cerere')} | {c.get('firma_nume')} ({normalizeaza_status_cerere_oferta(c.get('status_cerere'))})": c
            for c in cereri_filtrate
        }
        sel_cer_lbl = st.selectbox("Selectează cererea pentru analiză:", options=list(mapa_cereri.keys()), key="df_rfq_sel_analiza")
        cer_activa = mapa_cereri[sel_cer_lbl]
        cid_activa = int(cer_activa["id"])
        linii_cer = CereriOfertaRepository.get_linii_by_cerere(cid_activa) or []

        cs_left, cs_right = st.columns([2.0, 2.0], vertical_alignment="bottom")
        with cs_left:
            st_curent = normalizeaza_status_cerere_oferta(cer_activa.get("status_cerere"))
            nou_st_cer = st.selectbox(
                "Stare cerere",
                options=OPTIUNI_STATUS_CERERE_OFERTA,
                index=OPTIUNI_STATUS_CERERE_OFERTA.index(st_curent),
                key=f"df_rfq_st_sel_{cid_activa}",
            )
        with cs_right:
            if st.button("🔄 Actualizează Starea Cererii", key=f"df_rfq_btn_st_{cid_activa}", use_container_width=True):
                CereriOfertaRepository.update_status_cerere(cid_activa, nou_st_cer)
                _goleste_cache_de_facut()
                st.success(f"✅ Starea cererii {cer_activa.get('cod_cerere')} a devenit **{nou_st_cer}**.")
                st.rerun()

        if linii_cer:
            df_lin_init = pd.DataFrame([
                {
                    "id": int(l["id"]),
                    "Furnizor": str(l.get("furnizor_nume") or ""),
                    "Piesă": str(l.get("denumire_piesa") or ""),
                    "Cod Prod.": str(l.get("cod_producator") or ""),
                    "Piese înlocuitoare": str(l.get("piese_inlocuitoare") or ""),
                    "Cant.": float(l.get("cantitate") or 1.0),
                    "Preț Unitar": float(l.get("pret_unitar") or 0.0),
                    "Monedă": str(l.get("moneda") or "EUR"),
                    "Termen livrare": str(l.get("termen_livrare_zile") or ""),
                    "Selectat Client": bool(l.get("selectat_pentru_client", False)),
                }
                for l in linii_cer
            ])

            df_lin_edit = st.data_editor(
                df_lin_init,
                key=f"df_rfq_linii_editor_{cid_activa}",
                hide_index=True,
                num_rows="fixed",
                use_container_width=True,
                disabled=["id", "Piesă", "Cod Prod.", "Cant."],
                column_config={
                    "id": None,
                    "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
                    "Piesă": st.column_config.TextColumn("Piesă", width="large"),
                    "Cod Prod.": st.column_config.TextColumn("Cod Prod.", width="small"),
                    "Piese înlocuitoare": st.column_config.TextColumn("Piese înlocuitoare", width="medium"),
                    "Cant.": st.column_config.NumberColumn("Cant.", format="%.2f", width="small"),
                    "Preț Unitar": st.column_config.NumberColumn("Preț Unitar", min_value=0.0, format="%.2f", width="small"),
                    "Monedă": st.column_config.SelectboxColumn("Monedă", options=["EUR", "RON"], width="small"),
                    "Termen livrare": st.column_config.TextColumn("Termen livrare", width="small"),
                    "Selectat Client": st.column_config.CheckboxColumn("✅ Client", default=False, width="small"),
                },
            )

            df_analiza = df_lin_edit.copy()
            df_analiza["Total Linie"] = (
                pd.to_numeric(df_analiza["Cant."], errors="coerce").fillna(0.0)
                * pd.to_numeric(df_analiza["Preț Unitar"], errors="coerce").fillna(0.0)
            ).round(2)
            rezumat_furn = (
                df_analiza.groupby(["Furnizor", "Monedă"], as_index=False)["Total Linie"]
                .sum()
                .sort_values(by="Total Linie", ascending=True)
            )
            if not rezumat_furn.empty:
                st.caption("📊 **Analiză comparativă oferte furnizori:**")
                st.dataframe(rezumat_furn, hide_index=True, use_container_width=True)

            ca_b1, ca_b2 = st.columns(2)
            with ca_b1:
                if st.button(
                    "💾 Salvează Oferta Primită de la Furnizor (+ Task Ofertă Client)",
                    type="primary",
                    key=f"df_rfq_save_primita_{cid_activa}",
                    use_container_width=True,
                ):
                    payload_linii = [
                        {
                            "id": int(r["id"]),
                            "furnizor_nume": str(r.get("Furnizor") or "").strip(),
                            "pret_unitar": float(pd.to_numeric(r.get("Preț Unitar"), errors="coerce") or 0.0),
                            "moneda": str(r.get("Monedă") or "EUR").strip().upper(),
                            "termen_livrare_zile": str(r.get("Termen livrare") or "").strip(),
                            "piese_inlocuitoare": str(r.get("Piese înlocuitoare") or "").strip(),
                            "selectat_pentru_client": bool(r.get("Selectat Client", False)),
                        }
                        for _, r in df_lin_edit.iterrows()
                    ]
                    CereriOfertaRepository.salveaza_oferta_primita_furnizor(cid_activa, payload_linii)
                    _goleste_cache_de_facut()
                    st.success(
                        f"✅ Oferta furnizor pentru **{cer_activa.get('firma_nume')}** ({cer_activa.get('cod_cerere')}) "
                        f"a fost salvată și s-a adăugat task-ul în lista de task-uri."
                    )
                    st.rerun()

            with ca_b2:
                if st.button(
                    "🚀 Pregătește Liniile în Oferta către Client",
                    key=f"df_rfq_prep_oferta_client_{cid_activa}",
                    use_container_width=True,
                ):
                    firme_all = FirmeRepository.get_all() or []
                    firma_nume = str(cer_activa.get("firma_nume") or "").strip()
                    firma_obj = next((f for f in firme_all if str(f.get("nume_firma") or "").strip() == firma_nume), {})
                    adaos_client = float(firma_obj.get("adaos_comercial", 20.0) or 20.0)

                    linii_sel = [r for _, r in df_lin_edit.iterrows() if bool(r.get("Selectat Client", False))]
                    if not linii_sel:
                        linii_sel = [r for _, r in df_lin_edit.iterrows()]

                    randuri_oferta = []
                    for idx_r, r in enumerate(linii_sel, start=1):
                        cant = float(pd.to_numeric(r.get("Cant."), errors="coerce") or 1.0)
                        pret_furn = float(pd.to_numeric(r.get("Preț Unitar"), errors="coerce") or 0.0)
                        pret_cu_adaos = round(pret_furn * (1.0 + adaos_client / 100.0), 2)
                        mon = str(r.get("Monedă") or "EUR").strip().upper()
                        if mon not in ("RON", "EUR"):
                            mon = "EUR"
                        den = str(r.get("Piesă") or "").strip()
                        cod = str(r.get("Cod Prod.") or "").strip()
                        desc_finala = f"{den} ({cod})" if cod and cod.lower() not in den.lower() else den
                        termen = str(r.get("Termen livrare") or "1").strip() or "1"

                        randuri_oferta.append({
                            "Ordine": idx_r,
                            "Descriere": desc_finala,
                            "UM": "buc",
                            "Cantitate": cant,
                            "Pret Unitar": pret_cu_adaos,
                            "Moneda": mon,
                            "Termen livrare": termen,
                        })

                    if randuri_oferta:
                        st.session_state["df_oferta_editor"] = pd.DataFrame(randuri_oferta)
                        st.session_state["editor_reset_counter"] = st.session_state.get("editor_reset_counter", 0) + 1

                    draft = st.session_state.get("oferta_draft")
                    if isinstance(draft, dict):
                        if firma_nume:
                            draft["sel_firma"] = firma_nume
                            draft["ultima_firma_pers"] = firma_nume
                        masina_nume = str(cer_activa.get("masina_nume") or "").strip()
                        if masina_nume:
                            draft["sel_masina"] = masina_nume
                            draft["ultima_masina_selectata"] = masina_nume
                            draft["utilaj"] = masina_nume
                        draft["cerere_furnizor_id"] = cid_activa
                        draft["cod_cerere_furnizor"] = cer_activa.get("cod_cerere")
                        st.session_state["ofs_cnt"] = st.session_state.get("ofs_cnt", 0) + 1

                    CereriOfertaRepository.update_status_cerere(cid_activa, "Ofertat la client")
                    _goleste_cache_de_facut()
                    st.success(f"✅ Liniile au fost pregătite în editorul de **Oferte** pentru **{firma_nume}**.")
                    st.rerun()


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

    render_privire_ansamblu_de_facut(piese_rows)

    st.markdown("---")
    render_notite_vizita_de_facut()
    render_notare_rapida_teren()
    render_tabel_piese_de_comandat(piese_rows)
    render_cereri_oferta_furnizori_de_facut()

    st.markdown("---")
    render_memento_intretinere_de_facut()