#----------------------------------
#-------pages/piese.py-------------
#----------------------------------

import ast
import json
import operator
import streamlit as st
import streamlit.components.v1 as components
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.setari_repository import SetariRepository
from repositories.tarife_repository import TarifeRepository
from config import db_cursor

# Evaluator matematic sigur pentru +, -, *, /, paranteze (acceptă și virgulă ca separator zecimal)
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

OPT_MONEDA_UM_TARIFE = [
    "EUR/ora", "EUR/km", "EUR/buc", "EUR/set", "EUR/intervenție", "EUR/proiect",
    "RON/ora", "RON/km", "RON/buc", "RON/set", "RON/intervenție", "RON/proiect"
]
OPT_NIVELE_GRILA = ["Nivel A", "Nivel B"]


def _eval_ast_node(node):
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Împărțirea la 0 nu este permisă.")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_ast_node(node.operand))
    raise ValueError("Expresie matematică invalidă.")


def calculeaza_pret_din_expresie(text_pret: str, valoare_implicita: float = 0.0) -> tuple[float, str | None]:
    """
    Evaluează un număr sau o expresie matematică simplă (+, -, *, /).
    Returnează (rezultat_rotunjit, mesaj_eroare_sau_None).
    """
    brut = str(text_pret or "").strip()
    if not brut:
        return round(float(valoare_implicita), 2), None

    expresie = (
        brut.lower()
        .replace("ron", "")
        .replace("lei", "")
        .replace("euro", "")
        .replace("eur", "")
        .replace(",", ".")
        .strip()
    )
    try:
        arbore = ast.parse(expresie, mode="eval")
        rezultat = float(_eval_ast_node(arbore))
        if rezultat < 0:
            return 0.0, "Prețul calculat nu poate fi negativ."
        return round(rezultat, 2), None
    except ValueError as ve:
        return 0.0, str(ve)
    except Exception:
        return 0.0, f"Expresie invalidă: '{brut}'. Folosiți doar cifre și +, -, *, /."


