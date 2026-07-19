from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    Cost,
    CostScopeMode,
    ExploitationField,
    ReportStatus,
    SalesReport,
    WaterfallAllocationMode,
    WaterfallRun,
    WaterfallRunCostAllocation,
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


def _available_revenue_pools(sales) -> dict[str, Decimal]:
    raw = defaultdict(lambda: Decimal("0.00"))
    for report in sales:
        raw[report.exploitation_field] += report.net_revenue

    total_net = money(sum(raw.values(), Decimal("0.00")))
    positive = {field: value for field, value in raw.items() if value > 0}
    positive_total = sum(positive.values(), Decimal("0.00"))
    if total_net <= 0 or positive_total <= 0:
        return {field: Decimal("0.00") for field in raw}

    target = total_net
    fields = list(positive)
    pools = {}
    allocated = Decimal("0.00")
    for index, field in enumerate(fields):
        if index == len(fields) - 1:
            value = target - allocated
        else:
            value = money(target * positive[field] / positive_total)
            allocated += value
        pools[field] = max(value, Decimal("0.00"))
    return pools


def _step_scope_fields(step: WaterfallStep) -> set[str]:
    fields = step.plan.scoped_exploitation_fields()
    if step.exploitation_fields:
        fields &= set(step.exploitation_fields)
    return fields


def _pool_total(pools: dict[str, Decimal], fields: set[str]) -> Decimal:
    return money(sum((amount for field, amount in pools.items() if field in fields), Decimal("0.00")))


def _take_from_pools(pools: dict[str, Decimal], fields: set[str], requested: Decimal) -> Decimal:
    available = [(field, pools.get(field, Decimal("0.00"))) for field in fields if pools.get(field, Decimal("0.00")) > 0]
    total = sum((amount for _, amount in available), Decimal("0.00"))
    target = min(money(requested), money(total))
    if target <= 0 or not available:
        return Decimal("0.00")

    shares = []
    allocated = Decimal("0.00")
    for index, (field, amount) in enumerate(available):
        if index == len(available) - 1:
            share = min(target - allocated, amount)
        else:
            share = min(money(target * amount / total), amount)
            allocated += share
        shares.append((field, share))

    delta = target - sum((share for _, share in shares), Decimal("0.00"))
    if delta > 0:
        for index in range(len(shares) - 1, -1, -1):
            field, share = shares[index]
            capacity = pools[field] - share
            extra = min(delta, capacity)
            shares[index] = (field, share + extra)
            delta -= extra
            if delta <= 0:
                break

    for field, share in shares:
        pools[field] = money(pools[field] - share)
    return money(sum((share for _, share in shares), Decimal("0.00")))


def _cost_queryset_for_step(step: WaterfallStep, period_end):
    plan = step.plan
    costs = Cost.objects.filter(
        title=plan.title,
        currency=plan.currency,
        recoupable=True,
        cost_date__lte=period_end,
    ).order_by("cost_date", "id")
    if plan.effective_from:
        costs = costs.filter(cost_date__gte=plan.effective_from)
    if step.cost_categories:
        costs = costs.filter(category__in=step.cost_categories)
    return costs


def _finalized_cost_recovery(cost_ids) -> dict[tuple[int, str], Decimal]:
    rows = (
        WaterfallRunCostAllocation.objects.filter(
            cost_id__in=cost_ids,
            run_line__run__status=WaterfallRunStatus.FINALIZED,
        )
        .values("cost_id", "exploitation_field")
        .annotate(total=Sum("allocated_amount"))
    )
    return {
        (row["cost_id"], row["exploitation_field"]): money(row["total"])
        for row in rows
    }


