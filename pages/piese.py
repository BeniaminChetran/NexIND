# ------------------------------------------------
# --- pages/piese.py ----------------------------
# ------------------------------------------------

from datetime import date
import json
import pandas as pd
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.necesar_piese_repository import NecesarPieseRepository
from repositories.piese_repository import (
    OPTIUNI_STARE_COMANDA,
    PieseRepository,
    _normalizeaza_stare_comanda,
)
from repositories.reparatii_repository import ReparatiiRepository
from repositories.reparatii_electronice_repository import ReparatiiElectroniceRepository


def _are_acces_preturi_si_furnizori() -> bool:
    rol = str(st.session_state.get("user_role") or st.session_state.get("rol") or "").strip().lower()
    if rol in ("tehnician", "operator", "vizitator", "guest"):
        return False
    return True


def _curata_cache_piese():
    try:
        PieseRepository.get_all.clear()
    except Exception:
        pass
    try:
        NecesarPieseRepository.get_all.clear()
    except Exception:
        pass


def calculeaza_linie_bon_provizoriu(
    piesa_db: dict | None,
    cantitate: float,
    date_piesa_noua: dict | None = None,
) -> dict:
    cant = max(0.0, float(cantitate or 0.0))
    if piesa_db:
        pret = float(piesa_db.get("pret_achizitie") or 0.0)
        moneda = str(piesa_db.get("valuta_achizitie") or "RON").strip().upper() or "RON"
        return {
            "exista": True,
            "piesa_id": piesa_db.get("id"),
            "denumire": str(piesa_db.get("denumire") or "").strip(),
            "cod": str(piesa_db.get("cod_producator") or piesa_db.get("cod_comercial") or "").strip(),
            "proprietati": str(piesa_db.get("parametri") or "").strip(),
            "pret_unitar": round(pret, 2),
            "moneda": moneda,
            "cantitate": cant,
            "valoare_linie": round(pret * cant, 2),
        }

    info = date_piesa_noua or {}
    return {
        "exista": False,
        "piesa_id": None,
        "denumire": str(info.get("denumire") or "").strip(),
        "cod": str(info.get("cod") or "").strip(),
        "proprietati": str(info.get("proprietati") or "").strip(),
        "pret_unitar": 0.0,
        "moneda": "RON",
        "cantitate": cant,
        "valoare_linie": 0.0,
    }


def _sincronizeaza_din_rapoarte_electronice_si_teren() -> dict:
    """Comasează piesele din reparații electronice și necesar teren în catalogul `piese`."""
    piese_existente = PieseRepository.get_all() or []
    chei_existente = {
        (
            " ".join(str(p.get("denumire") or "").lower().split()),
            " ".join(str(p.get("cod_producator") or "").lower().split()),
        )
        for p in piese_existente
        if str(p.get("denumire") or "").strip()
    }

    adaugate_el = 0
    adaugate_teren = 0

    # 1. Din reparații electronice
    fise_el = ReparatiiElectroniceRepository.get_all() or []
    for f in fise_el:
        subansamblu_el = str(f.get("piesa_subansamblu") or "").strip()
        masina_el = str(f.get("masina_nume") or "General").strip() or "General"
        comp_raw = f.get("componente_json") or []
        if isinstance(comp_raw, str):
            try:
                comp_raw = json.loads(comp_raw)
            except Exception:
                comp_raw = []

        for comp in comp_raw:
            if not isinstance(comp, dict):
                continue
            den = str(
                comp.get("Componenta / Cod / Parametri")
                or comp.get("Componenta")
                or comp.get("denumire")
                or ""
            ).strip()
            if not den:
                continue
            cod = str(comp.get("Cod") or comp.get("cod_producator") or "").strip()
            prop = str(comp.get("Parametri") or comp.get("Proprietati") or comp.get("Observatii") or "").strip()
            stare = _normalizeaza_stare_comanda(comp.get("Stare") or comp.get("stare_comandata") or "De căutat")

            cheie = (" ".join(den.lower().split()), " ".join(cod.lower().split()))
            if cheie in chei_existente:
                continue

            PieseRepository.insert({
                "denumire": den,
                "cod_producator": cod,
                "cod_comercial": cod,
                "masina_montaj": masina_el,
                "subansamblu": subansamblu_el,
                "parametri": prop,
                "pret_achizitie": 0.0,
                "valuta_achizitie": "RON",
                "termen_livrare": "1",
                "stare_comandata": stare,
            })
            chei_existente.add(cheie)
            adaugate_el += 1

    # 2. Din necesar piese teren
    necesar_rows = NecesarPieseRepository.get_all() or []
    for nr in necesar_rows:
        den = str(nr.get("denumire_piesa") or "").strip()
        if not den:
            continue
        cod = str(nr.get("cod_producator") or "").strip()
        mas = str(nr.get("masina") or "General").strip() or "General"
        obs = str(nr.get("observatii") or "").strip()
        stare = _normalizeaza_stare_comanda(nr.get("status_comanda") or "De căutat")

        cheie = (" ".join(den.lower().split()), " ".join(cod.lower().split()))
        if cheie in chei_existente:
            continue

        PieseRepository.insert({
            "denumire": den,
            "cod_producator": cod,
            "cod_comercial": cod,
            "masina_montaj": mas,
            "subansamblu": "",
            "parametri": obs,
            "pret_achizitie": 0.0,
            "valuta_achizitie": "RON",
            "termen_livrare": "1",
            "stare_comandata": stare,
        })
        chei_existente.add(cheie)
        adaugate_teren += 1

    if adaugate_el or adaugate_teren:
        _curata_cache_piese()

    return {"electronica": adaugate_el, "teren": adaugate_teren}


