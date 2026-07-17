from datetime import date
from decimal import Decimal
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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


class SettlementWorkflowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = self.settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)

        self.user = get_user_model().objects.create_user(username="finance", password="test-pass")
        self.client.force_login(self.user)
        self.title = Title.objects.create(title_pl="Miesieczny film")
        self.producer = Counterparty.objects.create(name="Producent statementu")
        self.cinema = Counterparty.objects.create(name="Kino raportujace")
        self.plan = WaterfallPlan.objects.create(
            title=self.title,
            name="Umowne rozliczenie",
            status="active",
            currency=Currency.PLN,
        )
        WaterfallStep.objects.create(
            plan=self.plan,
            phase=1,
            name="Udzial producenta",
            step_type=WaterfallStepType.SPLIT,
            beneficiary=self.producer,
            percentage=Decimal("50.00"),
        )
        SalesReport.objects.create(
            title=self.title,
            counterparty=self.cinema,
            exploitation_field=ExploitationField.CINEMA,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            currency=Currency.PLN,
            gross_revenue=Decimal("1000.00"),
        )

    def workflow_payload(self):
        return {
            "title": str(self.title.pk),
            "plan": str(self.plan.pk),
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "currency": Currency.PLN,
        }

    def test_workbench_simulates_finalizes_and_generates_pdf(self):
        response = self.client.get("/settlements/", self.workflow_payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Miesieczny film")
        self.assertContains(response, "Uruchom symulację")

        response = self.client.post("/settlements/", {**self.workflow_payload(), "action": "simulate"})
        self.assertEqual(response.status_code, 302)
        run = WaterfallRun.objects.get(plan=self.plan)
        self.assertEqual(run.allocated_amount, Decimal("500.00"))

        response = self.client.post("/settlements/", {
            **self.workflow_payload(),
            "action": "finalize_and_generate",
            "run": str(run.pk),
            "run_id": str(run.pk),
            "recipient_ids": [str(self.producer.pk)],
        })
        self.assertEqual(response.status_code, 302)
        run.refresh_from_db()
        statement = RoyaltyStatement.objects.get(waterfall_run=run, recipient=self.producer)
        self.assertEqual(run.status, WaterfallRunStatus.FINALIZED)
        self.assertEqual(statement.amount_due, Decimal("500.00"))
        self.assertTrue(statement.statement_file.name.endswith(".pdf"))
        with statement.statement_file.open("rb") as pdf_file:
            self.assertEqual(pdf_file.read(4), b"%PDF")

        original_snapshot = statement.calculation_snapshot.copy()
        SalesReport.objects.create(
            title=self.title,
            counterparty=self.cinema,
            exploitation_field=ExploitationField.CINEMA,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            currency=Currency.PLN,
            gross_revenue=Decimal("9000.00"),
        )
        response = self.client.post("/settlements/", {
            **self.workflow_payload(),
            "action": "finalize_and_generate",
            "run_id": str(run.pk),
            "recipient_ids": [str(self.producer.pk)],
        })
        self.assertEqual(response.status_code, 302)
        statement.refresh_from_db()
        self.assertEqual(statement.calculation_snapshot, original_snapshot)
        self.assertEqual(statement.gross_revenue, Decimal("1000.00"))

    def test_invoice_upload_creates_cost_for_selected_title(self):
        invoice = SimpleUploadedFile("fv-001.pdf", b"%PDF-1.4 test invoice", content_type="application/pdf")
        response = self.client.post("/settlements/", {
            **self.workflow_payload(),
            "action": "upload_cost_invoice",
            "cost_date": "2026-06-15",
            "currency": Currency.PLN,
            "category": CostCategory.PA,
            "net_amount": "200.00",
            "vat_amount": "46.00",
            "recoupable": "on",
            "applies_to_all_exploitation_fields": "on",
            "invoice_file": invoice,
        })
        self.assertEqual(response.status_code, 302)
        cost = Cost.objects.get(title=self.title)
        self.assertEqual(cost.net_amount, Decimal("200.00"))
        self.assertTrue(cost.recoupable)
        self.assertTrue(cost.invoice_file.name.endswith(".pdf"))