def _cost_components_for_step(step: WaterfallStep, period_end, cost_state) -> list[dict]:
    costs = list(_cost_queryset_for_step(step, period_end))
    recovered = _finalized_cost_recovery([cost.pk for cost in costs])
    scope_fields = _step_scope_fields(step)
    components = []

    for cost in costs:
        for portion in cost.recoupment_portions():
            portion_field = portion["exploitation_field"]
            if cost.scope_mode == CostScopeMode.ALLOCATED:
                eligible_fields = {portion_field} & scope_fields
            else:
                eligible_fields = cost.waterfall_exploitation_fields() & scope_fields
            if not eligible_fields:
                continue

            key = (cost.pk, portion_field)
            if key not in cost_state:
                cost_state[key] = max(money(portion["amount"] - recovered.get(key, Decimal("0.00"))), Decimal("0.00"))
            if cost_state[key] <= 0:
                continue
            components.append({
                "key": key,
                "cost_id": cost.pk,
                "exploitation_field": portion_field,
                "eligible_fields": eligible_fields,
                "remaining": cost_state[key],
                "cost_date": cost.cost_date,
            })
    return components


def _previous_allocation(step: WaterfallStep, current_run: WaterfallRun) -> Decimal:
    total = WaterfallRunLine.objects.filter(
        step=step,
        run__status=WaterfallRunStatus.FINALIZED,
        run__period_end__lt=current_run.period_start,
    ).aggregate(total=Sum("allocated_amount"))["total"]
    return money(total)


def _previous_cost_allocation(step: WaterfallStep, current_run: WaterfallRun) -> Decimal:
    total = WaterfallRunCostAllocation.objects.filter(
        run_line__step=step,
        run_line__run__status=WaterfallRunStatus.FINALIZED,
        run_line__run__period_end__lt=current_run.period_start,
    ).aggregate(total=Sum("allocated_amount"))["total"]
    return money(total)


def _trim_cost_components(components: list[dict], target: Decimal) -> list[dict]:
    remaining_target = max(money(target), Decimal("0.00"))
    trimmed = []
    for component in components:
        amount = min(component["remaining"], remaining_target)
        if amount > 0:
            trimmed.append({**component, "remaining": amount})
            remaining_target -= amount
        if remaining_target <= 0:
            break
    return trimmed


def _recoupment_state(step: WaterfallStep, run: WaterfallRun, cost_state) -> tuple[Decimal, Decimal, dict]:
    fixed_base = step.target_amount
    details = {"fixed_target": str(step.target_amount)}
    if step.include_title_mg:
        fixed_base += step.plan.title.mg_advance
        details["title_mg"] = str(step.plan.title.mg_advance)

    components = _cost_components_for_step(step, run.period_end, cost_state) if step.include_recoupable_costs else []
    cost_outstanding = money(sum((component["remaining"] for component in components), Decimal("0.00")))
    premium_amount = money((fixed_base + cost_outstanding) * step.premium_percent / Decimal("100.00"))
    fixed_target = money(fixed_base + premium_amount)
    current_target = money(fixed_target + cost_outstanding)

    if step.cap_amount:
        current_target = min(current_target, step.cap_amount)
        fixed_target = min(fixed_target, current_target)
        components = _trim_cost_components(components, current_target - fixed_target)
        cost_outstanding = money(sum((component["remaining"] for component in components), Decimal("0.00")))

    previous_total = _previous_allocation(step, run)
    previous_cost = _previous_cost_allocation(step, run)
    previous_non_cost = max(previous_total - previous_cost, Decimal("0.00"))
    fixed_previous = step.opening_recouped + previous_non_cost
    fixed_remaining = max(money(fixed_target - fixed_previous), Decimal("0.00"))
    opening_balance = money(fixed_remaining + cost_outstanding)

    details.update({
        "premium_amount": str(premium_amount),
        "fixed_remaining": str(fixed_remaining),
        "cost_total": str(cost_outstanding),
        "cost_ids": sorted({component["cost_id"] for component in components}),
        "cost_components": [
            {
                "cost_id": component["cost_id"],
                "exploitation_field": component["exploitation_field"],
                "eligible_fields": sorted(component["eligible_fields"]),
                "remaining": str(component["remaining"]),
            }
            for component in components
        ],
        "target_with_premium": str(money(fixed_target + cost_outstanding)),
        "previous_recouped": str(money(step.opening_recouped + previous_total)),
    })
    return money(fixed_target + cost_outstanding), opening_balance, details


