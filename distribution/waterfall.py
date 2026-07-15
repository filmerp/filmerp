from decimal import Decimal

from django.db.models import Sum

from .models import Cost, ReportStatus, SalesReport, WaterfallParticipant, WaterfallRecoupmentRule


def money(value):
    return value or Decimal("0.00")


def allocate_participants(rule, split_base):
    participants = list(rule.participants.filter(active=True).select_related("recipient").order_by("sort_order", "recipient__name"))
    if not participants:
        amount = split_base * rule.participant_share_percent / Decimal("100.00")
        return [
            {
                "participant": None,
                "recipient": "Partner",
                "participation_type": "legacy",
                "share_percent": rule.participant_share_percent,
                "amount": amount,
                "raw_amount": amount,
                "cap_applied": False,
            }
        ] if amount else []

    allocations = []
    for participant in participants:
        raw_amount = split_base * participant.share_percent / Decimal("100.00")
        amount = raw_amount
        remaining_cap = participant.remaining_cap
        cap_applied = False
        if remaining_cap is not None and amount > remaining_cap:
            amount = remaining_cap
            cap_applied = True
        allocations.append(
            {
                "participant": participant,
                "recipient": participant.recipient.name,
                "participation_type": participant.get_participation_type_display(),
                "share_percent": participant.share_percent,
                "amount": amount,
                "raw_amount": raw_amount,
                "cap_applied": cap_applied,
            }
        )

    total_allocated = sum((item["amount"] for item in allocations), Decimal("0.00"))
    if total_allocated > split_base and total_allocated:
        scale = split_base / total_allocated
        for item in allocations:
            item["amount"] = item["amount"] * scale
            item["cap_applied"] = True
    return allocations


def calculate_waterfall(filters):
    rules = (
        WaterfallRecoupmentRule.objects.filter(active=True)
        .select_related("title")
        .prefetch_related("recoupment_items", "participants", "participants__recipient")
    )
    if filters.get("title_id"):
        rules = rules.filter(title_id=filters["title_id"])

    rows = []
    totals = {
        "net_revenue": Decimal("0.00"),
        "recoupable_costs": Decimal("0.00"),
        "recoupment_pool": Decimal("0.00"),
        "recouped_amount": Decimal("0.00"),
        "unrecouped_balance": Decimal("0.00"),
        "distributor_fee": Decimal("0.00"),
        "participant_share": Decimal("0.00"),
        "distributor_remainder": Decimal("0.00"),
        "manual_recoupment_items": Decimal("0.00"),
    }

    for rule in rules:
        sales = SalesReport.objects.filter(
            title=rule.title,
            exploitation_field=rule.exploitation_field,
            currency=rule.currency,
            period_start__gte=filters["date_from"],
            period_start__lte=filters["date_to"],
        ).exclude(status=ReportStatus.REJECTED)
        costs = Cost.objects.filter(
            title=rule.title,
            currency=rule.currency,
            recoupable=True,
            cost_date__gte=filters["date_from"],
            cost_date__lte=filters["date_to"],
        )
        if filters.get("counterparty_id"):
            sales = sales.filter(counterparty_id=filters["counterparty_id"])
            costs = costs.filter(supplier_id=filters["counterparty_id"])
        costs = [cost for cost in costs if cost.applies_to_exploitation_field(rule.exploitation_field)]

        gross_revenue = money(sales.aggregate(total=Sum("gross_revenue"))["total"])
        deductions = money(sales.aggregate(total=Sum("deductions"))["total"])
        vat_withholding = money(sales.aggregate(total=Sum("vat_withholding"))["total"])
        net_revenue = gross_revenue - deductions - vat_withholding
        recoupable_costs = sum((cost.net_amount for cost in costs), Decimal("0.00")) if rule.include_recoupable_costs else Decimal("0.00")
        recoupment_items = list(rule.recoupment_items.filter(active=True).order_by("priority", "item_type", "name"))
        manual_recoupment_items = sum((item.opening_balance for item in recoupment_items), Decimal("0.00"))
        total_recoupment_pool = rule.recoupment_pool + recoupable_costs + manual_recoupment_items
        recouped_amount = min(max(net_revenue, Decimal("0.00")), total_recoupment_pool)
        unrecouped_balance = max(total_recoupment_pool - recouped_amount, Decimal("0.00"))
        post_recoupment_revenue = max(net_revenue - recouped_amount, Decimal("0.00"))
        fee_base = post_recoupment_revenue if rule.fee_after_recoupment else max(net_revenue, Decimal("0.00"))
        distributor_fee = fee_base * rule.distributor_fee_percent / Decimal("100.00")
        split_base = max(post_recoupment_revenue - distributor_fee, Decimal("0.00"))
        participant_allocations = allocate_participants(rule, split_base)
        participant_share = sum((item["amount"] for item in participant_allocations), Decimal("0.00"))
        distributor_remainder = split_base - participant_share

        row = {
            "rule": rule,
            "recoupment_items": recoupment_items,
            "participant_allocations": participant_allocations,
            "gross_revenue": gross_revenue,
            "deductions": deductions,
            "vat_withholding": vat_withholding,
            "net_revenue": net_revenue,
            "recoupable_costs": recoupable_costs,
            "manual_recoupment_items": manual_recoupment_items,
            "recoupment_pool": total_recoupment_pool,
            "recouped_amount": recouped_amount,
            "unrecouped_balance": unrecouped_balance,
            "distributor_fee": distributor_fee,
            "split_base": split_base,
            "participant_share": participant_share,
            "distributor_remainder": distributor_remainder,
        }
        rows.append(row)
        for key in totals:
            totals[key] += row[key]

    return rows, totals
