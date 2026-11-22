#------------------------------------------
#--reparatii_electronice_repository.py-----
#------------------------------------------

import json
from repositories.base_repository import BaseRepository


class ReparatiiElectroniceRepository(BaseRepository):
    @classmethod
    def get_all(cls):
        query = "SELECT * FROM reparatii_electronice ORDER BY id DESC"
        return cls().fetch_all(query) or []

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
        res = cls().execute_returning(query, params)
        return res["id"] if res else None

    @classmethod
    def update(cls, record_id: int, data: dict):
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
        return cls().execute(query, params)

    @classmethod
    def delete(cls, record_id: int):
        query = "DELETE FROM reparatii_electronice WHERE id = %s"
        return cls().execute(query, (int(record_id),))