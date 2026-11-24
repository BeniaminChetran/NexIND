import logging
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.SetariRepository")

DEFAULT_CLAUZE_SUBSOL = (
    "Oferta de preț este exprimată în {MONEDA}, nu conține piese de schimb și este valabilă 15 zile.\n"
    "Costul pieselor de schimb se va transmite după constatare/diagnosticare.\n"
    "În funcție de complexitatea lucrărilor, durata intervenției poate suferi modificări. Acestea vă vor fi comunicate la fața locului."
)

DEFAULTS_SETARI = {
    "nume_firma_mea": "SC Nexus Industrial SRL",
    "cui_mea": "",
    "reg_com_mea": "",
    "adresa_mea": "",
    "banca_mea": "",
    "iban_mea": "",
    "swep_mea": "",
    "telefon_1": "",
    "telefon_2": "",
    "email_1": "",
    "email_2": "",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "google_sheet_url": "",
    "locatie_documentatii_gdrive": "",
    "email_tehnician": "",
    "cota_tva": 21.0,
    "pass": "",
    "valabilitate_implicita": "15 zile",
    "termeni_plata_impliciti": "5 zile de la emiterea facturii",
    "intocmit_de_implicit": "Echipa Nexus Industrial",
    "tehnician_implicit": "Tehnician Nexus",
    "clauze_subsol_implicite": DEFAULT_CLAUZE_SUBSOL,
    "adaos_comercial_implicit": 35.0,
}


@st.cache_resource
def _ensure_setari_schema_once() -> bool:
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                ALTER TABLE setari
                ADD COLUMN IF NOT EXISTS telefon_1 VARCHAR(50) DEFAULT '',
                ADD COLUMN IF NOT EXISTS telefon_2 VARCHAR(50) DEFAULT '',
                ADD COLUMN IF NOT EXISTS email_1 VARCHAR(150) DEFAULT '',
                ADD COLUMN IF NOT EXISTS email_2 VARCHAR(150) DEFAULT '',
                ADD COLUMN IF NOT EXISTS locatie_documentatii_gdrive TEXT DEFAULT ''
                """
            )
        return True
    except Exception as exc:
        logger.warning(f"Verificarea coloanelor pe 'setari' a întâmpinat o eroare: {exc}")
        return False


def _goleste_cache_setari() -> None:
    fn = getattr(SetariRepository.get_setari, "clear", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


class SetariRepository(BaseRepository):
    @classmethod
    @st.cache_data(ttl=300)
    def get_setari(cls_or_self=None) -> dict:
        cls = cls_or_self if isinstance(cls_or_self, type) else SetariRepository
        _ensure_setari_schema_once()
        res = cls().fetch_one("SELECT * FROM setari LIMIT 1") or {}
        merged = dict(DEFAULTS_SETARI)
        for key, default_val in DEFAULTS_SETARI.items():
            val = res.get(key)
            if val is not None and str(val).strip() != "":
                merged[key] = val
        for extra_key, extra_val in res.items():
            if extra_key not in merged:
                merged[extra_key] = extra_val
        return merged

    @classmethod
    def save_setari(cls, data: dict) -> None:
        _ensure_setari_schema_once()
        existing = cls.get_setari()
        merged = {**existing, **(data or {})}

        for contact_key in ("telefon_1", "telefon_2", "email_1", "email_2", "locatie_documentatii_gdrive"):
            merged[contact_key] = str(merged.get(contact_key) or "").strip()

        if merged.get("clauze_subsol_implicite") is None:
            merged["clauze_subsol_implicite"] = DEFAULT_CLAUZE_SUBSOL

        adaos_val = merged.get("adaos_comercial_implicit")
        merged["adaos_comercial_implicit"] = float(35.0 if adaos_val is None else adaos_val)
        merged["cota_tva"] = float(21.0 if merged.get("cota_tva") is None else merged.get("cota_tva"))
        merged["smtp_port"] = int(merged.get("smtp_port") or 587)

        params = (
            merged.get("nume_firma_mea"),
            merged.get("cui_mea"),
            merged.get("reg_com_mea"),
            merged.get("adresa_mea"),
            merged.get("banca_mea"),
            merged.get("iban_mea"),
            merged.get("swep_mea"),
            merged.get("telefon_1"),
            merged.get("telefon_2"),
            merged.get("email_1"),
            merged.get("email_2"),
            merged.get("smtp_server"),
            merged.get("smtp_port"),
            merged.get("smtp_user"),
            merged.get("smtp_pass"),
            merged.get("google_sheet_url"),
            merged.get("locatie_documentatii_gdrive"),
            merged.get("email_tehnician"),
            merged.get("cota_tva"),
            merged.get("pass"),
            merged.get("valabilitate_implicita"),
            merged.get("termeni_plata_impliciti"),
            merged.get("intocmit_de_implicit"),
            merged.get("tehnician_implicit"),
            merged.get("clauze_subsol_implicite"),
            merged.get("adaos_comercial_implicit"),
        )

        with db_cursor() as cur:
            cur.execute("DELETE FROM setari")
            cur.execute(
                """
                INSERT INTO setari (
                    nume_firma_mea, cui_mea, reg_com_mea, adresa_mea, banca_mea,
                    iban_mea, swep_mea, telefon_1, telefon_2, email_1, email_2,
                    smtp_server, smtp_port, smtp_user, smtp_pass, google_sheet_url,
                    locatie_documentatii_gdrive, email_tehnician, cota_tva, pass,
                    valabilitate_implicita, termeni_plata_impliciti,
                    intocmit_de_implicit, tehnician_implicit, clauze_subsol_implicite,
                    adaos_comercial_implicit
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )
        _goleste_cache_setari()
        logger.info("Setările au fost salvate în baza de date.")

    @classmethod
    def update_pass(cls, noua_parola: str) -> None:
        _ensure_setari_schema_once()
        with db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM setari")
            row = cur.fetchone()
            if not row or int(row.get("cnt", 0)) == 0:
                cur.execute("INSERT INTO setari (pass) VALUES (%s)", (noua_parola,))
            else:
                cur.execute("UPDATE setari SET pass = %s", (noua_parola,))
        _goleste_cache_setari()
        logger.info("Parola a fost actualizată în setări.")