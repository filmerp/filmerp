import csv
from io import BytesIO
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .avails import check_availability
from .pdf import build_royalty_statement_pdf
from .models import (
    CinemaBooking,
    Cost,
    Counterparty,
    DeliveryStatus,
    ExploitationField,
    LanguageVersion,
    RightsIssue,
    RightsStatus,
    RightsWindow,
    RoyaltyStatement,
    SalesAgreement,
    SalesReport,
    StatementStatus,
    Territory,
    Title,
    TitleMaterial,
    WaterfallRecoupmentRule,
)
from .waterfall import calculate_waterfall


@login_required
def dashboard(request):
    today = timezone.localdate()
    expiring_until = today + timedelta(days=90)
    open_statements = RoyaltyStatement.objects.exclude(status=StatementStatus.PAID)

    revenue_by_title = (
        SalesReport.objects.values("title__title_pl")
        .annotate(gross=Sum("gross_revenue"), count=Count("id"))
        .order_by("-gross")[:10]
    )
    revenue_by_field = (
        SalesReport.objects.values("exploitation_field")
        .annotate(gross=Sum("gross_revenue"), count=Count("id"))
        .order_by("-gross")[:10]
    )

    context = {
        "titles_count": Title.objects.count(),
        "active_rights_count": RightsWindow.objects.exclude(status__in=[RightsStatus.EXPIRED, RightsStatus.CANCELLED]).count(),
        "expiring_rights": RightsWindow.objects.filter(date_to__gte=today, date_to__lte=expiring_until).order_by("date_to")[:10],
        "open_issues_count": RightsIssue.objects.filter(resolved=False).count(),
        "open_issues": RightsIssue.objects.filter(resolved=False).select_related("rights_window", "rights_window__title")[:10],
        "unpaid_agreements": SalesAgreement.objects.filter(invoice_paid=False, payment_due_date__lt=today).select_related("title", "licensee")[:10],
        "gross_revenue_total": SalesReport.objects.aggregate(total=Sum("gross_revenue"))["total"] or 0,
        "costs_total": Cost.objects.aggregate(total=Sum("net_amount"))["total"] or 0,
        "open_statements_count": open_statements.count(),
        "open_statements_amount": sum((statement.amount_due for statement in open_statements), 0),
        "revenue_by_title": revenue_by_title,
        "revenue_by_field": revenue_by_field,
    }
    return render(request, "distribution/dashboard.html", context)


@login_required
def title_list(request):
    query = request.GET.get("q", "").strip()
    titles_qs = Title.objects.select_related("producer").order_by("title_pl")
    if query:
        titles_qs = titles_qs.filter(
            Q(title_pl__icontains=query)
            | Q(original_title__icontains=query)
            | Q(ean__icontains=query)
            | Q(director__icontains=query)
            | Q(cast__icontains=query)
        )
    titles_qs = titles_qs[:200]
    context = {
        "query": query,
        "titles": titles_qs,
    }
    return render(request, "distribution/title_list.html", context)


@login_required
def title_detail(request, pk):
    title = get_object_or_404(Title.objects.select_related("producer"), pk=pk)
    today = timezone.localdate()

    rights_windows = (
        title.rights_windows.select_related("counterparty", "acquisition_agreement", "sales_agreement")
        .prefetch_related("territories", "language_versions")
        .order_by("exploitation_field", "date_from")
    )
    sales_reports = title.sales_reports.select_related("counterparty", "territory").order_by("-period_end")[:20]
    costs = title.costs.select_related("supplier").order_by("-cost_date")[:20]
    cinema_bookings = title.cinema_bookings.select_related("cinema").order_by("-date_from")[:20]
    royalty_statements = title.royalty_statements.select_related("recipient").order_by("-period_end")[:10]
    materials = title.materials.select_related("language_version", "supplier").order_by("asset_type", "due_date")
    issues = RightsIssue.objects.filter(rights_window__title=title, resolved=False).select_related("rights_window", "conflicting_window")
    waterfall_rules = title.waterfall_rules.prefetch_related("recoupment_items", "participants", "participants__recipient").order_by("exploitation_field", "currency")

    gross_box_office = title.cinema_bookings.aggregate(total=Sum("box_office_gross"))["total"] or 0
    admissions = title.cinema_bookings.aggregate(total=Sum("admissions"))["total"] or 0
    screenings = title.cinema_bookings.aggregate(total=Sum("screenings"))["total"] or 0
    required_materials = materials.filter(required_for_release=True)
    open_materials = required_materials.exclude(status__in=[DeliveryStatus.READY, DeliveryStatus.SENT, DeliveryStatus.ACCEPTED])
    overdue_materials = [material for material in open_materials if material.is_overdue]

    context = {
        "title": title,
        "today": today,
        "rights_windows": rights_windows,
        "sales_reports": sales_reports,
        "costs": costs,
        "cinema_bookings": cinema_bookings,
        "royalty_statements": royalty_statements,
        "materials": materials,
        "issues": issues,
        "waterfall_rules": waterfall_rules,
        "gross_box_office": gross_box_office,
        "admissions": admissions,
        "screenings": screenings,
        "required_materials_count": required_materials.count(),
        "open_materials_count": open_materials.count(),
        "overdue_materials_count": len(overdue_materials),
    }
    return render(request, "distribution/title_detail.html", context)


