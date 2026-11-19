#-------------------------------
#-------- models.py--------------
#---------------------------------



from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class FirmaModel:
    nume_firma: str
    cui: Optional[str] = None
    reg_com: Optional[str] = None
    adresa: Optional[str] = None
    banca: Optional[str] = None
    cont: Optional[str] = None
    nume_persoana: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    id: Optional[int] = None

    def validate(self):
        if not self.nume_firma or not self.nume_firma.strip():
            raise ValueError("Numele firmei este obligatoriu.")

@dataclass
class MasinaModel:
    firma_id: int
    denumire: str
    tip_masina: Optional[str] = None
    serie: Optional[str] = None
    an_fabricatie: Optional[int] = None
    subansambluri: Optional[str] = None
    erori: Optional[str] = None
    defecte: Optional[str] = None
    remediu: Optional[str] = None
    piese_necesare: Optional[str] = None
    piese_inlocuite: Optional[str] = None
    tipuri_fluide: Optional[str] = None
    data_intretinere: Optional[str] = None
    tip_intretinere: Optional[str] = None
    id: Optional[int] = None

    def validate(self):
        if not self.firma_id:
            raise ValueError("ID-ul firmei este obligatoriu pentru mașină.")
        if not self.denumire or not self.denumire.strip():
            raise ValueError("Denumirea mașinii este obligatorie.")

@dataclass
class ReparatieModel:
    firma: str
    masina: str
    titlu_lucrare: str
    subansamblu: Optional[str] = None
    defect: Optional[str] = None
    cod_eroare: Optional[str] = None
    piese_valide: List[Dict[str, Any]] = field(default_factory=list)
    simptom: Optional[str] = None
    solutie: Optional[str] = None
    stare_fin: str = "Deschis"
    durata_min: Optional[int] = None
    optimizari: Optional[str] = None
    tehnician_nume: Optional[str] = None
    verificator_nume: Optional[str] = None
    tip_interventie: Optional[str] = None
    id: Optional[int] = None

    def validate(self):
        if not self.firma or not self.masina or not self.titlu_lucrare:
            raise ValueError("Câmpurile Firma, Mașina și Titlul Lucrării sunt obligatorii.")