
#--------------------------------------
#-----utils/acces_conturi.py-----------
#--------------------------------------
from dataclasses import dataclass
import streamlit as st

ALOCARI_OPERATORI_IMPLICITE: tuple[dict, ...] = (
    {
        "id": "op_1",
        "nume": "Popescu Ion",
        "telefon": "0722000001",
        "firma": "",
        "masini": [],
    },
    {
        "id": "op_2",
        "nume": "Ionescu Maria",
        "telefon": "0722000002",
        "firma": "",
        "masini": [],
    },
)

CONTURI_BIROU_IMPLICITE: tuple[dict, ...] = (
    {"id": "birou_1", "nume": "Birou — Utilizator 1", "rol": "birou_full"},
    {"id": "birou_2", "nume": "Birou — Utilizator 2", "rol": "birou_full"},
    {"id": "birou_3", "nume": "Birou — Utilizator 3", "rol": "birou_full"},
)

OPERATOR_IMPLICIT = {
    "id": "operator_masina",
    "nume": "Operator Mașină",
    "telefon": "",
    "firma": "",
    "masini": [],
    "rol": "operator_masina",
}


@dataclass(frozen=True)
class ContActiv:
    id: str
    nume: str
    rol: str  # "birou_full" | "operator_masina"
    telefon: str = ""
    firma: str = ""
    masini_alocate: tuple[str, ...] = ()

    @property
    def este_operator(self) -> bool:
        return self.rol == "operator_masina"

    @property
    def are_acces_total(self) -> bool:
        return self.rol == "birou_full"


def get_alocari_operatori() -> list[dict]:
    alocari = st.session_state.get("alocari_operatori_lista")
    if isinstance(alocari, list) and alocari:
        rezultat: list[dict] = []
        for i, item in enumerate(alocari):
            if not isinstance(item, dict):
                continue
            masini_raw = item.get("masini") or []
            if isinstance(masini_raw, str):
                masini_clean = [m.strip() for m in masini_raw.split(",") if m.strip()]
            elif isinstance(masini_raw, (list, tuple)):
                masini_clean = [str(m).strip() for m in masini_raw if str(m).strip()]
            else:
                masini_clean = []
            rezultat.append(
                {
                    "id": str(item.get("id") or f"op_{i+1}").strip(),
                    "nume": str(item.get("nume") or f"Operator {i+1}").strip(),
                    "telefon": str(item.get("telefon") or "").strip(),
                    "firma": str(item.get("firma") or "").strip(),
                    "masini": list(dict.fromkeys(masini_clean)),
                }
            )
        if rezultat:
            return rezultat
    return [
        {
            "id": item["id"],
            "nume": item["nume"],
            "telefon": item["telefon"],
            "firma": item["firma"],
            "masini": list(item["masini"]),
        }
        for item in ALOCARI_OPERATORI_IMPLICITE
    ]


def _gaseste_alocare_dupa_nume(nume: str) -> dict | None:
    nume_low = str(nume or "").strip().lower()
    if not nume_low:
        return None
    for item in get_alocari_operatori():
        if str(item.get("nume") or "").strip().lower() == nume_low:
            return item
    return None


