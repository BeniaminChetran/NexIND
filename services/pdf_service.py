#----------------------------------
#-------services/pdf_service.py------
#----------------------------------

import io
import os
import re
import json
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,# ------------------------------------------
# -------services/pdf_service.py------------
# ------------------------------------------

import json
from fpdf import FPDF


def _safe_txt(val) -> str:
    s = "" if val is None else str(val)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _extrage_randuri_operatiuni(fisa_data: dict) -> list[dict]:
    if isinstance(fisa_data.get("operatiuni"), list) and fisa_data["operatiuni"]:
        return fisa_data["operatiuni"]
    chk = fisa_data.get("checklist_json") or {}
    if isinstance(chk, str):
        try:
            chk = json.loads(chk)
        except Exception:
            chk = {}
    if isinstance(chk, dict):
        fisa_spec = chk.get("fisa_specifica_utilaj")
        if isinstance(fisa_spec, dict) and isinstance(fisa_spec.get("randuri"), list):
            return fisa_spec["randuri"]
    return []


def genereaza_pdf_mentenanta(fisa_data: dict) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    frecventa = str(fisa_data.get("frecventa") or "Lunară").strip()
    nr_fisa = str(fisa_data.get("nr_fisa") or fisa_data.get("id") or "-").strip()
    titlu_doc = str(fisa_data.get("titlu_pdf_operatiuni") or "").strip()
    if not titlu_doc:
        titlu_doc = (
            f"Operatiuni de intretinere {frecventa.lower()} la masina "
            f"{fisa_data.get('masina_nume') or '-'} tip {fisa_data.get('tip_masina') or fisa_data.get('producator_model') or '-'} "
            f"{str(fisa_data.get('data_interventie') or '')[:10]} {fisa_data.get('firma_nume') or '-'} "
            f"- {frecventa} - {nr_fisa}"
        )

    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, _safe_txt(titlu_doc))
    pdf.ln(1)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(95, 6, _safe_txt(f"Tip mentenanta realizata: {frecventa}"), border=1)
    pdf.cell(95, 6, _safe_txt(f"Nr. fisa: {nr_fisa}"), border=1, ln=True)

    pdf.set_font("Helvetica", size=9)
    pdf.cell(95, 6, _safe_txt(f"Client: {fisa_data.get('firma_nume') or '-'}"), border=1)
    pdf.cell(95, 6, _safe_txt(f"Data: {str(fisa_data.get('data_interventie') or '')[:10]}"), border=1, ln=True)

    pdf.cell(95, 6, _safe_txt(f"Masina: {fisa_data.get('masina_nume') or '-'}"), border=1)
    pdf.cell(95, 6, _safe_txt(f"Tip masina: {fisa_data.get('tip_masina') or fisa_data.get('producator_model') or '-'}"), border=1, ln=True)

    pdf.cell(95, 6, _safe_txt(f"Stare initiala: {fisa_data.get('stare_initiala') or '-'}"), border=1)
    pdf.cell(95, 6, _safe_txt(f"Stare finala: {fisa_data.get('stare_finala') or '-'}"), border=1, ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, _safe_txt("Operatiuni mentenanta efectuate"), ln=True)

    # Antet tabel (latime totala 190 mm)
    col_w = [12, 68, 42, 22, 16, 30]
    headers = ["Nr.", "Operatiune / Verificare", "Parametru", "Valoare", "UM", "Efectuat"]
    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 6, _safe_txt(h), border=1)
    pdf.ln()

    randuri = _extrage_randuri_operatiuni(fisa_data)
    pdf.set_font("Helvetica", size=8)
    if not randuri:
        pdf.cell(sum(col_w), 7, _safe_txt("Nu exista operatiuni inregistrate."), border=1, ln=True)
    else:
        for idx, r in enumerate(randuri, start=1):
            ord_v = str(r.get("Ordine") or idx)
            op_v = str(r.get("Operațiune / Verificare") or r.get("operatiune") or "")
            prm_v = str(r.get("Denumire parametru") or r.get("parametru") or "")
            val_v = str(r.get("Valoare") or r.get("valoare") or "")
            um_v = str(r.get("UM") or r.get("um") or "")
            ef_raw = r.get("Efectuat", True)
            ef_v = "DA" if (ef_raw is True or str(ef_raw).strip().lower() in ("true", "1", "da", "yes")) else "NU"

            x_start = pdf.get_x()
            y_start = pdf.get_y()
            line_h = 5
            nb_lines = max(
                1,
                len(_safe_txt(op_v)) // 36 + 1,
                len(_safe_txt(prm_v)) // 22 + 1,
            )
            row_h = max(6, nb_lines * line_h)

            if y_start + row_h > pdf.page_break_trigger:
                pdf.add_page()
                x_start = pdf.get_x()
                y_start = pdf.get_y()

            pdf.rect(x_start, y_start, col_w[0], row_h)
            pdf.rect(x_start + col_w[0], y_start, col_w[1], row_h)
            pdf.rect(x_start + sum(col_w[:2]), y_start, col_w[2], row_h)
            pdf.rect(x_start + sum(col_w[:3]), y_start, col_w[3], row_h)
            pdf.rect(x_start + sum(col_w[:4]), y_start, col_w[4], row_h)
            pdf.rect(x_start + sum(col_w[:5]), y_start, col_w[5], row_h)

            pdf.set_xy(x_start + 1, y_start + 1)
            pdf.cell(col_w[0] - 2, line_h, _safe_txt(ord_v))

            pdf.set_xy(x_start + col_w[0] + 1, y_start + 1)
            pdf.multi_cell(col_w[1] - 2, line_h, _safe_txt(op_v))

            pdf.set_xy(x_start + sum(col_w[:2]) + 1, y_start + 1)
            pdf.multi_cell(col_w[2] - 2, line_h, _safe_txt(prm_v))

            pdf.set_xy(x_start + sum(col_w[:3]) + 1, y_start + 1)
            pdf.cell(col_w[3] - 2, line_h, _safe_txt(val_v))

            pdf.set_xy(x_start + sum(col_w[:4]) + 1, y_start + 1)
            pdf.cell(col_w[4] - 2, line_h, _safe_txt(um_v))

            pdf.set_xy(x_start + sum(col_w[:5]) + 1, y_start + 1)
            pdf.cell(col_w[5] - 2, line_h, _safe_txt(ef_v))

            pdf.set_xy(x_start, y_start + row_h)

    if str(fisa_data.get("recomandari_iiot") or "").strip():
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _safe_txt("Recomandari / Observatii"), ln=True)
        pdf.set_font("Helvetica", size=9)
        pdf.multi_cell(0, 5, _safe_txt(fisa_data.get("recomandari_iiot")))

    pdf.ln(4)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(95, 7, _safe_txt(f"Tehnician: {fisa_data.get('tehnician') or '-'}"), border=1)
    pdf.cell(95, 7, _safe_txt(f"Beneficiar: {fisa_data.get('verificator') or '-'}"), border=1, ln=True)

    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
    Table,
    TableStyle,
    HRFlowable,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from config import db_cursor


