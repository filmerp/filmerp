from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    BookingActivityForm,
    BookingCampaignForm,
    BookingDealForm,
    BookingSettlementPaymentForm,
    BookingTermFormSet,
    CinemaAccountForm,
    CinemaContactForm,
    CinemaReportRowReviewForm,
)
from .cinema_imports import refresh_report_import_status, review_import_row
from .documents import sync_document_status_from_cinema_import
from .models import (
    AuditAction,
    BookingActivity,
    BookingActivityType,
    BookingCalculationMethod,
    BookingCampaign,
    BookingCampaignStatus,
    BookingDeal,
    BookingDealStage,
    BookingSettlementStatus,
    BookingSettlementBasis,
    BookingWeekDecision,
    BookingWeekStatus,
    CinemaBookingStatus,
    CinemaBookingWeek,
    CinemaContact,
    CinemaReportImport,
    CinemaReportImportRow,
    Counterparty,
    CounterpartyType,
    ImportStatus,
    Title,
)
from .security import record_audit_event


PIPELINE_STAGES = tuple(BookingDealStage.choices)
TERMINAL_STAGES = {BookingDealStage.LOST}
BOOKED_STAGES = {BookingDealStage.CONFIRMED}
CONTACT_ACTIVITY_TYPES = {
    BookingActivityType.CALL,
    BookingActivityType.EMAIL,
    BookingActivityType.MEETING,
}


def _crm_url(*, campaign_id="", view="overview"):
    params = []
    if campaign_id:
        params.append(f"campaign={campaign_id}")
    if view and view != "overview":
        params.append(f"view={view}")
    query = f"?{'&'.join(params)}" if params else ""
    return f"{reverse('distribution:booking_crm')}{query}"


def _week_report_url(week, *, import_id="", row_id=""):
    params = []
    if import_id:
        params.append(f"import={import_id}")
    if row_id:
        params.append(f"row={row_id}")
    query = f"?{'&'.join(params)}" if params else ""
    return f"{reverse('distribution:booking_week_report', args=[week.pk])}{query}"