@login_required
def avails(request):
    result = None
    errors = []
    selected_title = None
    selected_territories = Territory.objects.none()
    selected_languages = LanguageVersion.objects.none()

    title_id = request.GET.get("title") or ""
    exploitation_field = request.GET.get("exploitation_field") or ""
    territory_ids = [item for item in request.GET.getlist("territories") if item]
    language_ids = [item for item in request.GET.getlist("languages") if item]
    date_from_raw = request.GET.get("date_from") or ""
    date_to_raw = request.GET.get("date_to") or ""

    if any([title_id, exploitation_field, territory_ids, language_ids, date_from_raw, date_to_raw]):
        date_from = parse_date(date_from_raw)
        date_to = parse_date(date_to_raw)
        if not title_id:
            errors.append("Wybierz tytuł.")
        if not exploitation_field:
            errors.append("Wybierz pole eksploatacji.")
        if not date_from or not date_to:
            errors.append("Podaj poprawny zakres dat.")
        elif date_from > date_to:
            errors.append("Data od nie może być późniejsza niż data do.")
        if title_id:
            selected_title = get_object_or_404(Title, pk=title_id)
        selected_territories = Territory.objects.filter(pk__in=territory_ids).order_by("name")
        selected_languages = LanguageVersion.objects.filter(pk__in=language_ids).order_by("name")

        if not errors:
            result = check_availability(
                title=selected_title,
                exploitation_field=exploitation_field,
                territories=selected_territories,
                languages=selected_languages,
                date_from=date_from,
                date_to=date_to,
            )

    context = {
        "result": result,
        "errors": errors,
        "titles": Title.objects.order_by("title_pl"),
        "territories": Territory.objects.order_by("name"),
        "languages": LanguageVersion.objects.order_by("name"),
        "exploitation_fields": ExploitationField.choices,
        "filters": {
            "title": title_id,
            "exploitation_field": exploitation_field,
            "territories": territory_ids,
            "languages": language_ids,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
        },
        "selected_title": selected_title,
        "selected_territories": selected_territories,
        "selected_languages": selected_languages,
    }
    return render(request, "distribution/avails.html", context)


def _filtered_statements(request):
    statements = RoyaltyStatement.objects.select_related("title", "recipient").order_by("-period_end", "title__title_pl")
    filters = {
        "status": request.GET.get("status") or "",
        "title_id": request.GET.get("title") or "",
        "recipient_id": request.GET.get("recipient") or "",
        "date_from": request.GET.get("date_from") or "",
        "date_to": request.GET.get("date_to") or "",
    }
    if filters["status"]:
        statements = statements.filter(status=filters["status"])
    if filters["title_id"]:
        statements = statements.filter(title_id=filters["title_id"])
    if filters["recipient_id"]:
        statements = statements.filter(recipient_id=filters["recipient_id"])
    if filters["date_from"]:
        statements = statements.filter(period_end__gte=filters["date_from"])
    if filters["date_to"]:
        statements = statements.filter(period_start__lte=filters["date_to"])
    return statements, filters


