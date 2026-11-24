

# -------------------------------------------------------------
# -------repositories/parametri_masina_repository.py--------------
# -------------------------------------------------------------



from datetime import datetime
import json
import re
from config import db_cursor


def _incearca_float(val: str | float | int | None) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    txt = str(val).strip().replace(" ", "").replace(",", ".")
    # Extrage primul număr dacă există unitate lipită (ex: "24.5V" -> "24.5")
    match = re.match(r"^[+-]?\d+(?:\.\d+)?", txt)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parseaza_parametri_din_text(continut: str) -> list[dict]:
    """
    Parsează linii sau JSON într-o listă curată de dicționare:
    {"cod_param": ..., "valoare": ..., "descriere": ..., "documentatie_link": ...}

    Formate acceptate per linie:
    - cod_param;valoare;descriere;documentatie_link
    - cod_param | valoare | descriere | documentatie_link
    - cod_param = valoare
    - cod_param: valoare
    """
    text = (continut or "").strip()
    if not text:
        return []

    # Dacă este JSON valid (listă sau {"parametri": [...]})
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            items = data.get("parametri", []) if isinstance(data, dict) else data
            if isinstance(items, list):
                rez = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    cod = str(item.get("cod_param") or item.get("cod") or "").strip()
                    if not cod:
                        continue
                    rez.append(
                        {
                            "cod_param": cod,
                            "valoare": str(item.get("valoare") if item.get("valoare") is not None else "").strip(),
                            "descriere": str(item.get("descriere") or "").strip(),
                            "documentatie_link": str(
                                item.get("documentatie_link") or item.get("link") or ""
                            ).strip(),
                        }
                    )
                if rez:
                    return rez
        except Exception:
            pass

    rezultat: list[dict] = []
    for linie_bruta in text.splitlines():
        linie = linie_bruta.strip()
        if not linie or linie.startswith("#") or linie.startswith("//"):
            continue

        cod = ""
        valoare = ""
        descriere = ""
        link = ""

        if ";" in linie:
            parti = [p.strip() for p in linie.split(";")]
            cod = parti[0] if len(parti) > 0 else ""
            valoare = parti[1] if len(parti) > 1 else ""
            descriere = parti[2] if len(parti) > 2 else ""
            link = parti[3] if len(parti) > 3 else ""
        elif "|" in linie:
            parti = [p.strip() for p in linie.split("|")]
            cod = parti[0] if len(parti) > 0 else ""
            valoare = parti[1] if len(parti) > 1 else ""
            descriere = parti[2] if len(parti) > 2 else ""
            link = parti[3] if len(parti) > 3 else ""
        elif "=" in linie:
            stanga, dreapta = linie.split("=", 1)
            cod = stanga.strip()
            valoare = dreapta.strip()
        elif ":" in linie and not linie.lower().startswith("http"):
            stanga, dreapta = linie.split(":", 1)
            cod = stanga.strip()
            valoare = dreapta.strip()
        else:
            parti = re.split(r"\s{2,}|\t+", linie)
            cod = parti[0].strip() if len(parti) > 0 else ""
            valoare = parti[1].strip() if len(parti) > 1 else ""
            descriere = parti[2].strip() if len(parti) > 2 else ""

        if cod:
            rezultat.append(
                {
                    "cod_param": cod,
                    "valoare": valoare,
                    "descriere": descriere,
                    "documentatie_link": link,
                }
            )

    return rezultat