def _desired_allocation(step: WaterfallStep, base: Decimal, run: WaterfallRun, cost_state) -> tuple[Decimal, Decimal, dict]:
    details = {"step_type": step.step_type, "allocation_mode": step.allocation_mode, "percentage": str(step.percentage)}
    opening_recoupment = Decimal("0.00")
    if step.step_type == WaterfallStepType.RECOUPMENT:
        _, opening_recoupment, recoupment_details = _recoupment_state(step, run, cost_state)
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


def _line_values(step, base, allocation, opening_recoupment, details):
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


def _allocate_sequential_step(step, run, pools, cost_state):
    step_fields = _step_scope_fields(step)
    base = _pool_total(pools, step_fields)
    desired, opening_recoupment, details = _desired_allocation(step, base, run, cost_state)
    limit = min(desired, base)
    cost_allocations = []

    if step.step_type != WaterfallStepType.RECOUPMENT or not details.get("cost_components"):
        allocation = _take_from_pools(pools, step_fields, limit)
        return _line_values(step, base, allocation, opening_recoupment, details), cost_allocations

    fixed_requested = min(Decimal(details["fixed_remaining"]), limit)
    fixed_allocation = _take_from_pools(pools, step_fields, fixed_requested)
    remaining_limit = money(limit - fixed_allocation)
    cost_allocation_total = Decimal("0.00")

    for component in details["cost_components"]:
        if remaining_limit <= 0:
            break
        key = (component["cost_id"], component["exploitation_field"])
        requested = min(Decimal(component["remaining"]), cost_state.get(key, Decimal("0.00")), remaining_limit)
        allocated = _take_from_pools(pools, set(component["eligible_fields"]), requested)
        if allocated <= 0:
            continue
        cost_state[key] = money(cost_state[key] - allocated)
        remaining_limit = money(remaining_limit - allocated)
        cost_allocation_total += allocated
        cost_allocations.append({
            "cost_id": component["cost_id"],
            "exploitation_field": component["exploitation_field"],
            "allocated_amount": allocated,
        })

    allocation = money(fixed_allocation + cost_allocation_total)
    details["allocated_to_fixed"] = str(fixed_allocation)
    details["allocated_to_costs"] = str(money(cost_allocation_total))
    return _line_values(step, base, allocation, opening_recoupment, details), cost_allocations