@login_required
def statement_center(request):
    if request.method == "POST":
        action = request.POST.get("action")
        statement_ids = request.POST.getlist("statement_ids")
        statements = RoyaltyStatement.objects.filter(pk__in=statement_ids).select_related("title", "recipient")
        if not statement_ids:
            messages.warning(request, "Zaznacz przynajmniej jeden statement.")
            return redirect("distribution:statement_center")

        if action == "generate_pdf":
            generated = 0
            for statement in statements:
                pdf_file = build_royalty_statement_pdf(statement)
                statement.statement_file.save(pdf_file.name, pdf_file, save=True)
                generated += 1
            messages.success(request, f"Wygenerowano PDF: {generated}.")
        elif action == "mark_sent":
            updated = statements.update(status=StatementStatus.SENT, sent_at=timezone.localdate())
            messages.success(request, f"Oznaczono jako wyslane: {updated}.")
        elif action == "mark_approved":
            updated = statements.update(status=StatementStatus.APPROVED)
            messages.success(request, f"Oznaczono jako zaakceptowane: {updated}.")
        elif action == "mark_paid":
            updated = statements.update(status=StatementStatus.PAID, paid_at=timezone.localdate())
            messages.success(request, f"Oznaczono jako oplacone: {updated}.")
        elif action == "mark_disputed":
            updated = statements.update(status=StatementStatus.DISPUTED)
            messages.success(request, f"Oznaczono jako sporne: {updated}.")
        else:
            messages.warning(request, "Nieznana akcja.")
        return redirect("distribution:statement_center")

    statements, filters = _filtered_statements(request)
    if request.GET.get("export") == "xlsx":
        return _statement_center_export_xlsx(statements, filters)

    statement_list = list(statements[:300])
    amount_due_total = sum((statement.amount_due for statement in statement_list), 0)
    open_amount_total = sum((statement.amount_due for statement in statement_list if statement.status != StatementStatus.PAID), 0)
    status_counts = {
        row["status"]: row["count"]
        for row in statements.values("status").annotate(count=Count("id"))
    }
    status_count_rows = [
        {"value": value, "label": label, "count": status_counts.get(value, 0)}
        for value, label in StatementStatus.choices
    ]

    context = {
        "statements": statement_list,
        "filters": filters,
        "titles": Title.objects.order_by("title_pl"),
        "recipients": Counterparty.objects.order_by("name"),
        "statement_statuses": StatementStatus.choices,
        "status_counts": status_counts,
        "status_count_rows": status_count_rows,
        "statement_count": statements.count(),
        "amount_due_total": amount_due_total,
        "open_amount_total": open_amount_total,
    }
    return render(request, "distribution/statement_center.html", context)


def _report_filters(request):
    today = timezone.localdate()
    default_start = today.replace(month=1, day=1)
    date_from = request.GET.get("date_from") or default_start.isoformat()
    date_to = request.GET.get("date_to") or today.isoformat()
    title_id = request.GET.get("title") or ""
    counterparty_id = request.GET.get("counterparty") or ""
    return {
        "date_from": date_from,
        "date_to": date_to,
        "title_id": title_id,
        "counterparty_id": counterparty_id,
    }


def _filtered_sales_reports(filters):
    reports = SalesReport.objects.select_related("title", "counterparty", "territory").filter(
        period_start__gte=filters["date_from"],
        period_start__lte=filters["date_to"],
    )
    if filters["title_id"]:
        reports = reports.filter(title_id=filters["title_id"])
    if filters["counterparty_id"]:
        reports = reports.filter(counterparty_id=filters["counterparty_id"])
    return reports


def _filtered_costs(filters):
    costs = Cost.objects.select_related("title", "supplier").filter(
        cost_date__gte=filters["date_from"],
        cost_date__lte=filters["date_to"],
    )
    if filters["title_id"]:
        costs = costs.filter(title_id=filters["title_id"])
    if filters["counterparty_id"]:
        costs = costs.filter(supplier_id=filters["counterparty_id"])
    return costs