def inregistreaza_fonturi():
    font_regular = "Helvetica"
    font_bold = "Helvetica-Bold"

    cai_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    cai_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"
    ]

    for path in cai_regular:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("CustomFont", path))
            font_regular = "CustomFont"
            break

    for path in cai_bold:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("CustomFont-Bold", path))
            font_bold = "CustomFont-Bold"
            break

    return font_regular, font_bold


FONT_REG, FONT_BOLD = inregistreaza_fonturi()


def _gaseste_sigla_nexind() -> str | None:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidati = [
        os.path.join(base_dir, "Nexind_android.jpg"),
        os.path.join(base_dir, "Nexind_android.png"),
        "Nexind_android.jpg",
        "Nexind_android.png",
    ]
    for c in candidati:
        if os.path.exists(c):
            return c
    return None


def get_date_firma_mea():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM setari LIMIT 1")
        res = cur.fetchone()
    if res:
        return dict(res)
    return {
        "nume_firma_mea": "SC Nexus Industrial SRL",
        "cui_mea": "",
        "reg_com_mea": "",
        "adresa_mea": "",
        "banca_mea": "",
        "iban_mea": "",
        "swep_mea": "",
        "telefon_1": "",
        "telefon_2": "",
        "email_1": "",
        "email_2": "",
        "email_tehnician": "",
        "cota_tva": 21.0,
        "valabilitate_implicita": "15 zile",
        "termeni_plata_impliciti": "5 zile de la emiterea facturii",
        "intocmit_de_implicit": "Echipa Nexus Industrial",
        "tehnician_implicit": "Tehnician Nexus"
    }


def _extrage_linii_contact_dreapta(setari: dict) -> list[str]:
    """Returnează telefoanele și emailurile completate din setări pentru partea dreaptă."""
    if not isinstance(setari, dict):
        return []

    linii = []
    chei_telefon = ("telefon_1", "telefon_2", "tel_1", "tel_2", "telefon", "tel", "nr_telefon")
    chei_email = ("email_1", "email_2", "mail_1", "mail_2", "email", "mail", "adresa_email")

    telefoane_vazute = set()
    for k in chei_telefon:
        val = str(setari.get(k) or "").strip()
        if val and val.lower() not in ("none", "null", "nan"):
            for parte in val.replace(";", "/").split("/"):
                p_curat = parte.strip()
                if p_curat and p_curat not in telefoane_vazute:
                    telefoane_vazute.add(p_curat)
                    linii.append(f"Tel: {p_curat}")

    emailuri_vazute = set()
    for k in chei_email:
        val = str(setari.get(k) or "").strip()
        if val and val.lower() not in ("none", "null", "nan"):
            for parte in val.replace(";", ",").split(","):
                e_curat = parte.strip()
                if e_curat and e_curat.lower() not in emailuri_vazute:
                    emailuri_vazute.add(e_curat.lower())
                    linii.append(f"Email: {e_curat}")

    return linii


