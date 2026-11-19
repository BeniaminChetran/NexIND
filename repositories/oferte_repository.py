#-----------------------------------
#-----oferte_repository.py----------
#-----------------------------------

import json
import logging
from repositories.base_repository import BaseRepository
from config import db_cursor

logger = logging.getLogger("NexIndCMMS.OferteRepository")

class OferteRepository(BaseRepository):
    @classmethod
    def get_all(cls):
        query = "SELECT * FROM oferte ORDER BY id DESC"
        return cls().fetch_all(query)

    @classmethod
    def get_next_numar_oferta(cls) -> str:
        """Returnează următorul număr de ordine din tabelul oferte."""
        query = "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM oferte"
        res = cls().fetch_one(query)
        next_id = int(res["next_id"]) if res and res.get("next_id") is not None else 1
        return str(next_id)

    @classmethod
    def insert(cls, data: dict):
        articole_str = json.dumps(data.get("articole", []), ensure_ascii=False)
        with db_cursor() as c:
            c.execute("""
                INSERT INTO oferte (
                    numar_oferta, data_emitere, firma, titlu, valabilitate,
                    termeni_plata, observatii, moneda, curs_valutar,
                    articole_json, total_general, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get("numar_oferta"),
                data.get("data"),
                data.get("client"),
                data.get("titlu", ""),
                data.get("valabilitate", ""),
                data.get("termeni_plata", ""),
                data.get("observatii", ""),
                data.get("moneda", "EUR"),
                float(data.get("curs_valutar") or 1.0),
                articole_str,
                float(data.get("total_general") or 0.0),
                data.get("status", "Emisă")
            ))
            row = c.fetchone()
            inserted_id = row["id"] if row else data.get("numar_oferta")
            # Dacă numărul ofertei nu a fost setat manual, îl sincronizăm exact cu id-ul generat
            if not str(data.get("numar_oferta", "")).strip():
                c.execute("UPDATE oferte SET numar_oferta = %s WHERE id = %s", (str(inserted_id), inserted_id))
        logger.info(f"Ofertă inserată cu ID/Nr: {inserted_id}")
        return str(inserted_id)

    @classmethod
    def update_oferta_revizuita(cls, oferta_id: int, articole: list, total_general: float, observatii: str):
        articole_str = json.dumps(articole, ensure_ascii=False)
        with db_cursor() as c:
            c.execute("""
                UPDATE oferte
                SET articole_json = %s,
                    total_general = %s,
                    observatii = %s,
                    status = 'Revizuită'
                WHERE id = %s
            """, (articole_str, float(total_general), observatii, oferta_id))
        logger.info(f"Ofertă #{oferta_id} actualizată ca Revizuită.")

    @classmethod
    def update_status(cls, oferta_id: int, status: str):
        with db_cursor() as c:
            c.execute("UPDATE oferte SET status = %s WHERE id = %s", (status, oferta_id))

    @classmethod
    def delete(cls, oferta_id: int):
        with db_cursor() as c:
            c.execute("DELETE FROM oferte WHERE id = %s", (oferta_id,))