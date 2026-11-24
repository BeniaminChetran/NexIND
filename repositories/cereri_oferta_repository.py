# -----------------------------------------------------
# --- repositories/cereri_oferta_repository.py --------
# -----------------------------------------------------

import datetime
import logging
from typing import Any, Dict, List, Optional
import streamlit as st
from config import db_cursor
from repositories.base_repository import BaseRepository[cite: 7]
from repositories.taskuri_vizita_repository import TaskuriVizitaRepository[cite: 7]

logger = logging.getLogger("NexIndCMMS.CereriOfertaRepository")[cite: 7]

OPTIUNI_STATUS_CERERE_OFERTA = [
    "Trimis - aștept",
    "Primită - de făcut către client",
    "Ofertat la client",
    "Închisă",
][cite: 7]


def normalizeaza_status_cerere_oferta(val: Any) -> str:
    s = str(val or "").strip().lower()[cite: 7]
    if "primit" in s or "de facut" in s or "de făcut" in s:
        return "Primită - de făcut către client"[cite: 7]
    if "ofertat" in s:
        return "Ofertat la client"[cite: 7]
    if "inchis" in s or "închis" in s or "anulat" in s:
        return "Închisă"[cite: 7]
    return "Trimis - aștept"[cite: 7]


@st.cache_resource
def _asigura_tabele_cereri_once() -> bool:
    ddl_si_indexuri = """
        CREATE TABLE IF NOT EXISTS cereri_oferta_furnizori (
            id SERIAL PRIMARY KEY,
            cod_cerere VARCHAR(60) NOT NULL,
            firma_id INTEGER NULL,
            firma_nume VARCHAR(255) NOT NULL,
            masina_id INTEGER NULL,
            masina_nume VARCHAR(255) DEFAULT '',
            status_cerere VARCHAR(80) NOT NULL DEFAULT 'Trimis - aștept',
            data_trimitere DATE NOT NULL DEFAULT CURRENT_DATE,
            termen_raspuns DATE NULL,
            observatii TEXT DEFAULT '',
            oferta_client_id INTEGER NULL,
            task_creat BOOLEAN NOT NULL DEFAULT FALSE,
            data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS oferte_furnizori_linii (
            id SERIAL PRIMARY KEY,
            cerere_id INTEGER NOT NULL REFERENCES cereri_oferta_furnizori(id) ON DELETE CASCADE,
            furnizor_nume VARCHAR(255) NOT NULL,
            piesa_id INTEGER NULL,
            denumire_piesa VARCHAR(255) NOT NULL,
            cod_producator VARCHAR(120) DEFAULT '',
            piese_inlocuitoare TEXT DEFAULT '',
            cantitate NUMERIC(12, 2) NOT NULL DEFAULT 1.00,
            pret_unitar NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            moneda VARCHAR(10) NOT NULL DEFAULT 'EUR',
            termen_livrare_zile VARCHAR(60) DEFAULT '',
            selectat_pentru_client BOOLEAN NOT NULL DEFAULT FALSE,
            data_creare TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE cereri_oferta_furnizori ADD COLUMN IF NOT EXISTS masina_id INTEGER NULL;
        ALTER TABLE cereri_oferta_furnizori ADD COLUMN IF NOT EXISTS masina_nume VARCHAR(255) DEFAULT '';
        ALTER TABLE cereri_oferta_furnizori ADD COLUMN IF NOT EXISTS oferta_client_id INTEGER NULL;
        ALTER TABLE cereri_oferta_furnizori ADD COLUMN IF NOT EXISTS task_creat BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE oferte_furnizori_linii ADD COLUMN IF NOT EXISTS piese_inlocuitoare TEXT DEFAULT '';
        ALTER TABLE oferte_furnizori_linii ADD COLUMN IF NOT EXISTS selectat_pentru_client BOOLEAN NOT NULL DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS idx_cereri_oferta_status ON cereri_oferta_furnizori (status_cerere);
        CREATE INDEX IF NOT EXISTS idx_cereri_oferta_firma ON cereri_oferta_furnizori (firma_id);
        CREATE INDEX IF NOT EXISTS idx_oferte_linii_cerere ON oferte_furnizori_linii (cerere_id);
    """[cite: 7]
    with db_cursor() as cur:
        cur.execute(ddl_si_indexuri)
    return True