def _activeaza_stergere_pret_la_focus():
    """La focus (on activate) pe câmpurile de Preț Achiziție, golește valoarea existentă pentru tastare rapidă."""
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            function attachFocusClear() {
                const inputs = doc.querySelectorAll('input[aria-label*="Preț Achiziție"]');
                inputs.forEach(inp => {
                    if (!inp.dataset.focusClearBound) {
                        inp.dataset.focusClearBound = "true";
                        inp.addEventListener('focus', function() {
                            if (this.value && this.value.trim() !== "") {
                                this.dataset.prevVal = this.value;
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                nativeSetter.call(this, "");
                                this.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        });
                    }
                });
            }
            attachFocusClear();
            const observer = new MutationObserver(attachFocusClear);
            observer.observe(doc.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        height=0,
        width=0,
    )


# ------------------------------------------------------------------
# HELPERS TARIFE STANDARD (NIVEL A & NIVEL B) CU EDITARE UM
# ------------------------------------------------------------------
def _ensure_tarife_cols():
    try:
        with db_cursor() as c:
            c.execute("""
                ALTER TABLE tarife_implicite
                ADD COLUMN IF NOT EXISTS nivel_grila VARCHAR(30) DEFAULT 'Nivel A'
            """)
    except Exception:
        pass


def _get_tarife_all_safe():
    _ensure_tarife_cols()
    if hasattr(TarifeRepository, "get_all"):
        try:
            return TarifeRepository.get_all() or []
        except Exception:
            pass
    with db_cursor() as c:
        c.execute("SELECT * FROM tarife_implicite ORDER BY nivel_grila ASC, id ASC")
        return c.fetchall() or []


def _insert_tarif_safe(descriere: str, pret: float, moneda_um: str, nivel_grila: str):
    _ensure_tarife_cols()
    if hasattr(TarifeRepository, "insert"):
        try:
            return TarifeRepository.insert({
                "descriere": descriere,
                "pret": float(pret),
                "moneda_um": moneda_um,
                "nivel_grila": nivel_grila
            })
        except Exception:
            pass
    with db_cursor() as c:
        c.execute(
            "INSERT INTO tarife_implicite (descriere, pret, moneda_um, nivel_grila) VALUES (%s, %s, %s, %s)",
            (descriere, float(pret), moneda_um, nivel_grila)
        )


def _update_tarif_complet_safe(tarif_id: int, descriere: str, pret: float, moneda_um: str, nivel_grila: str):
    _ensure_tarife_cols()
    with db_cursor() as c:
        c.execute("""
            UPDATE tarife_implicite
            SET descriere = %s, pret = %s, moneda_um = %s, nivel_grila = %s
            WHERE id = %s
        """, (descriere, float(pret), moneda_um, nivel_grila, tarif_id))


def _delete_tarif_safe(tarif_id: int):
    if hasattr(TarifeRepository, "delete"):
        try:
            return TarifeRepository.delete(tarif_id)
        except Exception:
            pass
    with db_cursor() as c:
        c.execute("DELETE FROM tarife_implicite WHERE id = %s", (tarif_id,))


# ------------------------------------------------------------------
# HELPER AUDIT UTILIZARE PIESE ÎN ISTORIC (OFERTE, INTERVENȚII, UTILAJE)
# ------------------------------------------------------------------
@st.cache_data(ttl=120)
def _obtine_corpus_utilizare_istoric() -> str:
    """Colectează toate textele din oferte, intervenții, reparații electronice și componența utilajelor."""
    fragmente = []

    try:
        with db_cursor() as c:
            c.execute("SELECT articole_json, titlu FROM oferte")
            for row in c.fetchall() or []:
                fragmente.append(str(row.get("titlu") or ""))
                art = row.get("articole_json")
                if isinstance(art, str):
                    fragmente.append(art)
                elif isinstance(art, list):
                    fragmente.append(json.dumps(art, ensure_ascii=False))
    except Exception:
        pass

    try:
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii LIMIT 2000")
            for row in c.fetchall() or []:
                fragmente.append(" ".join(str(v) for v in row.values() if v is not None))
    except Exception:
        pass

    try:
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii_electronice LIMIT 2000")
            for row in c.fetchall() or []:
                fragmente.append(" ".join(str(v) for v in row.values() if v is not None))
    except Exception:
        pass

    try:
        with db_cursor() as c:
            c.execute("SELECT piese_necesare, piese_inlocuite, componenta_sisteme_json FROM masini")
            for row in c.fetchall() or []:
                fragmente.append(str(row.get("piese_necesare") or ""))
                fragmente.append(str(row.get("piese_inlocuite") or ""))
                comp = row.get("componenta_sisteme_json")
                if comp:
                    fragmente.append(json.dumps(comp, ensure_ascii=False) if not isinstance(comp, str) else comp)
    except Exception:
        pass

    return " \n ".join(fragmente).lower()


def _piesa_a_fost_utilizata(piesa_obj: dict, corpus_lower: str) -> bool:
    if not corpus_lower:
        return False
    den = str(piesa_obj.get("denumire") or "").strip().lower()
    cod_p = str(piesa_obj.get("cod_producator") or "").strip().lower()
    cod_c = str(piesa_obj.get("cod_comercial") or "").strip().lower()

    if len(cod_p) >= 3 and cod_p in corpus_lower:
        return True
    if len(cod_c) >= 3 and cod_c in corpus_lower:
        return True
    if len(den) >= 4 and den in corpus_lower:
        return True
    return False


def _are_lipsa_pret_sau_um(piesa_obj: dict) -> tuple[bool, list[str]]:
    motive = []
    pret = float(piesa_obj.get("pret_achizitie") or 0.0)
    valuta = str(piesa_obj.get("valuta_achizitie") or "").strip().upper()
    if pret <= 0:
        motive.append("Fără preț (0.00)")
    if valuta not in ("RON", "EUR"):
        motive.append("Fără monedă / UM")
    return (len(motive) > 0), motive


def render_piese():
    st.subheader("🔧 Gestiune Piese de Schimb, Tarife & Curățenie Prețuri")
    _activeaza_stergere_pret_la_focus()

    setari_info = SetariRepository.get_setari() or {}
    parola_setata = str(setari_info.get('pass', '')).strip()
    acces_permis = bool(st.session_state.get("is_unlocked", False)) or (not parola_setata)

    if not acces_permis:
        st.info("🔒 Prețurile de achiziție, furnizorii, tarifele standard și curățenia de prețuri sunt protejate. Deblochează sesiunea din **SistemAdmin → 🔑 Deblocare**.")

    tab_piese, tab_tarife_grile, tab_audit_curatenie = st.tabs([
        "🔩 Catalog Piese de Schimb",
        "💶 Tarife Standard (Grila Nivel A & Nivel B)",
        "🧹 Curățenie Prețuri, UM & Piese Neutilizate"
    ])

    # ==================================================================
    # TAB 1: CATALOG PIESE DE SCHIMB (FRAGMENT IZOLAT — FĂRĂ RERUN GLOBAL)
    # ==================================================================
    @st.fragment
    def _fragment_catalog_piese():
        masini = [m['denumire'] for m in MasiniRepository.get_all()]
        sel_m = st.selectbox(
            "Selectează Mașina (Filtrare listă & Asociere piesă nouă)",
            options=["Toate mașinile / General"] + masini,
            key="sel_masina_piese"
        )

        with st.expander("➕ Adaugă Piesă Nouă (Preț Achiziție în EUR sau RON)", expanded=False):
            with st.form("form_adauga_piesa", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    denumire = st.text_input("Denumire Piesă *")
                    cod_producator = st.text_input("Cod Producător")
                    cod_comercial = st.text_input("Cod Comercial")
                    subansamblu = st.text_input("Subansamblu")
                with col2:
                    parametri = st.text_area("Parametri Piesă (dimensiuni, tensiune, putere etc.)", height=100)
                    termen_livrare_nou = st.text_input("Termen livrare (ex: 1, 3-5 zile, Stoc)", value="1")
                    if acces_permis:
                        link_furnizor = st.text_input("Link Furnizor / Magazin (URL)")
                        cp_nou1, cp_nou2 = st.columns([3, 1], vertical_alignment="bottom")
                        with cp_nou1:
                            pret_expr_nou = st.text_input(
                                "Preț Achiziție — acceptă calcule (+, -, *, /)",
                                value="",
                                placeholder="ex: 120 + 35  sau  450 / 3  sau  85,50 * 2"
                            )
                        with cp_nou2:
                            valuta_noua = st.selectbox("Monedă", options=["EUR", "RON"], index=0)
                    else:
                        st.info("🔒 Prețul de achiziție și furnizorul sunt protejate de parolă.")
                        link_furnizor = ""
                        pret_expr_nou = ""
                        valuta_noua = "RON"

                st.caption(f"📌 Piesa se va înregistra pentru: **{sel_m}** (păstrează **EUR** pentru prețurile valabile pe termen lung și **RON** pentru achizițiile locale).")

                if st.form_submit_button("💾 Salvează Piesa", type="primary"):
                    if not denumire.strip():
                        st.error("Te rugăm să completezi denumirea piesei.")
                    else:
                        pret_calculat, err_pret = calculeaza_pret_din_expresie(pret_expr_nou, 0.0)
                        if err_pret:
                            st.error(f"⚠️ {err_pret}")
                        else:
                            PieseRepository.insert({
                                "denumire": denumire.strip(),
                                "cod_producator": cod_producator.strip(),
                                "cod_comercial": cod_comercial.strip(),
                                "subansamblu": subansamblu.strip(),
                                "parametri": parametri.strip(),
                                "termen_livrare": termen_livrare_nou.strip() or "1",
                                "link_furnizor": link_furnizor.strip(),
                                "pret_achizitie": pret_calculat,
                                "valuta_achizitie": valuta_noua,
                                "masina_montaj": sel_m if sel_m != "Toate mașinile / General" else "General"
                            })
                            _obtine_corpus_utilizare_istoric.clear()
                            st.success(f"✅ Piesa '{denumire}' a fost salvată (Preț: **{pret_calculat:.2f} {valuta_noua}** | Termen: {termen_livrare_nou})!")

        st.markdown("---")
        st.subheader("🔍 Căutare Rapidă, Editare & Ștergere Piese")

        c_search1, c_search2 = st.columns([5, 1], vertical_alignment="bottom")
        with c_search1:
            termen_cautare = st.text_input(
                "Caută piesa după expresie (poți scrie mai multe cuvinte, ex: 'rulment 6204' sau 'senzor 24v'):",
                placeholder="Scrie denumire, cod producător, cod comercial, parametru sau subansamblu...",
                key="termen_cautare_piese"
            ).strip().lower()
        with c_search2:
            if st.button("🧹 Resetează", key="btn_reset_cautare_piese", use_container_width=True):
                st.session_state["termen_cautare_piese"] = ""

        piese_baza = PieseRepository.get_filtrate(sel_m) or []
        cuvinte_cautate = [c for c in termen_cautare.split() if c]

        if not cuvinte_cautate:
            st.info(f"📦 Ai **{len(piese_baza)}** repere în această selecție. Introdu o expresie în câmpul de căutare de mai sus sau folosește tab-ul **🧹 Curățenie Prețuri, UM & Piese Neutilizate**.")
        else:
            piese_filtrate = []
            for p in piese_baza:
                index_cautare = " ".join([
                    str(p.get('denumire') or ''),
                    str(p.get('cod_producator') or ''),
                    str(p.get('cod_comercial') or ''),
                    str(p.get('parametri') or ''),
                    str(p.get('subansamblu') or ''),
                    str(p.get('masina_montaj') or '')
                ]).lower()
                if all(cuv in index_cautare for cuv in cuvinte_cautate):
                    piese_filtrate.append(p)

            if piese_filtrate:
                st.success(f"📦 S-au găsit **{len(piese_filtrate)}** repere pentru expresia **'{termen_cautare}'**:")
                for p in piese_filtrate[:100]:
                    masina_eticheta = p.get('masina_montaj', 'General')
                    pid = p.get('id')
                    pret_val = float(p.get('pret_achizitie', 0.0) or 0.0)
                    valuta_val = str(p.get('valuta_achizitie') or 'RON').strip().upper()
                    if valuta_val not in ("RON", "EUR"):
                        valuta_val = "RON"
                    termen_val = str(p.get('termen_livrare') or '1')
                    pret_antet = f" | Preț: {pret_val:.2f} {valuta_val}" if acces_permis else ""
                    cod_antet = f" [{p.get('cod_producator')}]" if p.get('cod_producator') else ""
                    param_scurt = (
                        f" — {p.get('parametri')[:40]}..."
                        if p.get('parametri') and len(str(p.get('parametri'))) > 40
                        else (f" — {p.get('parametri')}" if p.get('parametri') else "")
                    )

                    expander_title = f"🔩 {p['denumire']}{cod_antet}{param_scurt} ({masina_eticheta} | Termen: {termen_val}){pret_antet}"
                    with st.expander(expander_title, expanded=(len(piese_filtrate) == 1)):
                        if acces_permis and p.get('link_furnizor'):
                            st.markdown(f"🔗 **Link Furnizor:** [{p['link_furnizor']}]({p['link_furnizor']})")

                        with st.form(f"form_mod_piesa_{pid}"):
                            cp1, cp2 = st.columns(2)
                            with cp1:
                                mod_den = st.text_input("Denumire Piesă", value=p.get('denumire', ''), key=f"den_{pid}")
                                mod_prod = st.text_input("Cod Producător", value=p.get('cod_producator', ''), key=f"prod_{pid}")
                                mod_com = st.text_input("Cod Comercial", value=p.get('cod_comercial', ''), key=f"com_{pid}")
                                mod_sub = st.text_input("Subansamblu", value=p.get('subansamblu', ''), key=f"sub_{pid}")
                            with cp2:
                                mod_param = st.text_area("Parametri Piesă", value=p.get('parametri', '') or '', height=100, key=f"param_{pid}")
                                mod_termen = st.text_input("Termen livrare", value=termen_val, key=f"termen_{pid}")

                                if acces_permis:
                                    mod_link = st.text_input("Link Furnizor", value=p.get('link_furnizor', '') or '', key=f"link_{pid}")
                                    c_mp1, c_mp2 = st.columns([3, 1], vertical_alignment="bottom")
                                    with c_mp1:
                                        mod_pret_expr = st.text_input(
                                            "Preț Achiziție — acceptă calcule (+, -, *, /)",
                                            value=f"{pret_val:.2f}",
                                            placeholder=f"Actual: {pret_val:.2f} {valuta_val}",
                                            key=f"pret_{pid}"
                                        )
                                    with c_mp2:
                                        opt_val = ["EUR", "RON"]
                                        idx_val = opt_val.index(valuta_val) if valuta_val in opt_val else 1
                                        mod_valuta = st.selectbox("Monedă", options=opt_val, index=idx_val, key=f"val_{pid}")
                                else:
                                    st.info("🔒 Furnizorul și prețul de achiziție sunt ascunse. Deblochează din SistemAdmin → 🔑 Deblocare.")
                                    mod_link = p.get('link_furnizor', '') or ''
                                    mod_pret_expr = f"{pret_val:.2f}"
                                    mod_valuta = valuta_val

                            bt1, bt2 = st.columns(2)
                            if bt1.form_submit_button("💾 Salvează Modificările", key=f"sav_{pid}", type="primary"):
                                mod_pret_calc, err_mod = calculeaza_pret_din_expresie(mod_pret_expr, pret_val)
                                if err_mod:
                                    st.error(f"⚠️ {err_mod}")
                                else:
                                    PieseRepository.update(pid, {
                                        "denumire": mod_den.strip(),
                                        "cod_producator": mod_prod.strip(),
                                        "cod_comercial": mod_com.strip(),
                                        "subansamblu": mod_sub.strip(),
                                        "parametri": mod_param.strip(),
                                        "termen_livrare": mod_termen.strip() or "1",
                                        "link_furnizor": mod_link.strip(),
                                        "pret_achizitie": mod_pret_calc,
                                        "valuta_achizitie": mod_valuta
                                    })
                                    _obtine_corpus_utilizare_istoric.clear()
                                    st.toast(f"✅ Salvat: {mod_den.strip()} -> {mod_pret_calc:.2f} {mod_valuta}")
                            if bt2.form_submit_button("🗑️ Șterge Piesa", key=f"del_{pid}"):
                                PieseRepository.delete(pid)
                                _obtine_corpus_utilizare_istoric.clear()
                                st.toast("🗑️ Piesa a fost ștearsă!")
            else:
                st.warning(f"Nu s-a găsit nicio piesă care să conțină expresia **'{termen_cautare}'**.")

    with tab_piese:
        _fragment_catalog_piese()

    # ==================================================================
    # TAB 2: TARIFE STANDARD (FRAGMENT IZOLAT — FĂRĂ RERUN GLOBAL)
    # ==================================================================
    @st.fragment
    def _fragment_tarife_grile():
        st.markdown("##### 💶 Tarife Standard pentru Servicii & Activități (Grila Nivel A & Grila Nivel B)")
        st.caption(
            "Gestionează tarifele standard pe cele două nivele de grilă (**Nivel A** și **Nivel B**). "
            "Poți modifica denumirea, nivelul grilei, prețul și **unitatea de măsură (UM)** (ex: `EUR/ora`, `RON/km`, `EUR/buc`, `EUR/intervenție`)."
        )

        if not acces_permis:
            st.warning("🔒 Tarifele standard sunt protejate cu parolă. Mergi la **SistemAdmin → 🔑 Deblocare** pentru a le vizualiza sau modifica.")
            return

        with st.expander("➕ Adaugă Tarif Nou în Grila Nivel A / Nivel B", expanded=False):
            with st.form("form_add_tarif_piese_tab", clear_on_submit=True):
                ct1, ct2, ct3, ct4 = st.columns([3, 1.3, 1.4, 1.4], vertical_alignment="bottom")
                with ct1:
                    desc_t_nou = st.text_input("Descriere serviciu / activitate *", placeholder="ex: Manoperă intervenție CNC / Ora de transport")
                with ct2:
                    nivel_t_nou = st.selectbox("Nivel Grilă", options=OPT_NIVELE_GRILA, index=0)
                with ct3:
                    pret_t_nou = st.number_input("Preț unitar", min_value=0.0, step=5.0, format="%.2f")
                with ct4:
                    um_t_nou = st.selectbox("Monedă / UM", options=OPT_MONEDA_UM_TARIFE, index=0)

                if st.form_submit_button("💾 Adaugă Tarif", type="primary"):
                    if not desc_t_nou.strip():
                        st.error("⚠️ Introduceți descrierea serviciului / activității!")
                    else:
                        _insert_tarif_safe(desc_t_nou.strip(), pret_t_nou, um_t_nou, nivel_t_nou)
                        st.toast(f"✅ Tarif adăugat: {desc_t_nou.strip()} [{nivel_t_nou}]")

        tarife_all = _get_tarife_all_safe()
        c_ft1, c_ft2 = st.columns([2, 2], vertical_alignment="bottom")
        with c_ft1:
            filtru_grila_t = st.radio(
                "Filtrează după nivel grilă:",
                options=["Toate grilele", "Nivel A", "Nivel B"],
                horizontal=True,
                key="piese_tab_filtru_grila"
            )
        with c_ft2:
            filtru_lipsa_t = st.checkbox(
                "⚠️ Arată doar tarifele fără preț (0.00) sau fără UM",
                value=False,
                key="piese_tab_tarife_incomplete"
            )

        tarife_afis = []
        for t in tarife_all:
            niv = str(t.get("nivel_grila") or "Nivel A").strip()
            if niv not in OPT_NIVELE_GRILA:
                niv = "Nivel A"
            if filtru_grila_t != "Toate grilele" and niv != filtru_grila_t:
                continue
            pret_t = float(t.get("pret") or 0.0)
            um_t = str(t.get("moneda_um") or "").strip()
            if filtru_lipsa_t and not (pret_t <= 0 or not um_t or "/" not in um_t):
                continue
            tarife_afis.append(t)

        if not tarife_afis:
            st.info("Nu există tarife care să corespundă filtrelor selectate.")
            return

        st.caption(f"Se afișează **{len(tarife_afis)}** tarife:")
        for t in tarife_afis:
            tid = t["id"]
            niv_cur = str(t.get("nivel_grila") or "Nivel A").strip()
            if niv_cur not in OPT_NIVELE_GRILA:
                niv_cur = "Nivel A"
            um_cur = str(t.get("moneda_um") or "EUR/ora").strip()
            opt_um_row = list(OPT_MONEDA_UM_TARIFE)
            if um_cur and um_cur not in opt_um_row:
                opt_um_row.insert(0, um_cur)
            elif not um_cur:
                opt_um_row.insert(0, "-- Fără UM --")

            with st.form(f"form_row_tarif_{tid}"):
                col_t1, col_t2, col_t3, col_t4, col_t5, col_t6 = st.columns(
                    [3.2, 1.3, 1.3, 1.5, 0.7, 0.7], vertical_alignment="center"
                )
                nou_desc_t = col_t1.text_input(
                    "Descriere",
                    value=str(t.get("descriere") or ""),
                    key=f"pt_desc_tarif_{tid}",
                    label_visibility="collapsed"
                )
                nou_niv_t = col_t2.selectbox(
                    "Grilă",
                    options=OPT_NIVELE_GRILA,
                    index=OPT_NIVELE_GRILA.index(niv_cur),
                    key=f"pt_niv_tarif_{tid}",
                    label_visibility="collapsed"
                )
                nou_pret_t = col_t3.number_input(
                    "Preț",
                    value=float(t.get("pret") or 0.0),
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"pt_pret_tarif_{tid}",
                    label_visibility="collapsed"
                )
                nou_um_t = col_t4.selectbox(
                    "UM",
                    options=opt_um_row,
                    index=opt_um_row.index(um_cur) if um_cur in opt_um_row else 0,
                    key=f"pt_um_tarif_{tid}",
                    label_visibility="collapsed"
                )
                if col_t5.form_submit_button("💾", help="Salvează modificările tarifului"):
                    um_salvat = "" if nou_um_t == "-- Fără UM --" else nou_um_t
                    _update_tarif_complet_safe(tid, nou_desc_t.strip(), nou_pret_t, um_salvat, nou_niv_t)
                    st.toast(f"✅ Actualizat: {nou_desc_t.strip()} [{nou_niv_t}] -> {nou_pret_t:.2f} {um_salvat}")
                if col_t6.form_submit_button("🗑️", help="Șterge tariful"):
                    _delete_tarif_safe(tid)
                    st.toast("🗑️ Tarif șters.")

    with tab_tarife_grile:
        _fragment_tarife_grile()

    # ==================================================================
    # TAB 3: CURĂȚENIE PREȚURI (FRAGMENT IZOLAT — FĂRĂ RERUN GLOBAL)
    # ==================================================================
    @st.fragment
    def _fragment_audit_curatenie():
        st.markdown("##### 🧹 Audit & Curățenie Catalog Piese (Preț / UM lipsă & Repere neutilizate)")

        if not acces_permis:
            st.warning("🔒 Pentru a face curățenie în prețuri și a vedea valorile de achiziție, deblochează mai întâi sesiunea din **SistemAdmin → 🔑 Deblocare**.")
            return

        toate_piesele = PieseRepository.get_all() or []
        corpus_istoric = _obtine_corpus_utilizare_istoric()

        piese_fara_pret_um = []
        piese_neutilizate = []

        for p in toate_piesele:
            lipsa, motive = _are_lipsa_pret_sau_um(p)
            if lipsa:
                p_copy = dict(p)
                p_copy["_motive_lipsa"] = ", ".join(motive)
                piese_fara_pret_um.append(p_copy)

            if not _piesa_a_fost_utilizata(p, corpus_istoric):
                piese_neutilizate.append(p)

        m_c1, m_c2, m_c3 = st.columns(3)
        m_c1.metric("Total piese în catalog", len(toate_piesele))
        m_c2.metric("⚠️ Fără preț (0.00) sau fără UM", len(piese_fara_pret_um))
        m_c3.metric("💤 Neutilizate niciodată (în oferte/intervenții)", len(piese_neutilizate))

        st.markdown("---")
        mod_audit = st.radio(
            "Selectează lista de curățenie:",
            options=[
                f"⚠️ Repere fără preț (0.00) sau fără UM ({len(piese_fara_pret_um)})",
                f"💤 Piese neutilizate niciodată ({len(piese_neutilizate)})",
                f"📋 Toate piesele din catalog ({len(toate_piesele)})"
            ],
            key="radio_mod_audit_piese"
        )

        c_f1, c_f2 = st.columns([3, 1.5], vertical_alignment="bottom")
        with c_f1:
            filtru_txt_audit = st.text_input(
                "Filtrează în această listă (denumire, cod, mașină):",
                placeholder="ex: rulment, General, 0.00...",
                key="txt_filtru_audit_piese"
            ).strip().lower()
        with c_f2:
            doar_neutilizate_si_fara_pret = st.checkbox(
                "Doar cele care sunt ȘI neutilizate ȘI fără preț",
                value=False,
                key="chk_intersectie_audit"
            )

        if mod_audit.startswith("⚠️"):
            lista_curenta = piese_fara_pret_um
        elif mod_audit.startswith("💤"):
            lista_curenta = piese_neutilizate
        else:
            lista_curenta = toate_piesele

        if doar_neutilizate_si_fara_pret:
            ids_neutilizate = {p["id"] for p in piese_neutilizate}
            lista_curenta = [
                p for p in lista_curenta
                if p["id"] in ids_neutilizate and _are_lipsa_pret_sau_um(p)[0]
            ]

        if filtru_txt_audit:
            lista_curenta = [
                p for p in lista_curenta
                if filtru_txt_audit in (
                    f"{p.get('denumire', '')} {p.get('cod_producator', '')} "
                    f"{p.get('cod_comercial', '')} {p.get('masina_montaj', '')}"
                ).lower()
            ]

        if not lista_curenta:
            st.success("🎉 Nu există repere care să corespundă acestui filtru de curățenie!")
            return

        st.info(f"Se afișează **{len(lista_curenta)}** repere (maxim 100 pe pagină). Poți actualiza rapid prețul / moneda sau șterge reperul fără să îți reseteze pagina:")

        for p in lista_curenta[:100]:
            pid = p["id"]
            pret_c = float(p.get("pret_achizitie") or 0.0)
            val_c = str(p.get("valuta_achizitie") or "").strip().upper()
            este_nefolosita = not _piesa_a_fost_utilizata(p, corpus_istoric)
            lipsa_flag, motive_list = _are_lipsa_pret_sau_um(p)

            badges = []
            if lipsa_flag:
                badges.append(f"⚠️ {', '.join(motive_list)}")
            if este_nefolosita:
                badges.append("💤 Neutilizată")
            badge_str = " | ".join(badges) if badges else "✅ OK"

            cod_str = f" [{p.get('cod_producator')}]" if p.get("cod_producator") else ""
            titlu_row = f"🔩 {p.get('denumire', '')}{cod_str} ({p.get('masina_montaj') or 'General'}) — {badge_str}"

            with st.expander(titlu_row, expanded=False):
                with st.form(f"form_audit_row_{pid}"):
                    ca1, ca2, ca3, ca4, ca5 = st.columns([2.5, 1.3, 1.2, 0.8, 0.8], vertical_alignment="bottom")
                    with ca1:
                        aud_den = st.text_input("Denumire", value=str(p.get("denumire") or ""), key=f"aud_den_{pid}")
                    with ca2:
                        aud_pret_txt = st.text_input(
                            "Preț Achiziție",
                            value=f"{pret_c:.2f}",
                            key=f"aud_pret_{pid}"
                        )
                    with ca3:
                        opt_v_aud = ["EUR", "RON"]
                        idx_v_aud = opt_v_aud.index(val_c) if val_c in opt_v_aud else 0
                        aud_val = st.selectbox("Monedă / UM", options=opt_v_aud, index=idx_v_aud, key=f"aud_val_{pid}")
                    with ca4:
                        if st.form_submit_button("💾", help="Salvează prețul și moneda", use_container_width=True):
                            pret_nou_aud, err_a = calculeaza_pret_din_expresie(aud_pret_txt, pret_c)
                            if err_a:
                                st.error(err_a)
                            else:
                                PieseRepository.update(pid, {
                                    "denumire": aud_den.strip() or p.get("denumire", ""),
                                    "cod_producator": p.get("cod_producator") or "",
                                    "cod_comercial": p.get("cod_comercial") or "",
                                    "subansamblu": p.get("subansamblu") or "",
                                    "parametri": p.get("parametri") or "",
                                    "termen_livrare": str(p.get("termen_livrare") or "1"),
                                    "link_furnizor": p.get("link_furnizor") or "",
                                    "pret_achizitie": pret_nou_aud,
                                    "valuta_achizitie": aud_val
                                })
                                _obtine_corpus_utilizare_istoric.clear()
                                st.toast(f"✅ Salvat: {aud_den.strip()} -> {pret_nou_aud:.2f} {aud_val}")
                    with ca5:
                        if st.form_submit_button("🗑️", help="Șterge reperul", use_container_width=True):
                            PieseRepository.delete(pid)
                            _obtine_corpus_utilizare_istoric.clear()
                            st.toast(f"🗑️ Reper șters: {p.get('denumire', '')}")

    with tab_audit_curatenie:
        _fragment_audit_curatenie()