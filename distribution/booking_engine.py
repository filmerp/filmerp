from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")
PERCENT = Decimal("100.00")


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value))


def _money(value) -> Decimal:
    return _decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BookingCalculation:
    box_office_gross_vat: Decimal
    ticket_vat_rate: Decimal
    ticket_vat_amount: Decimal
    box_office_net_vat: Decimal
    settlement_base: Decimal
    percentage_amount: Decimal
    minimum_amount: Decimal
    fixed_amount: Decimal
    adjustment_amount: Decimal
    rental_amount: Decimal
    method: str
    basis: str

    def as_json(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def calculate_booking_rental(
    *,
    box_office_gross_vat,
    ticket_vat_rate,
    settlement_basis,
    calculation_method,
    share_percent,
    minimum_amount=Decimal("0.00"),
    fixed_amount=Decimal("0.00"),
    screenings=0,
    week_number=1,
    first_applicable_week=1,
    adjustment_amount=Decimal("0.00"),
) -> BookingCalculation:
    """Calculate cinema film rental while keeping every input auditable."""
    gross = max(_money(box_office_gross_vat), Decimal("0.00"))
    vat_rate = min(max(_decimal(ticket_vat_rate), Decimal("0.00")), PERCENT)
    divisor = Decimal("1.00") + (vat_rate / PERCENT)
    net = _money(gross / divisor) if divisor else gross
    vat_amount = _money(gross - net)
    base = net if settlement_basis == "net_vat" else gross

    share = min(max(_decimal(share_percent), Decimal("0.00")), PERCENT)
    percentage_amount = _money(base * share / PERCENT)
    minimum = max(_money(minimum_amount), Decimal("0.00"))
    fixed = max(_money(fixed_amount), Decimal("0.00"))
    adjustment = _money(adjustment_amount)

    if calculation_method == "percentage_minimum":
        calculated = max(percentage_amount, minimum)
    elif calculation_method == "fixed_screening":
        calculated = _money(fixed * max(int(screenings or 0), 0))
    elif calculation_method == "fixed_week":
        calculated = fixed
    elif calculation_method == "fixed_booking":
        calculated = fixed if int(week_number or 1) == int(first_applicable_week or 1) else Decimal("0.00")
    elif calculation_method == "custom":
        calculated = fixed
    else:
        calculated = percentage_amount

    rental = max(_money(calculated + adjustment), Decimal("0.00"))
    return BookingCalculation(
        box_office_gross_vat=gross,
        ticket_vat_rate=vat_rate,
        ticket_vat_amount=vat_amount,
        box_office_net_vat=net,
        settlement_base=base,
        percentage_amount=percentage_amount,
        minimum_amount=minimum,
        fixed_amount=fixed,
        adjustment_amount=adjustment,
        rental_amount=rental,
        method=calculation_method,
        basis=settlement_basis,
    )
