
#--------------------------------------
#-----utils/acces_conturi.py-----------
#--------------------------------------

from dataclasses import dataclass
import streamlit as st

CONTURI_BIROU_IMPLICITE = (
    {"id": "birou_1", "nume": "Birou — Utilizator 1", "rol": "birou_full"},
    {"id": "birou_2", "nume": "Birou — Utilizator 2", "rol": "birou_full"},
    {"id": "birou_3", "nume": "Birou — Utilizator 3", "rol": "birou_full"},
)

OPERATOR_IMPLICIT = {
    "id": "operator_masina",
    "nume": "Operator Mașină",
    "rol": "operator_masina",
}


@dataclass(frozen=True)
class ContActiv:
    id: str
    nume: str
    rol: str  # "birou_full" | "operator_masina"

    @property
    def este_operator(self) -> bool:
        return self.rol == "operator_masina"

    @property
    def are_acces_total(self) -> bool:
        return self.rol == "birou_full"


def _normalizeaza_cont(raw: dict | None) -> ContActiv:
    if not isinstance(raw, dict):
        c0 = CONTURI_BIROU_IMPLICITE[0]
        return ContActiv(id=c0["id"], nume=c0["nume"], rol=c0["rol"])

    rol = str(raw.get("rol") or "birou_full").strip()
    if rol not in ("birou_full", "operator_masina"):
        rol = "birou_full"

    return ContActiv(
        id=str(raw.get("id") or ("operator_masina" if rol == "operator_masina" else "birou_1")).strip(),
        nume=str(raw.get("nume") or (OPERATOR_IMPLICIT["nume"] if rol == "operator_masina" else CONTURI_BIROU_IMPLICITE[0]["nume"])).strip(),
        rol=rol,
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
    # Persoanele de la birou au acces total implicit
    st.session_state["is_unlocked"] = True
    st.session_state["preturi_deblocate"] = True


def activeaza_mod_operator(nume_operator: str | None = None) -> None:
    nume_curat = str(nume_operator or st.session_state.get("operator_nume_curent") or OPERATOR_IMPLICIT["nume"]).strip() or OPERATOR_IMPLICIT["nume"]
    st.session_state["operator_nume_curent"] = nume_curat
    st.session_state["cont_activ"] = {
        "id": "operator_masina",
        "nume": nume_curat,
        "rol": "operator_masina",
    }
    st.session_state["is_unlocked"] = False
    st.session_state["preturi_deblocate"] = False