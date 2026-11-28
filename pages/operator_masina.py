
#--------------------------------------
#-----pages/operator_masina.py-----------
#--------------------------------------


from datetime import datetime
import logging
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.reparatii_repository import ReparatiiRepository
from utils.acces_conturi import activeaza_mod_operator, get_cont_activ, seteaza_cont_birou

logger = logging.getLogger(__name__)

OPT_FIRMA = "-- Alege firma --"
OPT_MASINA = "-- Alege mașina --"


@st.cache_data(ttl=60, show_spinner=False)
def _incarca_firme_operator() -> list[dict]:
    return FirmeRepository.get_all() or []


@st.cache_data(ttl=60, show_spinner=False)
def _incarca_masini_firma_operator(firma_id: int) -> list[dict]:
    return MasiniRepository.get_by_firma(int(firma_id)) or []


def _marcheaza_masina_defecta(
    *,
    masina_obj: dict,
    defect_text: str,
    cod_eroare: str,
    simptom_text: str,
    operator_nume: str,
) -> tuple[bool, str]:
    mid = int(masina_obj["id"])
    denumire = str(masina_obj.get("denumire") or f"Mașina #{mid}").strip()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    defect_nou = defect_text.strip()
    if cod_eroare.strip():
        defect_nou = f"[{cod_eroare.strip()}] {defect_nou}" if defect_nou else f"[{cod_eroare.strip()}]"

    defecte_vechi = str(masina_obj.get("defecte") or "").strip()
    linie_log = f"{stamp} ({operator_nume}): {defect_nou}"
    defecte_actualizate = f"{linie_log}\n{defecte_vechi}".strip() if defecte_vechi else linie_log

    erori_vechi = str(masina_obj.get("erori") or "").strip()
    erori_actualizate = erori_vechi
    if cod_eroare.strip():
        cod_c = cod_eroare.strip()
        lista_cod = [c.strip() for c in erori_vechi.split(",") if c.strip()]
        if cod_c not in lista_cod:
            lista_cod.append(cod_c)
        erori_actualizate = ", ".join(lista_cod)

    try:
        with db_cursor() as cur:
            cur.execute(
                """
                ALTER TABLE masini
                ADD COLUMN IF NOT EXISTS stare_operare VARCHAR(50) DEFAULT 'Funcțională',
                ADD COLUMN IF NOT EXISTS ultim_defect_raportat TEXT DEFAULT '',
                ADD COLUMN IF NOT EXISTS raportat_de VARCHAR(150) DEFAULT '',
                ADD COLUMN IF NOT EXISTS data_raportare_defect TIMESTAMP
                """
            )
            cur.execute(
                """
                UPDATE masini
                SET stare_operare = 'Defectă',
                    ultim_defect_raportat = %s,
                    raportat_de = %s,
                    data_raportare_defect = %s,
                    defecte = %s,
                    erori = %s
                WHERE id = %s
                """,
                (
                    defect_nou,
                    operator_nume,
                    datetime.now(),
                    defecte_actualizate,
                    erori_actualizate,
                    mid,
                ),
            )
    except Exception as exc:
        logger.exception("Eroare la marcarea mașinii #%s ca defectă: %s", mid, exc)
        return False, f"Eroare la actualizarea mașinii în baza de date: {exc}"

    if hasattr(MasiniRepository.get_all, "clear"):
        MasiniRepository.get_all.clear()
    if hasattr(MasiniRepository.get_by_firma, "clear"):
        MasiniRepository.get_by_firma.clear()
    _incarca_masini_firma_operator.clear()

    return True, f"Mașina **{denumire}** a fost marcată ca **DEFECTĂ**."