@login_required
@permission_required("distribution.view_bookingdeal", raise_exception=True)
def booking_crm(request):
    today = timezone.localdate()
    active_view = request.GET.get("view", "overview")
    if active_view not in {"overview", "negotiations", "weeks", "cinemas", "tasks"}:
        active_view = "overview"
    negotiations_mode = request.GET.get("mode", "table")
    if negotiations_mode not in {"table", "kanban"}:
        negotiations_mode = "table"

    campaigns = BookingCampaign.objects.select_related("title", "owner").annotate(
        deals_count=Count("deals", distinct=True),
        confirmed_count=Count("deals", filter=Q(deals__stage__in=BOOKED_STAGES), distinct=True),
    ).order_by("-release_date", "title__title_pl")
    title_id = request.GET.get("title", "")
    requested_title = None
    if title_id.isdigit():
        requested_title = get_object_or_404(Title, pk=title_id)
        campaigns = campaigns.filter(title_id=title_id)
    selected_campaign = None
    campaign_id = request.GET.get("campaign")
    if campaign_id:
        selected_campaign = get_object_or_404(campaigns, pk=campaign_id)
    elif campaigns.exists() and (active_view == "overview" or "campaign" not in request.GET):
        selected_campaign = campaigns.exclude(
            status__in=[BookingCampaignStatus.COMPLETED, BookingCampaignStatus.CANCELLED]
        ).order_by("-release_date").first() or campaigns.first()

    deals = BookingDeal.objects.select_related(
        "campaign",
        "campaign__title",
        "cinema",
        "cinema__cinema_profile",
        "contact",
        "owner",
    ).prefetch_related("bookings", "terms")
    if selected_campaign:
        deals = deals.filter(campaign=selected_campaign)
    query = request.GET.get("q", "").strip()
    if query:
        deals = deals.filter(
            Q(cinema__name__icontains=query)
            | Q(cinema__cinema_profile__city__icontains=query)
            | Q(campaign__title__title_pl__icontains=query)
            | Q(contact__name__icontains=query)
        )
    owner_id = request.GET.get("owner", "")
    if owner_id:
        deals = deals.filter(owner_id=owner_id)
    deal_rows = list(deals.order_by("cinema__name"))

    pipeline = [
        {
            "value": value,
            "label": label,
            "deals": [deal for deal in deal_rows if deal.stage == value],
        }
        for value, label in PIPELINE_STAGES
    ]
    booked = [deal for deal in deal_rows if deal.stage in BOOKED_STAGES]
    overdue = [deal for deal in deal_rows if deal.is_overdue]
    confirmed_screens = sum(deal.confirmed_screens for deal in booked)
    target_cinemas = selected_campaign.target_cinemas if selected_campaign else 0
    progress_percent = min(round((len(booked) / target_cinemas) * 100), 100) if target_cinemas else 0

    weeks = CinemaBookingWeek.objects.select_related(
        "booking__title",
        "booking__cinema",
        "booking__crm_deal__campaign",
        "settlement",
    )
    if selected_campaign:
        weeks = weeks.filter(booking__crm_deal__campaign=selected_campaign)
    if owner_id:
        weeks = weeks.filter(booking__crm_deal__owner_id=owner_id)
    if query:
        weeks = weeks.filter(
            Q(booking__cinema__name__icontains=query)
            | Q(booking__title__title_pl__icontains=query)
            | Q(booking__city__icontains=query)
        )
    week_rows = list(weeks.order_by("-date_from", "booking__cinema__name"))
    missing_week_rows = [
        week for week in week_rows
        if week.status == BookingWeekStatus.PLANNED and week.date_to < today
    ]
    reported_week_rows = [week for week in week_rows if week.status != BookingWeekStatus.PLANNED]
    pending_verification_rows = [
        week for week in week_rows
        if week.status in {BookingWeekStatus.REPORTED, BookingWeekStatus.VERIFIED, BookingWeekStatus.CORRECTED}
    ]
    approved_week_rows = [week for week in week_rows if week.status == BookingWeekStatus.LOCKED]
    missing_invoice_rows = [
        week for week in approved_week_rows
        if hasattr(week, "settlement") and week.settlement.invoice_missing
    ]
    overdue_payment_rows = [
        week for week in approved_week_rows
        if hasattr(week, "settlement") and week.settlement.is_overdue
    ]
    admissions_total = sum(week.admissions for week in reported_week_rows)
    totals_by_currency = {}
    for week in approved_week_rows:
        totals = totals_by_currency.setdefault(
            week.currency,
            {"currency": week.currency, "box_office": Decimal("0.00"), "rental": Decimal("0.00")},
        )
        totals["box_office"] += week.box_office_gross
        if hasattr(week, "settlement"):
            totals["rental"] += week.settlement.rental_amount
    financial_totals = [totals_by_currency[key] for key in sorted(totals_by_currency)]

    task_deals = BookingDeal.objects.select_related(
        "campaign__title", "cinema", "owner"
    ).exclude(stage__in=TERMINAL_STAGES).exclude(next_action_date=None)
    if selected_campaign:
        task_deals = task_deals.filter(campaign=selected_campaign)
    if owner_id:
        task_deals = task_deals.filter(owner_id=owner_id)
    task_deals = task_deals.order_by("next_action_date", "campaign__title__title_pl", "cinema__name")

    cinema_types = [CounterpartyType.CINEMA, CounterpartyType.CINEMA_CHAIN]
    cinemas = Counterparty.objects.filter(counterparty_type__in=cinema_types).select_related(
        "cinema_profile", "cinema_profile__chain"
    ).prefetch_related("cinema_contacts").annotate(
        active_deals_count=Count(
            "booking_deals",
            filter=~Q(booking_deals__stage__in=TERMINAL_STAGES),
            distinct=True,
        )
    ).order_by("name")
    incomplete_cinemas_count = cinemas.filter(
        Q(cinema_profile__city="") | Q(cinema_contacts__isnull=True)
    ).distinct().count()
    if query and active_view == "cinemas":
        cinemas = cinemas.filter(
            Q(name__icontains=query)
            | Q(cinema_profile__city__icontains=query)
            | Q(cinema_contacts__name__icontains=query)
        ).distinct()
    cinema_data_filter = request.GET.get("cinema_data", "")
    if cinema_data_filter == "missing_city":
        cinemas = cinemas.filter(cinema_profile__city="")
    elif cinema_data_filter == "missing_contact":
        cinemas = cinemas.filter(cinema_contacts__isnull=True)
    elif cinema_data_filter == "missing_reporting":
        cinemas = cinemas.filter(reporting_cycle="none")
    cinema_page = Paginator(cinemas.distinct(), 50).get_page(request.GET.get("page"))

    owners = get_user_model().objects.filter(is_active=True).order_by("first_name", "last_name", "username")
    context = {
        "active_view": active_view,
        "negotiations_mode": negotiations_mode,
        "campaigns": campaigns,
        "selected_campaign": selected_campaign,
        "workspace_title": selected_campaign.title if selected_campaign else requested_title,
        "pipeline": pipeline,
        "deal_rows": deal_rows,
        "deals_count": len(deal_rows),
        "booked_count": len(booked),
        "confirmed_screens": confirmed_screens,
        "overdue_count": len(overdue),
        "target_cinemas": target_cinemas,
        "progress_percent": progress_percent,
        "week_rows": week_rows,
        "missing_week_rows": missing_week_rows,
        "missing_reports_count": len(missing_week_rows),
        "reported_weeks_count": len(reported_week_rows),
        "approved_weeks_count": len(approved_week_rows),
        "pending_verification_rows": pending_verification_rows,
        "pending_verification_count": len(pending_verification_rows),
        "missing_invoice_rows": missing_invoice_rows,
        "missing_invoice_count": len(missing_invoice_rows),
        "overdue_payment_rows": overdue_payment_rows,
        "overdue_payment_count": len(overdue_payment_rows),
        "financial_totals": financial_totals,
        "admissions_total": admissions_total,
        "task_deals": task_deals,
        "today": today,
        "task_horizon": today + timedelta(days=14),
        "cinemas": cinema_page.object_list,
        "cinema_page": cinema_page,
        "cinema_data_filter": cinema_data_filter,
        "incomplete_cinemas_count": incomplete_cinemas_count,
        "owners": owners,
        "query": query,
        "owner_id": owner_id,
        "can_add_campaign": request.user.has_perm("distribution.add_bookingcampaign"),
        "can_add_deal": request.user.has_perm("distribution.add_bookingdeal"),
        "can_change_week": request.user.has_perm("distribution.change_cinemabookingweek"),
        "can_upload_cinema_report": request.user.has_perm("distribution.add_cinemareportimport"),
        "can_add_cinema": request.user.has_perm("distribution.add_cinemaprofile") and request.user.has_perm("distribution.add_counterparty"),
    }
    return render(request, "distribution/booking_crm.html", context)


