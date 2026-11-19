#----------------------------------
#----masuratori_repository.py------
#----------------------------------

from repositories.base_repository import BaseRepository

class MasuratoriRepository(BaseRepository):
    @classmethod
    def get_by_masina(cls, masina_id):
        query = """
            SELECT id, firma_id, masina_id, subansamblu, parametru, valoare, unitate_masura, data_masurare 
            FROM parametri_masurati 
            WHERE masina_id = %s 
            ORDER BY data_masurare ASC
        """
        return cls().fetch_all(query, (masina_id,))

    @classmethod
    def insert(cls, data: dict):
        query = """
            INSERT INTO parametri_masurati (firma_id, masina_id, subansamblu, parametru, valoare, unitate_masura, data_masurare)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        params = (
            data.get("firma_id"),
            data.get("masina_id"),
            data.get("subansamblu"),
            data.get("parametru"),
            data.get("valoare"),
            data.get("unitate_masura"),
            data.get("data_masurare")
        )
        result = cls().execute_returning(query, params)
        return result['id'] if result else None