class ParametriMasinaRepository:
    @staticmethod
    def get_seturi_by_masina(masina_id: int) -> list[dict]:
        with db_cursor() as c:
            c.execute(
                """
                SELECT
                    s.id,
                    s.firma_id,
                    s.masina_id,
                    s.data_inregistrare,
                    s.model_piesa,
                    s.subansamblu,
                    s.sursa_import,
                    s.este_referinta,
                    s.observatii,
                    s.parametri_json,
                    COUNT(v.id) AS nr_parametri
                FROM seturi_parametri_masina s
                LEFT JOIN parametri_masina_valori v ON v.set_id = s.id
                WHERE s.masina_id = %s
                GROUP BY s.id
                ORDER BY s.data_inregistrare DESC, s.id DESC
                """,
                (masina_id,),
            )
            rows = c.fetchall()
            return [dict(r) for r in rows] if rows else []

    @staticmethod
    def get_valori_by_set(set_id: int) -> list[dict]:
        with db_cursor() as c:
            c.execute(
                """
                SELECT
                    id,
                    set_id,
                    firma_id,
                    masina_id,
                    cod_param,
                    valoare_text,
                    valoare_num,
                    descriere,
                    documentatie_link,
                    data_inregistrare
                FROM parametri_masina_valori
                WHERE set_id = %s
                ORDER BY cod_param ASC, id ASC
                """,
                (set_id,),
            )
            rows = c.fetchall()
            return [dict(r) for r in rows] if rows else []

    @staticmethod
    def salveaza_set_parametri(
        firma_id: int,
        masina_id: int,
        parametri: list[dict],
        model_piesa: str | None = None,
        subansamblu: str | None = None,
        sursa_import: str = "manual",
        este_referinta: bool = False,
        observatii: str | None = None,
        data_inregistrare: datetime | None = None,
    ) -> int:
        dt = data_inregistrare or datetime.now()
        lista_curata = []
        for p in parametri:
            cod = str(p.get("cod_param") or "").strip()
            if not cod:
                continue
            lista_curata.append(
                {
                    "cod_param": cod,
                    "valoare": str(p.get("valoare") if p.get("valoare") is not None else "").strip(),
                    "descriere": str(p.get("descriere") or "").strip(),
                    "documentatie_link": str(p.get("documentatie_link") or "").strip(),
                }
            )

        with db_cursor() as c:
            c.execute(
                """
                INSERT INTO seturi_parametri_masina (
                    firma_id,
                    masina_id,
                    data_inregistrare,
                    model_piesa,
                    subansamblu,
                    sursa_import,
                    este_referinta,
                    observatii,
                    parametri_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    firma_id,
                    masina_id,
                    dt,
                    (model_piesa or "").strip() or None,
                    (subansamblu or "").strip() or None,
                    sursa_import,
                    bool(este_referinta),
                    (observatii or "").strip() or None,
                    json.dumps(lista_curata, ensure_ascii=False),
                ),
            )
            set_row = c.fetchone()
            set_id = int(set_row["id"])

            if lista_curata:
                valori_rows = [
                    (
                        set_id,
                        firma_id,
                        masina_id,
                        item["cod_param"],
                        item["valoare"],
                        _incearca_float(item["valoare"]),
                        item["descriere"] or None,
                        item["documentatie_link"] or None,
                        dt,
                    )
                    for item in lista_curata
                ]
                c.executemany(
                    """
                    INSERT INTO parametri_masina_valori (
                        set_id,
                        firma_id,
                        masina_id,
                        cod_param,
                        valoare_text,
                        valoare_num,
                        descriere,
                        documentatie_link,
                        data_inregistrare
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    valori_rows,
                )

        return set_id

    @staticmethod
    def seteaza_referinta(set_id: int, este_referinta: bool = True) -> None:
        with db_cursor() as c:
            c.execute(
                "UPDATE seturi_parametri_masina SET este_referinta = %s WHERE id = %s",
                (bool(este_referinta), set_id),
            )

    @staticmethod
    def compara_seturi(set_referinta_id: int, set_nou_id: int) -> list[dict]:
        """
        Compară un set de referință (ex: când mașina mergea OK) cu un set nou.
        """
        ref_rows = ParametriMasinaRepository.get_valori_by_set(set_referinta_id)
        nou_rows = ParametriMasinaRepository.get_valori_by_set(set_nou_id)

        ref_map = {r["cod_param"].strip().lower(): r for r in ref_rows}
        nou_map = {r["cod_param"].strip().lower(): r for r in nou_rows}

        toate_cheile = list(dict.fromkeys(list(ref_map.keys()) + list(nou_map.keys())))
        rezultat: list[dict] = []

        for cheie in toate_cheile:
            r = ref_map.get(cheie)
            n = nou_map.get(cheie)

            cod = (n or r)["cod_param"]
            val_ref_txt = r["valoare_text"] if r else "—"
            val_nou_txt = n["valoare_text"] if n else "—"
            val_ref_num = r["valoare_num"] if r else None
            val_nou_num = n["valoare_num"] if n else None

            diferenta_num = None
            if val_ref_num is not None and val_nou_num is not None:
                diferenta_num = round(val_nou_num - val_ref_num, 6)

            if r and not n:
                status = "Lipsă în setul nou"
            elif n and not r:
                status = "Parametru nou"
            else:
                if val_ref_num is not None and val_nou_num is not None:
                    egal = abs(val_ref_num - val_nou_num) < 1e-9
                else:
                    egal = (val_ref_txt or "").strip() == (val_nou_txt or "").strip()
                status = "Identic (OK)" if egal else "Modificat"

            descriere = (n or r).get("descriere") or ""
            link = (n or r).get("documentatie_link") or ""

            rezultat.append(
                {
                    "cod_param": cod,
                    "descriere": descriere,
                    "valoare_referinta": val_ref_txt,
                    "valoare_noua": val_nou_txt,
                    "diferenta_num": diferenta_num,
                    "status": status,
                    "documentatie_link": link,
                }
            )

        return rezultat