@login_required
@require_POST
@permission_required("distribution.change_cinemabookingweek", raise_exception=True)
def booking_week_update(request, pk):
    week = get_object_or_404(
        CinemaBookingWeek.objects.select_related("booking__crm_deal__campaign", "settlement"),
        pk=pk,
    )
    status = request.POST.get("status", week.status)
    decision = request.POST.get("decision", week.decision)
    valid_statuses = {value for value, _ in BookingWeekStatus.choices}
    valid_decisions = {value for value, _ in BookingWeekDecision.choices}
    if status not in valid_statuses or decision not in valid_decisions:
        messages.error(request, "Nieprawidłowy status tygodnia lub decyzja.")
        return redirect(_crm_url(campaign_id=week.booking.crm_deal.campaign_id if week.booking.crm_deal_id else "", view="weeks"))
    if week.status == BookingWeekStatus.LOCKED and status != BookingWeekStatus.LOCKED:
        messages.error(request, "Zamkniętego tygodnia nie można otworzyć ponownie. Wczytaj raport korygujący.")
        return redirect(_week_report_url(week))
    if status == BookingWeekStatus.LOCKED and not request.user.has_perm("distribution.approve_cinema_reports"):
        raise PermissionDenied

    with transaction.atomic():
        week.status = status
        week.decision = decision
        week.save(update_fields=["status", "decision", "updated_at"])
        settlement = None
        if status != BookingWeekStatus.PLANNED:
            settlement = week.recalculate()
        if status == BookingWeekStatus.LOCKED and settlement:
            settlement.status = BookingSettlementStatus.APPROVED
            settlement.approved_by = request.user
            settlement.approved_at = timezone.now()
            if not settlement.payment_due_date:
                settlement.payment_due_date = timezone.localdate() + timedelta(
                    days=week.booking.cinema.payment_terms_days
                )
            settlement.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "payment_due_date",
                    "updated_at",
                ]
            )
            week.sync_sales_report()

        booking = week.booking
        if decision == BookingWeekDecision.EXTEND:
            next_number = week.week_number + 1
            next_from = week.date_to + timedelta(days=1)
            next_to = next_from + timedelta(days=6)
            booking.weeks.get_or_create(
                week_number=next_number,
                defaults={
                    "date_from": next_from,
                    "date_to": next_to,
                    "planned_screens": week.planned_screens,
                    "currency": week.currency,
                },
            )
            booking.date_to = max(booking.date_to, next_to)
            booking.status = CinemaBookingStatus.PLAYING
            booking.save(update_fields=["date_to", "status", "updated_at"])
            if booking.crm_deal_id and (booking.crm_deal.playing_to is None or booking.crm_deal.playing_to < next_to):
                booking.crm_deal.playing_to = next_to
                booking.crm_deal.save(update_fields=["playing_to", "updated_at"])
        elif decision == BookingWeekDecision.END:
            booking.date_to = week.date_to
            booking.status = CinemaBookingStatus.ENDED
            booking.save(update_fields=["date_to", "status", "updated_at"])

        record_audit_event(
            AuditAction.UPDATE,
            f"Zmieniono tydzień {week.week_number} bookingu {booking}.",
            request=request,
            module="booking_crm",
            instance=week,
            metadata={"status": status, "decision": decision},
        )
    messages.success(request, "Tydzień grania został zaktualizowany.")
    campaign_id = booking.crm_deal.campaign_id if booking.crm_deal_id else ""
    return redirect(_crm_url(campaign_id=campaign_id, view="weeks"))


