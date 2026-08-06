from django.core.exceptions import ValidationError
from copy import deepcopy

from django.db import transaction
from django.utils import timezone

from .models import Counterparty, RoyaltyStatement, StatementStatus, WaterfallRun
from .pdf import build_royalty_statement_pdf


@transaction.atomic
def create_statement_documents(run: WaterfallRun, recipient_ids) -> list[RoyaltyStatement]:
    run = WaterfallRun.objects.select_related("plan", "plan__title").get(pk=run.pk)
    allowed_ids = set(
        run.plan.steps.filter(active=True, beneficiary__isnull=False)
        .values_list("beneficiary_id", flat=True)
    )
    selected_ids = {
        int(value) for value in recipient_ids if str(value).isdigit()
    } & allowed_ids
    if not selected_ids:
        raise ValidationError("Wybierz co najmniej jednego odbiorce statementu.")

    statements = []
    for recipient in Counterparty.objects.filter(pk__in=selected_ids).order_by("name"):
        statement = RoyaltyStatement.objects.filter(
            waterfall_run=run,
            recipient=recipient,
        ).exclude(status=StatementStatus.VOIDED).order_by("-revision", "-pk").first()
        if statement is None:
            statement = RoyaltyStatement.objects.create(
                title=run.plan.title,
                recipient=recipient,
                period_start=run.period_start,
                period_end=run.period_end,
                currency=run.plan.currency,
                waterfall_plan=run.plan,
                waterfall_run=run,
                status=StatementStatus.DRAFT,
            )
        if not statement.locked_at or not statement.calculation_snapshot:
            statement.freeze_calculation(lock=True)
            run_sales_ids = run.calculation_snapshot.get("sales_report_ids")
            if run_sales_ids is not None:
                statement.calculation_snapshot["sales_report_ids"] = run_sales_ids
                statement.save(update_fields=["calculation_snapshot", "updated_at"])
        pdf_file = build_royalty_statement_pdf(statement)
        if statement.statement_file:
            statement.statement_file.delete(save=False)
        statement.statement_file.save(pdf_file.name, pdf_file, save=True)
        statements.append(statement)
    return statements


@transaction.atomic
def create_statement_revision(statement: RoyaltyStatement, *, reason: str, actor=None) -> RoyaltyStatement:
    original = RoyaltyStatement.objects.select_for_update().select_related(
        "title", "recipient", "waterfall_plan", "waterfall_run"
    ).get(pk=statement.pk)
    if original.status == StatementStatus.VOIDED:
        raise ValidationError("Nie można korygować statementu, który został już zastąpiony.")
    original.validate_for_issue()
    if not original.calculation_snapshot:
        original.freeze_calculation(lock=True)

    correction = RoyaltyStatement.objects.create(
        title=original.title,
        recipient=original.recipient,
        revision=original.revision + 1,
        supersedes=original,
        period_start=original.period_start,
        period_end=original.period_end,
        currency=original.currency,
        distributor_fee_percent=original.distributor_fee_percent,
        recipient_share_percent=original.recipient_share_percent,
        waterfall_plan=original.waterfall_plan,
        waterfall_run=original.waterfall_run,
        status=StatementStatus.DRAFT,
        calculation_snapshot=deepcopy(original.calculation_snapshot),
        calculated_at=original.calculated_at,
        locked_at=original.locked_at or timezone.now(),
        correction_reason=reason.strip(),
        notes=original.notes,
    )
    pdf_file = build_royalty_statement_pdf(correction)
    correction.statement_file.save(pdf_file.name, pdf_file, save=True)

    original.status = StatementStatus.VOIDED
    original.voided_at = timezone.now()
    original.voided_by = actor if getattr(actor, "pk", None) else None
    original.save(update_fields=["status", "voided_at", "voided_by", "updated_at"])
    return correction