@login_required
def reports(request):
    filters = _report_filters(request)
    sales_reports = _filtered_sales_reports(filters)
    costs = _filtered_costs(filters)
    net_expr = ExpressionWrapper(
        F("gross_revenue") - F("deductions") - F("vat_withholding"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    revenue_by_title = (
        sales_reports.values("title__title_pl")
        .annotate(gross=Sum("gross_revenue"), net=Sum(net_expr), reports=Count("id"))
        .order_by("-net", "title__title_pl")
    )
    revenue_by_field = (
        sales_reports.values("exploitation_field")
        .annotate(gross=Sum("gross_revenue"), net=Sum(net_expr), reports=Count("id"))
        .order_by("-net", "exploitation_field")
    )
    revenue_by_counterparty = (
        sales_reports.values("counterparty__name")
        .annotate(gross=Sum("gross_revenue"), net=Sum(net_expr), reports=Count("id"))
        .order_by("-net", "counterparty__name")
    )
    costs_by_title = (
        costs.values("title__title_pl")
        .annotate(net=Sum("net_amount"), gross=Sum(F("net_amount") + F("vat_amount")), costs=Count("id"))
        .order_by("-net", "title__title_pl")
    )

    gross_revenue = sales_reports.aggregate(total=Sum("gross_revenue"))["total"] or 0
    deductions = sales_reports.aggregate(total=Sum("deductions"))["total"] or 0
    vat_withholding = sales_reports.aggregate(total=Sum("vat_withholding"))["total"] or 0
    net_revenue = sales_reports.aggregate(total=Sum(net_expr))["total"] or 0
    cost_total = costs.aggregate(total=Sum("net_amount"))["total"] or 0
    waterfall_rows, waterfall_totals = calculate_waterfall(filters)

    context = {
        "filters": filters,
        "titles": Title.objects.order_by("title_pl"),
        "counterparties": Counterparty.objects.order_by("name"),
        "gross_revenue": gross_revenue,
        "deductions": deductions,
        "vat_withholding": vat_withholding,
        "net_revenue": net_revenue,
        "cost_total": cost_total,
        "margin": net_revenue - cost_total,
        "sales_count": sales_reports.count(),
        "cost_count": costs.count(),
        "revenue_by_title": revenue_by_title,
        "revenue_by_field": revenue_by_field,
        "revenue_by_counterparty": revenue_by_counterparty,
        "costs_by_title": costs_by_title,
        "waterfall_rows": waterfall_rows,
        "waterfall_totals": waterfall_totals,
        "overdue_agreements": SalesAgreement.objects.filter(invoice_paid=False, payment_due_date__lt=timezone.localdate()).select_related("title", "licensee")[:20],
        "open_issues": RightsIssue.objects.filter(resolved=False).select_related("rights_window", "rights_window__title")[:20],
    }
    return render(request, "distribution/reports.html", context)


@login_required
def reports_export_csv(request):
    filters = _report_filters(request)
    export_format = request.GET.get("format", "csv")
    if export_format == "xlsx":
        return _reports_export_xlsx(filters)
    if request.GET.get("section") == "waterfall":
        return _waterfall_export_csv(filters)
    sales_reports = _filtered_sales_reports(filters).order_by("period_start", "title__title_pl")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sales_report_export.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "title",
        "counterparty",
        "exploitation_field",
        "territory",
        "period_start",
        "period_end",
        "currency",
        "gross_revenue",
        "deductions",
        "vat_withholding",
        "net_revenue",
        "source_reference",
    ])
    for report in sales_reports:
        writer.writerow([
            report.title.title_pl,
            report.counterparty.name,
            report.get_exploitation_field_display(),
            report.territory.name if report.territory else "",
            report.period_start,
            report.period_end,
            report.currency,
            report.gross_revenue,
            report.deductions,
            report.vat_withholding,
            report.net_revenue,
            report.source_reference,
        ])
    return response


def _waterfall_export_csv(filters):
    waterfall_rows, _ = calculate_waterfall(filters)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="waterfall_recoupment_export.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "title",
        "exploitation_field",
        "currency",
        "net_revenue",
        "recoupable_costs",
        "manual_recoupment_items",
        "recoupment_pool",
        "recouped_amount",
        "unrecouped_balance",
        "distributor_fee",
        "split_base",
        "participant_share",
        "participant_allocations",
        "distributor_remainder",
    ])
    for row in waterfall_rows:
        rule = row["rule"]
        allocations = "; ".join(f"{item['recipient']}: {item['amount']}" for item in row["participant_allocations"])
        writer.writerow([
            rule.title.title_pl,
            rule.get_exploitation_field_display(),
            rule.currency,
            row["net_revenue"],
            row["recoupable_costs"],
            row["manual_recoupment_items"],
            row["recoupment_pool"],
            row["recouped_amount"],
            row["unrecouped_balance"],
            row["distributor_fee"],
            row["split_base"],
            row["participant_share"],
            allocations,
            row["distributor_remainder"],
        ])
    return response


def _append_table(sheet, headers, rows):
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E8EEF7")
    for row in rows:
        sheet.append(row)
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(max_length + 2, 12), 42)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def _statement_center_export_xlsx(statements, filters):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    statement_list = list(statements)
    _append_table(
        summary,
        ["Metric", "Value"],
        [
            ["Status", filters["status"] or "all"],
            ["Title", filters["title_id"] or "all"],
            ["Recipient", filters["recipient_id"] or "all"],
            ["Date from", filters["date_from"] or ""],
            ["Date to", filters["date_to"] or ""],
            ["Statement count", len(statement_list)],
            ["Amount due total", sum((statement.amount_due for statement in statement_list), 0)],
            ["Open amount total", sum((statement.amount_due for statement in statement_list if statement.status != StatementStatus.PAID), 0)],
        ],
    )
    details = workbook.create_sheet("Statements")
    _append_table(
        details,
        ["Title", "Recipient", "Period start", "Period end", "Currency", "Gross", "Net", "Recoupable costs", "Distributor fee", "Net receipts", "Amount due", "Status", "Sent at", "Paid at", "PDF"],
        [
            [
                statement.title.title_pl,
                statement.recipient.name,
                statement.period_start,
                statement.period_end,
                statement.currency,
                statement.gross_revenue,
                statement.net_revenue,
                statement.recoupable_costs,
                statement.distributor_fee_amount,
                statement.net_receipts,
                statement.amount_due,
                statement.get_status_display(),
                statement.sent_at or "",
                statement.paid_at or "",
                statement.statement_file.url if statement.statement_file else "",
            ]
            for statement in statement_list
        ],
    )
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="filmerp_statement_center.xlsx"'
    return response