@st.fragment
def render_bon_comanda_provizoriu(firme_nume: list[str], masini_all: list[dict], acces_permis: bool):
    st.subheader("📝 Bon de Comandă Provizoriu (Note Rapide Teren)")
    st.caption(
        "Data este completată automat. Piesele inexistente în baza de date se adaugă în `piese` "
        "cu preț `0.00` (și se calculează cu `0` în bon)."
    )

    if not firme_nume:
        st.warning("⚠️ Nu există firme înregistrate.")
        return

    firme_all = FirmeRepository.get_all() or []
    nume_to_id = {
        str(f.get("nume_firma") or "").strip(): int(f["id"])
        for f in firme_all
        if str(f.get("nume_firma") or "").strip() and f.get("id") is not None
    }

    c1, c2, c3 = st.columns([2.0, 2.0, 1.1], vertical_alignment="bottom")
    with c1:
        firma_bon = st.selectbox("Firmă *", options=firme_nume, key="bon_prov_firma")
    with c2:
        fid = nume_to_id.get(firma_bon)
        masini_firma = [
            str(m.get("denumire") or "").strip()
            for m in (masini_all or [])
            if str(m.get("denumire") or "").strip() and (fid is None or m.get("firma_id") == fid)
        ]
        opt_masini = ["-- Fără mașină (opțional) --"] + list(dict.fromkeys(masini_firma))
        masina_bon = st.selectbox("Mașină (opțional)", options=opt_masini, key="bon_prov_masina")
    with c3:
        st.text_input("Data (automat)", value=date.today().isoformat(), disabled=True, key="bon_prov_data_auto")

    piese_db = PieseRepository.get_all() or []
    mapa_piese: dict[str, dict] = {}
    for p in piese_db:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or "").strip()
        mas = str(p.get("masina_montaj") or "General").strip()
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + f" — {mas}"
        mapa_piese[eticheta] = p

    st.session_state.setdefault("bon_provizoriu_linii", [])
    st.session_state.setdefault("bon_prov_nou_den", "")

    # Același rând: Selectează piesa + Cantitate
    optiuni_select_piesa = [None] + list(mapa_piese.keys())
    col_sel_p, col_cant_p = st.columns([2.8, 1.0], vertical_alignment="bottom")
    with col_sel_p:
        piesa_aleasa = st.selectbox(
            "Selectează piesa",
            options=optiuni_select_piesa,
            index=0,
            format_func=lambda x: "-- Nicio piesă selectată --" if x is None else str(x),
            key="bon_prov_selecteaza_piesa",
        )
    with col_cant_p:
        cant_bon = st.number_input(
            "Cantitate *",
            min_value=0.01,
            value=1.0,
            step=1.0,
            format="%.2f",
            key="bon_prov_cant",
        )

    piesa_selectata: dict | None = (
        mapa_piese.get(piesa_aleasa)
        if isinstance(piesa_aleasa, str) and piesa_aleasa in mapa_piese
        else None
    )

    den_noua = ""
    cod_nou = ""
    prop_noua = ""
    mas_montaj_noua = "General"

    if piesa_selectata is None:
        # Câmpul "Denumire piesă nouă" este invizibil (nu este randat vizibil)
        den_noua = str(st.session_state.get("bon_prov_nou_den") or "").strip()

        n1, n2, n3 = st.columns([1.2, 1.8, 1.2])
        with n1:
            cod_nou = st.text_input("Cod piesă", key="bon_prov_nou_cod")
        with n2:
            prop_noua = st.text_input("Proprietăți / parametri", key="bon_prov_nou_prop")
        with n3:
            toate_masinile = sorted({
                "General",
                *([masina_bon] if masina_bon != "-- Fără mașină (opțional) --" else []),
                *[str(m.get("denumire") or "").strip() for m in (masini_all or []) if str(m.get("denumire") or "").strip()],
            })
            mas_montaj_noua = st.selectbox("Mașină montaj", options=toate_masinile, key="bon_prov_nou_masina")
    else:
        pret_afisat = float(piesa_selectata.get("pret_achizitie") or 0.0) if acces_permis else 0.0
        st.caption(
            f"Selectat: **{piesa_selectata.get('denumire')}** | "
            f"Cod: **{piesa_selectata.get('cod_producator') or '-'}** | "
            f"Preț unitar: **{pret_afisat:.2f} {piesa_selectata.get('valuta_achizitie') or 'RON'}**"
        )

    if st.button("➕ Adaugă reper în Bonul Provizoriu", type="primary", key="btn_bon_prov_add", use_container_width=True):
        if piesa_selectata is None:
            den_finala_noua = den_noua.strip()
            if not den_finala_noua:
                st.error("⚠️ Nu există nicio denumire setată pentru piesa nouă.")
                return

            potrivire_exacta = next(
                (p for p in piese_db if str(p.get("denumire") or "").strip().lower() == den_finala_noua.lower()),
                None,
            )
            if potrivire_exacta is not None:
                st.session_state["bon_prov_nou_den"] = ""
                linie = calculeaza_linie_bon_provizoriu(potrivire_exacta, cant_bon, None)
            else:
                date_noua = {
                    "denumire": den_finala_noua,
                    "cod": cod_nou,
                    "proprietati": prop_noua,
                    "masina_montaj": mas_montaj_noua,
                }
                new_id = PieseRepository.insert({
                    "denumire": den_finala_noua,
                    "cod_producator": cod_nou.strip(),
                    "cod_comercial": cod_nou.strip(),
                    "masina_montaj": mas_montaj_noua.strip() or "General",
                    "subansamblu": "",
                    "parametri": prop_noua.strip(),
                    "pret_achizitie": 0.0,
                    "valuta_achizitie": "RON",
                    "termen_livrare": "1",
                    "stare_comandata": "De căutat",
                })
                _curata_cache_piese()
                linie = calculeaza_linie_bon_provizoriu(None, cant_bon, date_noua)
                linie["piesa_id"] = new_id
        else:
            linie = calculeaza_linie_bon_provizoriu(piesa_selectata, cant_bon, None)

        linie["firma"] = firma_bon
        linie["masina"] = masina_bon if masina_bon != "-- Fără mașină (opțional) --" else "-"
        linie["data"] = date.today().isoformat()
        st.session_state["bon_provizoriu_linii"].append(linie)

        try:
            NecesarPieseRepository.noteaza_piesa_pe_teren(
                firma_client=firma_bon,
                firma_id=fid,
                denumire_piesa=linie["denumire"],
                cantitate=cant_bon,
                masina=linie["masina"],
                cod_producator=linie["cod"],
                prioritate_piesa="Urgentă",
                observatii=f"Bon provizoriu {linie['data']} | {linie['proprietati']}".strip(" |"),
            )
        except Exception:
            pass

    linii_bon = st.session_state.get("bon_provizoriu_linii") or []
    if linii_bon:
        df_bon = pd.DataFrame([
            {
                "Data": l["data"],
                "Firmă": l["firma"],
                "Mașină": l["masina"],
                "Denumire": l["denumire"],
                "Cod": l["cod"],
                "Proprietăți": l["proprietati"],
                "Cantitate": l["cantitate"],
                "Preț Reper": l["pret_unitar"] if acces_permis else 0.0,
                "Valoare Reper": l["valoare_linie"] if acces_permis else 0.0,
                "Monedă": l["moneda"],
                "Sursă DB": "Existentă" if l["exista"] else "Nouă (preț 0.00)",
            }
            for l in linii_bon
        ])
        st.dataframe(df_bon, hide_index=True, use_container_width=True)

        total_bon = round(sum(float(l.get("valoare_linie") or 0.0) for l in linii_bon), 2) if acces_permis else 0.0
        col_tot, col_del = st.columns([3.2, 1.0], vertical_alignment="center")
        with col_tot:
            st.markdown(f"### 💰 Total bon provizoriu: **{total_bon:.2f}**")
        with col_del:
            if st.button("🧹 Golește Bonul", key="btn_bon_prov_clear", use_container_width=True):
                st.session_state["bon_provizoriu_linii"] = []
                st.session_state["bon_prov_nou_den"] = ""


