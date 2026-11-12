#----------------------------------
#-------pdf_service.py-------------
#----------------------------------

import io
import os
import json
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from config import db_cursor

# 1. Configurare Font cu suport complet pentru diacritice românești (UTF-8)
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

def get_date_firma_mea():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM setari LIMIT 1")
        res = cur.fetchone()
    if res:
        return res
    return {
        "nume_firma_mea": "Nexus Industrial SRL", "cui_mea": "", "reg_com_mea": "",
        "adresa_mea": "", "banca_mea": "", "iban_mea": "", "swep_mea": ""
    }

def draw_header_footer(canvas, doc, titlu_document="RAPORT DE INTERVENȚIE TEHNICĂ"):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1E293B"))
    canvas.rect(0, A4[1] - 55, A4[0], 55, fill=1, stroke=0)
    
    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, 14)
    canvas.drawString(30, A4[1] - 34, titlu_document)
    
    canvas.setFont(FONT_REG, 9)
    canvas.drawRightString(A4[0] - 30, A4[1] - 34, "DOCUMENT OFICIAL")
    
    canvas.setFont(FONT_REG, 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(A4[0] / 2.0, 20, f"Pagina {doc.page} | Raport generat automat")
    canvas.restoreState()

def creeaza_stiluri():
    styles = getSampleStyleSheet()
    s_normal = ParagraphStyle('SNormal', parent=styles['Normal'], fontName=FONT_REG, fontSize=9, leading=13, textColor=colors.black)
    s_bold = ParagraphStyle('SBold', parent=s_normal, fontName=FONT_BOLD)
    s_small = ParagraphStyle('SSmall', parent=s_normal, fontSize=8, textColor=colors.HexColor("#475569"))
    s_sec_title = ParagraphStyle('SSecTitle', parent=s_normal, fontName=FONT_BOLD, fontSize=9.5, textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=2)
    return s_normal, s_bold, s_small, s_sec_title

# ------------------------------------------------------------------------------
# 1. RAPORT INTERVENȚIE TEHNICĂ (STANDARD / MECANIC)
# ------------------------------------------------------------------------------
def genereaza_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=65, bottomMargin=35)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    setari = get_date_firma_mea()

    # Datele firmei prestatoare
    elements.append(Paragraph(f"<b>{setari.get('nume_firma_mea', '')}</b> | CUI: {setari.get('cui_mea', '')} | Reg. Com.: {setari.get('reg_com_mea', '')}", s_normal))
    elements.append(Paragraph(f"Adresă: {setari.get('adresa_mea', '')} | Bancă: {setari.get('banca_mea', '')} | IBAN: {setari.get('iban_mea', '')} | SWIFT: {setari.get('swep_mea', '')}", s_small))
    elements.append(Spacer(1, 8))

    # Nr. Înregistrare și Data
    t_nr = Table([
        [Paragraph(f"<b>Nr. Înregistrare: #{data.get('id', '')}</b>", s_normal),
         Paragraph(f"<b>Data: {str(data.get('data', ''))[:10]}</b>", ParagraphStyle('Right', parent=s_normal, alignment=2))]
    ], colWidths=[265, 270])
    t_nr.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,0), 0.8, colors.HexColor("#CBD5E1")), ('BOTTOMPADDING', (0,0), (-1,0), 4)]))
    elements.append(t_nr)
    elements.append(Spacer(1, 8))

    # Calcul durată în format ore:minute (ex: 02:00)
    durata_min = int(data.get('durata') or 0)
    ore = durata_min // 60
    minute = durata_min % 60
    durata_formatata = f"{ore:02d}:{minute:02d} (ore:minute)"

    # Caseta Detalii Client & Detalii Echipament
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

    def adauga_sectiune(titlu, text):
        elements.append(Paragraph(titlu.upper(), s_sec_title))
        elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))
        text_formatat = str(text or "Nespecificat").replace("\n", "<br/>")
        elements.append(Paragraph(text_formatat, s_normal))
        elements.append(Spacer(1, 4))

    # 1. Titlu Lucrare + Tipul intervenției
    titlu_baza = data.get('titlu') or "Intervenție tehnică"
    tip_interv = data.get('tip_interventie') or ""
    titlu_complet = f"{titlu_baza} - {tip_interv}" if tip_interv else titlu_baza
    adauga_sectiune("Titlu Lucrare", titlu_complet)

    # 2. Simptom Inițial și Defect pe rânduri separate
    simptom_text = str(data.get('simptom') or "Nespecificat").replace("\n", "<br/>")
    defect_text = str(data.get('defect') or "Nespecificat").replace("\n", "<br/>")
    simptom_defect_separat = f"<b>Simptom inițial:</b> {simptom_text}<br/><br/><b>Defect constatat:</b> {defect_text}"
    adauga_sectiune("Simptom Inițial / Defect", simptom_defect_separat)

    # 3. Soluție
    adauga_sectiune("Soluție / Lucrări Executate", data.get('solutie'))

    # Tabel Piese
    elements.append(Paragraph("TABEL PIESE (UTILIZATE / ÎNLOCUITE / NECESARE / COMANDAT)", s_sec_title))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94A3B8"), spaceAfter=4))

    piese_list = data.get('piese_json', [])
    if isinstance(piese_list, str):
        try: piese_list = json.loads(piese_list)
        except: piese_list = []

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
        adauga_sectiune("Recomandări Tehnice & Siguranță", data.get('optimizari'))

    # Semnături
    elements.append(Spacer(1, 14))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
    semnaturi_data = [
        [Paragraph("<b>EFECTUAT DE (TEHNICIAN)</b>", ParagraphStyle('C', parent=s_bold, alignment=1)),
         Paragraph("<b>VERIFICAT / RECEPȚIONAT DE</b>", ParagraphStyle('C', parent=s_bold, alignment=1))],
        [Paragraph(f"Nume: {data.get('tehnician') or 'Tehnician Nexus'}", ParagraphStyle('C', parent=s_normal, alignment=1)),
         Paragraph(f"Nume: {data.get('verificator') or 'Client'}", ParagraphStyle('C', parent=s_normal, alignment=1))],
        [Spacer(1, 18), Spacer(1, 18)],
        [Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=1)),
         Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=1))]
    ]
    t_semn = Table(semnaturi_data, colWidths=[265, 270])
    elements.append(t_semn)

    doc.build(elements, onFirstPage=lambda c, d: draw_header_footer(c, d, "RAPORT DE INTERVENȚIE TEHNICĂ"),
              onLaterPages=lambda c, d: draw_header_footer(c, d, "RAPORT DE INTERVENȚIE TEHNICĂ"))
    buffer.seek(0)
    return buffer.getvalue()