def _reports_export_xlsx(filters):
    sales_reports = _filtered_sales_reports(filters).order_by("period_start", "title__title_pl")
    waterfall_rows, _ = calculate_waterfall(filters)
    costs = _filtered_costs(filters).order_by("cost_date", "title__title_pl")
    overdue_agreements = SalesAgreement.objects.filter(invoice_paid=False, payment_due_date__lt=timezone.localdate()).select_related("title", "licensee")
    open_issues = RightsIssue.objects.filter(resolved=False).select_related("rights_window", "rights_window__title")

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary_rows = [
        ["Date from", filters["date_from"]],
        ["Date to", filters["date_to"]],
        ["Sales report count", sales_reports.count()],
        ["Cost count", costs.count()],
        ["Waterfall rule count", len(waterfall_rows)],
    ]
    _append_table(summary, ["Metric", "Value"], summary_rows)

    sales_sheet = workbook.create_sheet("Sales reports")
    _append_table(
        sales_sheet,
        ["Title", "Counterparty", "Field", "Territory", "Period start", "Period end", "Currency", "Gross", "Deductions", "VAT withholding", "Net", "Source"],
        [
            [
                report.title.title_pl,
                report.counterparty.name,
                report.get_exploitation_field_display(),
                report.territory.name if report.territory else "",
                report.period_start,
                report.period_end,
                report.currency,
                report.gross_revenue,
                report.deductions,
                report.vat_withholding,
                report.net_revenue,
                report.source_reference,
            ]
            for report in sales_reports
        ],
    )

    waterfall_sheet = workbook.create_sheet("Waterfall")
    _append_table(
        waterfall_sheet,
        ["Title", "Field", "Currency", "Net revenue", "Recoupable costs", "Manual recoupment items", "Recoupment pool", "Recouped", "Unrecouped", "Distributor fee", "Split base", "Participant share", "Participant allocations", "Distributor remainder"],
        [
            [
                row["rule"].title.title_pl,
                row["rule"].get_exploitation_field_display(),
                row["rule"].currency,
                row["net_revenue"],
                row["recoupable_costs"],
                row["manual_recoupment_items"],
                row["recoupment_pool"],
                row["recouped_amount"],
                row["unrecouped_balance"],
                row["distributor_fee"],
                row["split_base"],
                row["participant_share"],
                "; ".join(f"{item['recipient']}: {item['amount']}" for item in row["participant_allocations"]),
                row["distributor_remainder"],
            ]
            for row in waterfall_rows
        ],
    )

    costs_sheet = workbook.create_sheet("Costs")
    _append_table(
        costs_sheet,
        ["Title", "Supplier", "Category", "Legacy field", "Waterfall all fields", "Waterfall fields", "Date", "Currency", "Net", "VAT", "Gross", "Recoupable", "Paid"],
        [
            [
                cost.title.title_pl,
                cost.supplier.name if cost.supplier else "",
                cost.get_category_display(),
                cost.get_exploitation_field_display() if cost.exploitation_field else "",
                "yes" if cost.applies_to_all_exploitation_fields else "no",
                ", ".join(sorted(cost.waterfall_exploitation_fields())),
                cost.cost_date,
                cost.currency,
                cost.net_amount,
                cost.vat_amount,
                cost.gross_amount,
                "yes" if cost.recoupable else "no",
                "yes" if cost.paid else "no",
            ]
            for cost in costs
        ],
    )

    alerts_sheet = workbook.create_sheet("Alerts")
    _append_table(
        alerts_sheet,
        ["Type", "Title", "Counterparty", "Date", "Message"],
        [[
            "Overdue payment",
            agreement.title.title_pl,
            agreement.licensee.name,
            agreement.payment_due_date,
            f"{agreement.fixed_fee} {agreement.currency}",
        ] for agreement in overdue_agreements] + [[
            "Rights issue",
            issue.rights_window.title.title_pl,
            issue.rights_window.counterparty.name if issue.rights_window.counterparty else "",
            issue.created_at.date(),
            issue.message,
        ] for issue in open_issues],
    )

    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="filmerp_report_export.xlsx"'
    return response
