from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io

def genereaza_pdf_electronic(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor("#1A365D"), alignment=1)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#2D3748"))
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName="Helvetica-Bold")

    elements.append(Paragraph(f"<b>RAPORT REPARAȚIE ELECTRONICĂ / MECATRONICĂ #{data.get('id')}</b>", title_style))
    elements.append(Spacer(1, 15))

    # Detalii generale
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

    # Componente implicate
    elements.append(Paragraph("<b>Componente Electronice / Elemente Înlocuite sau Reparate:</b>", bold_style))
    elements.append(Spacer(1, 5))

    comp_table_data = [["Componentă / Cod & Parametri", "Stare Componentă"]]
    for comp in data.get('componente_json', []):
        comp_table_data.append([
            comp.get('Componenta / Cod / Parametri', ''),
            comp.get('Stare', 'Necesara')
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