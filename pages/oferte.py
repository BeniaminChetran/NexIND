# ------------------------------------------------
# --- pages/oferte.py -------------------------
# ------------------------------------------------

from datetime import date
import pandas as pd
import streamlit as st

from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository


COLS_OFERTA = [
    "Ordine",
    "Descriere",
    "UM",
    "Cantitate",
    "Pret Unitar",
    "Moneda",
    "Termen livrare",
]


def valideaza_si_calculeaza_linie_oferta(
    piesa_catalog: dict,
    cantitate: float,
    adaos_comercial_pct: float,
) -> tuple[bool, str, dict | None]:
    """
    Validează piesa din catalog înainte de adăugarea în ofertă.
    Dacă lipsește denumirea sau prețul de intrare este <= 0, returnează exact 'pret inexistent'.
    """
    den_p = str(piesa_catalog.get("denumire") or "").strip()
    try:
        pret_achiz = float(piesa_catalog.get("pret_achizitie") or 0.0)
    except (TypeError, ValueError):
        pret_achiz = 0.0

    if not den_p or pret_achiz <= 0.0:
        return False, "pret inexistent", None

    cant = max(0.01, float(cantitate or 1.0))
    adaos = float(adaos_comercial_pct or 0.0)
    pret_vanzare = round(pret_achiz * (1.0 + adaos / 100.0), 2)

    moneda = str(piesa_catalog.get("valuta_achizitie") or "RON").strip().upper()
    if moneda not in ("RON", "EUR", "USD"):
        moneda = "RON"

    cod_p = str(
        piesa_catalog.get("cod_producator") or piesa_catalog.get("cod_comercial") or ""
    ).strip()
    desc_p = f"{den_p} ({cod_p})" if cod_p else den_p
    furnizor = str(
        piesa_catalog.get("furnizor") or piesa_catalog.get("nume_furnizor") or ""
    ).strip()

    return True, "", {
        "desc": desc_p,
        "denumire": den_p,
        "cod": cod_p,
        "cant": cant,
        "pret_achiz": round(pret_achiz, 2),
        "pret_vanzare": pret_vanzare,
        "valoare": round(pret_vanzare * cant, 2),
        "moneda": moneda,
        "furnizor": furnizor or "Furnizor nespecificat",
    }


def _asigura_mapare_furnizori_oferta() -> dict:
    st.session_state.setdefault("oferta_2_map_furnizori", {})
    return st.session_state["oferta_2_map_furnizori"]


def _sincronizeaza_editor_inainte_de_adaugare() -> pd.DataFrame:
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    df_base = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_base.columns:
            df_base[col] = None
    df_base = df_base[COLS_OFERTA]

    counter = st.session_state.get("oferta_2_editor_counter", 0)
    ed_key = f"oferta_2_data_editor_{counter}"
    state_ed = st.session_state.get(ed_key)
    if isinstance(state_ed, dict):
        for idx_str, changes in (state_ed.get("edited_rows") or {}).items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df_base) and isinstance(changes, dict):
                for col_name, new_val in changes.items():
                    if col_name in df_base.columns:
                        df_base.at[idx, col_name] = new_val
    return df_base


