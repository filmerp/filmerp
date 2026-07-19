from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PRIMARY = colors.HexColor("#2271b1")
ACCENT = colors.HexColor("#1d2327")
LIGHT = colors.HexColor("#eef5f6")
BORDER = colors.HexColor("#cfd8dc")


def money(value: Decimal, currency: str) -> str:
    return f"{value:,.2f} {currency}".replace(",", " ")


def _table_style(*, header=True, amount_column=None):
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
        ])
    commands.append(("FONTSIZE", (0, 1 if header else 0), (-1, -1), 7.5))
    if amount_column is not None:
        commands.append(("ALIGN", (amount_column, 1 if header else 0), (amount_column, -1), "RIGHT"))
    return TableStyle(commands)


def build_royalty_statement_pdf(statement) -> ContentFile:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Royalty Statement RS-{statement.pk:06d}",
        author="FILMERP",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Eyebrow", parent=styles["Normal"], fontSize=8, leading=10, textColor=PRIMARY, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="StatementTitle", parent=styles["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#1f2933"), alignment=0))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading3"], fontSize=11, leading=14, textColor=PRIMARY, spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.5, leading=10, textColor=colors.HexColor("#4b5563")))
    styles.add(ParagraphStyle(name="Amount", parent=styles["Small"], alignment=2, textColor=colors.black))

    sales = list(statement.sales_queryset().select_related("counterparty", "territory"))
    costs = list(statement.recoupable_costs_queryset().select_related("supplier"))
    deductions = sum((report.deductions for report in sales), Decimal("0.00"))
    withholding = sum((report.vat_withholding for report in sales), Decimal("0.00"))
    run = statement.waterfall_run
    document_number = f"RS-{statement.pk:06d}"

    story = [
        Paragraph("FILMERP / ROYALTY ACCOUNTING", styles["Eyebrow"]),
        Paragraph("Royalty Statement", styles["StatementTitle"]),
        Spacer(1, 2 * mm),
    ]
    identity = [
        ["Document", document_number, "Generated", timezone.localdate().isoformat()],
        ["Title", Paragraph(escape(str(statement.title)), styles["Small"]), "Currency", statement.currency],
        ["Recipient", Paragraph(escape(str(statement.recipient)), styles["Small"]), "Period", f"{statement.period_start} - {statement.period_end}"],
    ]
    if statement.waterfall_plan_id:
        identity.append(["Calculation basis", Paragraph(escape(f"{statement.waterfall_plan.name}, version {statement.waterfall_plan.version}"), styles["Small"]), "Status", statement.get_status_display()])
    identity_table = Table(identity, colWidths=[28 * mm, 67 * mm, 25 * mm, 56 * mm])
    identity_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([identity_table, Paragraph("Settlement summary", styles["Section"])])

    remaining_label = "Remaining after waterfall" if run else "Net receipts"
    summary = [
        ["Gross revenue", money(statement.gross_revenue, statement.currency)],
        ["Reported deductions", money(deductions, statement.currency)],
        ["VAT / withholding", money(withholding, statement.currency)],
        ["Net revenue", money(statement.net_revenue, statement.currency)],
        ["Recoupable costs in period", money(statement.recoupable_costs, statement.currency)],
        [remaining_label, money(statement.net_receipts, statement.currency)],
        ["AMOUNT DUE TO RECIPIENT", money(statement.amount_due, statement.currency)],
    ]
    summary_table = Table(summary, colWidths=[116 * mm, 60 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), PRIMARY),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
    ]))
    story.append(summary_table)

    if run:
        recipient_lines = list(run.lines.filter(beneficiary=statement.recipient).select_related("step"))
        story.append(Paragraph("Recipient waterfall", styles["Section"]))
        waterfall_rows = [["Phase / step", "Opening base", "Allocation", "Recoupment balance"]]
        for line in recipient_lines:
            waterfall_rows.append([
                Paragraph(escape(f"{line.phase}. {line.step.name}"), styles["Small"]),
                money(line.calculation_base, statement.currency),
                money(line.allocated_amount, statement.currency),
                f"{money(line.opening_recoupment, statement.currency)} -> {money(line.closing_recoupment, statement.currency)}",
            ])
        if len(waterfall_rows) == 1:
            waterfall_rows.append(["No allocation lines for this recipient.", "", "", ""])
        waterfall_table = Table(waterfall_rows, repeatRows=1, colWidths=[65 * mm, 35 * mm, 35 * mm, 41 * mm])
        waterfall_table.setStyle(_table_style(amount_column=2))
        story.append(waterfall_table)

    story.append(Paragraph("Revenue detail", styles["Section"]))
    sales_rows = [["Source / field", "Territory", "Period", "Gross", "Deductions", "Net"]]
    for report in sales:
        sales_rows.append([
            Paragraph(f"{escape(report.counterparty.name)}<br/>{escape(report.get_exploitation_field_display())}", styles["Small"]),
            Paragraph(escape(report.territory.name if report.territory else "-"), styles["Small"]),
            Paragraph(f"{report.period_start}<br/>{report.period_end}", styles["Small"]),
            Paragraph(money(report.gross_revenue, report.currency), styles["Amount"]),
            Paragraph(money(report.deductions + report.vat_withholding, report.currency), styles["Amount"]),
            Paragraph(money(report.net_revenue, report.currency), styles["Amount"]),
        ])
    if len(sales_rows) == 1:
        sales_rows.append(["No revenue reports in this period.", "", "", "", "", ""])
    sales_table = Table(sales_rows, repeatRows=1, colWidths=[44 * mm, 24 * mm, 31 * mm, 26 * mm, 28 * mm, 24 * mm])
    sales_table.setStyle(_table_style(amount_column=5))
    story.append(sales_table)

    story.append(Paragraph("Recoupable cost detail", styles["Section"]))
    cost_rows = [["Category", "Date", "Supplier", "Scope", "Net amount"]]
    for cost in costs:
        scope = "All fields" if cost.applies_to_all_exploitation_fields else ", ".join(sorted(cost.waterfall_exploitation_fields())) or "-"
        cost_rows.append([
            cost.get_category_display(),
            str(cost.cost_date),
            Paragraph(escape(cost.supplier.name if cost.supplier else "-"), styles["Small"]),
            Paragraph(escape(scope), styles["Small"]),
            money(cost.net_amount, cost.currency),
        ])
    if len(cost_rows) == 1:
        cost_rows.append(["No recoupable costs in this period.", "", "", "", ""])
    cost_table = Table(cost_rows, repeatRows=1, colWidths=[38 * mm, 25 * mm, 48 * mm, 38 * mm, 28 * mm])
    cost_table.setStyle(_table_style(amount_column=4))
    story.extend([cost_table, Spacer(1, 8 * mm), Paragraph("Generated from a locked FILMERP calculation snapshot. Source records are identified in the statement audit data.", styles["Small"])])

    def draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(16 * mm, 8 * mm, f"FILMERP / {document_number}")
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    filename = f"royalty_statement_{statement.pk}_{statement.period_end}.pdf"
    return ContentFile(buffer.getvalue(), name=filename)
