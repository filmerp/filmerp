from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def money(value: Decimal, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", " ")


def build_royalty_statement_pdf(statement) -> ContentFile:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Royalty Statement", styles["Title"]),
        Paragraph(f"{statement.title} / {statement.recipient}", styles["Heading2"]),
        Paragraph(f"Period: {statement.period_start} - {statement.period_end}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]

    summary = [
        ["Gross revenue", money(statement.gross_revenue, statement.currency)],
        ["Net revenue", money(statement.net_revenue, statement.currency)],
        ["Recoupable costs", money(statement.recoupable_costs, statement.currency)],
        [f"Distributor fee ({statement.distributor_fee_percent}%)", money(statement.distributor_fee_amount, statement.currency)],
        ["Net receipts", money(statement.net_receipts, statement.currency)],
        [f"Recipient share ({statement.recipient_share_percent}%)", money(statement.amount_due, statement.currency)],
    ]
    summary_table = Table(summary, colWidths=[105 * mm, 55 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f1ff")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([summary_table, Spacer(1, 8 * mm), Paragraph("Sales reports", styles["Heading3"])])

    sales_rows = [["Field", "Territory", "Period", "Gross", "Net"]]
    for report in statement.sales_queryset().select_related("territory"):
        sales_rows.append([
            report.get_exploitation_field_display(),
            report.territory.name if report.territory else "",
            f"{report.period_start} - {report.period_end}",
            money(report.gross_revenue, report.currency),
            money(report.net_revenue, report.currency),
        ])
    if len(sales_rows) == 1:
        sales_rows.append(["No sales reports in this period.", "", "", "", ""])
    sales_table = Table(sales_rows, colWidths=[35 * mm, 35 * mm, 45 * mm, 25 * mm, 25 * mm])
    sales_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(sales_table)

    story.extend([Spacer(1, 8 * mm), Paragraph("Recoupable costs", styles["Heading3"])])
    cost_rows = [["Category", "Date", "Supplier", "Net amount"]]
    for cost in statement.recoupable_costs_queryset().select_related("supplier"):
        cost_rows.append([
            cost.get_category_display(),
            str(cost.cost_date),
            cost.supplier.name if cost.supplier else "",
            money(cost.net_amount, cost.currency),
        ])
    if len(cost_rows) == 1:
        cost_rows.append(["No recoupable costs in this period.", "", "", ""])
    cost_table = Table(cost_rows, colWidths=[45 * mm, 30 * mm, 60 * mm, 30 * mm])
    cost_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cost_table)

    doc.build(story)
    filename = f"royalty_statement_{statement.pk}_{statement.period_end}.pdf"
    return ContentFile(buffer.getvalue(), name=filename)
