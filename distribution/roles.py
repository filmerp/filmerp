from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from distribution.models import (
    AcquisitionAgreement,
    CinemaBooking,
    CinemaReportImport,
    CinemaReportImportRow,
    Cost,
    Counterparty,
    LanguageVersion,
    RightsIssue,
    RightsWindow,
    RoyaltyStatement,
    SalesAgreement,
    SalesReport,
    Territory,
    Title,
    TitleMaterial,
    WaterfallParticipant,
    WaterfallRecoupmentItem,
    WaterfallRecoupmentRule,
)


ROLE_MODELS = {
    "legal": [AcquisitionAgreement, SalesAgreement, RightsWindow, RightsIssue, Territory, LanguageVersion, Title, Counterparty],
    "sales": [SalesAgreement, SalesReport, CinemaBooking, CinemaReportImport, CinemaReportImportRow, RightsWindow, Territory, LanguageVersion, Title, TitleMaterial, Counterparty],
    "finance": [SalesAgreement, SalesReport, Cost, RoyaltyStatement, WaterfallRecoupmentRule, WaterfallRecoupmentItem, WaterfallParticipant, CinemaReportImport, CinemaReportImportRow, Title, TitleMaterial, Counterparty],
    "readonly": [AcquisitionAgreement, SalesAgreement, RightsWindow, RightsIssue, Territory, LanguageVersion, Title, TitleMaterial, Counterparty, SalesReport, CinemaBooking, CinemaReportImport, CinemaReportImportRow, Cost, RoyaltyStatement, WaterfallRecoupmentRule, WaterfallRecoupmentItem, WaterfallParticipant],
}

ROLE_ACTIONS = {
    "legal": ["view", "add", "change", "delete"],
    "sales": ["view", "add", "change", "delete"],
    "finance": ["view", "add", "change", "delete"],
    "readonly": ["view"],
}


def sync_role_groups():
    synced = []
    for role, models in ROLE_MODELS.items():
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.clear()
        actions = ROLE_ACTIONS[role]
        permissions = []
        for model in models:
            content_type = ContentType.objects.get_for_model(model)
            codenames = [f"{action}_{model._meta.model_name}" for action in actions]
            permissions.extend(Permission.objects.filter(content_type=content_type, codename__in=codenames))
        group.permissions.set(permissions)
        synced.append((role, len(permissions)))
    return synced
