from decimal import Decimal

from django.db import transaction

from .models import (
    AcquisitionAgreement,
    WaterfallAllocationMode,
    WaterfallPlan,
    WaterfallPlanStatus,
    WaterfallStep,
    WaterfallStepType,
)


@transaction.atomic
def create_contract_waterfall(cleaned_data):
    title = cleaned_data["title"]
    licensor = cleaned_data["licensor"]
    distributor = cleaned_data["distributor"]
    scope = list(cleaned_data.get("exploitation_fields") or [])

    agreement = AcquisitionAgreement.objects.create(
        title=title,
        licensor=licensor,
        contract_number=cleaned_data.get("contract_number", ""),
        signed_date=cleaned_data.get("signed_date"),
        rights_start=cleaned_data.get("rights_start"),
        rights_end=cleaned_data.get("rights_end"),
        currency=cleaned_data["currency"],
        mg_advance=cleaned_data["mg_advance"],
        revenue_share_percent=cleaned_data["licensor_share_percent"],
        pa_recoupable=cleaned_data["pa_recoupable"],
        status=cleaned_data["status"],
        notes=cleaned_data.get("notes", ""),
    )
    agreement.territories.set(cleaned_data.get("territories"))

    title.mg_advance = cleaned_data["mg_advance"]
    title.acquisition_currency = cleaned_data["currency"]
    if not title.producer_id:
        title.producer = licensor
    title.save(update_fields=["mg_advance", "acquisition_currency", "producer", "updated_at"])

    plan_name = "Główny waterfall"
    previous = title.waterfall_plans.filter(name=plan_name).order_by("-version").first()
    version = previous.version + 1 if previous else 1
    if previous and previous.status == WaterfallPlanStatus.ACTIVE:
        previous.status = WaterfallPlanStatus.ARCHIVED
        previous.save(update_fields=["status", "updated_at"])

    plan = WaterfallPlan.objects.create(
        title=title,
        name=plan_name,
        version=version,
        status=WaterfallPlanStatus.ACTIVE,
        currency=cleaned_data["currency"],
        effective_from=cleaned_data.get("rights_start"),
        effective_to=cleaned_data.get("rights_end"),
        applies_to_all_exploitation_fields=cleaned_data["applies_to_all_exploitation_fields"],
        exploitation_fields=scope,
        notes=f"Utworzono z umowy {agreement.contract_number or agreement.pk}. {cleaned_data.get('notes', '')}".strip(),
    )

    steps = []
    fee = cleaned_data["distributor_fee_percent"]
    if fee:
        steps.append(WaterfallStep(
            plan=plan, phase=0, sort_order=10, name="Fee dystrybutora",
            step_type=WaterfallStepType.COMMISSION, beneficiary=distributor, percentage=fee,
        ))
    if cleaned_data["pa_recoupable"]:
        steps.append(WaterfallStep(
            plan=plan, phase=0, sort_order=20, name="Zwrot kosztów P&A",
            step_type=WaterfallStepType.RECOUPMENT, beneficiary=distributor,
            include_recoupable_costs=True,
            cost_categories=list(cleaned_data["pa_cost_categories"]),
            exploitation_fields=scope,
        ))
    if cleaned_data["mg_advance"]:
        steps.append(WaterfallStep(
            plan=plan, phase=0, sort_order=30, name="Zwrot MG",
            step_type=WaterfallStepType.RECOUPMENT, beneficiary=distributor,
            include_title_mg=True,
        ))

    licensor_share = cleaned_data["licensor_share_percent"]
    distributor_share = Decimal("100.00") - licensor_share
    for order, beneficiary, percentage, label in (
        (10, licensor, licensor_share, "Udział licencjodawcy"),
        (20, distributor, distributor_share, "Udział dystrybutora"),
    ):
        if percentage:
            steps.append(WaterfallStep(
                plan=plan, phase=1, sort_order=order, name=label,
                step_type=WaterfallStepType.SPLIT,
                allocation_mode=WaterfallAllocationMode.PARI_PASSU,
                beneficiary=beneficiary, percentage=percentage,
            ))
    WaterfallStep.objects.bulk_create(steps)
    return agreement, plan
