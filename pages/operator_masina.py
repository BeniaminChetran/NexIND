
#--------------------------------------
#-----pages/operator_masina.py-----------
#--------------------------------------

from datetime import date, datetime, time, timedelta
import logging
import re
from urllib.parse import parse_qs, urlparse
import streamlit as st

from config import db_cursor
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.reparatii_repository import ReparatiiRepository
from repositories.taskuri_vizita_repository import TaskuriVizitaRepository
from utils.acces_conturi import (
    activeaza_mod_operator,
    get_alocari_operatori,
    get_cont_activ,
    seteaza_cont_birou,
)

logger = logging.getLogger(__name__)

OPT_FIRMA = "-- Alege firma --"
OPT_MASINA = "-- Alege mașina --"
OPT_ALTA_MASINA = "➕ Altă mașină / Mașină nouă (în afara listei alocate)"

_QR_ID_RE = re.compile(r"(?:masina(?:_id)?|m_id|id)\s*[:=]\s*(\d+)", flags=re.IGNORECASE)
_QR_DEN_RE = re.compile(r"(?:masina|utilaj|den|denumire)\s*[:=]\s*(.+)", flags=re.IGNORECASE)


@st.cache_data(ttl=120, show_spinner=False)
def _incarca_date_operator_cached() -> tuple[list[dict], list[dict]]:
    firme = FirmeRepository.get_all() or []
    masini = MasiniRepository.get_all() or []
    return firme, masini


def _goleste_cache_operator() -> None:
    _incarca_date_operator_cached.clear()
    for repo in (MasiniRepository, ReparatiiRepository, TaskuriVizitaRepository):
        for fn_name in ("get_all", "get_by_firma"):
            fn = getattr(repo, fn_name, None)
            if fn is not None and hasattr(fn, "clear"):
                try:
                    fn.clear()
                except Exception:
                    pass


def _rezolva_qr_masina(qr_raw: str, masini_all: list[dict]) -> dict | None:
    txt = str(qr_raw or "").strip()
    if not txt:
        return None

    # 1. URL cu query param ?masina_id=... sau ?qr=...
    if txt.startswith(("http://", "https://")):
        try:
            parsed = urlparse(txt)
            qs = parse_qs(parsed.query)
            for key in ("masina_id", "id", "m_id", "qr", "masina"):
                vals = qs.get(key)
                if vals and str(vals[0]).strip():
                    match = _rezolva_qr_masina(str(vals[0]).strip(), masini_all)
                    if match is not None:
                        return match
        except Exception:
            pass

    # 2. Format tip "MASINA:12" sau "masina_id=12"
    m_id = _QR_ID_RE.search(txt)
    if m_id:
        target_id = int(m_id.group(1))
        for m in masini_all:
            if int(m.get("id") or 0) == target_id:
                return m

    # 3. Număr direct sau prefix numeric
    if txt.isdigit():
        target_id = int(txt)
        for m in masini_all:
            if int(m.get("id") or 0) == target_id:
                return m

    # 4. Format tip "MASINA:Denumire" sau potrivire după serie / denumire
    m_den = _QR_DEN_RE.search(txt)
    cautare = (m_den.group(1) if m_den else txt).strip().lower()

    for m in masini_all:
        serie = str(m.get("serie") or "").strip().lower()
        if serie and serie == cautare:
            return m

    for m in masini_all:
        den = str(m.get("denumire") or "").strip().lower()
        if den and den == cautare:
            return m

    for m in masini_all:
        den = str(m.get("denumire") or "").strip().lower()
        if den and cautare in den:
            return m

    return None