# ------------------------------------------------------------------------------
# 2. RAPORT REPARAȚIE ELECTRONICĂ / MECATRONICĂ
# ------------------------------------------------------------------------------
def genereaza_pdf_electronic(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=65, bottomMargin=35)
    elements = []
    s_normal, s_bold, s_small, s_sec_title = creeaza_stiluri()
    setari = get_date_firma_mea()

    elements.append(Paragraph(f"<b>{setari.get('nume_firma_mea', '')}</b> | CUI: {setari.get('cui_mea', '')} | Reg. Com.: {setari.get('reg_com_mea', '')}", s_normal))
    elements.append(Paragraph(f"Adresă: {setari.get('adresa_mea', '')} | Bancă: {setari.get('banca_mea', '')} | IBAN: {setari.get('iban_mea', '')} | SWIFT: {setari.get('swep_mea', '')}", s_small))
    elements.append(Spacer(1, 8))

    t_nr = Table([
        [Paragraph(f"<b>Nr. Fișă Electronică: #{data.get('id', '')}</b>", s_normal),
         Paragraph(f"<b>Data: {str(data.get('data', ''))[:10]}</b>", ParagraphStyle('Right', parent=s_normal, alignment=2))]
    ], colWidths=[265, 270])
    t_nr.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,0), 0.8, colors.HexColor("#CBD5E1")), ('BOTTOMPADDING', (0,0), (-1,0), 4)]))
    elements.append(t_nr)
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
    elements.append(Paragraph(str(data.get('defect_reclamat') or "Nespecificat").replace("\n", "<br/>"), s_normal))
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
    semnaturi_data = [
        [Paragraph("<b>EFECTUAT DE (TEHNICIAN ELECTRONICĂ)</b>", ParagraphStyle('C', parent=s_bold, alignment=1)),
         Paragraph("<b>VERIFICAT / RECEPȚIONAT DE</b>", ParagraphStyle('C', parent=s_bold, alignment=1))],
        [Paragraph(f"Nume: {data.get('tehnician') or 'Tehnician Service'}", ParagraphStyle('C', parent=s_normal, alignment=1)),
         Paragraph(f"Nume: {data.get('verificator') or 'Client'}", ParagraphStyle('C', parent=s_normal, alignment=1))],
        [Spacer(1, 18), Spacer(1, 18)],
        [Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=1)),
         Paragraph("Semnătură: ___________________", ParagraphStyle('C', parent=s_normal, alignment=1))]
    ]
    elements.append(Table(semnaturi_data, colWidths=[265, 270]))

    doc.build(elements, onFirstPage=lambda c, d: draw_header_footer(c, d, "RAPORT REPARAȚIE ELECTRONICĂ"),
              onLaterPages=lambda c, d: draw_header_footer(c, d, "RAPORT REPARAȚIE ELECTRONICĂ"))
    buffer.seek(0)
    return buffer.getvalue()