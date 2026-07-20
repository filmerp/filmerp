from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from auditlog.registry import auditlog

from . import models


DOMAIN_MODELS = [
    models.Territory,
    models.LanguageVersion,
    models.Counterparty,
    models.Title,
    models.AcquisitionAgreement,
    models.SalesAgreement,
    models.RightsWindow,
    models.RightsIssue,
    models.CinemaBooking,
    models.CinemaReportImport,
    models.CinemaReportImportRow,
    models.SalesReport,
    models.Cost,
    models.DocumentInboxItem,
    models.TitleMaterial,
    models.WaterfallRecoupmentRule,
    models.WaterfallRecoupmentItem,
    models.WaterfallParticipant,
    models.WaterfallPlan,
    models.WaterfallStep,
    models.WaterfallRun,
    models.WaterfallRunLine,
    models.WaterfallRunCostAllocation,
    models.RoyaltyStatement,
]


for model in DOMAIN_MODELS:
    auditlog.register(model)

auditlog.register(
    get_user_model(),
    exclude_fields=["password", "last_login"],
    m2m_fields={"groups", "user_permissions"},
)
auditlog.register(Group, m2m_fields={"permissions"})
auditlog.register(models.SecurityProfile)