@st.fragment
def render_catalog_general_piese(masini_all: list[dict], acces_permis: bool):
    st.subheader("📦 Catalog General Piese (Editare Completă)")
    st.caption(
        "Toate piesele introduse (manual, din teren sau din reparații electronice) apar aici. "
        "Poți edita **orice celulă** direct în tabel și salva dintr-un singur click."
    )

    c_sync, c_info = st.columns([1.6, 3.4], vertical_alignment="center")
    with c_sync:
        if st.button("🔄 Importă Piese din Electronică & Teren", key="btn_sync_el_teren", use_container_width=True):
            rez = _sincronizeaza_din_rapoarte_electronice_si_teren()
            st.success(
                f"Sincronizat: **{rez['electronica']}** piese din reparații electronice, "
                f"**{rez['teren']}** piese din note teren."
            )

    piese_all = PieseRepository.get_all() or []
    if not piese_all:
        st.info("Nu există piese în catalog.")
        return

    df_raw = pd.DataFrame(piese_all)

    f1, f2, f3 = st.columns([2.2, 1.5, 1.5])
    with f1:
        q_cautare = st.text_input(
            "Caută piesă / cod / proprietăți / subansamblu",
            placeholder="ex: releu, 24V, encoder, placa...",
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
    if sel_mas != "Toate mașinile":
        df_f = df_f[df_f["masina_montaj"].fillna("General").astype(str).str.strip() == sel_mas]
    if sel_stare != "Toate stările":
        df_f = df_f[
            df_f["stare_comandata"].apply(_normalizeaza_stare_comanda) == sel_stare
        ]
    if q_cautare:
        mask = (
            df_f["denumire"].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
            | df_f["cod_producator"].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
            | df_f["cod_comercial"].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
            | df_f["parametri"].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
            | df_f["subansamblu"].fillna("").astype(str).str.lower().str.contains(q_cautare, na=False)
        )
        df_f = df_f[mask]

    if df_f.empty:
        st.info("Nicio piesă nu corespunde filtrelor.")
        return

    df_init = pd.DataFrame([
        {
            "id": int(r["id"]),
            "Denumire": str(r.get("denumire") or "").strip(),
            "Cod Producător": str(r.get("cod_producator") or "").strip(),
            "Cod Comercial": str(r.get("cod_comercial") or "").strip(),
            "Mașină Montaj": str(r.get("masina_montaj") or "General").strip(),
            "Subansamblu": str(r.get("subansamblu") or "").strip(),
            "Proprietăți": str(r.get("parametri") or "").strip(),
            "Preț Achiziție": float(r.get("pret_achizitie") or 0.0),
            "Valută": str(r.get("valuta_achizitie") or "RON").strip().upper() or "RON",
            "Termen Livrare (zile)": str(r.get("termen_livrare") or "1").strip(),
            "Stare Comandată": _normalizeaza_stare_comanda(r.get("stare_comandata")),
            "Furnizor": str(r.get("furnizor") or "").strip(),
            "Link Furnizor": str(r.get("link_furnizor") or "").strip(),
            "Șterge": False,
        }
        for _, r in df_f.iterrows()
    ])

    disabled_cols = ["id"]
    if not acces_permis:
        disabled_cols.extend(["Preț Achiziție", "Valută", "Furnizor", "Link Furnizor"])

    editor_key = f"editor_piese_general_{sel_mas}_{sel_stare}_{len(df_init)}"
    edited = st.data_editor(
        df_init,
        key=editor_key,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        disabled=disabled_cols,
        column_config={
            "id": None,
            "Denumire": st.column_config.TextColumn("Denumire *", width="large", required=True),
            "Cod Producător": st.column_config.TextColumn("Cod Producător", width="medium"),
            "Cod Comercial": st.column_config.TextColumn("Cod Comercial", width="medium"),
            "Mașină Montaj": st.column_config.TextColumn("Mașină Montaj", width="medium"),
            "Subansamblu": st.column_config.TextColumn("Subansamblu", width="medium"),
            "Proprietăți": st.column_config.TextColumn("Proprietăți / Parametri", width="large"),
            "Preț Achiziție": st.column_config.NumberColumn("Preț Achiziție", min_value=0.0, format="%.2f", width="small"),
            "Valută": st.column_config.SelectboxColumn("Valută", options=["RON", "EUR", "USD"], width="small"),
            "Termen Livrare (zile)": st.column_config.TextColumn("Termen (zile)", width="small"),
            "Stare Comandată": st.column_config.SelectboxColumn("Stare Comandată", options=OPTIUNI_STARE_COMANDA, width="medium"),
            "Furnizor": st.column_config.TextColumn("Furnizor", width="medium"),
            "Link Furnizor": st.column_config.TextColumn("Link Furnizor", width="medium"),
            "Șterge": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
        },
    )

    if st.button("💾 Salvează Modificările în Catalogul de Piese", type="primary", key="btn_save_piese_general"):
        df_final = edited.copy()
        state_ed = st.session_state.get(editor_key)
        if isinstance(state_ed, dict):
            for idx_str, changes in (state_ed.get("edited_rows") or {}).items():
                try:
                    idx = int(idx_str)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(df_final) and isinstance(changes, dict):
                    for col_name, new_val in changes.items():
                        if col_name in df_final.columns:
                            df_final.at[idx, col_name] = new_val

        orig_map = {int(r["id"]): r for _, r in df_init.iterrows()}
        nr_mod = 0
        nr_del = 0

        for _, row in df_final.iterrows():
            pid = int(row["id"])
            if bool(row.get("Șterge", False)):
                PieseRepository.delete(pid)
                nr_del += 1
                continue

            orig = orig_map.get(pid)
            if orig is None:
                continue

            payload = {
                "denumire": str(row.get("Denumire") or "").strip(),
                "cod_producator": str(row.get("Cod Producător") or "").strip(),
                "cod_comercial": str(row.get("Cod Comercial") or "").strip(),
                "masina_montaj": str(row.get("Mașină Montaj") or "General").strip() or "General",
                "subansamblu": str(row.get("Subansamblu") or "").strip(),
                "parametri": str(row.get("Proprietăți") or "").strip(),
                "pret_achizitie": float(row.get("Preț Achiziție") or 0.0),
                "valuta_achizitie": str(row.get("Valută") or "RON").strip().upper() or "RON",
                "termen_livrare": str(row.get("Termen Livrare (zile)") or "1").strip(),
                "stare_comandata": _normalizeaza_stare_comanda(row.get("Stare Comandată")),
                "furnizor": str(row.get("Furnizor") or "").strip(),
                "link_furnizor": str(row.get("Link Furnizor") or "").strip(),
            }

            if not payload["denumire"]:
                continue

            schimbat = (
                payload["denumire"] != orig["Denumire"]
                or payload["cod_producator"] != orig["Cod Producător"]
                or payload["cod_comercial"] != orig["Cod Comercial"]
                or payload["masina_montaj"] != orig["Mașină Montaj"]
                or payload["subansamblu"] != orig["Subansamblu"]
                or payload["parametri"] != orig["Proprietăți"]
                or abs(payload["pret_achizitie"] - float(orig["Preț Achiziție"])) > 1e-6
                or payload["valuta_achizitie"] != orig["Valută"]
                or payload["termen_livrare"] != orig["Termen Livrare (zile)"]
                or payload["stare_comandata"] != orig["Stare Comandată"]
                or payload["furnizor"] != orig["Furnizor"]
                or payload["link_furnizor"] != orig["Link Furnizor"]
            )

            if schimbat:
                PieseRepository.update(pid, payload)
                nr_mod += 1

        _curata_cache_piese()
        if editor_key in st.session_state:
            del st.session_state[editor_key]

        if nr_mod == 0 and nr_del == 0:
            st.info("ℹ️ Nu există modificări nesalvate.")
        else:
            st.success(f"✅ Salvat: **{nr_mod}** piese actualizate, **{nr_del}** șterse.")


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
        with c8:
            valuta = st.selectbox("Valută", options=["RON", "EUR", "USD"], disabled=not acces_permis)
        with c9:
            termen = st.text_input("Termen livrare (zile)", value="1")
        with c10:
            stare = st.selectbox("Stare comandată", options=OPTIUNI_STARE_COMANDA, index=0)

        c11, c12 = st.columns(2)
        with c11:
            furnizor = st.text_input("Furnizor", disabled=not acces_permis)
        with c12:
            link_f = st.text_input("Link furnizor", disabled=not acces_permis)

        submitted = st.form_submit_button("💾 Salvează Piesa", type="primary")

    if submitted:
        if not den.strip():
            st.error("⚠️ Denumirea piesei este obligatorie.")
            return
        PieseRepository.insert({
            "denumire": den.strip(),
            "cod_producator": cod_p.strip(),
            "cod_comercial": cod_c.strip(),
            "masina_montaj": mas.strip() or "General",
            "subansamblu": sub.strip(),
            "parametri": prop.strip(),
            "pret_achizitie": float(pret),
            "valuta_achizitie": valuta,
            "termen_livrare": termen.strip() or "1",
            "stare_comandata": stare,
            "furnizor": furnizor.strip(),
            "link_furnizor": link_f.strip(),
        })
        _curata_cache_piese()
        st.success(f"✅ Piesa **{den.strip()}** a fost adăugată în catalog.")


def render_piese():
    st.title("🔩 Gestiune Piese & Bonuri Provizorii")

    acces_permis = _are_acces_preturi_si_furnizori()
    firme_all = FirmeRepository.get_all() or []
    firme_nume = sorted({
        str(f.get("nume_firma") or "").strip()
        for f in firme_all
        if str(f.get("nume_firma") or "").strip()
    })
    masini_all = MasiniRepository.get_all() or []

    tab_bon, tab_catalog, tab_nou = st.tabs([
        "📝 Bon Comandă Provizoriu",
        "📦 Catalog General Piese (Editabil)",
        "➕ Adaugă Piesă Nouă",
    ])

    with tab_bon:
        render_bon_comanda_provizoriu(firme_nume, masini_all, acces_permis)

    with tab_catalog:
        render_catalog_general_piese(masini_all, acces_permis)

    with tab_nou:
        render_adaugare_piesa_noua(masini_all, acces_permis)