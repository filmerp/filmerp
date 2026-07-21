from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    BookingActivityForm,
    BookingCampaignForm,
    BookingDealForm,
    CinemaAccountForm,
    CinemaContactForm,
)
from .models import (
    AuditAction,
    BookingActivity,
    BookingActivityType,
    BookingCampaign,
    BookingCampaignStatus,
    BookingDeal,
    BookingDealStage,
    CinemaContact,
    Counterparty,
    CounterpartyType,
)
from .security import record_audit_event


PIPELINE_STAGES = tuple(BookingDealStage.choices)
TERMINAL_STAGES = {BookingDealStage.ENDED, BookingDealStage.LOST}
BOOKED_STAGES = {
    BookingDealStage.CONFIRMED,
    BookingDealStage.PLAYING,
    BookingDealStage.HOLDOVER,
    BookingDealStage.ENDED,
}
CONTACT_ACTIVITY_TYPES = {
    BookingActivityType.CALL,
    BookingActivityType.EMAIL,
    BookingActivityType.MEETING,
}


def _crm_url(*, campaign_id="", view="pipeline"):
    params = []
    if campaign_id:
        params.append(f"campaign={campaign_id}")
    if view and view != "pipeline":
        params.append(f"view={view}")
    query = f"?{'&'.join(params)}" if params else ""
    return f"{reverse('distribution:booking_crm')}{query}"


@login_required
@permission_required("distribution.view_bookingdeal", raise_exception=True)
def booking_crm(request):
    today = timezone.localdate()
    active_view = request.GET.get("view", "pipeline")
    if active_view not in {"pipeline", "cinemas", "tasks"}:
        active_view = "pipeline"

    campaigns = BookingCampaign.objects.select_related("title", "owner").annotate(
        deals_count=Count("deals", distinct=True),
        confirmed_count=Count("deals", filter=Q(deals__stage__in=BOOKED_STAGES), distinct=True),
    ).order_by("-release_date", "title__title_pl")
    selected_campaign = None
    campaign_id = request.GET.get("campaign")
    if campaign_id:
        selected_campaign = get_object_or_404(campaigns, pk=campaign_id)
    elif campaigns.exists():
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
    ).prefetch_related("bookings")
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
    if query and active_view == "cinemas":
        cinemas = cinemas.filter(
            Q(name__icontains=query)
            | Q(cinema_profile__city__icontains=query)
            | Q(cinema_contacts__name__icontains=query)
        ).distinct()

    owners = get_user_model().objects.filter(is_active=True).order_by("first_name", "last_name", "username")
    context = {
        "active_view": active_view,
        "campaigns": campaigns,
        "selected_campaign": selected_campaign,
        "pipeline": pipeline,
        "deals_count": len(deal_rows),
        "booked_count": len(booked),
        "confirmed_screens": confirmed_screens,
        "overdue_count": len(overdue),
        "target_cinemas": target_cinemas,
        "progress_percent": progress_percent,
        "task_deals": task_deals,
        "today": today,
        "task_horizon": today + timedelta(days=14),
        "cinemas": cinemas,
        "owners": owners,
        "query": query,
        "owner_id": owner_id,
        "can_add_campaign": request.user.has_perm("distribution.add_bookingcampaign"),
        "can_add_deal": request.user.has_perm("distribution.add_bookingdeal"),
        "can_add_cinema": request.user.has_perm("distribution.add_cinemaprofile") and request.user.has_perm("distribution.add_counterparty"),
    }
    return render(request, "distribution/booking_crm.html", context)


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
    form = BookingDealForm(
        request.POST or None,
        instance=deal,
        campaign=campaign,
        user=request.user,
    )
    activity_form = BookingActivityForm(prefix="activity")

    if request.method == "POST" and action == "save_deal" and form.is_valid():
        created = deal is None
        with transaction.atomic():
            saved = form.save()
            booking = None
            if saved.stage in {
                BookingDealStage.CONFIRMED,
                BookingDealStage.PLAYING,
                BookingDealStage.HOLDOVER,
            }:
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
