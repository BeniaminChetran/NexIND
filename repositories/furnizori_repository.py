# ----------------------------------------------------
# -------repositories/furnizori_repository.py----------
# -----------------------------------------------------



from __future__ import annotations

import csv
import io
import json
import streamlit as st
from config import db_cursor

_TABELA_VERIFICATA = False


class FurnizoriRepository:
    @staticmethod
    def ensure_table() -> None:
        global _TABELA_VERIFICATA
        if _TABELA_VERIFICATA:
            return
        with db_cursor() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS furnizori (
                    id SERIAL PRIMARY KEY,
                    nume_furnizor TEXT NOT NULL UNIQUE,
                    cui TEXT DEFAULT '',
                    persoana_contact TEXT DEFAULT '',
                    telefon TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    site_web TEXT DEFAULT '',
                    termen_plata_zile INTEGER DEFAULT 0,
                    moneda_preferata TEXT DEFAULT 'EUR',
                    observatii TEXT DEFAULT '',
                    activ BOOLEAN DEFAULT TRUE,
                    creat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actualizat_la TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_furnizori_activ_nume ON furnizori (activ, LOWER(nume_furnizor))"
            )
        _TABELA_VERIFICATA = True

    @staticmethod
    def _clear_cache() -> None:
        for fn_name in ("get_all", "get_active_names"):
            fn = getattr(FurnizoriRepository, fn_name, None)
            if fn is not None and hasattr(fn, "clear"):
                try:
                    fn.clear()
                except Exception:
                    pass

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def get_all(doar_activi: bool = False) -> list[dict]:
        FurnizoriRepository.ensure_table()
        sql = (
            "SELECT id, nume_furnizor, cui, persoana_contact, telefon, email, site_web, "
            "termen_plata_zile, moneda_preferata, observatii, activ, creat_la, actualizat_la "
            "FROM furnizori "
            + ("WHERE activ = TRUE " if doar_activi else "")
            + "ORDER BY LOWER(nume_furnizor) ASC, id ASC"
        )
        with db_cursor() as c:
            c.execute(sql)
            rows = c.fetchall() or []
        return [dict(r) for r in rows]

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def get_active_names() -> list[str]:
        rows = FurnizoriRepository.get_all(doar_activi=True)
        return [str(r["nume_furnizor"]).strip() for r in rows if str(r.get("nume_furnizor") or "").strip()]

    @staticmethod
    def upsert(data: dict) -> int:
        FurnizoriRepository.ensure_table()
        nume = str(data.get("nume_furnizor") or "").strip()
        if not nume:
            raise ValueError("Numele furnizorului este obligatoriu.")

        moneda = str(data.get("moneda_preferata") or "EUR").strip().upper()
        if moneda not in ("EUR", "RON", "USD"):
            moneda = "EUR"

        params = (
            nume,
            str(data.get("cui") or "").strip(),
            str(data.get("persoana_contact") or "").strip(),
            str(data.get("telefon") or "").strip(),
            str(data.get("email") or "").strip(),
            str(data.get("site_web") or "").strip(),
            max(0, int(data.get("termen_plata_zile") or 0)),
            moneda,
            str(data.get("observatii") or "").strip(),
            bool(data.get("activ", True)),
        )

        with db_cursor() as c:
            c.execute(
                """
                INSERT INTO furnizori (
                    nume_furnizor, cui, persoana_contact, telefon, email, site_web,
                    termen_plata_zile, moneda_preferata, observatii, activ, actualizat_la
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (nume_furnizor) DO UPDATE SET
                    cui = EXCLUDED.cui,
                    persoana_contact = EXCLUDED.persoana_contact,
                    telefon = EXCLUDED.telefon,
                    email = EXCLUDED.email,
                    site_web = EXCLUDED.site_web,
                    termen_plata_zile = EXCLUDED.termen_plata_zile,
                    moneda_preferata = EXCLUDED.moneda_preferata,
                    observatii = EXCLUDED.observatii,
                    activ = EXCLUDED.activ,
                    actualizat_la = CURRENT_TIMESTAMP
                RETURNING id
                """,
                params,
            )
            row = c.fetchone()
            fid = int(row["id"]) if isinstance(row, dict) else int(row[0])

        FurnizoriRepository._clear_cache()
        return fid

    @staticmethod
    def update(furnizor_id: int, data: dict) -> None:
        FurnizoriRepository.ensure_table()
        nume = str(data.get("nume_furnizor") or "").strip()
        if not nume:
            raise ValueError("Numele furnizorului este obligatoriu.")

        moneda = str(data.get("moneda_preferata") or "EUR").strip().upper()
        if moneda not in ("EUR", "RON", "USD"):
            moneda = "EUR"

        with db_cursor() as c:
            c.execute(
                """
                UPDATE furnizori
                SET nume_furnizor = %s,
                    cui = %s,
                    persoana_contact = %s,
                    telefon = %s,
                    email = %s,
                    site_web = %s,
                    termen_plata_zile = %s,
                    moneda_preferata = %s,
                    observatii = %s,
                    activ = %s,
                    actualizat_la = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    nume,
                    str(data.get("cui") or "").strip(),
                    str(data.get("persoana_contact") or "").strip(),
                    str(data.get("telefon") or "").strip(),
                    str(data.get("email") or "").strip(),
                    str(data.get("site_web") or "").strip(),
                    max(0, int(data.get("termen_plata_zile") or 0)),
                    moneda,
                    str(data.get("observatii") or "").strip(),
                    bool(data.get("activ", True)),
                    int(furnizor_id),
                ),
            )
        FurnizoriRepository._clear_cache()

    @staticmethod
    def delete(furnizor_id: int) -> None:
        FurnizoriRepository.ensure_table()
        with db_cursor() as c:
            c.execute("DELETE FROM furnizori WHERE id = %s", (int(furnizor_id),))
        FurnizoriRepository._clear_cache()

    @staticmethod
    def import_from_upload(uploaded_file) -> tuple[int, list[str]]:
        FurnizoriRepository.ensure_table()
        if uploaded_file is None:
            return 0, []

        raw_bytes = uploaded_file.getvalue()
        text = raw_bytes.decode("utf-8-sig", errors="replace").strip()
        if not text:
            return 0, []

        records: list[dict] = []
        ext = str(uploaded_file.name or "").lower().rsplit(".", 1)[-1]

        if ext == "json":
            parsed = json.loads(text)
            items = parsed if isinstance(parsed, list) else (parsed.get("furnizori") or [])
            for it in items:
                if isinstance(it, str):
                    if it.strip():
                        records.append({"nume_furnizor": it.strip()})
                elif isinstance(it, dict):
                    nume = str(it.get("nume_furnizor") or it.get("furnizor") or it.get("nume") or "").strip()
                    if nume:
                        records.append({
                            "nume_furnizor": nume,
                            "cui": it.get("cui", ""),
                            "persoana_contact": it.get("persoana_contact", "") or it.get("contact", ""),
                            "telefon": it.get("telefon", ""),
                            "email": it.get("email", ""),
                            "site_web": it.get("site_web", "") or it.get("site", ""),
                            "termen_plata_zile": it.get("termen_plata_zile", 0),
                            "moneda_preferata": it.get("moneda_preferata", "EUR"),
                            "observatii": it.get("observatii", ""),
                            "activ": bool(it.get("activ", True)),
                        })
        else:
            sample = text[:1024]
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            fieldnames = [str(f or "").strip().lower() for f in (reader.fieldnames or [])]
            has_header = any(
                k in fieldnames for k in ("nume_furnizor", "furnizor", "nume", "cui", "email", "telefon")
            )
            if has_header:
                for row in reader:
                    norm_row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
                    nume = norm_row.get("nume_furnizor") or norm_row.get("furnizor") or norm_row.get("nume") or ""
                    if not nume:
                        continue
                    try:
                        termen = int(float(norm_row.get("termen_plata_zile") or 0))
                    except Exception:
                        termen = 0
                    records.append({
                        "nume_furnizor": nume,
                        "cui": norm_row.get("cui", ""),
                        "persoana_contact": norm_row.get("persoana_contact") or norm_row.get("contact") or "",
                        "telefon": norm_row.get("telefon", ""),
                        "email": norm_row.get("email", ""),
                        "site_web": norm_row.get("site_web") or norm_row.get("site") or "",
                        "termen_plata_zile": termen,
                        "moneda_preferata": norm_row.get("moneda_preferata") or norm_row.get("moneda") or "EUR",
                        "observatii": norm_row.get("observatii") or norm_row.get("obs") or "",
                        "activ": norm_row.get("activ", "true").lower() not in ("0", "false", "nu", "no"),
                    })
            else:
                for line in text.splitlines():
                    parts = [p.strip() for p in line.split(delimiter)]
                    if parts and parts[0]:
                        records.append({
                            "nume_furnizor": parts[0],
                            "cui": parts[1] if len(parts) > 1 else "",
                            "persoana_contact": parts[2] if len(parts) > 2 else "",
                            "telefon": parts[3] if len(parts) > 3 else "",
                            "email": parts[4] if len(parts) > 4 else "",
                            "observatii": parts[5] if len(parts) > 5 else "",
                        })

        saved = 0
        errors: list[str] = []
        for rec in records:
            try:
                FurnizoriRepository.upsert(rec)
                saved += 1
            except Exception as exc:
                errors.append(f"{rec.get('nume_furnizor')}: {exc}")

        FurnizoriRepository._clear_cache()
        return saved, errors