@login_required
@permission_required("distribution.view_cinemabookingweek", raise_exception=True)
def booking_week_report(request, pk):
    week = get_object_or_404(
        CinemaBookingWeek.objects.select_related(
            "booking__title",
            "booking__cinema",
            "booking__crm_deal__campaign",
            "settlement",
        ),
        pk=pk,
    )
    campaign_id = week.booking.crm_deal.campaign_id if week.booking.crm_deal_id else ""
    selected_import = None
    selected_row = None
    row_form = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "upload_report":
            messages.info(request, "Raport wgraj przez Dokumenty. Po rozpoznaniu wrócisz na Panel główny.")
            return redirect(
                f"{reverse('distribution:document_center')}?target_week={week.pk}&type=cinema_report#upload"
            )

        if action in {"save_row", "approve_row"}:
            if not request.user.has_perm("distribution.change_cinemareportimportrow"):
                raise PermissionDenied
            selected_import = get_object_or_404(
                CinemaReportImport,
                pk=request.POST.get("import_id"),
                target_booking_week=week,
            )
            selected_row = get_object_or_404(
                CinemaReportImportRow,
                pk=request.POST.get("row_id"),
                report_import=selected_import,
            )
            row_form = CinemaReportRowReviewForm(
                request.POST,
                instance=selected_row,
                target_week=week,
            )
            if row_form.is_valid():
                selected_row = row_form.save()
                review = review_import_row(selected_row, week)
                if action == "save_row":
                    messages.success(request, "Dane rozpoznanego wiersza zostały zapisane.")
                elif not request.user.has_perm("distribution.approve_cinema_reports"):
                    raise PermissionDenied
                elif not review["ready"]:
                    messages.error(request, "Usuń wskazane błędy przed zatwierdzeniem rozliczenia.")
                else:
                    try:
                        with transaction.atomic():
                            selected_row.approve(approved_by=request.user)
                            refresh_report_import_status(selected_import)
                            sync_document_status_from_cinema_import(selected_import, reviewed_by=request.user)
                            record_audit_event(
                                AuditAction.APPROVE,
                                f"Zatwierdzono rozliczenie tygodnia {week.week_number} dla {week.booking.cinema}.",
                                request=request,
                                module="booking_crm",
                                instance=week,
                                metadata={
                                    "import_id": selected_import.pk,
                                    "row_id": selected_row.pk,
                                },
                            )
                        messages.success(
                            request,
                            "Rozliczenie zatwierdzono. Przychód trafił do raportów, waterfallu i Statement Center.",
                        )
                    except ValidationError as exc:
                        messages.error(request, " ".join(exc.messages))
                return redirect(
                    _week_report_url(
                        week,
                        import_id=selected_import.pk,
                        row_id=selected_row.pk,
                    )
                )
            messages.error(request, "Popraw zaznaczone pola.")

        if action in {"save_invoice", "mark_paid"}:
            if not request.user.has_perm("distribution.change_bookingweeksettlement"):
                raise PermissionDenied
            settlement = getattr(week, "settlement", None)
            if not settlement or settlement.status != BookingSettlementStatus.APPROVED:
                messages.error(request, "Najpierw zatwierdź rozliczenie tygodnia.")
                return redirect(_week_report_url(week))
            if action == "mark_paid":
                settlement.paid_at = timezone.localdate()
                settlement.save(update_fields=["paid_at", "updated_at"])
                week.sync_sales_report()
                record_audit_event(
                    AuditAction.UPDATE,
                    f"Oznaczono płatność za tydzień {week.week_number} jako otrzymaną.",
                    request=request,
                    module="booking_crm",
                    instance=settlement,
                )
                messages.success(request, "Płatność została oznaczona jako otrzymana.")
                return redirect(_week_report_url(week))

            payment_form = BookingSettlementPaymentForm(request.POST, request.FILES, instance=settlement)
            if payment_form.is_valid():
                settlement = payment_form.save(commit=False)
                if (
                    settlement.invoice_number or settlement.invoice_file
                ) and not settlement.invoice_issued_at:
                    settlement.invoice_issued_at = timezone.localdate()
                if settlement.invoice_issued_at and not settlement.payment_due_date:
                    settlement.payment_due_date = settlement.invoice_issued_at + timedelta(
                        days=week.booking.cinema.payment_terms_days
                    )
                settlement.save()
                week.booking.invoice_issued = bool(
                    settlement.invoice_number or settlement.invoice_file or settlement.invoice_issued_at
                )
                week.booking.save(update_fields=["invoice_issued", "updated_at"])
                week.sync_sales_report()
                record_audit_event(
                    AuditAction.UPDATE,
                    f"Zaktualizowano fakturę i płatność dla tygodnia {week.week_number}.",
                    request=request,
                    module="booking_crm",
                    instance=settlement,
                )
                messages.success(request, "Dane faktury i płatności zostały zapisane.")
                return redirect(_week_report_url(week))
            messages.error(request, "Popraw dane faktury lub płatności.")

    imports = list(
        CinemaReportImport.objects.filter(
            Q(target_booking_week=week) | Q(rows__booking_week=week)
        )
        .distinct()
        .prefetch_related("rows__title", "rows__cinema")
        .order_by("-created_at")
    )
    import_id = request.GET.get("import") or request.POST.get("import_id")
    if import_id:
        selected_import = next((item for item in imports if str(item.pk) == str(import_id)), None)
        if selected_import is None:
            raise PermissionDenied
    elif imports:
        selected_import = imports[0]

    reviewed_rows = []
    if selected_import:
        import_rows = selected_import.rows.select_related("title", "cinema")
        if selected_import.target_booking_week_id != week.pk:
            import_rows = import_rows.filter(booking_week=week)
        reviewed_rows = [
            review_import_row(row, week)
            for row in import_rows.order_by("-confidence", "pk")
        ]
        row_id = request.GET.get("row") or request.POST.get("row_id")
        if row_id:
            selected_row = next(
                (item["row"] for item in reviewed_rows if str(item["row"].pk) == str(row_id)),
                None,
            )
        if selected_row is None and reviewed_rows:
            selected_row = sorted(
                reviewed_rows,
                key=lambda item: (
                    item["ready"],
                    item["row"].confidence,
                    bool(item["row"].box_office_gross),
                ),
                reverse=True,
            )[0]["row"]
        if selected_row and row_form is None:
            row_form = CinemaReportRowReviewForm(instance=selected_row, target_week=week)
            if selected_row.status == ImportStatus.IMPORTED or not request.user.has_perm(
                "distribution.change_cinemareportimportrow"
            ):
                for field in row_form.fields.values():
                    field.disabled = True

    selected_review = review_import_row(selected_row, week) if selected_row else None
    settlement = getattr(week, "settlement", None)
    payment_form = BookingSettlementPaymentForm(instance=settlement) if settlement else None
    term_values = week.calculation_values()
    context = {
        "week": week,
        "campaign_id": campaign_id,
        "imports": imports,
        "selected_import": selected_import,
        "reviewed_rows": reviewed_rows,
        "selected_row": selected_row,
        "selected_review": selected_review,
        "row_form": row_form,
        "settlement": settlement,
        "payment_form": payment_form,
        "term_values": term_values,
        "term_method_label": dict(BookingCalculationMethod.choices).get(
            term_values["calculation_method"],
            term_values["calculation_method"],
        ),
        "term_basis_label": dict(BookingSettlementBasis.choices).get(
            term_values["settlement_basis"],
            term_values["settlement_basis"],
        ),
        "revisions": week.revisions.order_by("-created_at"),
        "can_upload": request.user.has_perm("distribution.add_cinemareportimport"),
        "can_review": request.user.has_perm("distribution.change_cinemareportimportrow"),
        "can_approve": request.user.has_perm("distribution.approve_cinema_reports"),
        "can_manage_payment": request.user.has_perm("distribution.change_bookingweeksettlement"),
    }
    return render(request, "distribution/booking_week_report.html", context)