def _salveaza_sesizare_interventie(
    *,
    firma_nume: str,
    masina_denumire: str,
    subansamblu: str,
    simptom: str,
    defect: str,
    cod_eroare: str,
    operator_nume: str,
) -> tuple[bool, str]:
    try:
        payload = {
            "firma": firma_nume,
            "masina": masina_denumire,
            "subansamblu": subansamblu or "General",
            "defect": defect,
            "cod_eroare": cod_eroare or "Niciunul",
            "piese_valide": [],
            "titlu_lucrare": f"Defect raportat de operator ({masina_denumire})",
            "simptom": simptom,
            "solutie": "",
            "stare_fin": "Oprită / Necesar piese",
            "durata_min": 0,
            "optimizari": "",
            "tehnician_nume": f"Operator: {operator_nume}",
            "verificator_nume": "",
            "tip_interventie": "diagnostic",
        }
        rid = ReparatiiRepository.insert(payload)
        if not rid:
            return False, "Nu s-a putut înregistra sesizarea în raportul de intervenții."
        return True, f"Sesizarea a fost înregistrată (Raport #{rid})."
    except Exception as exc:
        logger.exception("Eroare la salvarea sesizării operatorului: %s", exc)
        return False, f"Eroare la salvarea sesizării: {exc}"


