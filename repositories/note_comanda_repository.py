# ------------------------------------------
# -repositories/note_comanda_repository.py-
# ------------------------------------------

import datetime
import json
import logging
from config import db_cursor
from repositories.base_repository import BaseRepository

logger = logging.getLogger("NexIndCMMS.NoteComandaRepository")

OPTIUNI_STARE_NOTA_COMANDA = [
    "Necomandat",
    "Comandat",
    "În așteptare",
    "Vine",
    "Livrat",
    "Anulat",
]


def normalizeaza_stare_nota_comanda(val) -> str:
    s = str(val or "").strip()
    if s in OPTIUNI_STARE_NOTA_COMANDA:
        return s
    low = s.lower()
    mapa = {
        "necomandat": "Necomandat",
        "comandat": "Comandat",
        "in asteptare": "În așteptare",
        "în așteptare": "În așteptare",
        "vine": "Vine",
        "pe drum": "Vine",
        "livrat": "Livrat",
        "anulat": "Anulat",
    }
    return mapa.get(low, "Necomandat")


class NoteComandaRepository(BaseRepository):
    _tabel_verificat = False

    @classmethod
    def ensure_tables(cls) -> None:
        if cls._tabel_verificat:
            return
        with db_cursor() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS note_comanda_furnizori (
                    id SERIAL PRIMARY KEY,
                    numar_nota VARCHAR(64) NOT NULL,
                    data_emitere DATE NOT NULL DEFAULT CURRENT_DATE,
                    furnizor_nume VARCHAR(255) NOT NULL,
                    client_nume VARCHAR(255),
                    oferta_id INTEGER,
                    numar_oferta VARCHAR(64),
                    cerere_oferta_id INTEGER,
                    moneda VARCHAR(10) NOT NULL DEFAULT 'EUR',
                    total_nota NUMERIC(12, 2) NOT NULL DEFAULT 0,
                    stare_generala VARCHAR(50) NOT NULL DEFAULT 'Necomandat',
                    observatii TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS note_comanda_furnizori_linii (
                    id SERIAL PRIMARY KEY,
                    nota_id INTEGER NOT NULL REFERENCES note_comanda_furnizori(id) ON DELETE CASCADE,
                    furnizor_nume VARCHAR(255) NOT NULL,
                    piesa_denumire VARCHAR(500) NOT NULL,
                    cod_piesa VARCHAR(120) DEFAULT '',
                    cantitate NUMERIC(12, 2) NOT NULL DEFAULT 1,
                    pret NUMERIC(12, 2) NOT NULL DEFAULT 0,
                    moneda VARCHAR(10) NOT NULL DEFAULT 'EUR',
                    termen_livrare VARCHAR(120) DEFAULT '',
                    stare_comanda VARCHAR(50) NOT NULL DEFAULT 'Necomandat',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        cls._tabel_verificat = True

    @classmethod
    def get_next_numar_nota(cls) -> str:
        cls.ensure_tables()
        row = cls().fetch_one("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM note_comanda_furnizori")
        nxt = int(row["next_id"]) if row and row.get("next_id") is not None else 1
        return f"NC-{datetime.date.today().year}-{nxt:04d}"

    @classmethod
    def _recalculeaza_stare_si_total_nota(cls, nota_id: int) -> None:
        cls.ensure_tables()
        with db_cursor() as c:
            c.execute(
                """
                SELECT cantitate, pret, stare_comanda
                FROM note_comanda_furnizori_linii
                WHERE nota_id = %s
                """,
                (int(nota_id),),
            )
            linii = [dict(r) for r in (c.fetchall() or [])]
            if not linii:
                return

            total = round(
                sum(float(l.get("cantitate") or 0.0) * float(l.get("pret") or 0.0) for l in linii),
                2,
            )
            stari = [normalizeaza_stare_nota_comanda(l.get("stare_comanda")) for l in linii]
            stari_active = [s for s in stari if s != "Anulat"]

            if not stari_active:
                stare_gen = "Anulat"
            elif all(s == "Livrat" for s in stari_active):
                stare_gen = "Livrat"
            elif all(s == "Necomandat" for s in stari_active):
                stare_gen = "Necomandat"
            elif any(s == "Vine" for s in stari_active):
                stare_gen = "Vine"
            elif any(s == "Comandat" for s in stari_active):
                stare_gen = "Comandat"
            elif any(s == "În așteptare" for s in stari_active):
                stare_gen = "În așteptare"
            else:
                stare_gen = stari_active[0]

            c.execute(
                """
                UPDATE note_comanda_furnizori
                SET total_nota = %s,
                    stare_generala = %s
                WHERE id = %s
                """,
                (total, stare_gen, int(nota_id)),
            )

    @classmethod
    def genereaza_din_oferta(
        cls,
        *,
        oferta_id: int | str | None,
        numar_oferta: str,
        data_emitere: datetime.date,
        client_nume: str,
        linii_furnizor: list[dict],
        cerere_oferta_id: int | None = None,
        observatii: str = "",
    ) -> list[dict]:
        """
        Creează câte o notă de comandă per furnizor pentru reperele ofertate.
        Fiecare linie conține: furnizor_nume, piesa_denumire, cod_piesa, cantitate, pret, moneda, stare_comanda.
        """
        cls.ensure_tables()
        if not linii_furnizor:
            return []

        grupate: dict[str, list[dict]] = {}
        for ln in linii_furnizor:
            den = str(ln.get("piesa_denumire") or "").strip()
            if not den:
                continue
            furn = str(ln.get("furnizor_nume") or "").strip() or "Furnizor nespecificat"
            grupate.setdefault(furn, []).append(ln)

        note_create: list[dict] = []
        oid_int = None
        try:
            if oferta_id is not None and str(oferta_id).strip().isdigit():
                oid_int = int(oferta_id)
        except Exception:
            oid_int = None

        with db_cursor() as c:
            for furn_nume, items in grupate.items():
                numar_nota = cls.get_next_numar_nota()
                moneda_nota = str(items[0].get("moneda") or "EUR").strip().upper()
                if moneda_nota not in ("EUR", "RON"):
                    moneda_nota = "EUR"

                total_nota = round(
                    sum(float(it.get("cantitate") or 1.0) * float(it.get("pret") or 0.0) for it in items),
                    2,
                )

                c.execute(
                    """
                    INSERT INTO note_comanda_furnizori (
                        numar_nota, data_emitere, furnizor_nume, client_nume,
                        oferta_id, numar_oferta, cerere_oferta_id,
                        moneda, total_nota, stare_generala, observatii
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, numar_nota
                    """,
                    (
                        numar_nota,
                        data_emitere or datetime.date.today(),
                        furn_nume,
                        str(client_nume or "").strip(),
                        oid_int,
                        str(numar_oferta or "").strip(),
                        cerere_oferta_id,
                        moneda_nota,
                        total_nota,
                        "Necomandat",
                        str(observatii or "").strip(),
                    ),
                )
                hdr = c.fetchone() or {}
                nota_id = int(hdr["id"])
                nr_gen = str(hdr.get("numar_nota") or numar_nota)

                for it in items:
                    st_init = normalizeaza_stare_nota_comanda(it.get("stare_comanda") or "Necomandat")
                    mon_l = str(it.get("moneda") or moneda_nota).strip().upper()
                    if mon_l not in ("EUR", "RON"):
                        mon_l = moneda_nota

                    c.execute(
                        """
                        INSERT INTO note_comanda_furnizori_linii (
                            nota_id, furnizor_nume, piesa_denumire, cod_piesa,
                            cantitate, pret, moneda, termen_livrare, stare_comanda
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            nota_id,
                            furn_nume,
                            str(it.get("piesa_denumire") or "").strip(),
                            str(it.get("cod_piesa") or "").strip(),
                            float(it.get("cantitate") or 1.0),
                            float(it.get("pret") or 0.0),
                            mon_l,
                            str(it.get("termen_livrare") or "").strip(),
                            st_init,
                        ),
                    )

                note_create.append({
                    "id": nota_id,
                    "numar_nota": nr_gen,
                    "furnizor_nume": furn_nume,
                    "nr_linii": len(items),
                    "total_nota": total_nota,
                    "moneda": moneda_nota,
                })

        logger.info("Generate %s note de comandă pentru oferta #%s", len(note_create), numar_oferta)
        return note_create

    @classmethod
    def get_all_cu_linii(cls) -> list[dict]:
        cls.ensure_tables()
        note_rows = cls().fetch_all("SELECT * FROM note_comanda_furnizori ORDER BY id DESC") or []
        linii_rows = cls().fetch_all("SELECT * FROM note_comanda_furnizori_linii ORDER BY id ASC") or []

        linii_by_nota: dict[int, list[dict]] = {}
        for ln in linii_rows:
            nid = int(ln["nota_id"])
            item = dict(ln)
            item["stare_comanda"] = normalizeaza_stare_nota_comanda(item.get("stare_comanda"))
            linii_by_nota.setdefault(nid, []).append(item)

        rezultat: list[dict] = []
        for n in note_rows:
            item_n = dict(n)
            nid = int(item_n["id"])
            item_n["stare_generala"] = normalizeaza_stare_nota_comanda(item_n.get("stare_generala"))
            item_n["linii"] = linii_by_nota.get(nid, [])
            rezultat.append(item_n)
        return rezultat

    @classmethod
    def update_linie_stare(cls, linie_id: int, stare_comanda: str) -> None:
        cls.ensure_tables()
        st_norm = normalizeaza_stare_nota_comanda(stare_comanda)
        with db_cursor() as c:
            c.execute(
                """
                UPDATE note_comanda_furnizori_linii
                SET stare_comanda = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING nota_id
                """,
                (st_norm, int(linie_id)),
            )
            r = c.fetchone() or {}
            nota_id = r.get("nota_id")
        if nota_id is not None:
            cls._recalculeaza_stare_si_total_nota(int(nota_id))

    @classmethod
    def update_nota_stare_generala(cls, nota_id: int, stare_noua: str) -> None:
        cls.ensure_tables()
        st_norm = normalizeaza_stare_nota_comanda(stare_noua)
        with db_cursor() as c:
            c.execute(
                """
                UPDATE note_comanda_furnizori_linii
                SET stare_comanda = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE nota_id = %s
                """,
                (st_norm, int(nota_id)),
            )
            c.execute(
                """
                UPDATE note_comanda_furnizori
                SET stare_generala = %s
                WHERE id = %s
                """,
                (st_norm, int(nota_id)),
            )

    @classmethod
    def delete_nota(cls, nota_id: int) -> None:
        cls.ensure_tables()
        with db_cursor() as c:
            c.execute("DELETE FROM note_comanda_furnizori WHERE id = %s", (int(nota_id),))