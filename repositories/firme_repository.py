#--------------------------------
#-----firme_repository.py--------
#--------------------------------

from config import db_cursor, logger

class FirmeRepository:
    @staticmethod
    def get_all():
        with db_cursor() as cur:
            cur.execute("""
                SELECT id, nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon 
                FROM firme 
                ORDER BY nume_firma
            """)
            return cur.fetchall()

    @staticmethod
    def insert(data: dict):
        with db_cursor() as c:
            c.execute("""
                INSERT INTO firme (nume_firma, cui, reg_com, adresa, banca, cont, nume_persoana, email, telefon) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['nume_firma'], data.get('cui'), data.get('reg_com'),
                data.get('adresa'), data.get('banca'), data.get('cont'),
                data.get('nume_persoana'), data.get('email'), data.get('telefon')
            ))
        logger.info(f"Firma noua adaugata: {data['nume_firma']}")

    @staticmethod
    def update(firma_id: int, data: dict):
        with db_cursor() as c:
            c.execute("""
                UPDATE firme 
                SET nume_firma=%s, cui=%s, reg_com=%s, adresa=%s, banca=%s, cont=%s, nume_persoana=%s, email=%s, telefon=%s 
                WHERE id=%s
            """, (
                data['nume_firma'], data.get('cui'), data.get('reg_com'),
                data.get('adresa'), data.get('banca'), data.get('cont'),
                data.get('nume_persoana'), data.get('email'), data.get('telefon'),
                firma_id
            ))
        logger.info(f"Firma #{firma_id} actualizata.")

    @staticmethod
    def delete(firma_id: int):
        with db_cursor() as c:
            c.execute("DELETE FROM firme WHERE id=%s", (firma_id,))
        logger.info(f"Firma #{firma_id} a fost stearsă.")