def _normalizeaza_cont(raw: dict | None) -> ContActiv:
    if not isinstance(raw, dict):
        c0 = CONTURI_BIROU_IMPLICITE[0]
        return ContActiv(id=c0["id"], nume=c0["nume"], rol=c0["rol"])

    rol = str(raw.get("rol") or "birou_full").strip()
    if rol not in ("birou_full", "operator_masina"):
        rol = "birou_full"

    if rol == "operator_masina":
        nume = str(raw.get("nume") or OPERATOR_IMPLICIT["nume"]).strip() or OPERATOR_IMPLICIT["nume"]
        aloc = _gaseste_alocare_dupa_nume(nume)
        telefon = str(raw.get("telefon") or (aloc.get("telefon") if aloc else "") or "").strip()
        firma = str(raw.get("firma") or (aloc.get("firma") if aloc else "") or "").strip()
        masini_src = raw.get("masini_alocate")
        if masini_src is None and aloc is not None:
            masini_src = aloc.get("masini") or []
        masini_tuple = tuple(
            dict.fromkeys(str(m).strip() for m in (masini_src or []) if str(m).strip())
        )
        return ContActiv(
            id=str(raw.get("id") or (aloc.get("id") if aloc else "operator_masina")).strip(),
            nume=nume,
            rol="operator_masina",
            telefon=telefon,
            firma=firma,
            masini_alocate=masini_tuple,
        )

    return ContActiv(
        id=str(raw.get("id") or CONTURI_BIROU_IMPLICITE[0]["id"]).strip(),
        nume=str(raw.get("nume") or CONTURI_BIROU_IMPLICITE[0]["nume"]).strip(),
        rol="birou_full",
    )


def get_conturi_birou() -> list[dict]:
    conturi = st.session_state.get("conturi_birou_lista")
    if isinstance(conturi, list) and conturi:
        return [
            {
                "id": str(c.get("id") or f"birou_{i+1}"),
                "nume": str(c.get("nume") or f"Birou — Utilizator {i+1}"),
                "rol": "birou_full",
            }
            for i, c in enumerate(conturi)
            if isinstance(c, dict)
        ]
    return [dict(c) for c in CONTURI_BIROU_IMPLICITE]


def get_cont_activ() -> ContActiv:
    st.session_state.setdefault("cont_activ", dict(CONTURI_BIROU_IMPLICITE[0]))
    return _normalizeaza_cont(st.session_state.get("cont_activ"))


def seteaza_cont_birou(cont_dict: dict) -> None:
    cont = _normalizeaza_cont({**(cont_dict or {}), "rol": "birou_full"})
    st.session_state["cont_activ"] = {
        "id": cont.id,
        "nume": cont.nume,
        "rol": "birou_full",
    }
    st.session_state["is_unlocked"] = True
    st.session_state["preturi_deblocate"] = True


def activeaza_mod_operator(
    nume_operator: str | None = None,
    telefon: str | None = None,
    firma: str | None = None,
    masini_alocate: list[str] | tuple[str, ...] | None = None,
) -> None:
    alocari = get_alocari_operatori()
    aloc_baza = _gaseste_alocare_dupa_nume(nume_operator or "") or (alocari[0] if alocari else OPERATOR_IMPLICIT)

    nume_curat = str(nume_operator if nume_operator is not None else st.session_state.get("operator_nume_curent") or aloc_baza.get("nume") or OPERATOR_IMPLICIT["nume"]).strip()
    if not nume_curat:
        nume_curat = OPERATOR_IMPLICIT["nume"]

    aloc_match = _gaseste_alocare_dupa_nume(nume_curat) or aloc_baza
    tel_curat = str(telefon if telefon is not None else st.session_state.get("operator_telefon_curent") or aloc_match.get("telefon") or "").strip()
    firma_curata = str(firma if firma is not None else st.session_state.get("operator_firma_curent") or aloc_match.get("firma") or "").strip()

    if masini_alocate is not None:
        masini_list = [str(m).strip() for m in masini_alocate if str(m).strip()]
    else:
        masini_list = list(aloc_match.get("masini") or [])

    st.session_state["operator_nume_curent"] = nume_curat
    st.session_state["operator_telefon_curent"] = tel_curat
    st.session_state["operator_firma_curent"] = firma_curata
    st.session_state["cont_activ"] = {
        "id": str(aloc_match.get("id") or "operator_masina"),
        "nume": nume_curat,
        "telefon": tel_curat,
        "firma": firma_curata,
        "masini_alocate": list(dict.fromkeys(masini_list)),
        "rol": "operator_masina",
    }
    st.session_state["is_unlocked"] = False
    st.session_state["preturi_deblocate"] = False