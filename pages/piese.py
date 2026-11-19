#----------------------------------
#-------piese.py-------------------
#----------------------------------

import ast
import operator
import streamlit as st
import streamlit.components.v1 as components
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository
from repositories.setari_repository import SetariRepository

# Evaluator matematic sigur pentru +, -, *, /, paranteze (acceptă și virgulă ca separator zecimal)
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

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

def render_piese():
    st.subheader("🔧 Gestiune Piese de Schimb & Parametri Tehnici")
    _activeaza_stergere_pret_la_focus()
    
    setari_info = SetariRepository.get_setari() or {}
    parola_setata = str(setari_info.get('pass', '')).strip()
    
    if "preturi_deblocate" not in st.session_state:
        st.session_state["preturi_deblocate"] = False

    with st.sidebar:
        st.markdown("---")
        st.markdown("🔒 **Date Achiziție & Furnizori**")
        if not st.session_state["preturi_deblocate"]:
            parola_introdusa = st.text_input("Introdu parola din Setări", type="password", key="input_pass_piese")
            if st.button("Deblochează Datele"):
                if parola_setata and parola_introdusa == parola_setata:
                    st.session_state["preturi_deblocate"] = True
                    st.success("Date deblocate!")
                    st.rerun()
                else:
                    st.error("Parolă incorectă sau nesetată în Setări.")
        else:
            st.success("🔓 Prețuri (EUR / RON) și furnizori vizibili.")
            if st.button("Blochează la loc"):
                st.session_state["preturi_deblocate"] = False
                st.rerun()

    acces_permis = st.session_state["preturi_deblocate"] or (not parola_setata)

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
                        st.success(f"✅ Piesa '{denumire}' a fost salvată (Preț: **{pret_calculat:.2f} {valuta_noua}** | Termen: {termen_livrare_nou})!")
                        st.rerun()

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
            st.rerun()

    piese_baza = PieseRepository.get_filtrate(sel_m) or []
    cuvinte_cautate = [c for c in termen_cautare.split() if c]

    if not cuvinte_cautate:
        st.info(f"📦 Ai **{len(piese_baza)}** repere în această selecție. Introdu o expresie în câmpul de căutare de mai sus pentru a afișa, edita sau șterge piesele dorite.")
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
                                st.info("🔒 Furnizorul și prețul de achiziție sunt ascunse. Deblochează din sidebar.")
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
                                st.success(f"✅ Modificări salvate! Preț nou: **{mod_pret_calc:.2f} {mod_valuta}**")
                                st.rerun()
                        if bt2.form_submit_button("🗑️ Șterge Piesa", key=f"del_{pid}"):
                            PieseRepository.delete(pid)
                            st.success("Piesa a fost ștearsă!")
                            st.rerun()
        else:
            st.warning(f"Nu s-a găsit nicio piesă care să conțină expresia **'{termen_cautare}'**.")