@login_required
@permission_required("distribution.add_bookingdeal", raise_exception=True)
def booking_bulk_cinemas(request):
    campaign_id = request.GET.get("campaign") or request.POST.get("campaign")
    campaign = get_object_or_404(BookingCampaign.objects.select_related("title", "owner"), pk=campaign_id)
    cinema_types = [CounterpartyType.CINEMA, CounterpartyType.CINEMA_CHAIN]
    cinemas = Counterparty.objects.filter(counterparty_type__in=cinema_types).select_related(
        "cinema_profile", "cinema_profile__chain"
    ).order_by("name")
    query = request.GET.get("q", "").strip()
    if query:
        cinemas = cinemas.filter(
            Q(name__icontains=query)
            | Q(cinema_profile__city__icontains=query)
            | Q(cinema_profile__chain__name__icontains=query)
        ).distinct()

    if request.method == "POST":
        selected_ids = request.POST.getlist("cinema_ids")
        selected = list(Counterparty.objects.filter(pk__in=selected_ids, counterparty_type__in=cinema_types))
        expanded = []
        seen = set()
        for cinema in selected:
            venues = list(
                Counterparty.objects.filter(
                    cinema_profile__chain=cinema,
                    counterparty_type=CounterpartyType.CINEMA,
                ).order_by("name")
            ) if cinema.counterparty_type == CounterpartyType.CINEMA_CHAIN else []
            targets = venues or [cinema]
            for target in targets:
                if target.pk not in seen:
                    expanded.append(target)
                    seen.add(target.pk)

        if not expanded:
            messages.warning(request, "Zaznacz co najmniej jedno kino lub sieć.")
            return redirect(f"{reverse('distribution:booking_bulk_cinemas')}?campaign={campaign.pk}")

        created_count = 0
        existing_count = 0
        with transaction.atomic():
            for cinema in expanded:
                deal, created = BookingDeal.objects.get_or_create(
                    campaign=campaign,
                    cinema=cinema,
                    defaults={
                        "owner": campaign.owner or request.user,
                        "stage": BookingDealStage.TARGET,
                        "opening_date": campaign.release_date,
                        "playing_to": campaign.release_date + timedelta(days=6),
                        "expected_screens": 1,
                        "calculation_method": campaign.default_calculation_method,
                        "settlement_basis": campaign.default_settlement_basis,
                        "ticket_vat_rate": campaign.default_ticket_vat_rate,
                        "distributor_share_percent": campaign.default_share_percent,
                        "minimum_guarantee": campaign.default_minimum_guarantee,
                        "fixed_fee": campaign.default_fixed_fee,
                        "currency": campaign.currency,
                    },
                )
                if created:
                    deal.ensure_default_term()
                    created_count += 1
                else:
                    existing_count += 1
        record_audit_event(
            AuditAction.CREATE,
            f"Dodano zbiorczo {created_count} kin do kampanii {campaign}.",
            request=request,
            module="booking_crm",
            instance=campaign,
            metadata={"created": created_count, "existing": existing_count},
        )
        if created_count:
            messages.success(request, f"Dodano {created_count} kin do kampanii.")
        if existing_count:
            messages.info(request, f"Pominięto {existing_count} kin już obecnych w kampanii.")
        return redirect(_crm_url(campaign_id=campaign.pk, view="negotiations"))

    return render(request, "distribution/booking_bulk_cinemas.html", {
        "campaign": campaign,
        "cinemas": cinemas,
        "query": query,
    })


