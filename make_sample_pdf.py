from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

styles = getSampleStyleSheet()
text = "NeuroFlow is a retrieval augmented generation platform. " * 12
table = Table([["Name", "Role", "Score"], ["Asha", "Engineer", "92"], ["Ravi", "Analyst", "87"]])
table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))

SimpleDocTemplate("sample.pdf", pagesize=A4).build([
    Paragraph("Page one: introduction", styles["Heading1"]),
    Paragraph(text, styles["Normal"]),
    PageBreak(),
    Paragraph("Page two: results", styles["Heading1"]),
    Paragraph(text, styles["Normal"]),
    table,
])