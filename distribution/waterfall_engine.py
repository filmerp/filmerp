from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Cost,
    ReportStatus,
    SalesReport,
    WaterfallAllocationMode,
    WaterfallRun,
    WaterfallRunLine,
    WaterfallRunStatus,
    WaterfallStep,
    WaterfallStepType,
)


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return (value or Decimal("0.00")).quantize(CENT, rounding=ROUND_HALF_UP)


def _sales_for_run(run: WaterfallRun):
    plan = run.plan
    reports = SalesReport.objects.filter(
        title=plan.title,
        currency=plan.currency,
        period_start__lte=run.period_end,
        period_end__gte=run.period_start,
    ).exclude(status=ReportStatus.REJECTED)
    if not plan.applies_to_all_exploitation_fields:
        reports = reports.filter(exploitation_field__in=plan.exploitation_fields)
    return reports


def _costs_for_step(step: WaterfallStep, period_end):
    plan = step.plan
    costs = Cost.objects.filter(
        title=plan.title,
        currency=plan.currency,
        recoupable=True,
        cost_date__lte=period_end,
    )
    if plan.effective_from:
        costs = costs.filter(cost_date__gte=plan.effective_from)
    if step.cost_categories:
        costs = costs.filter(category__in=step.cost_categories)

    scoped_fields = set(step.exploitation_fields or [])
    if not scoped_fields and not plan.applies_to_all_exploitation_fields:
        scoped_fields = plan.scoped_exploitation_fields()
    if scoped_fields:
        matching_ids = [
            cost.pk
            for cost in costs
            if any(cost.applies_to_exploitation_field(field) for field in scoped_fields)
        ]
        costs = costs.filter(pk__in=matching_ids)
    return costs


def _previous_allocation(step: WaterfallStep, current_run: WaterfallRun) -> Decimal:
    total = WaterfallRunLine.objects.filter(
        step=step,
        run__status=WaterfallRunStatus.FINALIZED,
        run__period_end__lt=current_run.period_start,
    ).aggregate(total=Sum("allocated_amount"))["total"]
    return money(total)


def _recoupment_state(step: WaterfallStep, run: WaterfallRun) -> tuple[Decimal, Decimal, dict]:
    target = step.target_amount
    details = {"fixed_target": str(step.target_amount)}
    if step.include_title_mg:
        target += step.plan.title.mg_advance
        details["title_mg"] = str(step.plan.title.mg_advance)
    if step.include_recoupable_costs:
        costs = _costs_for_step(step, run.period_end)
        cost_total = sum((cost.net_amount for cost in costs), Decimal("0.00"))
        target += cost_total
        details["cost_total"] = str(cost_total)
        details["cost_ids"] = list(costs.values_list("pk", flat=True))
    target = target * (Decimal("100.00") + step.premium_percent) / Decimal("100.00")
    if step.cap_amount:
        target = min(target, step.cap_amount)
    previous = step.opening_recouped + _previous_allocation(step, run)
    opening_balance = max(money(target - previous), Decimal("0.00"))
    details.update({"target_with_premium": str(money(target)), "previous_recouped": str(money(previous))})
    return money(target), opening_balance, details


def _desired_allocation(step: WaterfallStep, base: Decimal, run: WaterfallRun) -> tuple[Decimal, Decimal, dict]:
    details = {"step_type": step.step_type, "allocation_mode": step.allocation_mode, "percentage": str(step.percentage)}
    opening_recoupment = Decimal("0.00")
    if step.step_type == WaterfallStepType.RECOUPMENT:
        _, opening_recoupment, recoupment_details = _recoupment_state(step, run)
        details.update(recoupment_details)
        desired = opening_recoupment
        if step.percentage:
            desired = min(desired, base * step.percentage / Decimal("100.00"))
    else:
        desired = step.fixed_amount + (base * step.percentage / Decimal("100.00"))
        if step.cap_amount:
            previous = _previous_allocation(step, run)
            desired = min(desired, max(step.cap_amount - previous, Decimal("0.00")))
            details["previous_allocated"] = str(previous)
    return money(max(desired, Decimal("0.00"))), money(opening_recoupment), details


def _line_values(step, run, base, allocation, opening_recoupment, details):
    closing_recoupment = max(opening_recoupment - allocation, Decimal("0.00"))
    return {
        "step": step,
        "phase": step.phase,
        "beneficiary": step.beneficiary,
        "opening_available": base,
        "calculation_base": base,
        "allocated_amount": allocation,
        "closing_available": max(base - allocation, Decimal("0.00")),
        "opening_recoupment": opening_recoupment,
        "closing_recoupment": money(closing_recoupment),
        "calculation_details": details,
    }


