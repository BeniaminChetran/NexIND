#----------------------------------
#-------pdf_service.py-------------
#----------------------------------

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import json

def genereaza_pdf(data):
    """Generare raport PDF pentru intervenții mecanice/standard"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor("#1A365D"), alignment=1)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#2D3748"))
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName="Helvetica-Bold")

    elements.append(Paragraph(f"<b>RAPORT INTERVENȚIE TEHNICĂ #{data.get('id')}</b>", title_style))
    elements.append(Spacer(1, 15))

    info_data = [
        [Paragraph("<b>Client / Firmă:</b>", bold_style), Paragraph(data.get('client', ''), normal_style)],
        [Paragraph("<b>Mașină / Echipament:</b>", bold_style), Paragraph(data.get('masina', ''), normal_style)],
        [Paragraph("<b>Titlu Lucrare:</b>", bold_style), Paragraph(data.get('titlu', ''), normal_style)],
        [Paragraph("<b>Simptom / Defect:</b>", bold_style), Paragraph(data.get('defect', ''), normal_style)],
        [Paragraph("<b>Soluție Aplicată:</b>", bold_style), Paragraph(data.get('solutie', ''), normal_style)],
        [Paragraph("<b>Stare Finală:</b>", bold_style), Paragraph(data.get('stare_finala', ''), normal_style)],
        [Paragraph("<b>Durată Intervenție:</b>", bold_style), Paragraph(f"{data.get('durata', 0)} minute", normal_style)],
        [Paragraph("<b>Tehnician:</b>", bold_style), Paragraph(data.get('tehnician', ''), normal_style)],
        [Paragraph("<b>Verificat de:</b>", bold_style), Paragraph(data.get('verificator', ''), normal_style)],
        [Paragraph("<b>Data:</b>", bold_style), Paragraph(str(data.get('data', ''))[:19], normal_style)]
    ]
    
    t_info = Table(info_data, colWidths=[150, 380])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_info)
    elements.append(Spacer(1, 15))

    # Piese utilizate
    elements.append(Paragraph("<b>Piese / Materiale Implicate:</b>", bold_style))
    elements.append(Spacer(1, 5))

    piese_list = data.get('piese_json', [])
    if isinstance(piese_list, str):
        try: piese_list = json.loads(piese_list)
        except: piese_list = []

    p_table_data = [["Piesă", "Cantitate", "Tip"]]
    for p in piese_list:
        p_table_data.append([
            str(p.get('piesa', p.get('Piesa', ''))),
            str(p.get('cantitate', p.get('Cantitate', 1))),
            str(p.get('tip', p.get('Tip', '')))
        ])

    t_piese = Table(p_table_data, colWidths=[260, 100, 170])
    t_piese.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_piese)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def genereaza_pdf_electronic(data):
    """Generare raport PDF specific pentru reparații electronice / mecatronice"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor("#1A365D"), alignment=1)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#2D3748"))
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName="Helvetica-Bold")

    elements.append(Paragraph(f"<b>RAPORT REPARAȚIE ELECTRONICĂ / MECATRONICĂ #{data.get('id')}</b>", title_style))
    elements.append(Spacer(1, 15))

    info_data = [
        [Paragraph("<b>Client / Firmă:</b>", bold_style), Paragraph(data.get('client', ''), normal_style)],
        [Paragraph("<b>Echipament / Mașină:</b>", bold_style), Paragraph(data.get('masina', 'General / Fără mașină'), normal_style)],
        [Paragraph("<b>Piesă / Subansamblu:</b>", bold_style), Paragraph(data.get('piesa_subansamblu', ''), normal_style)],
        [Paragraph("<b>Defect Reclamat:</b>", bold_style), Paragraph(data.get('defect_reclamat', ''), normal_style)],
        [Paragraph("<b>Stare Finală:</b>", bold_style), Paragraph(data.get('stare_finala', ''), normal_style)],
        [Paragraph("<b>Tehnician:</b>", bold_style), Paragraph(data.get('tehnician', ''), normal_style)],
        [Paragraph("<b>Verificat de:</b>", bold_style), Paragraph(data.get('verificator', ''), normal_style)],
        [Paragraph("<b>Data:</b>", bold_style), Paragraph(str(data.get('data', ''))[:19], normal_style)]
    ]
    
    t_info = Table(info_data, colWidths=[150, 380])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_info)
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("<b>Componente Electronice / Elemente Înlocuite sau Reparate:</b>", bold_style))
    elements.append(Spacer(1, 5))

    comp_table_data = [["Componentă / Cod & Parametri", "Stare Componentă"]]
    for comp in data.get('componente_json', []):
        comp_table_data.append([
            str(comp.get('Componenta / Cod / Parametri', '')),
            str(comp.get('Stare', 'Necesara'))
        ])

    t_comp = Table(comp_table_data, colWidths=[380, 150])
    t_comp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_comp)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()