class CereriOfertaRepository(BaseRepository):
    @classmethod
    def _asigura_tabele(cls) -> None:
        _asigura_tabele_cereri_once()

    @classmethod
    def creeaza_cerere(
        cls,
        firma_nume: str,
        firma_id: Optional[int] = None,
        masina_nume: str = "",
        masina_id: Optional[int] = None,
        termen_raspuns: Optional[datetime.date] = None,
        observatii: str = "",
        linii_piese: Optional[List[Dict[str, Any]]] = None,
        furnizori_selectati: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cls._asigura_tabele()[cite: 7]

        firma_curata = str(firma_nume or "").strip()[cite: 7]
        if not firma_curata:
            raise ValueError("Clientul / firma este obligatorie.")[cite: 7]

        masina_curata = str(masina_nume or "").strip()[cite: 7]
        if masina_curata.startswith("--"):
            masina_curata = ""[cite: 7]

        cod_cerere = f"RFQ-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"[cite: 7]
        row = cls().execute_returning(
            """
            INSERT INTO cereri_oferta_furnizori (
                cod_cerere, firma_id, firma_nume, masina_id, masina_nume,
                status_cerere, data_trimitere, termen_raspuns, observatii
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, %s, %s)
            RETURNING *
            """,
            (
                cod_cerere,
                int(firma_id) if firma_id is not None else None,
                firma_curata,
                int(masina_id) if masina_id is not None else None,
                masina_curata,
                "Trimis - aștept",
                termen_raspuns,
                str(observatii or "").strip(),
            ),
        )[cite: 7]
        cerere = dict(row) if row else {}[cite: 7]
        cerere_id = cerere.get("id")[cite: 7]

        furnizori_lista = [str(f).strip() for f in (furnizori_selectati or []) if str(f).strip()][cite: 7]
        if not furnizori_lista:
            furnizori_lista = ["Furnizor de stabilit"][cite: 7]

        if cerere_id and linii_piese:
            batch_linii = []
            for furn in furnizori_lista:
                for idx_l, lp in enumerate(linii_piese):
                    den = str(lp.get("denumire_piesa") or "").strip()[cite: 7]
                    if not den:
                        continue[cite: 7]
                    batch_linii.append((
                        int(cerere_id),
                        furn,
                        lp.get("piesa_id"),
                        den,
                        str(lp.get("cod_producator") or "").strip(),
                        str(lp.get("piese_inlocuitoare") or "").strip(),
                        float(lp.get("cantitate") or 1.0),
                        float(lp.get("pret_unitar") or 0.0),
                        str(lp.get("moneda") or "EUR").strip().upper(),
                        str(lp.get("termen_livrare_zile") or "").strip(),
                        idx_l == 0 and furn == furnizori_lista[0],
                    ))[cite: 7]
            if batch_linii:
                cls().executemany(
                    """
                    INSERT INTO oferte_furnizori_linii (
                        cerere_id, furnizor_nume, piesa_id, denumire_piesa,
                        cod_producator, piese_inlocuitoare, cantitate,
                        pret_unitar, moneda, termen_livrare_zile, selectat_pentru_client
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    batch_linii,
                )

        cls.get_cereri.clear()[cite: 7]
        cls.get_linii_by_cerere.clear()[cite: 7]
        return cerere[cite: 7]

    @classmethod
    def salveaza_oferta_primita_furnizor(
        cls,
        cerere_id: int,
        linii_actualizate: List[Dict[str, Any]],
        creeaza_task_daca_lipseste: bool = True,
    ) -> None:
        cls._asigura_tabele()[cite: 7]
        cerere = cls().fetch_one("SELECT * FROM cereri_oferta_furnizori WHERE id = %s", (int(cerere_id),))[cite: 7]
        if not cerere:
            raise ValueError("Cererea de ofertă nu a fost găsită.")[cite: 7]
        cerere = dict(cerere)[cite: 7]

        batch_updates = []
        for l in linii_actualizate or []:
            lid = l.get("id")[cite: 7]
            if lid is not None:
                batch_updates.append((
                    str(l.get("furnizor_nume") or "").strip(),
                    float(l.get("pret_unitar") or 0.0),
                    str(l.get("moneda") or "EUR").strip().upper(),
                    str(l.get("termen_livrare_zile") or "").strip(),
                    str(l.get("piese_inlocuitoare") or "").strip(),
                    bool(l.get("selectat_pentru_client", False)),
                    int(lid),
                    int(cerere_id),
                ))[cite: 7]

        if batch_updates:
            cls().executemany(
                """
                UPDATE oferte_furnizori_linii
                SET furnizor_nume = %s,
                    pret_unitar = %s,
                    moneda = %s,
                    termen_livrare_zile = %s,
                    piese_inlocuitoare = %s,
                    selectat_pentru_client = %s
                WHERE id = %s AND cerere_id = %s
                """,
                batch_updates,
            )

        cls().execute(
            "UPDATE cereri_oferta_furnizori SET status_cerere = %s WHERE id = %s",
            ("Primită - de făcut către client", int(cerere_id)),
        )[cite: 7]

        if creeaza_task_daca_lipseste and not bool(cerere.get("task_creat", False)):
            firma = str(cerere.get("firma_nume") or "").strip()[cite: 7]
            masina = str(cerere.get("masina_nume") or "").strip()[cite: 7]
            cod_c = str(cerere.get("cod_cerere") or f"#{cerere_id}").strip()[cite: 7]
            nota_task = f"De făcut ofertă la client ({firma}) — ofertă furnizor primită pe cererea {cod_c}."[cite: 7]
            if masina:
                nota_task += f" Echipament: {masina}."[cite: 7]

            TaskuriVizitaRepository.insert(
                data_vizita=datetime.date.today(),
                de_facut_pana_la=datetime.date.today() + datetime.timedelta(days=1),
                firma=firma,
                firma_id=cerere.get("firma_id"),
                masina=masina,
                note_vizita=nota_task,
                stare="De ofertat",
            )[cite: 7]
            cls().execute(
                "UPDATE cereri_oferta_furnizori SET task_creat = TRUE WHERE id = %s",
                (int(cerere_id),),
            )[cite: 7]

        cls.get_cereri.clear()[cite: 7]
        cls.get_linii_by_cerere.clear()[cite: 7]

    @classmethod
    def update_status_cerere(cls, cerere_id: int, status_nou: str) -> None:
        cls._asigura_tabele()[cite: 7]
        st_norm = normalizeaza_status_cerere_oferta(status_nou)[cite: 7]
        cls().execute(
            "UPDATE cereri_oferta_furnizori SET status_cerere = %s WHERE id = %s",
            (st_norm, int(cerere_id)),
        )[cite: 7]
        if st_norm == "Primită - de făcut către client":
            cerere = cls().fetch_one("SELECT * FROM cereri_oferta_furnizori WHERE id = %s", (int(cerere_id),))[cite: 7]
            if cerere and not bool(dict(cerere).get("task_creat", False)):
                c_dict = dict(cerere)[cite: 7]
                nota_task = f"De făcut ofertă la client ({c_dict.get('firma_nume')}) — cererea {c_dict.get('cod_cerere')} este primită."[cite: 7]
                if c_dict.get("masina_nume"):
                    nota_task += f" Echipament: {c_dict.get('masina_nume')}."[cite: 7]
                TaskuriVizitaRepository.insert(
                    data_vizita=datetime.date.today(),
                    de_facut_pana_la=datetime.date.today() + datetime.timedelta(days=1),
                    firma=c_dict.get("firma_nume") or "",
                    firma_id=c_dict.get("firma_id"),
                    masina=c_dict.get("masina_nume") or "",
                    note_vizita=nota_task,
                    stare="De ofertat",
                )[cite: 7]
                cls().execute(
                    "UPDATE cereri_oferta_furnizori SET task_creat = TRUE WHERE id = %s",
                    (int(cerere_id),),
                )[cite: 7]

        cls.get_cereri.clear()[cite: 7]

    @classmethod
    def leaga_oferta_client(cls, cerere_id: int, oferta_client_id: int) -> None:
        cls._asigura_tabele()[cite: 7]
        cls().execute(
            """
            UPDATE cereri_oferta_furnizori
            SET oferta_client_id = %s, status_cerere = 'Ofertat la client'
            WHERE id = %s
            """,
            (int(oferta_client_id), int(cerere_id)),
        )[cite: 7]
        cls.get_cereri.clear()[cite: 7]

    @classmethod
    @st.cache_data(ttl=120)
    def get_cereri(cls_or_self=None) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else CereriOfertaRepository[cite: 7]
        cls._asigura_tabele()[cite: 7]
        rows = cls().fetch_all(
            """
            SELECT *
            FROM cereri_oferta_furnizori
            ORDER BY data_trimitere DESC, id DESC
            """
        ) or [][cite: 7]
        return [dict(r) for r in rows][cite: 7]

    @classmethod
    @st.cache_data(ttl=120)
    def get_linii_by_cerere(cls_or_self, cerere_id: int) -> List[Dict[str, Any]]:
        cls = cls_or_self if isinstance(cls_or_self, type) else CereriOfertaRepository[cite: 7]
        cls._asigura_tabele()[cite: 7]
        rows = cls().fetch_all(
            """
            SELECT *
            FROM oferte_furnizori_linii
            WHERE cerere_id = %s
            ORDER BY furnizor_nume ASC, id ASC
            """,
            (int(cerere_id),),
        ) or [][cite: 7]
        return [dict(r) for r in rows][cite: 7]