@transaction.atomic
def calculate_waterfall_run(run: WaterfallRun) -> WaterfallRun:
    run = WaterfallRun.objects.select_for_update().select_related("plan", "plan__title").get(pk=run.pk)
    if run.status != WaterfallRunStatus.DRAFT:
        raise ValidationError("Tylko robocze uruchomienie moze zostac przeliczone.")

    sales = _sales_for_run(run)
    sales_list = list(sales)
    gross_revenue = money(sum((report.gross_revenue for report in sales_list), Decimal("0.00")))
    deductions = money(sum((report.deductions for report in sales_list), Decimal("0.00")))
    withholding = money(sum((report.vat_withholding for report in sales_list), Decimal("0.00")))
    net_revenue = money(gross_revenue - deductions - withholding)
    pools = _available_revenue_pools(sales_list)
    steps = list(run.plan.steps.filter(active=True).select_related("beneficiary").order_by("phase", "sort_order", "id"))
    phases = defaultdict(list)
    for step in steps:
        phases[step.phase].append(step)

    calculated_lines = []
    cost_state = {}
    for phase in sorted(phases):
        sequential = [step for step in phases[phase] if step.allocation_mode == WaterfallAllocationMode.SEQUENTIAL]
        parallel = [step for step in phases[phase] if step.allocation_mode != WaterfallAllocationMode.SEQUENTIAL]

        for step in sequential:
            values, cost_allocations = _allocate_sequential_step(step, run, pools, cost_state)
            calculated_lines.append((values, cost_allocations))

        if parallel:
            if any(step.include_recoupable_costs for step in parallel):
                raise ValidationError("Koszty fakturowe nie mogą być rozliczane w kroku równoległym. Ustaw tryb 'kolejno'.")
            candidates = []
            for step in parallel:
                fields = _step_scope_fields(step)
                base = _pool_total(pools, fields)
                desired, opening_recoupment, details = _desired_allocation(step, base, run, cost_state)
                candidates.append((step, fields, base, desired, opening_recoupment, details))
            desired_total = sum((candidate[3] for candidate in candidates), Decimal("0.00"))
            phase_available = money(sum(pools.values(), Decimal("0.00")))
            scale = min(Decimal("1.00"), phase_available / desired_total) if desired_total else Decimal("0.00")
            for step, fields, base, desired, opening_recoupment, details in candidates:
                details["parallel_scale"] = str(scale)
                allocation = _take_from_pools(pools, fields, money(desired * scale))
                calculated_lines.append((_line_values(step, base, allocation, opening_recoupment, details), []))

    run.lines.all().delete()
    cost_snapshot = []
    for sequence, (values, cost_allocations) in enumerate(calculated_lines, start=1):
        line = WaterfallRunLine.objects.create(run=run, sequence=sequence, **values)
        for allocation in cost_allocations:
            WaterfallRunCostAllocation.objects.create(run_line=line, **allocation)
            cost_snapshot.append({
                "cost_id": allocation["cost_id"],
                "exploitation_field": allocation["exploitation_field"],
                "allocated_amount": str(allocation["allocated_amount"]),
            })

    allocated_amount = money(sum((values["allocated_amount"] for values, _ in calculated_lines), Decimal("0.00")))
    run.gross_revenue = gross_revenue
    run.net_revenue = net_revenue
    run.allocated_amount = allocated_amount
    run.closing_available = money(sum(pools.values(), Decimal("0.00")))
    run.calculated_at = timezone.now()
    run.calculation_snapshot = {
        "sales_report_ids": [report.pk for report in sales_list],
        "deductions": str(deductions),
        "vat_withholding": str(withholding),
        "plan_version": run.plan.version,
        "step_ids": [step.pk for step in steps],
        "cost_ids": sorted({item["cost_id"] for item in cost_snapshot}),
        "cost_allocations": cost_snapshot,
        "closing_revenue_by_field": {field: str(amount) for field, amount in pools.items()},
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


def _portion_amounts(cost: Cost) -> dict[str, Decimal]:
    return {portion["exploitation_field"]: money(portion["amount"]) for portion in cost.recoupment_portions()}


@transaction.atomic
def finalize_waterfall_run(run: WaterfallRun, user=None) -> WaterfallRun:
    run = WaterfallRun.objects.select_for_update().get(pk=run.pk)
    if run.status != WaterfallRunStatus.DRAFT:
        raise ValidationError("Tylko robocze uruchomienie moze zostac zatwierdzone.")
    if not run.calculated_at:
        raise ValidationError("Najpierw przelicz uruchomienie waterfall.")

    draft_rows = list(
        WaterfallRunCostAllocation.objects.filter(run_line__run=run)
        .values("cost_id", "exploitation_field")
        .annotate(total=Sum("allocated_amount"))
    )
    cost_ids = [row["cost_id"] for row in draft_rows]
    costs = {cost.pk: cost for cost in Cost.objects.select_for_update().filter(pk__in=cost_ids)}
    recovered = _finalized_cost_recovery(cost_ids)
    for row in draft_rows:
        key = (row["cost_id"], row["exploitation_field"])
        portion_amount = _portion_amounts(costs[row["cost_id"]]).get(row["exploitation_field"], Decimal("0.00"))
        if money(recovered.get(key, Decimal("0.00")) + row["total"]) > portion_amount:
            raise ValidationError("Co najmniej jeden koszt został odzyskany w innym rozliczeniu. Przelicz okres ponownie.")

    run.status = WaterfallRunStatus.FINALIZED
    run.finalized_at = timezone.now()
    run.finalized_by = user if getattr(user, "is_authenticated", False) else None
    run.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])
    return run