def _calculeaza_totaluri_oferta(
    df_linii: pd.DataFrame,
    discount_pct: float,
    discount_val: float,
    cota_tva_pct: float,
) -> dict:
    if df_linii is None or df_linii.empty:
        return {
            "subtotal": 0.0,
            "discount_procent_val": 0.0,
            "discount_valoric": 0.0,
            "baza_impozabila": 0.0,
            "tva_valoare": 0.0,
            "total_general": 0.0,
        }

    subtotal = 0.0
    for _, row in df_linii.iterrows():
        desc = str(row.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = float(row.get("Cantitate") or 0.0)
        except (TypeError, ValueError):
            cant = 0.0
        try:
            pret = float(row.get("Pret Unitar") or 0.0)
        except (TypeError, ValueError):
            pret = 0.0
        subtotal += max(0.0, cant) * max(0.0, pret)

    subtotal = round(subtotal, 2)
    disc_pct_val = round(subtotal * max(0.0, float(discount_pct or 0.0)) / 100.0, 2)
    disc_val_fix = max(0.0, round(float(discount_val or 0.0), 2))
    baza = max(0.0, round(subtotal - disc_pct_val - disc_val_fix, 2))
    tva = round(baza * max(0.0, float(cota_tva_pct or 0.0)) / 100.0, 2)
    total_gen = round(baza + tva, 2)

    return {
        "subtotal": subtotal,
        "discount_procent_val": disc_pct_val,
        "discount_valoric": disc_val_fix,
        "baza_impozabila": baza,
        "tva_valoare": tva,
        "total_general": total_gen,
    }


def _genereaza_note_comanda_furnizori(df_linii: pd.DataFrame) -> list[dict]:
    if df_linii is None or df_linii.empty:
        return []

    mp_furn = _asigura_mapare_furnizori_oferta()
    grupate: dict[str, list[dict]] = {}

    for _, row in df_linii.iterrows():
        desc = str(row.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = max(0.01, float(row.get("Cantitate") or 1.0))
        except (TypeError, ValueError):
            cant = 1.0

        meta = mp_furn.get(desc) or mp_furn.get(desc.lower()) or {}
        furnizor = str(meta.get("furnizor_nume") or "Furnizor nespecificat").strip() or "Furnizor nespecificat"
        pret_intrare = float(meta.get("pret_furnizor") or 0.0)
        moneda = str(meta.get("moneda_furnizor") or row.get("Moneda") or "RON").strip().upper() or "RON"
        cod = str(meta.get("cod_piesa") or "").strip()
        denumire = str(meta.get("piesa_denumire") or desc).strip()

        grupate.setdefault(furnizor, []).append({
            "Furnizor": furnizor,
            "Piesă": denumire,
            "Cod": cod,
            "Cantitate": cant,
            "Preț Intrare": round(pret_intrare, 2),
            "Valoare Intrare": round(pret_intrare * cant, 2),
            "Monedă": moneda,
            "Termen livrare": str(row.get("Termen livrare") or "1").strip(),
        })

    note = []
    for furn, repere in grupate.items():
        total_furn = round(sum(float(x.get("Valoare Intrare") or 0.0) for x in repere), 2)
        note.append({
            "furnizor": furn,
            "total_intrare": total_furn,
            "repere": repere,
        })
    return note


@st.fragment
def _fragment_deviz_oferta(firma_obj: dict, adaos_client: float):
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    st.session_state.setdefault("oferta_2_editor_counter", 0)
    st.session_state.setdefault("oferta_2_eroare_piesa", "")

    piese_all = PieseRepository.get_all() or []
    piese_dict: dict[str, dict] = {}
    for p in piese_all:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or p.get("cod_comercial") or "").strip()
        pret_ach = float(p.get("pret_achizitie") or 0.0)
        mon = str(p.get("valuta_achizitie") or "RON").strip().upper() or "RON"
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + f" — {pret_ach:.2f} {mon}"
        piese_dict[eticheta] = p

    st.markdown("#### ➕ Adaugă piesă din catalog în ofertă")
    c_sel, c_cant, c_term, c_btn = st.columns([3.0, 1.0, 1.2, 1.2], vertical_alignment="bottom")
    with c_sel:
        opt_piese = ["-- Alege piesa --"] + list(piese_dict.keys())
        sel_piesa_catalog = st.selectbox(
            "Piesă din baza de date",
            options=opt_piese,
            key="oferta_2_sel_piesa",
        )
    with c_cant:
        cant_piesa = st.number_input(
            "Cantitate",
            min_value=0.01,
            value=1.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_cant_piesa",
        )
    with c_term:
        termen_piesa = st.text_input(
            "Termen livrare",
            value="1",
            key="oferta_2_termen_piesa",
        )
    with c_btn:
        btn_add_piesa = st.button(
            "➕ Adaugă",
            type="primary",
            key="oferta_2_btn_add_piesa",
            use_container_width=True,
        )

    if btn_add_piesa:
        st.session_state["oferta_2_eroare_piesa"] = ""
        if sel_piesa_catalog == "-- Alege piesa --":
            st.session_state["oferta_2_eroare_piesa"] = "⚠️ Selectați mai întâi o piesă din catalog!"
        else:
            p_info = piese_dict[sel_piesa_catalog]
            ok_p, err_p, info_calc = valideaza_si_calculeaza_linie_oferta(
                piesa_catalog=p_info,
                cantitate=float(cant_piesa),
                adaos_comercial_pct=adaos_client,
            )
            if not ok_p or info_calc is None:
                st.session_state["oferta_2_eroare_piesa"] = err_p  # exact: "pret inexistent"
            else:
                df_baza_p = _sincronizeaza_editor_inainte_de_adaugare()
                next_ord = len(df_baza_p) + 1

                linie_piesa = pd.DataFrame([{
                    "Ordine": next_ord,
                    "Descriere": info_calc["desc"],
                    "UM": "buc",
                    "Cantitate": info_calc["cant"],
                    "Pret Unitar": info_calc["pret_vanzare"],
                    "Moneda": info_calc["moneda"],
                    "Termen livrare": str(termen_piesa or p_info.get("termen_livrare") or "1").strip(),
                }])
                st.session_state["df_oferta_editor"] = pd.concat(
                    [df_baza_p, linie_piesa],
                    ignore_index=True,
                )

                mp_furn = _asigura_mapare_furnizori_oferta()
                meta_p = {
                    "furnizor_nume": info_calc["furnizor"],
                    "piesa_denumire": info_calc["denumire"],
                    "cod_piesa": info_calc["cod"],
                    "pret_furnizor": info_calc["pret_achiz"],
                    "moneda_furnizor": info_calc["moneda"],
                }
                mp_furn[info_calc["desc"]] = meta_p
                mp_furn[info_calc["desc"].lower()] = meta_p

                st.session_state["oferta_2_editor_counter"] = (
                    st.session_state.get("oferta_2_editor_counter", 0) + 1
                )

    if st.session_state.get("oferta_2_eroare_piesa"):
        st.error(st.session_state["oferta_2_eroare_piesa"])

    st.markdown("#### 📋 Linii ofertă")
    df_init = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_init.columns:
            df_init[col] = None
    df_init = df_init[COLS_OFERTA]

    ed_key = f"oferta_2_data_editor_{st.session_state.get('oferta_2_editor_counter', 0)}"
    edited_df = st.data_editor(
        df_init,
        key=ed_key,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ordine": st.column_config.NumberColumn("Nr.", min_value=1, step=1, format="%d", width="small"),
            "Descriere": st.column_config.TextColumn("Descriere / Piesă / Serviciu", width="large", required=True),
            "UM": st.column_config.TextColumn("UM", width="small"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Pret Unitar": st.column_config.NumberColumn("Preț Vânzare", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Moneda": st.column_config.SelectboxColumn("Monedă", options=["RON", "EUR", "USD"], width="small"),
            "Termen livrare": st.column_config.TextColumn("Termen livrare", width="medium"),
        },
    )
    st.session_state["df_oferta_editor"] = edited_df

    # Tabel calculat cu Valoare = Cantitate * Pret Unitar
    randuri_calc = []
    for idx, r in edited_df.iterrows():
        desc = str(r.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = max(0.0, float(r.get("Cantitate") or 0.0))
        except (TypeError, ValueError):
            cant = 0.0
        try:
            pret_u = max(0.0, float(r.get("Pret Unitar") or 0.0))
        except (TypeError, ValueError):
            pret_u = 0.0
        val_lin = round(cant * pret_u, 2)
        randuri_calc.append({
            "Nr.": int(r.get("Ordine") or (idx + 1)),
            "Descriere": desc,
            "UM": str(r.get("UM") or "buc").strip() or "buc",
            "Cantitate": cant,
            "Preț Unitar": round(pret_u, 2),
            "Valoare": val_lin,
            "Monedă": str(r.get("Moneda") or "RON").strip().upper() or "RON",
            "Termen livrare": str(r.get("Termen livrare") or "").strip(),
        })

    if randuri_calc:
        st.markdown("#### 🧮 Valori calculate pe linie")
        st.dataframe(pd.DataFrame(randuri_calc), hide_index=True, use_container_width=True)

    st.markdown("#### 💶 Discounturi & TVA")
    d1, d2, d3 = st.columns(3)
    with d1:
        disc_pct = st.number_input(
            "Discount procentual (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_disc_pct",
        )
    with d2:
        disc_val = st.number_input(
            "Discount valoric",
            min_value=0.0,
            value=0.0,
            step=10.0,
            format="%.2f",
            key="oferta_2_disc_val",
        )
    with d3:
        cota_tva = st.number_input(
            "Cotă TVA (%)",
            min_value=0.0,
            max_value=100.0,
            value=19.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_tva_pct",
        )

    tot = _calculeaza_totaluri_oferta(edited_df, disc_pct, disc_val, cota_tva)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Subtotal (fără TVA)", f"{tot['subtotal']:.2f}")
    m2.metric("Total discounturi", f"{round(tot['discount_procent_val'] + tot['discount_valoric'], 2):.2f}")
    m3.metric(f"TVA ({cota_tva:g}%)", f"{tot['tva_valoare']:.2f}")
    m4.metric("Total General", f"{tot['total_general']:.2f}")


@st.fragment
def _fragment_note_comanda_furnizori():
    st.subheader("📦 Note de Comandă către Furnizori")
    st.caption("Se generează automat pe baza pieselor din ofertă și a furnizorilor asociați în catalogul `piese`.")

    df_linii = st.session_state.get("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    note = _genereaza_note_comanda_furnizori(df_linii)

    if not note:
        st.info("Nu există încă piese adăugate în ofertă pentru a genera note de comandă către furnizori.")
        return

    for nota in note:
        with st.expander(
            f"🏭 Furnizor: **{nota['furnizor']}** — Total achiziție: **{nota['total_intrare']:.2f}**",
            expanded=True,
        ):
            st.dataframe(pd.DataFrame(nota["repere"]), hide_index=True, use_container_width=True)


def render_oferte_2():
    st.title("💼 Oferte de Preț & Note de Comandă Furnizori")

    firme_db = FirmeRepository.get_all() or []
    firme_dict = {
        str(f.get("nume_firma") or "").strip(): f
        for f in firme_db
        if str(f.get("nume_firma") or "").strip()
    }
    if not firme_dict:
        st.warning("⚠️ Nu există firme înregistrate.")
        return

    masini_db = MasiniRepository.get_all() or []

    tab_oferta, tab_note_furn = st.tabs([
        "📄 Ofertă Client",
        "📦 Note de Comandă Furnizori",
    ])

    with tab_oferta:
        c1, c2, c3, c4 = st.columns([2.0, 2.0, 1.1, 1.1], vertical_alignment="bottom")
        with c1:
            sel_firma = st.selectbox("Firmă client *", options=list(firme_dict.keys()), key="oferta_2_firma")
        firma_obj = firme_dict[sel_firma]
        fid = firma_obj.get("id")

        with c2:
            masini_firma = [
                str(m.get("denumire") or "").strip()
                for m in masini_db
                if str(m.get("denumire") or "").strip() and (fid is None or m.get("firma_id") == fid)
            ]
            opt_mas = ["-- Fără mașină --"] + sorted(set(masini_firma))
            st.selectbox("Mașină / Utilaj", options=opt_mas, key="oferta_2_masina")
        with c3:
            adaos_client = float(firma_obj.get("adaos_comercial") or 20.0)
            st.number_input(
                "Adaos firmă (%)",
                value=adaos_client,
                disabled=True,
                format="%.2f",
                key="oferta_2_adaos_display",
            )
        with c4:
            st.text_input("Data ofertă", value=date.today().isoformat(), disabled=True, key="oferta_2_data")

        _fragment_deviz_oferta(firma_obj=firma_obj, adaos_client=adaos_client)

    with tab_note_furn:
        _fragment_note_comanda_furnizori()# ------------------------------------------------
# --- pages/oferte_2.py -------------------------
# ------------------------------------------------

from datetime import date
import pandas as pd
import streamlit as st

from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository


COLS_OFERTA = [
    "Ordine",
    "Descriere",
    "UM",
    "Cantitate",
    "Pret Unitar",
    "Moneda",
    "Termen livrare",
]


@st.cache_data(ttl=3600)
def obtine_curs_bnr():
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/xml,text/xml,text/html,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    }
    ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request("https://www.bnr.ro/nbrfxrates.xml", headers=headers_browser)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            for cube in root.iter("{http://www.bnr.ro/xsd}Cube"):
                if cube.get("date"):
                    for rate in cube.findall("{http://www.bnr.ro/xsd}Rate"):
                        if rate.get("currency") == "EUR":
                            return float(rate.text)
    except Exception:
        pass

    try:
        req_cb = urllib.request.Request("https://www.cursbnr.ro/", headers=headers_browser)
        with urllib.request.urlopen(req_cb, timeout=5, context=ctx) as response:
            html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r"1\s*EURO\s*=\s*([0-9]+\.[0-9]{4})\s*Lei", html, re.IGNORECASE)
            if match:
                return float(match.group(1))
    except Exception:
        pass

    try:
        url_ecb = "https://api.frankfurter.app/latest?from=EUR&to=RON"
        req_ecb = urllib.request.Request(url_ecb, headers=headers_browser)
        with urllib.request.urlopen(req_ecb, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "rates" in data and "RON" in data["rates"]:
                return float(data["rates"]["RON"])
    except Exception:
        pass

    return 5.35



def valideaza_si_calculeaza_linie_oferta(
    piesa_catalog: dict,
    cantitate: float,
    adaos_comercial_pct: float,
) -> tuple[bool, str, dict | None]:
    """
    Validează piesa din catalog înainte de adăugarea în ofertă.
    Dacă lipsește denumirea sau prețul de intrare este <= 0, returnează exact 'pret inexistent'.
    """
    den_p = str(piesa_catalog.get("denumire") or "").strip()
    try:
        pret_achiz = float(piesa_catalog.get("pret_achizitie") or 0.0)
    except (TypeError, ValueError):
        pret_achiz = 0.0

    if not den_p or pret_achiz <= 0.0:
        return False, "pret inexistent", None

    cant = max(0.01, float(cantitate or 1.0))
    adaos = float(adaos_comercial_pct or 0.0)
    pret_vanzare = round(pret_achiz * (1.0 + adaos / 100.0), 2)

    moneda = str(piesa_catalog.get("valuta_achizitie") or "RON").strip().upper()
    if moneda not in ("RON", "EUR", "USD"):
        moneda = "RON"

    cod_p = str(
        piesa_catalog.get("cod_producator") or piesa_catalog.get("cod_comercial") or ""
    ).strip()
    desc_p = f"{den_p} ({cod_p})" if cod_p else den_p
    furnizor = str(
        piesa_catalog.get("furnizor") or piesa_catalog.get("nume_furnizor") or ""
    ).strip()

    return True, "", {
        "desc": desc_p,
        "denumire": den_p,
        "cod": cod_p,
        "cant": cant,
        "pret_achiz": round(pret_achiz, 2),
        "pret_vanzare": pret_vanzare,
        "valoare": round(pret_vanzare * cant, 2),
        "moneda": moneda,
        "furnizor": furnizor or "Furnizor nespecificat",
    }


def _asigura_mapare_furnizori_oferta() -> dict:
    st.session_state.setdefault("oferta_2_map_furnizori", {})
    return st.session_state["oferta_2_map_furnizori"]


def _sincronizeaza_editor_inainte_de_adaugare() -> pd.DataFrame:
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    df_base = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_base.columns:
            df_base[col] = None
    df_base = df_base[COLS_OFERTA]

    counter = st.session_state.get("oferta_2_editor_counter", 0)
    ed_key = f"oferta_2_data_editor_{counter}"
    state_ed = st.session_state.get(ed_key)
    if isinstance(state_ed, dict):
        for idx_str, changes in (state_ed.get("edited_rows") or {}).items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df_base) and isinstance(changes, dict):
                for col_name, new_val in changes.items():
                    if col_name in df_base.columns:
                        df_base.at[idx, col_name] = new_val
    return df_base


def _calculeaza_totaluri_oferta(
    df_linii: pd.DataFrame,
    discount_pct: float,
    discount_val: float,
    cota_tva_pct: float,
) -> dict:
    if df_linii is None or df_linii.empty:
        return {
            "subtotal": 0.0,
            "discount_procent_val": 0.0,
            "discount_valoric": 0.0,
            "baza_impozabila": 0.0,
            "tva_valoare": 0.0,
            "total_general": 0.0,
        }

    subtotal = 0.0
    for _, row in df_linii.iterrows():
        desc = str(row.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = float(row.get("Cantitate") or 0.0)
        except (TypeError, ValueError):
            cant = 0.0
        try:
            pret = float(row.get("Pret Unitar") or 0.0)
        except (TypeError, ValueError):
            pret = 0.0
        subtotal += max(0.0, cant) * max(0.0, pret)

    subtotal = round(subtotal, 2)
    disc_pct_val = round(subtotal * max(0.0, float(discount_pct or 0.0)) / 100.0, 2)
    disc_val_fix = max(0.0, round(float(discount_val or 0.0), 2))
    baza = max(0.0, round(subtotal - disc_pct_val - disc_val_fix, 2))
    tva = round(baza * max(0.0, float(cota_tva_pct or 0.0)) / 100.0, 2)
    total_gen = round(baza + tva, 2)

    return {
        "subtotal": subtotal,
        "discount_procent_val": disc_pct_val,
        "discount_valoric": disc_val_fix,
        "baza_impozabila": baza,
        "tva_valoare": tva,
        "total_general": total_gen,
    }


def _genereaza_note_comanda_furnizori(df_linii: pd.DataFrame) -> list[dict]:
    if df_linii is None or df_linii.empty:
        return []

    mp_furn = _asigura_mapare_furnizori_oferta()
    grupate: dict[str, list[dict]] = {}

    for _, row in df_linii.iterrows():
        desc = str(row.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = max(0.01, float(row.get("Cantitate") or 1.0))
        except (TypeError, ValueError):
            cant = 1.0

        meta = mp_furn.get(desc) or mp_furn.get(desc.lower()) or {}
        furnizor = str(meta.get("furnizor_nume") or "Furnizor nespecificat").strip() or "Furnizor nespecificat"
        pret_intrare = float(meta.get("pret_furnizor") or 0.0)
        moneda = str(meta.get("moneda_furnizor") or row.get("Moneda") or "RON").strip().upper() or "RON"
        cod = str(meta.get("cod_piesa") or "").strip()
        denumire = str(meta.get("piesa_denumire") or desc).strip()

        grupate.setdefault(furnizor, []).append({
            "Furnizor": furnizor,
            "Piesă": denumire,
            "Cod": cod,
            "Cantitate": cant,
            "Preț Intrare": round(pret_intrare, 2),
            "Valoare Intrare": round(pret_intrare * cant, 2),
            "Monedă": moneda,
            "Termen livrare": str(row.get("Termen livrare") or "1").strip(),
        })

    note = []
    for furn, repere in grupate.items():
        total_furn = round(sum(float(x.get("Valoare Intrare") or 0.0) for x in repere), 2)
        note.append({
            "furnizor": furn,
            "total_intrare": total_furn,
            "repere": repere,
        })
    return note


@st.fragment
def _fragment_deviz_oferta(firma_obj: dict, adaos_client: float):
    st.session_state.setdefault("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    st.session_state.setdefault("oferta_2_editor_counter", 0)
    st.session_state.setdefault("oferta_2_eroare_piesa", "")

    piese_all = PieseRepository.get_all() or []
    piese_dict: dict[str, dict] = {}
    for p in piese_all:
        den = str(p.get("denumire") or "").strip()
        if not den:
            continue
        cod = str(p.get("cod_producator") or p.get("cod_comercial") or "").strip()
        pret_ach = float(p.get("pret_achizitie") or 0.0)
        mon = str(p.get("valuta_achizitie") or "RON").strip().upper() or "RON"
        eticheta = f"{den}" + (f" [{cod}]" if cod else "") + f" — {pret_ach:.2f} {mon}"
        piese_dict[eticheta] = p

    st.markdown("#### ➕ Adaugă piesă din catalog în ofertă")
    c_sel, c_cant, c_term, c_btn = st.columns([3.0, 1.0, 1.2, 1.2], vertical_alignment="bottom")
    with c_sel:
        opt_piese = ["-- Alege piesa --"] + list(piese_dict.keys())
        sel_piesa_catalog = st.selectbox(
            "Piesă din baza de date",
            options=opt_piese,
            key="oferta_2_sel_piesa",
        )
    with c_cant:
        cant_piesa = st.number_input(
            "Cantitate",
            min_value=0.01,
            value=1.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_cant_piesa",
        )
    with c_term:
        termen_piesa = st.text_input(
            "Termen livrare",
            value="1",
            key="oferta_2_termen_piesa",
        )
    with c_btn:
        btn_add_piesa = st.button(
            "➕ Adaugă",
            type="primary",
            key="oferta_2_btn_add_piesa",
            use_container_width=True,
        )

    if btn_add_piesa:
        st.session_state["oferta_2_eroare_piesa"] = ""
        if sel_piesa_catalog == "-- Alege piesa --":
            st.session_state["oferta_2_eroare_piesa"] = "⚠️ Selectați mai întâi o piesă din catalog!"
        else:
            p_info = piese_dict[sel_piesa_catalog]
            ok_p, err_p, info_calc = valideaza_si_calculeaza_linie_oferta(
                piesa_catalog=p_info,
                cantitate=float(cant_piesa),
                adaos_comercial_pct=adaos_client,
            )
            if not ok_p or info_calc is None:
                st.session_state["oferta_2_eroare_piesa"] = err_p  # exact: "pret inexistent"
            else:
                df_baza_p = _sincronizeaza_editor_inainte_de_adaugare()
                next_ord = len(df_baza_p) + 1

                linie_piesa = pd.DataFrame([{
                    "Ordine": next_ord,
                    "Descriere": info_calc["desc"],
                    "UM": "buc",
                    "Cantitate": info_calc["cant"],
                    "Pret Unitar": info_calc["pret_vanzare"],
                    "Moneda": info_calc["moneda"],
                    "Termen livrare": str(termen_piesa or p_info.get("termen_livrare") or "1").strip(),
                }])
                st.session_state["df_oferta_editor"] = pd.concat(
                    [df_baza_p, linie_piesa],
                    ignore_index=True,
                )

                mp_furn = _asigura_mapare_furnizori_oferta()
                meta_p = {
                    "furnizor_nume": info_calc["furnizor"],
                    "piesa_denumire": info_calc["denumire"],
                    "cod_piesa": info_calc["cod"],
                    "pret_furnizor": info_calc["pret_achiz"],
                    "moneda_furnizor": info_calc["moneda"],
                }
                mp_furn[info_calc["desc"]] = meta_p
                mp_furn[info_calc["desc"].lower()] = meta_p

                st.session_state["oferta_2_editor_counter"] = (
                    st.session_state.get("oferta_2_editor_counter", 0) + 1
                )

    if st.session_state.get("oferta_2_eroare_piesa"):
        st.error(st.session_state["oferta_2_eroare_piesa"])

    st.markdown("#### 📋 Linii ofertă")
    df_init = st.session_state["df_oferta_editor"].copy()
    for col in COLS_OFERTA:
        if col not in df_init.columns:
            df_init[col] = None
    df_init = df_init[COLS_OFERTA]

    ed_key = f"oferta_2_data_editor_{st.session_state.get('oferta_2_editor_counter', 0)}"
    edited_df = st.data_editor(
        df_init,
        key=ed_key,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ordine": st.column_config.NumberColumn("Nr.", min_value=1, step=1, format="%d", width="small"),
            "Descriere": st.column_config.TextColumn("Descriere / Piesă / Serviciu", width="large", required=True),
            "UM": st.column_config.TextColumn("UM", width="small"),
            "Cantitate": st.column_config.NumberColumn("Cantitate", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Pret Unitar": st.column_config.NumberColumn("Preț Vânzare", min_value=0.0, step=1.0, format="%.2f", width="small"),
            "Moneda": st.column_config.SelectboxColumn("Monedă", options=["RON", "EUR", "USD"], width="small"),
            "Termen livrare": st.column_config.TextColumn("Termen livrare", width="medium"),
        },
    )
    st.session_state["df_oferta_editor"] = edited_df

    # Tabel calculat cu Valoare = Cantitate * Pret Unitar
    randuri_calc = []
    for idx, r in edited_df.iterrows():
        desc = str(r.get("Descriere") or "").strip()
        if not desc:
            continue
        try:
            cant = max(0.0, float(r.get("Cantitate") or 0.0))
        except (TypeError, ValueError):
            cant = 0.0
        try:
            pret_u = max(0.0, float(r.get("Pret Unitar") or 0.0))
        except (TypeError, ValueError):
            pret_u = 0.0
        val_lin = round(cant * pret_u, 2)
        randuri_calc.append({
            "Nr.": int(r.get("Ordine") or (idx + 1)),
            "Descriere": desc,
            "UM": str(r.get("UM") or "buc").strip() or "buc",
            "Cantitate": cant,
            "Preț Unitar": round(pret_u, 2),
            "Valoare": val_lin,
            "Monedă": str(r.get("Moneda") or "RON").strip().upper() or "RON",
            "Termen livrare": str(r.get("Termen livrare") or "").strip(),
        })

    if randuri_calc:
        st.markdown("#### 🧮 Valori calculate pe linie")
        st.dataframe(pd.DataFrame(randuri_calc), hide_index=True, use_container_width=True)

    st.markdown("#### 💶 Discounturi & TVA")
    d1, d2, d3 = st.columns(3)
    with d1:
        disc_pct = st.number_input(
            "Discount procentual (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_disc_pct",
        )
    with d2:
        disc_val = st.number_input(
            "Discount valoric",
            min_value=0.0,
            value=0.0,
            step=10.0,
            format="%.2f",
            key="oferta_2_disc_val",
        )
    with d3:
        cota_tva = st.number_input(
            "Cotă TVA (%)",
            min_value=0.0,
            max_value=100.0,
            value=19.0,
            step=1.0,
            format="%.2f",
            key="oferta_2_tva_pct",
        )

    tot = _calculeaza_totaluri_oferta(edited_df, disc_pct, disc_val, cota_tva)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Subtotal (fără TVA)", f"{tot['subtotal']:.2f}")
    m2.metric("Total discounturi", f"{round(tot['discount_procent_val'] + tot['discount_valoric'], 2):.2f}")
    m3.metric(f"TVA ({cota_tva:g}%)", f"{tot['tva_valoare']:.2f}")
    m4.metric("Total General", f"{tot['total_general']:.2f}")


@st.fragment
def _fragment_note_comanda_furnizori():
    st.subheader("📦 Note de Comandă către Furnizori")
    st.caption("Se generează automat pe baza pieselor din ofertă și a furnizorilor asociați în catalogul `piese`.")

    df_linii = st.session_state.get("df_oferta_editor", pd.DataFrame(columns=COLS_OFERTA))
    note = _genereaza_note_comanda_furnizori(df_linii)

    if not note:
        st.info("Nu există încă piese adăugate în ofertă pentru a genera note de comandă către furnizori.")
        return

    for nota in note:
        with st.expander(
            f"🏭 Furnizor: **{nota['furnizor']}** — Total achiziție: **{nota['total_intrare']:.2f}**",
            expanded=True,
        ):
            st.dataframe(pd.DataFrame(nota["repere"]), hide_index=True, use_container_width=True)


def render_oferte():
    st.title("💼 Oferte de Preț & Note de Comandă Furnizori")

    firme_db = FirmeRepository.get_all() or []
    firme_dict = {
        str(f.get("nume_firma") or "").strip(): f
        for f in firme_db
        if str(f.get("nume_firma") or "").strip()
    }
    if not firme_dict:
        st.warning("⚠️ Nu există firme înregistrate.")
        return

    masini_db = MasiniRepository.get_all() or []

    tab_oferta, tab_note_furn = st.tabs([
        "📄 Ofertă Client",
        "📦 Note de Comandă Furnizori",
    ])

    with tab_oferta:
        c1, c2, c3, c4 = st.columns([2.0, 2.0, 1.1, 1.1], vertical_alignment="bottom")
        with c1:
            sel_firma = st.selectbox("Firmă client *", options=list(firme_dict.keys()), key="oferta_2_firma")
        firma_obj = firme_dict[sel_firma]
        fid = firma_obj.get("id")

        with c2:
            masini_firma = [
                str(m.get("denumire") or "").strip()
                for m in masini_db
                if str(m.get("denumire") or "").strip() and (fid is None or m.get("firma_id") == fid)
            ]
            opt_mas = ["-- Fără mașină --"] + sorted(set(masini_firma))
            st.selectbox("Mașină / Utilaj", options=opt_mas, key="oferta_2_masina")
        with c3:
            adaos_client = float(firma_obj.get("adaos_comercial") or 20.0)
            st.number_input(
                "Adaos firmă (%)",
                value=adaos_client,
                disabled=True,
                format="%.2f",
                key="oferta_2_adaos_display",
            )
        with c4:
            st.text_input("Data ofertă", value=date.today().isoformat(), disabled=True, key="oferta_2_data")

        _fragment_deviz_oferta(firma_obj=firma_obj, adaos_client=adaos_client)

    with tab_note_furn:
        _fragment_note_comanda_furnizori()