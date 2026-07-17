from django.core.exceptions import ValidationError
from django.db import transaction

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
        statement = RoyaltyStatement.objects.filter(waterfall_run=run, recipient=recipient).first()
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