@transaction.atomic
def calculate_waterfall_run(run: WaterfallRun) -> WaterfallRun:
    run = WaterfallRun.objects.select_for_update().select_related("plan", "plan__title").get(pk=run.pk)
    if run.status != WaterfallRunStatus.DRAFT:
        raise ValidationError("Tylko robocze uruchomienie moze zostac przeliczone.")

    sales = _sales_for_run(run)
    gross_revenue = money(sales.aggregate(total=Sum("gross_revenue"))["total"])
    deductions = money(sales.aggregate(total=Sum("deductions"))["total"])
    withholding = money(sales.aggregate(total=Sum("vat_withholding"))["total"])
    net_revenue = money(gross_revenue - deductions - withholding)
    available = max(net_revenue, Decimal("0.00"))
    steps = list(run.plan.steps.filter(active=True).select_related("beneficiary").order_by("phase", "sort_order", "id"))
    phases = defaultdict(list)
    for step in steps:
        phases[step.phase].append(step)

    calculated_lines = []
    for phase in sorted(phases):
        sequential = [step for step in phases[phase] if step.allocation_mode == WaterfallAllocationMode.SEQUENTIAL]
        parallel = [step for step in phases[phase] if step.allocation_mode != WaterfallAllocationMode.SEQUENTIAL]

        for step in sequential:
            base = available
            desired, opening_recoupment, details = _desired_allocation(step, base, run)
            allocation = min(desired, available)
            calculated_lines.append(_line_values(step, run, base, allocation, opening_recoupment, details))
            available = money(available - allocation)

        if parallel and available:
            phase_base = available
            candidates = []
            for step in parallel:
                desired, opening_recoupment, details = _desired_allocation(step, phase_base, run)
                candidates.append((step, desired, opening_recoupment, details))
            desired_total = sum((candidate[1] for candidate in candidates), Decimal("0.00"))
            scale = min(Decimal("1.00"), phase_base / desired_total) if desired_total else Decimal("0.00")
            allocations = [money(candidate[1] * scale) for candidate in candidates]
            rounding_delta = money(min(phase_base, desired_total) - sum(allocations, Decimal("0.00")))
            if allocations and rounding_delta:
                allocations[-1] += rounding_delta
            for candidate, allocation in zip(candidates, allocations):
                step, _, opening_recoupment, details = candidate
                details["parallel_scale"] = str(scale)
                line = _line_values(step, run, phase_base, allocation, opening_recoupment, details)
                calculated_lines.append(line)
            available = money(available - sum(allocations, Decimal("0.00")))

    run.lines.all().delete()
    for sequence, values in enumerate(calculated_lines, start=1):
        WaterfallRunLine.objects.create(run=run, sequence=sequence, **values)

    allocated_amount = money(sum((line["allocated_amount"] for line in calculated_lines), Decimal("0.00")))
    run.gross_revenue = gross_revenue
    run.net_revenue = net_revenue
    run.allocated_amount = allocated_amount
    run.closing_available = available
    run.calculated_at = timezone.now()
    run.calculation_snapshot = {
        "sales_report_ids": list(sales.values_list("pk", flat=True)),
        "deductions": str(deductions),
        "vat_withholding": str(withholding),
        "plan_version": run.plan.version,
        "step_ids": [step.pk for step in steps],
    }
    run.save(update_fields=[
        "gross_revenue",
        "net_revenue",
        "allocated_amount",
        "closing_available",
        "calculated_at",
        "calculation_snapshot",
        "updated_at",
    ])
    return run


@transaction.atomic
def finalize_waterfall_run(run: WaterfallRun, user=None) -> WaterfallRun:
    run = WaterfallRun.objects.select_for_update().get(pk=run.pk)
    if run.status != WaterfallRunStatus.DRAFT:
        raise ValidationError("Tylko robocze uruchomienie moze zostac zatwierdzone.")
    if not run.calculated_at:
        raise ValidationError("Najpierw przelicz uruchomienie waterfall.")
    run.status = WaterfallRunStatus.FINALIZED
    run.finalized_at = timezone.now()
    run.finalized_by = user if getattr(user, "is_authenticated", False) else None
    run.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])
    return run