def _construieste_antet_cu_sigla(
    setari: dict,
    titlu_dreapta: str,
    nr_text: str,
    data_text: str,
    s_normal: ParagraphStyle,
    s_bold: ParagraphStyle,
    s_small: ParagraphStyle,
    include_banca_iban: bool = False,
) -> Table:
    """
    Stânga: sigla Nexind sus, dedesubt datele firmei (același font s_normal / s_bold).
    Dreapta: titlul, numărul, data și dedesubt telefoanele și emailurile aliniate la dreapta (același font s_normal).
    """
    stanga_elems = []
    logo_path = _gaseste_sigla_nexind()
    if logo_path:
        try:
            img = RLImage(logo_path, width=20 * mm, height=20 * mm)
            img.hAlign = "LEFT"
            stanga_elems.append(img)
            stanga_elems.append(Spacer(1, 2 * mm))
        except Exception:
            pass

    nume = str((setari or {}).get("nume_firma_mea") or "").strip()
    cui = str((setari or {}).get("cui_mea") or "").strip()
    reg_com = str((setari or {}).get("reg_com_mea") or "").strip()
    adresa = str((setari or {}).get("adresa_mea") or "").strip()
    banca = str((setari or {}).get("banca_mea") or "").strip()
    iban = str((setari or {}).get("iban_mea") or "").strip()
    swift = str((setari or {}).get("swep_mea") or "").strip()

    if nume:
        stanga_elems.append(Paragraph(f"<b>{nume}</b>", s_bold))

    fiscal = []
    if cui:
        fiscal.append(f"CUI: {cui}")
    if reg_com:
        fiscal.append(f"Reg. Com.: {reg_com}")
    if fiscal:
        stanga_elems.append(Paragraph(" | ".join(fiscal), s_normal))

    if adresa:
        stanga_elems.append(Paragraph(f"Adresă: {adresa}", s_normal))

    if include_banca_iban:
        banca_parts = []
        if banca:
            banca_parts.append(f"Bancă: {banca}")
        if iban:
            banca_parts.append(f"IBAN: {iban}")
        if swift:
            banca_parts.append(f"SWIFT: {swift}")
        if banca_parts:
            stanga_elems.append(Paragraph(" | ".join(banca_parts), s_normal))
    elif swift:
        stanga_elems.append(Paragraph(f"SWIFT: {swift}", s_normal))

    style_titlu_dr = ParagraphStyle(
        "TitluDreapta",
        parent=s_bold,
        fontSize=12.5,
        leading=16,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0F172A"),
    )
    style_meta_dr = ParagraphStyle(
        "MetaDreapta",
        parent=s_normal,
        fontSize=s_normal.fontSize,
        leading=s_normal.leading,
        alignment=TA_RIGHT,
    )

    dreapta_elems = [
        Paragraph(f"<b>{titlu_dreapta}</b>", style_titlu_dr),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Nr.:</b> {nr_text}", style_meta_dr),
        Paragraph(f"<b>Data:</b> {data_text}", style_meta_dr),
    ]

    linii_contact_dr = _extrage_linii_contact_dreapta(setari or {})
    if linii_contact_dr:
        dreapta_elems.append(Spacer(1, 1.5 * mm))
        for lc in linii_contact_dr:
            dreapta_elems.append(Paragraph(lc, style_meta_dr))

    tbl = Table([[stanga_elems, dreapta_elems]], colWidths=[96 * mm, 92 * mm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor("#CBD5E1")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
    ]))
    return tbl



