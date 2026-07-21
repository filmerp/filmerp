from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from distribution.models import (
    AcquisitionAgreement,
    BookingActivity,
    BookingCampaign,
    BookingDeal,
    CinemaBooking,
    CinemaContact,
    CinemaProfile,
    CinemaReportImport,
    CinemaReportImportRow,
    Cost,
    Counterparty,
    DocumentInboxItem,
    LanguageVersion,
    RightsIssue,
    RightsWindow,
    RoyaltyStatement,
    SalesAgreement,
    SalesReport,
    SecurityProfile,
    Territory,
    Title,
    TitleMaterial,
    WaterfallPlan,
    WaterfallRun,
    WaterfallRunCostAllocation,
    WaterfallRunLine,
    WaterfallStep,
)


BOOKING_MODELS = [BookingCampaign, BookingDeal, BookingActivity, CinemaProfile, CinemaContact]


ROLE_MODELS = {
    "legal": [AcquisitionAgreement, SalesAgreement, RightsWindow, RightsIssue, Territory, LanguageVersion, Title, Counterparty, WaterfallPlan, WaterfallStep, *BOOKING_MODELS],
    "sales": [SalesAgreement, SalesReport, CinemaBooking, CinemaReportImport, CinemaReportImportRow, DocumentInboxItem, RightsWindow, Territory, LanguageVersion, Title, TitleMaterial, Counterparty, *BOOKING_MODELS],
    "finance": [AcquisitionAgreement, SalesAgreement, SalesReport, CinemaBooking, Cost, RoyaltyStatement, WaterfallPlan, WaterfallStep, WaterfallRun, WaterfallRunLine, WaterfallRunCostAllocation, CinemaReportImport, CinemaReportImportRow, DocumentInboxItem, Title, TitleMaterial, Counterparty, *BOOKING_MODELS],
    "readonly": [AcquisitionAgreement, SalesAgreement, RightsWindow, RightsIssue, Territory, LanguageVersion, Title, TitleMaterial, Counterparty, SalesReport, CinemaBooking, CinemaReportImport, CinemaReportImportRow, DocumentInboxItem, Cost, RoyaltyStatement, WaterfallPlan, WaterfallStep, WaterfallRun, WaterfallRunLine, WaterfallRunCostAllocation, *BOOKING_MODELS],
}

ROLE_ACTIONS = {
    "legal": ["view", "add", "change", "delete"],
    "sales": ["view", "add", "change", "delete"],
    "finance": ["view", "add", "change", "delete"],
    "readonly": ["view"],
}

ROLE_CUSTOM_PERMISSIONS = {
    "legal": ["view_business_audit"],
    "sales": ["approve_cinema_reports"],
    "finance": [
        "approve_cinema_reports",
        "finalize_waterfalls",
        "generate_statements",
        "send_statements",
        "mark_statements_paid",
        "export_financial_data",
        "view_business_audit",
    ],
    "readonly": [],
}


def sync_role_groups(*, reset=False):
    synced = []
    for role, models in ROLE_MODELS.items():
        group, _ = Group.objects.get_or_create(name=role)
        actions = ROLE_ACTIONS[role]
        permissions = []
        for model in models:
            content_type = ContentType.objects.get_for_model(model)
            codenames = [f"{action}_{model._meta.model_name}" for action in actions]
            permissions.extend(Permission.objects.filter(content_type=content_type, codename__in=codenames))
        security_content_type = ContentType.objects.get_for_model(SecurityProfile)
        permissions.extend(
            Permission.objects.filter(
                content_type=security_content_type,
                codename__in=ROLE_CUSTOM_PERMISSIONS[role],
            )
        )
        if reset:
            group.permissions.set(set(permissions))
        else:
            group.permissions.add(*set(permissions))
        synced.append((role, group.permissions.count()))

    administrator, _ = Group.objects.get_or_create(name="administrator")
    administrator_permissions = Permission.objects.filter(
        content_type__app_label__in=["distribution", "auth", "auditlog", "usersessions", "mfa"]
    )
    if reset:
        administrator.permissions.set(administrator_permissions)
    else:
        administrator.permissions.add(*administrator_permissions)
    for user in get_user_model().objects.filter(is_superuser=True):
        user.groups.add(administrator)
    synced.append(("administrator", administrator.permissions.count()))
    return synced