def render_operator_masina():
    cont = get_cont_activ()
    if not cont.este_operator:
        activeaza_mod_operator()
        cont = get_cont_activ()

    st.subheader("👷 Raportare Defect Mașină (Acces Operator)")
    st.caption(
        "Modul cu drepturi restrânse: selectează mașina pe care lucrezi, seteaz-o ca **Defectă** "
        "și descrie defectul sau eroarea apărută."
    )

    col_op1, col_op2, col_op3 = st.columns([2.0, 1.5, 1.5], vertical_alignment="center")
    with col_op1:
        nume_op = st.text_input(
            "Nume operator",
            value=st.session_state.get("operator_nume_curent", cont.nume),
            key="op_input_nume",
        )
        if nume_op.strip() and nume_op.strip() != cont.nume:
            activeaza_mod_operator(nume_op.strip())
            cont = get_cont_activ()
    with col_op2:
        st.caption(f"👤 Activ ca: **{cont.nume}**")
    with col_op3:
        if st.button("🏢 Revino la Cont Birou", use_container_width=True, key="op_btn_iesire_birou"):
            seteaza_cont_birou({"id": "birou_1", "nume": "Birou — Utilizator 1", "rol": "birou_full"})
            st.rerun()

    firme_db = _incarca_firme_operator()
    if not firme_db:
        st.warning("Nu există firme configurate momentan.")
        return

    firme_map = {
        str(f["nume_firma"]).strip(): f
        for f in firme_db
        if isinstance(f, dict) and str(f.get("nume_firma") or "").strip()
    }
    opt_firme = [OPT_FIRMA] + sorted(firme_map.keys(), key=str.lower)

    c_f, c_m = st.columns(2)
    with c_f:
        sel_firma = st.selectbox("1. Firmă / Secție", options=opt_firme, key="op_sel_firma")

    if sel_firma == OPT_FIRMA:
        st.info("Selectează firma pentru a vedea mașinile disponibile.")
        return

    firma_id = int(firme_map[sel_firma]["id"])
    masini_db = _incarca_masini_firma_operator(firma_id)
    if not masini_db:
        st.info("Nu există mașini înregistrate pentru această firmă.")
        return

    masini_map = {
        str(m["denumire"]).strip(): m
        for m in masini_db
        if isinstance(m, dict) and str(m.get("denumire") or "").strip()
    }
    opt_masini = [OPT_MASINA] + sorted(masini_map.keys(), key=str.lower)

    with c_m:
        sel_masina = st.selectbox("2. Mașina pe care lucrezi", options=opt_masini, key="op_sel_masina")

    if sel_masina == OPT_MASINA:
        st.info("Selectează mașina pe care lucrezi pentru a raporta un defect.")
        return

    masina_obj = masini_map[sel_masina]
    subansambluri_opt = ["General"]
    if masina_obj.get("subansambluri"):
        extras = [s.strip() for s in str(masina_obj["subansambluri"]).split(",") if s.strip()]
        subansambluri_opt = list(dict.fromkeys(["General"] + extras))

    erori_cunoscute = []
    if masina_obj.get("erori"):
        erori_cunoscute = [e.strip() for e in str(masina_obj["erori"]).split(",") if e.strip()]

    stare_curenta_op = str(masina_obj.get("stare_operare") or "Funcțională")
    if stare_curenta_op == "Defectă":
        st.error(
            f"🚨 Mașina **{sel_masina}** este deja marcată **Defectă**."
            + (f" Ultimul defect: {masina_obj.get('ultim_defect_raportat')}" if masina_obj.get("ultim_defect_raportat") else "")
        )
    else:
        st.success(f"✅ Stare curentă mașină **{sel_masina}**: **{stare_curenta_op}**")

    with st.form("form_operator_raporteaza_defect", clear_on_submit=True):
        marcheaza_defecta = st.checkbox(
            "🚨 Marchează această mașină ca DEFECTĂ",
            value=True,
        )

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            subansamblu = st.selectbox("Subansamblu afectat", options=subansambluri_opt)
        with col_s2:
            if erori_cunoscute:
                cod_preset = st.selectbox("Cod eroare din listă (opțional)", options=[""] + erori_cunoscute)
                cod_manual = st.text_input("Sau scrie cod eroare / alarmă", placeholder="ex: ALM 414, E-12, F30002")
                cod_eroare_final = (cod_manual or cod_preset).strip()
            else:
                cod_eroare_final = st.text_input("Cod eroare / alarmă (opțional)", placeholder="ex: ALM 414, E-12, F30002").strip()

        simptom = st.text_input(
            "Ce se observă / simptom (opțional)",
            placeholder="ex: se oprește în ciclu, vibrații, scurgeri ulei, nu pornește axa...",
        )
        defect_descriere = st.text_area(
            "Descrierea defectului / erorii *",
            height=120,
            placeholder="Scrie clar ce s-a defectat sau ce eroare apare pe ecran...",
        )
        trimite_si_in_istoric = st.checkbox(
            "Trimite și în lista de intervenții / defecte pentru echipa tehnică",
            value=True,
        )

        submitted = st.form_submit_button("🚨 Salvează Raportul de Defect", type="primary", use_container_width=True)

        if submitted:
            defect_clean = str(defect_descriere or "").strip()
            if not defect_clean and not cod_eroare_final:
                st.error("⚠️ Scrie defectul / eroarea înainte de a trimite.")
            elif not marcheaza_defecta and not trimite_si_in_istoric:
                st.warning("⚠️ Bifează cel puțin o opțiune: marcarea mașinii ca defectă sau trimiterea sesizării.")
            else:
                operator_final = (nume_op or cont.nume).strip() or "Operator Mașină"
                mesaje_ok = []
                mesaje_err = []

                if marcheaza_defecta:
                    ok_m, msg_m = _marcheaza_masina_defecta(
                        masina_obj=masina_obj,
                        defect_text=defect_clean,
                        cod_eroare=cod_eroare_final,
                        simptom_text=str(simptom or "").strip(),
                        operator_nume=operator_final,
                    )
                    (mesaje_ok if ok_m else mesaje_err).append(msg_m)

                if trimite_si_in_istoric:
                    ok_i, msg_i = _salveaza_sesizare_interventie(
                        firma_nume=sel_firma,
                        masina_denumire=sel_masina,
                        subansamblu=subansamblu,
                        simptom=str(simptom or "").strip(),
                        defect=defect_clean or f"Eroare {cod_eroare_final}",
                        cod_eroare=cod_eroare_final,
                        operator_nume=operator_final,
                    )
                    (mesaje_ok if ok_i else mesaje_err).append(msg_i)

                for m_err in mesaje_err:
                    st.error(f"❌ {m_err}")
                for m_ok in mesaje_ok:
                    st.success(f"✅ {m_ok}")