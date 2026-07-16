from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import (
    Cost,
    CostCategory,
    Counterparty,
    Currency,
    ExploitationField,
    RoyaltyStatement,
    SalesReport,
    WaterfallAllocationMode,
    WaterfallPlan,
    WaterfallRun,
    WaterfallRunStatus,
    WaterfallStep,
    WaterfallStepType,
    Title,
)
from .waterfall_v2 import calculate_waterfall_run, finalize_waterfall_run


class WaterfallV2Tests(TestCase):
    def setUp(self):
        self.title = Title.objects.create(title_pl="Film testowy", mg_advance=Decimal("50.00"))
        self.distributor = Counterparty.objects.create(name="Dystrybutor")
        self.producer = Counterparty.objects.create(name="Producent")
        self.investor = Counterparty.objects.create(name="Inwestor")
        self.cinema = Counterparty.objects.create(name="Kino")
        self.plan = WaterfallPlan.objects.create(title=self.title, name="Plan PISF", currency=Currency.PLN)

    def add_sales(self, start, end, gross="1000.00", field=ExploitationField.CINEMA, currency=Currency.PLN):
        return SalesReport.objects.create(
            title=self.title,
            counterparty=self.cinema,
            exploitation_field=field,
            period_start=start,
            period_end=end,
            currency=currency,
            gross_revenue=Decimal(gross),
        )

    def test_pisf_style_phases_and_parallel_hard_money(self):
        self.add_sales(date(2026, 1, 1), date(2026, 3, 31))
        WaterfallStep.objects.create(
            plan=self.plan, phase=0, sort_order=10, name="Fee dystrybutora",
            step_type=WaterfallStepType.COMMISSION, beneficiary=self.distributor, percentage=Decimal("10.00"),
        )
        WaterfallStep.objects.create(
            plan=self.plan, phase=0, sort_order=20, name="P&A",
            step_type=WaterfallStepType.RECOUPMENT, beneficiary=self.distributor, target_amount=Decimal("200.00"),
        )
        for beneficiary in (self.producer, self.investor):
            WaterfallStep.objects.create(
                plan=self.plan, phase=1, name=f"Hard money {beneficiary.name}",
                step_type=WaterfallStepType.RECOUPMENT,
                allocation_mode=WaterfallAllocationMode.PARI_PASSU,
                beneficiary=beneficiary,
                target_amount=Decimal("300.00"),
            )

        run = calculate_waterfall_run(WaterfallRun.objects.create(
            plan=self.plan, period_start=date(2026, 1, 1), period_end=date(2026, 3, 31),
        ))

        self.assertEqual(run.net_revenue, Decimal("1000.00"))
        self.assertEqual(list(run.lines.values_list("allocated_amount", flat=True)), [
            Decimal("100.00"), Decimal("200.00"), Decimal("300.00"), Decimal("300.00"),
        ])
        self.assertEqual(run.closing_available, Decimal("100.00"))

    def test_finalized_recoupment_carries_forward(self):
        step = WaterfallStep.objects.create(
            plan=self.plan, phase=0, name="MG", step_type=WaterfallStepType.RECOUPMENT,
            beneficiary=self.producer, target_amount=Decimal("500.00"),
        )
        self.add_sales(date(2026, 1, 1), date(2026, 3, 31), gross="300.00")
        first = calculate_waterfall_run(WaterfallRun.objects.create(
            plan=self.plan, period_start=date(2026, 1, 1), period_end=date(2026, 3, 31),
        ))
        finalize_waterfall_run(first)
        self.add_sales(date(2026, 4, 1), date(2026, 6, 30), gross="300.00")
        second = calculate_waterfall_run(WaterfallRun.objects.create(
            plan=self.plan, period_start=date(2026, 4, 1), period_end=date(2026, 6, 30),
        ))

        line = second.lines.get(step=step)
        self.assertEqual(line.opening_recoupment, Decimal("200.00"))
        self.assertEqual(line.allocated_amount, Decimal("200.00"))
        self.assertEqual(second.closing_available, Decimal("100.00"))

    def test_recoupable_cost_scope_and_statement_freeze(self):
        self.plan.applies_to_all_exploitation_fields = False
        self.plan.exploitation_fields = [ExploitationField.CINEMA]
        self.plan.save()
        self.add_sales(date(2026, 1, 1), date(2026, 3, 31), gross="1000.00")
        self.add_sales(date(2026, 1, 1), date(2026, 3, 31), gross="900.00", field=ExploitationField.LINEAR_TV)
        Cost.objects.create(
            title=self.title, category=CostCategory.PA, cost_date=date(2026, 2, 1),
            currency=Currency.PLN, net_amount=Decimal("100.00"), recoupable=True,
            exploitation_field=ExploitationField.CINEMA,
        )
        statement = RoyaltyStatement.objects.create(
            title=self.title, recipient=self.producer,
            period_start=date(2026, 1, 1), period_end=date(2026, 3, 31),
            currency=Currency.PLN, waterfall_plan=self.plan,
            distributor_fee_percent=Decimal("10.00"), recipient_share_percent=Decimal("50.00"),
        )
        statement.freeze_calculation(lock=True)
        self.assertEqual(statement.gross_revenue, Decimal("1000.00"))
        self.assertEqual(statement.amount_due, Decimal("400.00"))

        self.add_sales(date(2026, 2, 1), date(2026, 2, 28), gross="1000.00")
        statement.refresh_from_db()
        self.assertEqual(statement.gross_revenue, Decimal("1000.00"))
        self.assertEqual(statement.amount_due, Decimal("400.00"))

    def test_currencies_are_kept_separate_on_title(self):
        self.add_sales(date(2026, 1, 1), date(2026, 1, 31), gross="100.00", currency=Currency.PLN)
        self.add_sales(date(2026, 1, 1), date(2026, 1, 31), gross="50.00", currency=Currency.EUR)
        rows = {row["currency"]: row for row in self.title.financial_summary_by_currency}
        self.assertEqual(rows[Currency.PLN]["net"], Decimal("100.00"))
        self.assertEqual(rows[Currency.EUR]["net"], Decimal("50.00"))
        self.assertEqual(set(rows), {Currency.PLN, Currency.EUR})