def _marcheaza_masina_defecta(
    *,
    masina_obj: dict,
    defect_text: str,
    cod_eroare: str,
    operator_nume: str,
    operator_tel: str,
) -> tuple[bool, str]:
    mid = int(masina_obj["id"])
    denumire = str(masina_obj.get("denumire") or f"Mașina #{mid}").strip()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    defect_nou = defect_text.strip()
    if cod_eroare.strip():
        defect_nou = f"[{cod_eroare.strip()}] {defect_nou}" if defect_nou else f"[{cod_eroare.strip()}]"

    contact_txt = f"{operator_nume} ({operator_tel})" if operator_tel else operator_nume
    defecte_vechi = str(masina_obj.get("defecte") or "").strip()
    linie_log = f"{stamp} ({contact_txt}): {defect_nou}"
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
                    contact_txt,
                    datetime.now(),
                    defecte_actualizate,
                    erori_actualizate,
                    mid,
                ),
            )
    except Exception as exc:
        logger.exception("Eroare la marcarea mașinii #%s ca defectă: %s", mid, exc)
        return False, f"Eroare la actualizarea mașinii în baza de date: {exc}"

    return True, f"Mașina **{denumire}** a fost marcată ca **DEFECTĂ**."


def _salveaza_sesizare_reparatii(
    *,
    firma_nume: str,
    masina_denumire: str,
    subansamblu: str,
    simptom: str,
    defect: str,
    cod_eroare: str,
    operator_nume: str,
    operator_tel: str,
) -> tuple[bool, str]:
    try:
        contact_txt = f"{operator_nume} ({operator_tel})" if operator_tel else operator_nume
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
            "tehnician_nume": f"Operator: {contact_txt}",
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


def _creeaza_task_masina_in_afara_listei(
    *,
    firma_nume: str,
    firma_id: int | None,
    masina_denumire: str,
    defect_text: str,
    cod_eroare: str,
    operator_nume: str,
    operator_tel: str,
) -> tuple[bool, str]:
    contact_txt = f"{operator_nume} ({operator_tel})" if operator_tel else operator_nume
    err_part = f" [Cod: {cod_eroare}]" if cod_eroare else ""
    def_part = f" — Defect: {defect_text}" if defect_text else ""
    nota = (
        f"Mașină în afara listei alocate («{masina_denumire}») raportată de {contact_txt}{err_part}{def_part}. "
        f"Acțiuni: 1) Luat legătura cu superiorii firmei; 2) Întocmit ofertă de preț pentru intervenție la mașina nouă."
    )
    try:
        try:
            TaskuriVizitaRepository.insert(
                data_vizita=date.today(),
                de_facut_pana_la=date.today() + timedelta(days=1),
                ora_limita=time(17, 0),
                firma=firma_nume,
                firma_id=firma_id,
                masina=masina_denumire,
                note_vizita=nota,
                stare="Urgent",
            )
        except TypeError:
            TaskuriVizitaRepository.insert(
                data_vizita=date.today(),
                de_facut_pana_la=date.today() + timedelta(days=1),
                firma=firma_nume,
                firma_id=firma_id,
                masina=masina_denumire,
                note_vizita=nota,
                stare="Urgent",
            )
        return True, "Task creat: luat legătura cu superiorii firmei și întocmit ofertă de preț pentru intervenție la mașina nouă."
    except Exception as exc:
        logger.exception("Eroare la crearea task-ului pentru mașină în afara listei: %s", exc)
        return False, f"Eroare la crearea task-ului: {exc}"


