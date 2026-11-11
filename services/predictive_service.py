#-----------------------------------
#---------predictive_service.py-----
#-----------------------------------

from config import db_cursor

def get_predictive_piese_data(firma: str, masina: str):
    with db_cursor() as cur_piese:
        cur_piese.execute("""
            SELECT piese_json FROM reparatii
            WHERE firma = %s AND masina = %s AND piese_json IS NOT NULL
        """, (firma, masina))
        return cur_piese.fetchall()