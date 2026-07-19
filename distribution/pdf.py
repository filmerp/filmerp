from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.files.base import ContentFile
from django.db.models import Sum
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PRIMARY = colors.HexColor("#0058f8")
ACCENT = colors.HexColor("#1d2327")
LIGHT = colors.HexColor("#eef5f6")
BORDER = colors.HexColor("#cfd8dc")
FONT_REGULAR = "FILMERPUbuntu"
FONT_BOLD = "FILMERPUbuntuBold"


def _register_statement_fonts():
    font_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    font_files = {
        FONT_REGULAR: "Ubuntu-R.ttf",
        FONT_BOLD: "Ubuntu-B.ttf",
    }
    registered = set(pdfmetrics.getRegisteredFontNames())
    for font_name, file_name in font_files.items():
        if font_name not in registered:
            pdfmetrics.registerFont(TTFont(font_name, font_dir / file_name))
    pdfmetrics.registerFontFamily(
        FONT_REGULAR,
        normal=FONT_REGULAR,
        bold=FONT_BOLD,
        italic=FONT_REGULAR,
        boldItalic=FONT_BOLD,
    )


_register_statement_fonts()


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
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
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
    styles.add(ParagraphStyle(name="Eyebrow", parent=styles["Normal"], fontSize=8, leading=10, textColor=PRIMARY, fontName=FONT_BOLD))
    styles.add(ParagraphStyle(name="StatementTitle", parent=styles["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#1f2933"), alignment=0, fontName=FONT_BOLD))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading3"], fontSize=11, leading=14, textColor=PRIMARY, spaceBefore=12, spaceAfter=6, fontName=FONT_BOLD))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7.5, leading=10, textColor=colors.HexColor("#4b5563"), fontName=FONT_REGULAR))
    styles.add(ParagraphStyle(name="Amount", parent=styles["Small"], alignment=2, textColor=colors.black))
    styles.add(ParagraphStyle(name="TableHeader", parent=styles["Normal"], fontSize=7, leading=8, textColor=colors.white, fontName=FONT_BOLD))

    def bilingual_label(english, polish, *, inverse=False):
        primary_color = "#ffffff" if inverse else "#4b5563"
        secondary_color = "#dbeafe" if inverse else "#667085"
        return Paragraph(
            f"<font color='{primary_color}'><b>{escape(english)}</b></font>"
            f"<br/><font size='7' color='{secondary_color}'>{escape(polish)}</font>",
            styles["Small"],
        )

    def bilingual_header(english, polish):
        return Paragraph(
            f"{escape(english)}<br/><font size='6' color='#dbeafe'>{escape(polish)}</font>",
            styles["TableHeader"],
        )

    sales = list(statement.sales_queryset().select_related("counterparty", "territory"))
    costs = list(statement.recoupable_costs_queryset().select_related("supplier"))
    deductions = statement.deductions_total
    withholding = statement.withholding_tax_total
    run = statement.waterfall_run
    recovered_by_cost = {}
    if run:
        for row in run.lines.order_by().values("cost_allocations__cost_id").annotate(total=Sum("cost_allocations__allocated_amount")):
            if row["cost_allocations__cost_id"]:
                recovered_by_cost[row["cost_allocations__cost_id"]] = row["total"] or Decimal("0.00")
    document_number = f"RS-{statement.pk:06d}"

    story = [
        Paragraph("FILMERP / ROYALTY ACCOUNTING", styles["Eyebrow"]),
        Paragraph("Royalty Statement", styles["StatementTitle"]),
        Spacer(1, 2 * mm),
    ]
    identity = [
        [bilingual_label("Document", "Dokument"), Paragraph(document_number, styles["Small"]), bilingual_label("Generated", "Wygenerowano"), Paragraph(timezone.localdate().isoformat(), styles["Small"])],
        [bilingual_label("Title", "Tytuł"), Paragraph(escape(str(statement.title)), styles["Small"]), bilingual_label("Currency", "Waluta"), Paragraph(statement.currency, styles["Small"])],
        [bilingual_label("Recipient", "Odbiorca"), Paragraph(escape(str(statement.recipient)), styles["Small"]), bilingual_label("Period", "Okres"), Paragraph(f"{statement.period_start} - {statement.period_end}", styles["Small"])],
        [bilingual_label("Calculation Basis", "Podstawa kalkulacji"), Paragraph(escape(statement.calculation_basis_label), styles["Small"]), bilingual_label("Status", "Status"), Paragraph(escape(statement.get_status_display()), styles["Small"])],
    ]
    identity_table = Table(identity, colWidths=[35 * mm, 57 * mm, 34 * mm, 50 * mm])
    identity_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
        ("FONTNAME", (2, 0), (2, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([identity_table, Paragraph("Settlement Summary / Podsumowanie rozliczenia", styles["Section"])])

    recoupment_label = (
        bilingual_label("Cost Recoupment in Waterfall", "Koszty odzyskane w waterfallu")
        if run
        else bilingual_label("Recoupable Costs", "Koszty podlegające odzyskaniu")
    )
    fee_label = (
        bilingual_label("Commission Allocations", "Alokacje prowizji")
        if run
        else bilingual_label("Distributor Fee", "Prowizja dystrybutora")
    )
    remaining_label = (
        bilingual_label("Closing Balance", "Saldo końcowe waterfall")
        if run
        else bilingual_label("Net Receipts", "Wpływy netto do podziału")
    )
    summary = [
        [bilingual_label("Gross Receipts", "Przychody brutto dystrybucyjne"), money(statement.gross_revenue, statement.currency)],
        [bilingual_label("Deductions", "Potrącenia dystrybucyjne"), money(deductions, statement.currency)],
        [bilingual_label("Taxes / Withholding", "Podatki i potrącenia u źródła"), money(withholding, statement.currency)],
        [bilingual_label("Net Revenue", "Przychody netto dystrybucyjne"), money(statement.net_revenue, statement.currency)],
        [recoupment_label, money(statement.recoupable_costs, statement.currency)],
        [fee_label, money(statement.distributor_fee_amount, statement.currency)],
        [remaining_label, money(statement.net_receipts, statement.currency)],
    ]
    if not run:
        summary.append([
            bilingual_label("Participant Share", "Udział odbiorcy"),
            f"{statement.applied_recipient_share_percent:.2f}%",
        ])
    summary.append([
        bilingual_label("AMOUNT DUE TO PARTICIPANT", "KWOTA NALEŻNA ODBIORCY", inverse=True),
        money(statement.amount_due, statement.currency),
    ])
    summary_table = Table(summary, colWidths=[116 * mm, 60 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), PRIMARY),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
    ]))
    if run:
        calculation_note = (
            "<b>Calculation logic / Logika kalkulacji:</b> Amount Due is the sum of allocations assigned "
            "to this participant in the approved waterfall. / Kwota należna jest sumą alokacji przypisanych "
            "temu odbiorcy w zatwierdzonym waterfallu."
        )
    else:
        calculation_note = (
            "<b>Calculation logic / Logika kalkulacji:</b> Gross Receipts - Deductions - Taxes / Withholding "
            "= Net Revenue; Net Revenue - Recoupable Costs - Distributor Fee = Net Receipts; Net Receipts x "
            "Participant Share = Amount Due."
        )
    story.extend([summary_table, Spacer(1, 2 * mm), Paragraph(calculation_note, styles["Small"])])

    if run:
        recipient_lines = list(run.lines.filter(beneficiary=statement.recipient).select_related("step"))
        story.append(Paragraph("Recipient Waterfall / Waterfall odbiorcy", styles["Section"]))
        waterfall_rows = [[
            bilingual_header("Phase / Step", "Faza / krok"),
            bilingual_header("Calculation Base", "Podstawa"),
            bilingual_header("Allocation", "Alokacja"),
            bilingual_header("Recoupment Balance", "Saldo recoupment"),
        ]]
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

    story.append(Paragraph("Revenue Detail / Szczegóły przychodów", styles["Section"]))
    sales_rows = [[
        bilingual_header("Source / Right", "Źródło / pole"),
        bilingual_header("Territory", "Terytorium"),
        bilingual_header("Period", "Okres"),
        bilingual_header("Gross Receipts", "Przychody brutto"),
        bilingual_header("Deductions", "Potrącenia"),
        bilingual_header("Taxes / WHT", "Podatki / WHT"),
        bilingual_header("Net Revenue", "Przychody netto"),
    ]]
    for report in sales:
        sales_rows.append([
            Paragraph(f"{escape(report.counterparty.name)}<br/>{escape(report.get_exploitation_field_display())}", styles["Small"]),
            Paragraph(escape(report.territory.name if report.territory else "-"), styles["Small"]),
            Paragraph(f"{report.period_start}<br/>{report.period_end}", styles["Small"]),
            Paragraph(money(report.gross_revenue, report.currency), styles["Amount"]),
            Paragraph(money(report.deductions, report.currency), styles["Amount"]),
            Paragraph(money(report.vat_withholding, report.currency), styles["Amount"]),
            Paragraph(money(report.net_revenue, report.currency), styles["Amount"]),
        ])
    if len(sales_rows) == 1:
        sales_rows.append(["No revenue reports in this period.", "", "", "", "", "", ""])
    sales_table = Table(sales_rows, repeatRows=1, colWidths=[38 * mm, 22 * mm, 28 * mm, 23 * mm, 22 * mm, 22 * mm, 22 * mm])
    sales_table.setStyle(_table_style(amount_column=6))
    story.append(sales_table)

    story.append(Paragraph("Recoupable Costs / Koszty podlegające odzyskaniu", styles["Section"]))
    cost_rows = [[
        bilingual_header("Category", "Kategoria"),
        bilingual_header("Date", "Data"),
        bilingual_header("Supplier", "Dostawca"),
        bilingual_header("Scope", "Zakres"),
        bilingual_header("Recovered in Run", "Odzyskano w rozliczeniu") if run else bilingual_header("Recoupable Amount", "Kwota do odzyskania bez VAT"),
    ]]
    for cost in costs:
        scope = cost.scope_label or "-"
        cost_rows.append([
            cost.get_category_display(),
            str(cost.cost_date),
            Paragraph(escape(cost.supplier.name if cost.supplier else "-"), styles["Small"]),
            Paragraph(escape(scope), styles["Small"]),
            money(recovered_by_cost.get(cost.pk, cost.net_amount), cost.currency),
        ])
    if len(cost_rows) == 1:
        cost_rows.append(["No recoupable costs in this period.", "", "", "", ""])
    cost_table = Table(cost_rows, repeatRows=1, colWidths=[38 * mm, 25 * mm, 48 * mm, 38 * mm, 28 * mm])
    cost_table.setStyle(_table_style(amount_column=4))
    story.extend([cost_table, Spacer(1, 8 * mm), Paragraph("Generated from a locked FILMERP calculation snapshot. Source records are identified in the statement audit data.", styles["Small"])])

    def draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, 7)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(16 * mm, 8 * mm, f"FILMERP / {document_number}")
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    filename = f"royalty_statement_{statement.pk}_{statement.period_end}.pdf"
    return ContentFile(buffer.getvalue(), name=filename)