def render_operator_masina():
    cont = get_cont_activ()
    if not cont.este_operator:
        activeaza_mod_operator()
        cont = get_cont_activ()

    firme_db, masini_all = _incarca_date_operator_cached()
    firme_map_id = {
        int(f["id"]): str(f["nume_firma"]).strip()
        for f in firme_db
        if isinstance(f, dict) and f.get("id") is not None and str(f.get("nume_firma") or "").strip()
    }
    firme_map_nume = {v: k for k, v in firme_map_id.items()}

    st.subheader("👷 Raportare Defect Mașină (Acces Operator)")
    st.caption(
        "Modul cu drepturi restrânse: selectează mașina pe care lucrezi (din lista alocată sau prin scanare QR), "
        "seteaz-o ca **Defectă** și scrie defectul sau eroarea."
    )

    # --- 1. IDENTITATE OPERATOR: NUME, NR TELEFON, FIRMA ---
    alocari = get_alocari_operatori()
    opt_preset_op = ["-- Alt operator --"] + [a["nume"] for a in alocari if a.get("nume")]

    c_op0, c_op1, c_op2, c_op3 = st.columns([1.4, 1.5, 1.3, 1.2], vertical_alignment="center")
    with c_op0:
        idx_preset = opt_preset_op.index(cont.nume) if cont.nume in opt_preset_op else 0
        sel_preset = st.selectbox("Profil predefinit", options=opt_preset_op, index=idx_preset, key="op_sel_preset")

    with c_op1:
        nume_op = st.text_input("Nume operator *", value=cont.nume, key="op_input_nume")

    with c_op2:
        tel_op = st.text_input("Nr. telefon *", value=cont.telefon, placeholder="07xx...", key="op_input_tel")

    with c_op3:
        st.caption(f"👤 **{nume_op.strip() or cont.nume}**")
        if st.button("🏢 Revino la Birou", use_container_width=True, key="op_btn_iesire_birou"):
            seteaza_cont_birou({"id": "birou_1", "nume": "Birou — Utilizator 1", "rol": "birou_full"})
            st.rerun()

    if sel_preset != "-- Alt operator --" and sel_preset != cont.nume:
        activeaza_mod_operator(nume_operator=sel_preset)
        st.rerun()

    opt_firme = [OPT_FIRMA] + sorted(firme_map_nume.keys(), key=str.lower)
    firma_init = cont.firma if cont.firma in firme_map_nume else OPT_FIRMA
    idx_firma_init = opt_firme.index(firma_init) if firma_init in opt_firme else 0

    sel_firma = st.selectbox("1. Firmă", options=opt_firme, index=idx_firma_init, key="op_sel_firma")

    if (
        (nume_op.strip() and nume_op.strip() != cont.nume)
        or (tel_op.strip() != cont.telefon)
        or (sel_firma != OPT_FIRMA and sel_firma != cont.firma)
    ):
        activeaza_mod_operator(
            nume_operator=nume_op.strip() or cont.nume,
            telefon=tel_op.strip(),
            firma="" if sel_firma == OPT_FIRMA else sel_firma,
        )
        cont = get_cont_activ()

    if sel_firma == OPT_FIRMA:
        st.info("Selectează firma pentru a vedea mașinile.")
        return

    firma_id = firme_map_nume.get(sel_firma)
    masini_firma = [
        m for m in masini_all
        if isinstance(m, dict) and str(m.get("denumire") or "").strip() and m.get("firma_id") == firma_id
    ]
    masini_firma_map = {str(m["denumire"]).strip(): m for m in masini_firma}

    # --- 2. SCANARE / INTRODUCERE QR CODE CU TRIMITERE EXACTA LA MASINA ---
    with st.expander("📷 Scanare / Cod QR Mașină (trimitere directă la mașină)", expanded=False):
        q_col1, q_col2 = st.columns([2.6, 1.0], vertical_alignment="bottom")
        with q_col1:
            qr_input = st.text_input(
                "Scanează sau lipește codul QR al mașinii",
                placeholder="ex: MASINA:12, ?masina_id=12, serie fabricație sau denumire mașină...",
                key="op_qr_cod_input",
            )
        with q_col2:
            if st.button("🎯 Deschide Mașina", type="primary", use_container_width=True, key="op_btn_scan_qr"):
                m_qr = _rezolva_qr_masina(qr_input, masini_all)
                if m_qr is None:
                    st.error("❌ Nu s-a găsit nicio mașină pentru codul QR introdus.")
                else:
                    fid_qr = m_qr.get("firma_id")
                    firma_qr = firme_map_id.get(int(fid_qr)) if fid_qr is not None else sel_firma
                    den_qr = str(m_qr.get("denumire") or "").strip()
                    if firma_qr and firma_qr in firme_map_nume:
                        st.session_state["op_sel_firma"] = firma_qr
                        activeaza_mod_operator(
                            nume_operator=nume_op.strip() or cont.nume,
                            telefon=tel_op.strip(),
                            firma=firma_qr,
                        )
                    st.session_state["op_sel_masina"] = den_qr
                    st.session_state["op_qr_masina_selectata"] = den_qr
                    st.toast(f"🎯 Mașină identificată prin QR: {den_qr}")
                    st.rerun()

        if masini_firma_map:
            m_ref_lbl = st.selectbox(
                "Generează cod QR text pentru etichetă utilaj",
                options=sorted(masini_firma_map.keys(), key=str.lower),
                key="op_qr_gen_masina",
            )
            m_ref = masini_firma_map[m_ref_lbl]
            st.code(f"MASINA:{m_ref['id']}", language="text")

    # --- 3. LISTA PREDEFINITA DE MASINI ALOCATE + OPTIUNE IN AFARA LISTEI ---
    alocari_map = {str(a.get("nume") or "").strip().lower(): a for a in alocari}
    aloc_curenta = alocari_map.get((nume_op or cont.nume).strip().lower())
    lista_alocata_raw = list(aloc_curenta.get("masini") or []) if aloc_curenta else list(cont.masini_alocate)
    lista_alocata_firma = [d for d in lista_alocata_raw if d in masini_firma_map]

    if lista_alocata_firma:
        st.caption("📋 Mașini alocate predefinit operatorului la această firmă: **" + ", ".join(lista_alocata_firma) + "**")
        opt_masini = [OPT_MASINA] + lista_alocata_firma + [OPT_ALTA_MASINA]
    else:
        st.caption("📋 Nu sunt setate mașini predefinite pentru acest operator la firma selectată — poți alege din lista firmei sau adăuga o mașină nouă.")
        opt_masini = [OPT_MASINA] + sorted(masini_firma_map.keys(), key=str.lower) + [OPT_ALTA_MASINA]

    cur_mas = st.session_state.get("op_sel_masina", OPT_MASINA)
    if cur_mas not in opt_masini and cur_mas in masini_firma_map:
        opt_masini.insert(1, cur_mas)
    idx_mas = opt_masini.index(cur_mas) if cur_mas in opt_masini else 0

    sel_masina = st.selectbox("2. Denumire mașină", options=opt_masini, index=idx_mas, key="op_sel_masina")
    if sel_masina == OPT_MASINA:
        st.info("Selectează mașina pe care lucrezi sau scanează codul QR.")
        return

    este_in_afara_listei = False
    masina_obj: dict | None = None
    denumire_masina_finala = ""
    subansambluri_opt = ["General"]
    erori_cunoscute: list[str] = []

    if sel_masina == OPT_ALTA_MASINA:
        este_in_afara_listei = True
        st.warning(
            "⚠️ Mașina nu este în lista alocată operatorului. La salvare se va crea automat un task "
            "pentru **a lua legătura cu superiorii firmei** și **a întocmi ofertă de preț pentru intervenție la mașina nouă**."
        )
        c_ext1, c_ext2 = st.columns(2)
        with c_ext1:
            masina_din_firma_alta = st.selectbox(
                "Alege o mașină existentă din firmă (dacă există)",
                options=["-- Nu e în lista firmei (scriu denumire nouă) --"] + sorted(masini_firma_map.keys(), key=str.lower),
                key="op_alta_masina_din_firma",
            )
        with c_ext2:
            denumire_masina_noua = st.text_input(
                "Denumire mașină nouă *",
                placeholder="ex: Presă hidraulică #4 / CNC nou...",
                key="op_alta_masina_denumire_noua",
            )

        if masina_din_firma_alta != "-- Nu e în lista firmei (scriu denumire nouă) --":
            masina_obj = masini_firma_map[masina_din_firma_alta]
            denumire_masina_finala = masina_din_firma_alta
        else:
            denumire_masina_finala = str(denumire_masina_noua or "").strip()
    else:
        masina_obj = masini_firma_map.get(sel_masina)
        denumire_masina_finala = sel_masina
        if lista_alocata_firma and sel_masina not in lista_alocata_firma:
            este_in_afara_listei = True

    if masina_obj:
        if masina_obj.get("subansambluri"):
            extras = [s.strip() for s in str(masina_obj["subansambluri"]).split(",") if s.strip()]
            subansambluri_opt = list(dict.fromkeys(["General"] + extras))
        if masina_obj.get("erori"):
            erori_cunoscute = [e.strip() for e in str(masina_obj["erori"]).split(",") if e.strip()]

        stare_curenta_op = str(masina_obj.get("stare_operare") or "Funcțională")
        if stare_curenta_op == "Defectă":
            st.error(
                f"🚨 Mașina **{denumire_masina_finala}** este deja marcată **Defectă**."
                + (f" Ultimul defect: {masina_obj.get('ultim_defect_raportat')}" if masina_obj.get("ultim_defect_raportat") else "")
            )
        else:
            st.success(f"✅ Stare curentă **{denumire_masina_finala}**: **{stare_curenta_op}**")

    # --- 4. FORMULAR RAPORTARE DEFECT / EROARE ---
    with st.form("form_operator_raporteaza_defect", clear_on_submit=True):
        marcheaza_defecta = st.checkbox("🚨 Setează mașina ca DEFECTĂ", value=True)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            subansamblu = st.selectbox("Subansamblu", options=subansambluri_opt)
        with col_s2:
            if erori_cunoscute:
                cod_preset = st.selectbox("Cod eroare cunoscut (opțional)", options=[""] + erori_cunoscute)
                cod_manual = st.text_input("Sau cod eroare / alarmă", placeholder="ex: ALM 414, E-12, F30002")
                cod_eroare_final = (cod_manual or cod_preset).strip()
            else:
                cod_eroare_final = st.text_input("Cod eroare / alarmă (opțional)", placeholder="ex: ALM 414, E-12, F30002").strip()

        simptom = st.text_input(
            "Simptom observat (opțional)",
            placeholder="ex: se oprește brusc, zgomot anormal, lipsă presiune...",
        )
        defect_descriere = st.text_area(
            "Defectul sau eroarea apărută *",
            height=120,
            placeholder="Descrie defectul sau eroarea...",
        )
        trimite_si_in_istoric = st.checkbox(
            "Trimite și în lista de intervenții / defecte",
            value=True,
        )

        submitted = st.form_submit_button("🚨 Salvează Raportul de Defect", type="primary", use_container_width=True)

        if submitted:
            nume_final = (nume_op or cont.nume).strip() or "Operator Mașină"
            tel_final = (tel_op or cont.telefon).strip()
            defect_clean = str(defect_descriere or "").strip()

            if not nume_final:
                st.error("⚠️ Completează numele operatorului.")
            elif not denumire_masina_finala:
                st.error("⚠️ Completează sau selectează denumirea mașinii.")
            elif not defect_clean and not cod_eroare_final:
                st.error("⚠️ Scrie defectul sau eroarea.")
            else:
                activeaza_mod_operator(
                    nume_operator=nume_final,
                    telefon=tel_final,
                    firma=sel_firma,
                )
                mesaje_ok: list[str] = []
                mesaje_err: list[str] = []

                if marcheaza_defecta and masina_obj is not None:
                    ok_m, msg_m = _marcheaza_masina_defecta(
                        masina_obj=masina_obj,
                        defect_text=defect_clean,
                        cod_eroare=cod_eroare_final,
                        operator_nume=nume_final,
                        operator_tel=tel_final,
                    )
                    (mesaje_ok if ok_m else mesaje_err).append(msg_m)

                if trimite_si_in_istoric:
                    ok_i, msg_i = _salveaza_sesizare_reparatii(
                        firma_nume=sel_firma,
                        masina_denumire=denumire_masina_finala,
                        subansamblu=subansamblu,
                        simptom=str(simptom or "").strip(),
                        defect=defect_clean or f"Eroare {cod_eroare_final}",
                        cod_eroare=cod_eroare_final,
                        operator_nume=nume_final,
                        operator_tel=tel_final,
                    )
                    (mesaje_ok if ok_i else mesaje_err).append(msg_i)

                if este_in_afara_listei:
                    ok_t, msg_t = _creeaza_task_masina_in_afara_listei(
                        firma_nume=sel_firma,
                        firma_id=firma_id,
                        masina_denumire=denumire_masina_finala,
                        defect_text=defect_clean,
                        cod_eroare=cod_eroare_final,
                        operator_nume=nume_final,
                        operator_tel=tel_final,
                    )
                    (mesaje_ok if ok_t else mesaje_err).append(msg_t)

                if any([marcheaza_defecta and masina_obj is not None, trimite_si_in_istoric, este_in_afara_listei]):
                    _goleste_cache_operator()

                for m_err in mesaje_err:
                    st.error(f"❌ {m_err}")
                for m_ok in mesaje_ok:
                    st.success(f"✅ {m_ok}")