import json
from config import db_cursor
from repositories.base_repository import BaseRepository


class ReparatiiElectroniceRepository(BaseRepository):
    @classmethod
    def get_all(cls):
        with db_cursor() as c:
            c.execute("SELECT * FROM reparatii_electronice ORDER BY id DESC")
            return c.fetchall() or []

    @classmethod
    def insert(cls, data: dict):
        query = """
            INSERT INTO reparatii_electronice (
                firma_id, masina_id, firma_nume, masina_nume,
                piesa_subansamblu, defect_reclamat, componente_json,
                stare_finala, tehnician, verificator, data_creare
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        """
        params = (
            data.get("firma_id"),
            data.get("masina_id"),
            data.get("firma_nume"),
            data.get("masina_nume"),
            data.get("piesa_subansamblu"),
            data.get("defect_reclamat"),
            json.dumps(data.get("componente_json") or [], ensure_ascii=False),
            data.get("stare_finala"),
            data.get("tehnician"),
            data.get("verificator"),
        )
        with db_cursor() as c:
            c.execute(query, params)
            res = c.fetchone()
        return res["id"] if res else None

    @classmethod
    def update(cls, record_id: int, data: dict) -> bool:
        query = """
            UPDATE reparatii_electronice
            SET piesa_subansamblu = %s,
                defect_reclamat = %s,
                componente_json = %s,
                stare_finala = %s,
                tehnician = %s,
                verificator = %s
            WHERE id = %s
        """
        params = (
            data.get("piesa_subansamblu"),
            data.get("defect_reclamat"),
            json.dumps(data.get("componente_json") or [], ensure_ascii=False),
            data.get("stare_finala"),
            data.get("tehnician"),
            data.get("verificator"),
            int(record_id),
        )
        with db_cursor() as c:
            c.execute(query, params)
            return (c.rowcount or 0) > 0

    @classmethod
    def delete(cls, record_id: int) -> bool:
        with db_cursor() as c:
            c.execute("DELETE FROM reparatii_electronice WHERE id = %s", (int(record_id),))
            return (c.rowcount or 0) > 0


def sincronizeaza_componente_in_piese_generale(
    componente_lista: list[dict],
    sursa_info: str = "",
    masina_tinta: str = "General",
) -> int:
    """
    Comasează componentele din reparațiile electronice în tabelul `piese`
    o singură dată per mașină (`masina_montaj`), permițând aceeași piesă pe mașini diferite.
    Returnează numărul de piese procesate.
    """
    if not componente_lista:
        return 0

    masina_curata = str(masina_tinta or "").strip()
    if not masina_curata or masina_curata == "General / Fără mașină":
        masina_curata = "General"

    procesate = 0
    vazute_in_lot = set()

    with db_cursor() as c:
        c.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'piese'
        """)
        cols_piese = {row["column_name"] for row in (c.fetchall() or [])}
        if not cols_piese:
            return 0

        col_den = "denumire" if "denumire" in cols_piese else ("nume" if "nume" in cols_piese else None)
        if not col_den:
            return 0

        col_cant = (
            "cantitate" if "cantitate" in cols_piese
            else ("stoc" if "stoc" in cols_piese else ("cantitate_stoc" if "cantitate_stoc" in cols_piese else None))
        )
        are_masina_montaj = "masina_montaj" in cols_piese

        for item in componente_lista:
            if not isinstance(item, dict):
                continue
            den_raw = str(item.get("Componenta / Cod / Parametri") or "").strip()
            den = " ".join(den_raw.split())
            if not den:
                continue

            cheie_lot = (masina_curata.lower(), den.lower())
            if cheie_lot in vazute_in_lot:
                continue
            vazute_in_lot.add(cheie_lot)

            try:
                cant_val = float(item.get("Cantitate") if item.get("Cantitate") is not None else 1.0)
                if cant_val <= 0:
                    cant_val = 1.0
            except (TypeError, ValueError):
                cant_val = 1.0

            if are_masina_montaj:
                c.execute(
                    f"""
                    SELECT id{', ' + col_cant if col_cant else ''}
                    FROM piese
                    WHERE LOWER(TRIM({col_den})) = LOWER(TRIM(%s))
                      AND LOWER(TRIM(COALESCE(masina_montaj, 'General'))) = LOWER(TRIM(%s))
                    LIMIT 1
                    """,
                    (den, masina_curata),
                )
            else:
                c.execute(
                    f"SELECT id{', ' + col_cant if col_cant else ''} FROM piese WHERE LOWER(TRIM({col_den})) = LOWER(TRIM(%s)) LIMIT 1",
                    (den,),
                )

            existent = c.fetchone()

            if existent:
                procesate += 1
            else:
                campuri = [col_den]
                valori = [den]

                if are_masina_montaj:
                    campuri.append("masina_montaj")
                    valori.append(masina_curata)

                if col_cant:
                    campuri.append(col_cant)
                    valori.append(cant_val)

                if "stare" in cols_piese:
                    campuri.append("stare")
                    valori.append(str(item.get("Stare") or "Necesara"))

                if "observatii" in cols_piese and sursa_info:
                    campuri.append("observatii")
                    valori.append(sursa_info)
                elif "descriere" in cols_piese and sursa_info:
                    campuri.append("descriere")
                    valori.append(sursa_info)

                placeholders = ", ".join(["%s"] * len(campuri))
                c.execute(
                    f"INSERT INTO piese ({', '.join(campuri)}) VALUES ({placeholders})",
                    tuple(valori),
                )
                procesate += 1

    return procesate