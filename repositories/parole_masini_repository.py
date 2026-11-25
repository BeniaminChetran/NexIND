

# -------------------------------------------------------------
# -------repositories/parole_masini_repository.py--------------
# -------------------------------------------------------------

from config import db_cursor


class ParoleMasiniRepository:
    @staticmethod
    def get_by_masina(masina_id: int) -> list[dict]:
        with db_cursor() as c:
            c.execute(
                """
                SELECT
                    pm.id,
                    pm.firma_id,
                    f.nume_firma,
                    pm.masina_id,
                    m.denumire AS denumire_masina,
                    pm.parola,
                    pm.unde_se_aplica,
                    pm.observatii,
                    pm.creat_la
                FROM parole_masini pm
                JOIN firme f ON f.id = pm.firma_id
                JOIN masini m ON m.id = pm.masina_id
                WHERE pm.masina_id = %s
                ORDER BY pm.unde_se_aplica ASC, pm.id DESC
                """,
                (masina_id,),
            )
            rows = c.fetchall()
            return [dict(r) for r in rows] if rows else []

    @staticmethod
    def insert(
        firma_id: int,
        masina_id: int,
        parola: str,
        unde_se_aplica: str,
        observatii: str | None = None,
    ) -> int:
        with db_cursor() as c:
            c.execute(
                """
                INSERT INTO parole_masini (firma_id, masina_id, parola, unde_se_aplica, observatii)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    firma_id,
                    masina_id,
                    parola.strip(),
                    unde_se_aplica.strip(),
                    (observatii or "").strip() or None,
                ),
            )
            row = c.fetchone()
            return int(row["id"]) if row else 0

    @staticmethod
    def update(
        parola_id: int,
        parola: str,
        unde_se_aplica: str,
        observatii: str | None = None,
    ) -> None:
        with db_cursor() as c:
            c.execute(
                """
                UPDATE parole_masini
                SET parola = %s,
                    unde_se_aplica = %s,
                    observatii = %s
                WHERE id = %s
                """,
                (
                    parola.strip(),
                    unde_se_aplica.strip(),
                    (observatii or "").strip() or None,
                    int(parola_id),
                ),
            )

    @staticmethod
    def delete(parola_id: int) -> None:
        with db_cursor() as c:
            c.execute("DELETE FROM parole_masini WHERE id = %s", (int(parola_id),))
            