def draw_header_footer(canvas, doc, titlu_document="RAPORT DE INTERVENȚIE TEHNICĂ", centreaza_titlu=False, font_size_titlu=14):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1E293B"))
    canvas.rect(0, A4[1] - 48, A4[0], 48, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, font_size_titlu)
    if centreaza_titlu:
        canvas.drawCentredString(A4[0] / 2.0, A4[1] - 29, titlu_document)
    else:
        canvas.drawString(30, A4[1] - 29, titlu_document)

    canvas.setFont(FONT_REG, 8)
    canvas.drawRightString(A4[0] - 30, A4[1] - 29, "DOCUMENT OFICIAL")

    canvas.setFont(FONT_REG, 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(A4[0] / 2.0, 20, f"Pagina {doc.page} | Raport generat automat")
    canvas.restoreState()


def creeaza_stiluri():
    styles = getSampleStyleSheet()
    s_normal = ParagraphStyle('SNormal', parent=styles['Normal'], fontName=FONT_REG, fontSize=9, leading=13, textColor=colors.black)
    s_bold = ParagraphStyle('SBold', parent=s_normal, fontName=FONT_BOLD)
    s_small = ParagraphStyle('SSmall', parent=s_normal, fontSize=8.2, leading=11.5, textColor=colors.HexColor("#334155"))
    s_sec_title = ParagraphStyle('SSecTitle', parent=s_normal, fontName=FONT_BOLD, fontSize=9.5, textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=2)
    return s_normal, s_bold, s_small, s_sec_title


def formateaza_linii_cu_simbol(text):
    if not text:
        return "Nespecificat"

    linii_brute = text.split('\n')
    linii_finale = []

    for l in linii_brute:
        l_curat = l.strip()
        if not l_curat:
            continue
        parti = l_curat.split('#')
        for p in parti:
            p_limpezit = p.strip()
            if p_limpezit:
                linii_finale.append(f"• {p_limpezit}")

    if not linii_finale:
        return text.replace("\n", "<br/>")

    return "<br/>".join(linii_finale)


def formateaza_adresa_pe_randuri(adresa: str) -> str:
    """Rupe adresa clientului pe rânduri compacte fără spații sau rânduri goale."""
    if not adresa:
        return ""
    txt = str(adresa).strip()
    if "\n" in txt:
        linii = [l.strip() for l in txt.splitlines() if l.strip()]
        return "<br/>".join(linii)
    txt = re.sub(
        r',?\s*(?=(Ora[șs]\b|Loc\.|Localitatea\b|Strada\b|Str\.|Bd\.|Bdul\b|Calea\b|Sector\b|Cod\s*po[șs]tal\b))',
        '<br/>',
        txt,
        flags=re.IGNORECASE
    )
    linii = [l.strip() for l in txt.split("<br/>") if l.strip()]
    return "<br/>".join(linii)


def formateaza_termeni_plata_pe_randuri(termeni: str) -> str:
    """Împarte termenii de plată pe rânduri separate (după virgulă, ; sau Enter)."""
    if not termeni:
        return ""
    parti = [p.strip() for p in re.split(r'[\n;,]+', str(termeni)) if p.strip()]
    if len(parti) <= 1:
        return str(termeni).strip()
    return "<br/>" + "<br/>".join([f"• {p}" for p in parti])


def formateaza_numar_ro(valoare) -> str:
    """Formatează numerele fără separator de mii, cu virgulă la zecimale și fără zerouri inutile."""
    try:
        num = float(valoare)
    except (TypeError, ValueError):
        return str(valoare or "0")

    num_rot = round(num, 2)
    if num_rot == int(num_rot):
        return str(int(num_rot))

    s_dec = f"{num_rot:.2f}".rstrip("0").rstrip(".")
    return s_dec.replace(".", ",")


# ------------------------------------------------------------------------------
# 1. RAPORT INTERVENȚIE TEHNICĂ (STANDARD / MECANIC)
# ------------------------------------------------------------------------------
def genereaza_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=58, bottomMargin=35)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    setari = get_date_firma_mea()

    elements.append(_construieste_antet_cu_sigla(
        setari=setari,
        titlu_dreapta="RAPORT DE INTERVENȚIE",
        nr_text=f"#{data.get('id', '')}",
        data_text=str(data.get('data', ''))[:10],
        s_normal=s_normal,
        s_bold=s_bold,
        s_small=s_small,
        include_banca_iban=False,
    ))
    elements.append(Spacer(1, 8))

    durata_min = int(data.get('durata') or 0)
    ore = durata_min // 60
    minute = durata_min % 60
    durata_formatata = f"{ore:02d}:{minute:02d} (ore:minute)"

    detalii_data = [
        [Paragraph("<b>DETALII CLIENT</b>", s_bold), Paragraph("<b>DETALII ECHIPAMENT</b>", s_bold)],
        [Paragraph(f"Client: {data.get('client') or 'Nespecificat'}", s_normal),
         Paragraph(f"Echipament: {data.get('masina', '')} ({data.get('subansamblu', '')})", s_normal)],
        [Paragraph(f"Durată: <b>{durata_formatata}</b>", s_normal),
         Paragraph(f"Cod Eroare: {data.get('cod_eroare', 'N/A')}", s_normal)],
        ["", Paragraph(f"<b>Stare Finală: {data.get('stare_finala', '')}</b>", s_normal)]
    ]
    t_detalii = Table(detalii_data, colWidths=[265, 270])
    t_detalii.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_detalii)
    elements.append(Spacer(1, 6))

    def adauga_sectiune(titlu, text_formatat):
        elements.append(Paragraph(titlu.upper(), s_sec_title))
        elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))
        elements.append(Paragraph(text_formatat, s_normal))
        elements.append(Spacer(1, 4))

    titlu_baza = data.get('titlu') or "Intervenție tehnică"
    tip_interv = data.get('tip_interventie') or ""
    titlu_complet = f"{titlu_baza} - {tip_interv}" if tip_interv else titlu_baza
    adauga_sectiune("Titlu Lucrare", titlu_complet)

    simptom_text = formateaza_linii_cu_simbol(data.get('simptom'))
    defect_text = formateaza_linii_cu_simbol(data.get('defect'))
    simptom_defect_separat = f"<b>Simptom inițial:</b><br/>{simptom_text}<br/><br/><b>Defect constatat:</b><br/>{defect_text}"
    adauga_sectiune("Simptom Inițial / Defect", simptom_defect_separat)

    solutie_text = formateaza_linii_cu_simbol(data.get('solutie'))
    solutie_formatata = f"<b>Lucrări executate:</b><br/>{solutie_text}"
    adauga_sectiune("Soluție / Lucrări Executate", solutie_formatata)

    elements.append(Paragraph("TABEL PIESE (UTILIZATE / ÎNLOCUITE / NECESARE / COMANDAT)", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))

    piese_list = data.get('piese_json', [])
    if isinstance(piese_list, str):
        try:
            piese_list = json.loads(piese_list)
        except Exception:
            piese_list = []

    p_rows = [[Paragraph("<b>Denumire Piesă</b>", s_bold), Paragraph("<b>Cantitate</b>", s_bold), Paragraph("<b>Tip / Status</b>", s_bold)]]
    if piese_list:
        for p in piese_list:
            p_rows.append([
                Paragraph(str(p.get('piesa', p.get('Piesa', ''))), s_normal),
                Paragraph(str(p.get('cantitate', p.get('Cantitate', 1))), s_normal),
                Paragraph(str(p.get('tip', p.get('Tip', ''))), s_normal)
            ])
    else:
        p_rows.append([Paragraph("Nicio piesă înregistrată", s_normal), "", ""])

    t_piese = Table(p_rows, colWidths=[295, 100, 140])
    t_piese.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F8FAFC")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_piese)
    elements.append(Spacer(1, 6))

    if data.get('optimizari'):
        adauga_sectiune("Recomandări Tehnice & Siguranță", formateaza_linii_cu_simbol(data.get('optimizari')))

    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
    tehnician_def = setari.get('tehnician_implicit') or 'Tehnician Nexus'
    semnaturi_data = [
        [Paragraph("<b>EFECTUAT DE (TEHNICIAN)</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER)),
         Paragraph("<b>VERIFICAT / RECEPȚIONAT DE</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER))],
        [Paragraph(f"Nume: {data.get('tehnician') or tehnician_def}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph(f"Nume: {data.get('verificator') or 'Client'}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))],
        [Spacer(1, 18), Spacer(1, 18)],
        [Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))]
    ]
    t_semn = Table(semnaturi_data, colWidths=[265, 270])
    elements.append(t_semn)

    doc.build(
        elements,
        onFirstPage=lambda c, d: draw_header_footer(c, d, "RAPORT DE INTERVENȚIE TEHNICĂ"),
        onLaterPages=lambda c, d: draw_header_footer(c, d, "RAPORT DE INTERVENȚIE TEHNICĂ")
    )
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------------------
# 2. RAPORT REPARAȚIE ELECTRONICĂ / MECATRONICĂ
# ------------------------------------------------------------------------------
def genereaza_pdf_electronic(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=58, bottomMargin=35)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    setari = get_date_firma_mea()

    elements.append(_construieste_antet_cu_sigla(
        setari=setari,
        titlu_dreapta="RAPORT ELECTRONICĂ",
        nr_text=f"#{data.get('id', '')}",
        data_text=str(data.get('data', ''))[:10],
        s_normal=s_normal,
        s_bold=s_bold,
        s_small=s_small,
        include_banca_iban=False,
    ))
    elements.append(Spacer(1, 8))

    detalii_data = [
        [Paragraph("<b>DETALII CLIENT</b>", s_bold), Paragraph("<b>DETALII SUBANSAMBLU / ECHIPAMENT</b>", s_bold)],
        [Paragraph(f"Client: {data.get('client') or 'Nespecificat'}", s_normal),
         Paragraph(f"Mașină: {data.get('masina', 'General / Fără mașină')}", s_normal)],
        ["", Paragraph(f"Piesă / Modul: {data.get('piesa_subansamblu', '')}", s_normal)],
        ["", Paragraph(f"<b>Stare Finală: {data.get('stare_finala', '')}</b>", s_normal)]
    ]
    t_detalii = Table(detalii_data, colWidths=[265, 270])
    t_detalii.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_detalii)
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("DEFECT RECLAMAT", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))
    elements.append(Paragraph(formateaza_linii_cu_simbol(data.get('defect_reclamat')), s_normal))
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("COMPONENTE ELECTRONICE / ELEMENTE ÎNLOCUITE SAU REPARATE", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))

    comp_rows = [[Paragraph("<b>Componentă / Cod & Parametri</b>", s_bold), Paragraph("<b>Stare Componentă</b>", s_bold)]]
    comp_list = data.get('componente_json', [])
    if comp_list:
        for comp in comp_list:
            comp_rows.append([
                Paragraph(str(comp.get('Componenta / Cod / Parametri', '')), s_normal),
                Paragraph(str(comp.get('Stare', 'Necesară')), s_normal)
            ])
    else:
        comp_rows.append([Paragraph("Nicio componentă înregistrată", s_normal), ""])

    t_comp = Table(comp_rows, colWidths=[385, 150])
    t_comp.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F8FAFC")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_comp)

    elements.append(Spacer(1, 18))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
    tehnician_def = setari.get('tehnician_implicit') or 'Tehnician Nexus'
    semnaturi_data = [
        [Paragraph("<b>EFECTUAT DE (TEHNICIAN ELECTRONICĂ)</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER)),
         Paragraph("<b>VERIFICAT / RECEPȚIONAT DE</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER))],
        [Paragraph(f"Nume: {data.get('tehnician') or tehnician_def}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph(f"Nume: {data.get('verificator') or 'Client'}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))],
        [Spacer(1, 18), Spacer(1, 18)],
        [Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))]
    ]
    elements.append(Table(semnaturi_data, colWidths=[265, 270]))

    doc.build(
        elements,
        onFirstPage=lambda c, d: draw_header_footer(c, d, "RAPORT REPARAȚIE ELECTRONICĂ"),
        onLaterPages=lambda c, d: draw_header_footer(c, d, "RAPORT REPARAȚIE ELECTRONICĂ")
    )
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------------------
# 3. OFERTĂ DE PREȚ COMERCIALĂ
# ------------------------------------------------------------------------------
def genereaza_pdf_oferta(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=58, bottomMargin=35)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    s_client_compact = ParagraphStyle('SClientCompact', parent=s_normal, fontSize=9, leading=10.8, textColor=colors.black)
    s_cond_title = ParagraphStyle('SCondTitle', parent=s_bold, fontSize=10, leading=12.5, textColor=colors.HexColor("#0F172A"))
    s_cond_item = ParagraphStyle('SCondItem', parent=s_normal, fontSize=9.5, leading=13, textColor=colors.HexColor("#0F172A"))
    setari = get_date_firma_mea()
    moneda = data.get('moneda', 'EUR')
    este_revizuita = bool(data.get('este_revizuita', False))

    titlu_banner = "OFERTĂ DE PREȚ COMERCIALĂ (REVIZUITĂ)" if este_revizuita else "OFERTĂ DE PREȚ COMERCIALĂ"
    nr_afisare = str(data.get('numar_oferta') or data.get('id') or '')
    if este_revizuita:
        nr_afisare = f"#{nr_afisare} (REVIZUITĂ)"
    elif nr_afisare and not nr_afisare.startswith("#"):
        nr_afisare = f"#{nr_afisare}"

    elements.append(_construieste_antet_cu_sigla(
        setari=setari,
        titlu_dreapta="OFERTĂ DE PREȚ",
        nr_text=nr_afisare,
        data_text=str(data.get('data', ''))[:10],
        s_normal=s_normal,
        s_bold=s_bold,
        s_small=s_small,
        include_banca_iban=True,
    ))
    elements.append(Spacer(1, 8))

    adresa_formatata = formateaza_adresa_pe_randuri(data.get('adresa_client', ''))
    valabilitate_txt = str(data.get('valabilitate') or setari.get('valabilitate_implicita') or '15 zile')
    termeni_plata_formatat = formateaza_termeni_plata_pe_randuri(
        data.get('termeni_plata') or setari.get('termeni_plata_impliciti') or '5 zile de la emiterea facturii'
    )
    curs_valutar_pdf = float(data.get('curs_valutar') or 0.0)
    linie_curs = (
        f"<br/><b>Curs valutar BNR:</b> <b>1 EUR = {formateaza_numar_ro(curs_valutar_pdf)} RON</b>"
        if curs_valutar_pdf > 0 else ""
    )

    reg_com_client = str(data.get('reg_com_client') or '').strip()
    linie_reg_com = f"<br/>Nr. Reg. Com.: {reg_com_client}" if reg_com_client else ""

    box_client_html = (
        f"<b>{data.get('client', '')}</b><br/>"
        f"CUI: {data.get('cui_client', '')}{linie_reg_com}<br/>"
        f"Adresă: {adresa_formatata}"
    )

    box_conditii_html = (
        f"<b>Valabilitate:</b> <b>{valabilitate_txt}</b><br/>"
        f"<b>Termeni de plată:</b> <b>{termeni_plata_formatat}</b><br/>"
        f"<b>Monedă:</b> <b>{moneda}</b>"
        f"{linie_curs}"
    )

    detalii_oferta = [
        [Paragraph("<b>BENEFICIAR / CLIENT</b>", s_cond_title), "", Paragraph("<b>CONDIȚII COMERCIALE</b>", s_cond_title)],
        [
            Paragraph(box_client_html, s_client_compact),
            "",
            Paragraph(box_conditii_html, s_cond_item)
        ]
    ]
    t_detalii = Table(detalii_oferta, colWidths=[210, 92, 233])
    t_detalii.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (0,-1), 8),
        ('LEFTPADDING', (2,0), (2,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(t_detalii)
    elements.append(Spacer(1, 10))

    in_atentia = str(data.get('in_atentia', '')).strip()
    if in_atentia and in_atentia != "În atenția":
        elements.append(Paragraph(f"<b>{in_atentia}</b>", s_bold))
        elements.append(Spacer(1, 3))

    formula_adresare = str(data.get('formula_adresare') or "Ca urmare a discuției anterioare, revenim cu următoarea ofertă de preț.").strip()
    if formula_adresare:
        elements.append(Paragraph(formula_adresare.replace("\n", "<br/>"), s_normal))
        elements.append(Spacer(1, 8))

    parti_echipament = []
    val_utilaj = str(data.get("utilaj")).strip() if data.get("utilaj") is not None else ""
    if val_utilaj and val_utilaj.lower() not in ("none", "nan", "null"):
        parti_echipament.append(val_utilaj)

    campuri_suplimentare = [
        ("Tip", data.get("utilaj_tip")),
        ("Seria", data.get("utilaj_serie")),
        ("An fabric.", data.get("utilaj_an")),
    ]
    for eticheta, val in campuri_suplimentare:
        val_str = str(val).strip() if val is not None else ""
        if val_str and val_str.lower() not in ("none", "nan", "null"):
            parti_echipament.append(f"<b>{eticheta}:</b> {val_str}")

    if parti_echipament:
        linie_echipament = "<b>Date identificare Echipament:</b> " + "; ".join(parti_echipament)
        elements.append(Paragraph(linie_echipament, s_normal))
        elements.append(Spacer(1, 8))

    elements.append(Paragraph("DETALIERE ARTICOLE / SERVICII", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))

    articole = data.get('articole', [])
    t_rows = [[
        Paragraph("<b>Nr.</b>", s_bold),
        Paragraph("<b>Denumire Articol / Serviciu</b>", s_bold),
        Paragraph("<b>UM</b>", s_bold),
        Paragraph("<b>Cant.</b>", s_bold),
        Paragraph(f"<b>Preț Unitar<br/>({moneda})</b>", ParagraphStyle('R', parent=s_bold, alignment=TA_RIGHT)),
        Paragraph(f"<b>Valoare<br/>({moneda})</b>", ParagraphStyle('R', parent=s_bold, alignment=TA_RIGHT)),
        Paragraph("<b>Termen<br/>livrare</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER))
    ]]

    subtotal = 0.0
    col_pret_cheie = f"Pret Unitar ({moneda})"
    curs_conv = float(data.get('curs_valutar') or 1.0)
    for idx, art in enumerate(articole, 1):
        cant = float(art.get('Cantitate') or 1.0)
        if art.get(col_pret_cheie) is not None:
            pret = float(art.get(col_pret_cheie))
        elif art.get('Pret Unitar (RON)') is not None:
            pret_ron = float(art.get('Pret Unitar (RON)'))
            pret = round(pret_ron / curs_conv, 2) if (moneda == "EUR" and curs_conv > 0) else pret_ron
        elif art.get('Pret Unitar (EUR)') is not None:
            pret_eur = float(art.get('Pret Unitar (EUR)'))
            pret = round(pret_eur * curs_conv, 2) if (moneda == "RON" and curs_conv > 0) else pret_eur
        else:
            pret = 0.0

        valoare = round(cant * pret, 2)
        subtotal += valoare
        termen_livrare = str(art.get('Termen livrare', '') or '')

        t_rows.append([
            Paragraph(str(idx), s_normal),
            Paragraph(str(art.get('Descriere', '')), s_normal),
            Paragraph(str(art.get('UM', 'buc')), s_normal),
            Paragraph(formateaza_numar_ro(cant), s_normal),
            Paragraph(formateaza_numar_ro(pret), ParagraphStyle('R', parent=s_normal, alignment=TA_RIGHT)),
            Paragraph(formateaza_numar_ro(valoare), ParagraphStyle('R', parent=s_normal, alignment=TA_RIGHT)),
            Paragraph(termen_livrare, ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))
        ])

    t_articole = Table(t_rows, colWidths=[28, 222, 35, 42, 72, 78, 58])
    t_articole.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_articole)
    elements.append(Spacer(1, 8))

    cota_tva_procent = float(
        data.get('cota_tva')
        if data.get('cota_tva') is not None
        else (setari.get('cota_tva') if setari.get('cota_tva') is not None else 21.0)
    )
    tva = round(subtotal * (cota_tva_procent / 100.0), 2)
    total_general = round(subtotal + tva, 2)

    t_totaluri = Table([
        ["", Paragraph("<b>Subtotal fără TVA:</b>", s_normal), Paragraph(f"<b>{formateaza_numar_ro(subtotal)} {moneda}</b>", ParagraphStyle('R', parent=s_normal, alignment=TA_RIGHT))],
        ["", Paragraph(f"<b>TVA ({formateaza_numar_ro(cota_tva_procent)}%):</b>", s_normal), Paragraph(f"<b>{formateaza_numar_ro(tva)} {moneda}</b>", ParagraphStyle('R', parent=s_normal, alignment=TA_RIGHT))],
        ["", Paragraph("<b>TOTAL GENERAL:</b>", ParagraphStyle('Big', parent=s_bold, fontSize=10)), Paragraph(f"<b>{formateaza_numar_ro(total_general)} {moneda}</b>", ParagraphStyle('BigR', parent=s_bold, fontSize=10, alignment=TA_RIGHT))]
    ], colWidths=[260, 155, 120])
    t_totaluri.setStyle(TableStyle([
        ('LINEABOVE', (1,2), (2,2), 1, colors.HexColor("#1E293B")),
        ('BACKGROUND', (1,2), (2,2), colors.HexColor("#F1F5F9")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t_totaluri)
    elements.append(Spacer(1, 10))

    if data.get('observatii'):
        elements.append(Paragraph("MENȚIUNI / OBSERVAȚII", s_sec_title))
        elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))
        linii_obs = [l.strip() for l in str(data.get('observatii')).split('\n') if l.strip()]
        obs_formatat = "<br/>".join([l if l.startswith("-") or l.startswith("•") else f"- {l}" for l in linii_obs])
        elements.append(Paragraph(obs_formatat, s_normal))

    intocmit_de_txt = str(data.get('intocmit_de') or setari.get('intocmit_de_implicit') or 'Echipa Nexus Industrial').strip()
    acceptat_de_txt = str(data.get('acceptat_de') or '').strip()
    reprez_beneficiar = acceptat_de_txt if acceptat_de_txt else str(data.get('client', ''))

    elements.append(Spacer(1, 18))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
    semnaturi_data = [
        [Paragraph("<b>ÎNTOCMIT / EMIS DE</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER)),
         Paragraph("<b>ACCEPTAT / BENEFICIAR</b>", ParagraphStyle('C', parent=s_bold, alignment=TA_CENTER))],
        [Paragraph(f"Reprezentant: {intocmit_de_txt}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph(f"Reprezentant: {reprez_beneficiar}", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))],
        [Spacer(1, 16), Spacer(1, 16)],
        [Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER)),
         Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=TA_CENTER))]
    ]
    elements.append(Table(semnaturi_data, colWidths=[265, 270]))

    doc.build(
        elements,
        onFirstPage=lambda c, d: draw_header_footer(c, d, titlu_banner, centreaza_titlu=True, font_size_titlu=10.5),
        onLaterPages=lambda c, d: draw_header_footer(c, d, titlu_banner, centreaza_titlu=True, font_size_titlu=10.5)
    )
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------------------
# 4. FIȘĂ DE MENTENANȚĂ PREVENTIVĂ & AUDIT TEHNIC
# ------------------------------------------------------------------------------
def genereaza_pdf_mentenanta(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=58, bottomMargin=32)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    s_tbl = ParagraphStyle('SMentTbl', parent=s_normal, fontSize=8.3, leading=11)
    s_tbl_bold = ParagraphStyle('SMentTblBold', parent=s_bold, fontSize=8.3, leading=11)
    s_tbl_center = ParagraphStyle('SMentTblCenter', parent=s_tbl, alignment=TA_CENTER)
    setari = get_date_firma_mea()

    elements.append(_construieste_antet_cu_sigla(
        setari=setari,
        titlu_dreapta="FIȘĂ MENTENANȚĂ",
        nr_text=f"#{data.get('id', '')}",
        data_text=str(data.get('data_interventie', ''))[:10],
        s_normal=s_normal,
        s_bold=s_bold,
        s_small=s_small,
        include_banca_iban=False,
    ))
    elements.append(Spacer(1, 6))

    urmat_str = str(data.get('urmatoarea_revizie') or '-')[:10]
    id_rows = [
        [
            Paragraph(f"<b>Beneficiar / Client:</b> {data.get('firma_nume', '')}", s_tbl),
            Paragraph(f"<b>Punct de Lucru / Oraș:</b> {data.get('punct_lucru', '')}", s_tbl)
        ],
        [
            Paragraph(f"<b>Denumire Echipament:</b> {data.get('masina_nume', '')}", s_tbl),
            Paragraph(f"<b>Producător / Model:</b> {data.get('producator_model', '')}", s_tbl)
        ],
        [
            Paragraph(f"<b>Serie Fabricație:</b> {data.get('serie_fabricatie', '')}", s_tbl),
            Paragraph(f"<b>Nr. Inventar Intern:</b> {data.get('nr_inventar', '')}", s_tbl)
        ],
        [
            Paragraph(f"<b>Ore Funcționare Utilaj:</b> {data.get('ore_functionare') or '-'} ore", s_tbl),
            Paragraph(f"<b>Ore Cumulate / Următoarea Revizie:</b> {data.get('ore_cumulate') or '-'} | {urmat_str}", s_tbl)
        ],
        [
            Paragraph(f"<b>Nivel Grilă Aplicabilă:</b> {data.get('nivel_grila', '')}", s_tbl),
            Paragraph(f"<b>Stare Inițială:</b> {data.get('stare_initiala', '')}", s_tbl)
        ],
        [
            Paragraph(f"<b>Stare Finală Utilaj:</b> <b>{data.get('stare_finala', '')}</b>", s_tbl),
            ""
        ]
    ]
    t_id = Table(id_rows, colWidths=[270, 269])
    t_id.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor("#EEF2FF")),
        ('SPAN', (0, 5), (1, 5)),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_id)
    elements.append(Spacer(1, 8))

    checklist = data.get("checklist_json") or {}
    if isinstance(checklist, str):
        try:
            checklist = json.loads(checklist)
        except Exception:
            checklist = {}

    ordine_chei = [
        "electric_decuplat",
        "electric_cuplat",
        "mecanic",
        "hidraulic",
        "pneumatic",
        "vacuum",
        "auxiliare"
    ]

    for s_key in ordine_chei:
        sec_data = checklist.get(s_key)
        if not sec_data:
            continue
        if sec_data.get("activ") is False:
            continue

        elements.append(Paragraph(sec_data.get("titlu", s_key).upper(), s_sec_title))
        elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=3))

        randuri = sec_data.get("randuri", [])
        tbl_rows = [[
            Paragraph("<b>Specificație Operațiune</b>", s_tbl_bold),
            Paragraph("<b>Conformitate</b>", ParagraphStyle('CC', parent=s_tbl_bold, alignment=TA_CENTER)),
            Paragraph("<b>Observații / Valori Măsurate</b>", s_tbl_bold)
        ]]

        for r in randuri:
            conf = str(r.get("Conformitate") or "N/A").strip().upper()
            if conf == "DA":
                conf_html = "<b>[X] DA</b>  [ ] NU  [ ] N/A"
            elif conf == "NU":
                conf_html = "[ ] DA  <font color='#B91C1C'><b>[X] NU</b></font>  [ ] N/A"
            else:
                conf_html = "[ ] DA  [ ] NU  <b>[X] N/A</b>"

            tbl_rows.append([
                Paragraph(str(r.get("Operațiune", "")), s_tbl),
                Paragraph(conf_html, s_tbl_center),
                Paragraph(str(r.get("Observații / Valori Măsurate", "") or ""), s_tbl)
            ])

        t_sec = Table(tbl_rows, colWidths=[285, 114, 140], repeatRows=1)
        t_sec.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 3.5),
        ]))
        elements.append(t_sec)

        necesar_txt = str(sec_data.get("necesar_text") or "").strip()
        if necesar_txt:
            nec_lbl = sec_data.get("necesar_label") or "Piese / Observații"
            elements.append(Spacer(1, 3))
            elements.append(Paragraph(f"<b>{nec_lbl}:</b> {necesar_txt.replace(chr(10), '<br/>')}", s_tbl))

        elements.append(Spacer(1, 6))

    recomandari_iiot = str(data.get("recomandari_iiot") or "").strip()
    elements.append(Paragraph("7. RECOMANDĂRI TEHNICE, AUDIT UPGRADE / IIoT & RECEPȚIE LUCRĂRI", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))
    elements.append(Paragraph(
        recomandari_iiot.replace("\n", "<br/>") if recomandari_iiot else "Fără recomandări suplimentare.", s_normal))
    elements.append(Spacer(1, 14))

    tehnician_def = setari.get('tehnician_implicit') or 'Tehnician Nexus'
    nume_beneficiar = str(data.get('verificator') or 'Client').strip()
    functie_ben = str(data.get('functie_verificator') or '').strip()
    linie_functie = f"<br/>Funcție: {functie_ben}" if functie_ben else ""

    semnaturi_data = [
        [
            Paragraph("<b>PRESTATOR (INGINER / TEHNICIAN SERVICE)</b>", ParagraphStyle('C1', parent=s_tbl_bold, alignment=TA_CENTER)),
            Paragraph("<b>BENEFICIAR / CLIENT (VERIFICAT & RECEPȚIONAT)</b>", ParagraphStyle('C2', parent=s_tbl_bold, alignment=TA_CENTER))
        ],
        [
            Paragraph(f"Nume & Prenume: {data.get('tehnician') or tehnician_def}", ParagraphStyle('C3', parent=s_tbl, alignment=TA_CENTER)),
            Paragraph(f"Nume & Prenume: {nume_beneficiar}{linie_functie}", ParagraphStyle('C4', parent=s_tbl, alignment=TA_CENTER))
        ],
        [Spacer(1, 16), Spacer(1, 16)],
        [
            Paragraph("Semnătură: ___________________________", ParagraphStyle('C5', parent=s_tbl, alignment=TA_CENTER)),
            Paragraph("Semnătură: ___________________________", ParagraphStyle('C6', parent=s_tbl, alignment=TA_CENTER))
        ]
    ]
    t_semn = Table(semnaturi_data, colWidths=[269, 270])
    t_semn.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('LINEBEFORE', (1, 0), (1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_semn)

    doc.build(
        elements,
        onFirstPage=lambda c, d: draw_header_footer(c, d, "FIȘĂ DE MENTENANȚĂ PREVENTIVĂ & AUDIT TEHNIC", centreaza_titlu=True, font_size_titlu=11),
        onLaterPages=lambda c, d: draw_header_footer(c, d, "FIȘĂ DE MENTENANȚĂ PREVENTIVĂ & AUDIT TEHNIC", centreaza_titlu=True, font_size_titlu=11)
    )
    buffer.seek(0)
    return buffer.getvalue()