@login_required
def booking_campaign_form(request, pk=None):
    campaign = get_object_or_404(BookingCampaign, pk=pk) if pk else None
    permission = "distribution.change_bookingcampaign" if campaign else "distribution.add_bookingcampaign"
    if not request.user.has_perm(permission):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    form = BookingCampaignForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        created = campaign is None
        saved = form.save()
        record_audit_event(
            AuditAction.CREATE if created else AuditAction.UPDATE,
            f"{'Utworzono' if created else 'Zmieniono'} kampanię bookingową {saved}.",
            request=request,
            module="booking_crm",
            instance=saved,
        )
        messages.success(request, "Kampania bookingowa została zapisana.")
        return redirect(_crm_url(campaign_id=saved.pk))
    return render(request, "distribution/booking_campaign_form.html", {"form": form, "campaign": campaign})


@login_required
def booking_deal_form(request, pk=None):
    deal = get_object_or_404(
        BookingDeal.objects.select_related("campaign__title", "cinema", "contact", "owner"),
        pk=pk,
    ) if pk else None
    permission = "distribution.change_bookingdeal" if deal else "distribution.add_bookingdeal"
    if not request.user.has_perm(permission):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied

    original_stage = deal.stage if deal else ""
    campaign = deal.campaign if deal else None
    campaign_id = request.GET.get("campaign") or request.POST.get("campaign")
    if not campaign and campaign_id:
        campaign = get_object_or_404(BookingCampaign, pk=campaign_id)

    action = request.POST.get("action") if request.method == "POST" else ""
    form_instance = deal or BookingDeal()
    form = BookingDealForm(
        request.POST or None,
        instance=form_instance,
        campaign=campaign,
        user=request.user,
    )
    term_initial = []
    if not deal and campaign:
        term_initial = [{
            "name": "Warunki podstawowe",
            "week_from": 1,
            "calculation_method": campaign.default_calculation_method,
            "settlement_basis": campaign.default_settlement_basis,
            "ticket_vat_rate": campaign.default_ticket_vat_rate,
            "distributor_share_percent": campaign.default_share_percent,
            "minimum_amount": campaign.default_minimum_guarantee,
            "fixed_amount": campaign.default_fixed_fee,
            "currency": campaign.currency,
        }]
    terms_submitted = request.method == "POST" and action == "save_deal" and "terms-TOTAL_FORMS" in request.POST
    term_formset = BookingTermFormSet(
        request.POST if terms_submitted else None,
        instance=form_instance,
        prefix="terms",
        initial=term_initial,
    )
    activity_form = BookingActivityForm(prefix="activity")

    terms_valid = term_formset.is_valid() if terms_submitted else True
    if request.method == "POST" and action == "save_deal" and form.is_valid() and terms_valid:
        created = deal is None
        with transaction.atomic():
            saved = form.save()
            if terms_submitted:
                term_formset.instance = saved
                term_formset.save()
            if not saved.terms.exists():
                saved.ensure_default_term()
            booking = None
            if saved.stage == BookingDealStage.CONFIRMED:
                booking = saved.ensure_booking()
            if original_stage and original_stage != saved.stage:
                BookingActivity.objects.create(
                    deal=saved,
                    activity_type=BookingActivityType.STATUS,
                    summary=f"Zmiana statusu: {dict(BookingDealStage.choices).get(original_stage, original_stage)} → {saved.get_stage_display()}.",
                    created_by=request.user,
                )
            record_audit_event(
                AuditAction.CREATE if created else AuditAction.UPDATE,
                f"{'Utworzono' if created else 'Zmieniono'} negocjację bookingową {saved}.",
                request=request,
                module="booking_crm",
                instance=saved,
                metadata={"stage": saved.stage, "booking_id": booking.pk if booking else None},
            )
        messages.success(request, "Negocjacja bookingowa została zapisana.")
        return redirect("distribution:booking_deal_edit", pk=saved.pk)

    if request.method == "POST" and action == "add_activity" and deal:
        activity_form = BookingActivityForm(request.POST, prefix="activity")
        if activity_form.is_valid():
            with transaction.atomic():
                activity = activity_form.save(commit=False)
                activity.deal = deal
                activity.created_by = request.user
                activity.save()
                update_fields = []
                if activity.activity_type in CONTACT_ACTIVITY_TYPES:
                    deal.last_contact_at = activity.occurred_at
                    update_fields.append("last_contact_at")
                next_action = activity_form.cleaned_data.get("next_action", "")
                next_action_date = activity_form.cleaned_data.get("next_action_date")
                if next_action or next_action_date:
                    deal.next_action = next_action
                    deal.next_action_date = next_action_date
                    update_fields.extend(["next_action", "next_action_date"])
                if update_fields:
                    deal.save(update_fields=[*set(update_fields), "updated_at"])
                record_audit_event(
                    AuditAction.CREATE,
                    f"Dodano aktywność bookingową: {activity.get_activity_type_display()}.",
                    request=request,
                    module="booking_crm",
                    instance=activity,
                    metadata={"deal_id": deal.pk},
                )
            messages.success(request, "Aktywność została dopisana do historii.")
            return redirect("distribution:booking_deal_edit", pk=deal.pk)

    activities = deal.activities.select_related("created_by") if deal else BookingActivity.objects.none()
    bookings = deal.bookings.order_by("-date_from") if deal else []
    context = {
        "form": form,
        "term_formset": term_formset,
        "activity_form": activity_form,
        "deal": deal,
        "campaign": campaign,
        "activities": activities,
        "bookings": bookings,
    }
    return render(request, "distribution/booking_deal_form.html", context)


@login_required
def booking_cinema_form(request, pk=None):
    cinema_types = [CounterpartyType.CINEMA, CounterpartyType.CINEMA_CHAIN]
    cinema = get_object_or_404(Counterparty, pk=pk, counterparty_type__in=cinema_types) if pk else None
    permission = "distribution.change_cinemaprofile" if cinema else "distribution.add_cinemaprofile"
    if not request.user.has_perm(permission) or not request.user.has_perm(
        "distribution.change_counterparty" if cinema else "distribution.add_counterparty"
    ):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied

    action = request.POST.get("action") if request.method == "POST" else ""
    form = CinemaAccountForm(request.POST or None, instance=cinema)
    contact_id = request.GET.get("contact") or request.POST.get("contact_id")
    selected_contact = None
    if contact_id and cinema:
        selected_contact = get_object_or_404(CinemaContact, pk=contact_id, cinema=cinema)
    contact_form = CinemaContactForm(prefix="contact", instance=selected_contact)

    if request.method == "POST" and action == "save_cinema" and form.is_valid():
        created = cinema is None
        saved = form.save()
        record_audit_event(
            AuditAction.CREATE if created else AuditAction.UPDATE,
            f"{'Utworzono' if created else 'Zmieniono'} konto kina {saved}.",
            request=request,
            module="booking_crm",
            instance=saved,
        )
        messages.success(request, "Dane kina lub sieci zostały zapisane.")
        return redirect("distribution:booking_cinema_edit", pk=saved.pk)

    if request.method == "POST" and action == "save_contact" and cinema:
        contact_permission = "distribution.change_cinemacontact" if selected_contact else "distribution.add_cinemacontact"
        if not request.user.has_perm(contact_permission):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        contact_form = CinemaContactForm(request.POST, prefix="contact", instance=selected_contact)
        if contact_form.is_valid():
            created = selected_contact is None
            contact = contact_form.save_for_cinema(cinema)
            record_audit_event(
                AuditAction.CREATE if created else AuditAction.UPDATE,
                f"{'Dodano' if created else 'Zmieniono'} kontakt bookingowy {contact.name} w {cinema}.",
                request=request,
                module="booking_crm",
                instance=contact,
            )
            messages.success(request, "Osoba kontaktowa została zapisana.")
            return redirect("distribution:booking_cinema_edit", pk=cinema.pk)

    contacts = cinema.cinema_contacts.order_by("-is_primary", "name") if cinema else []
    deals = cinema.booking_deals.select_related("campaign__title", "owner").order_by("-campaign__release_date") if cinema else []
    context = {
        "form": form,
        "contact_form": contact_form,
        "cinema": cinema,
        "contacts": contacts,
        "deals": deals,
        "selected_contact": selected_contact,
    }
    return render(request, "distribution/booking_cinema_form.html", context)
