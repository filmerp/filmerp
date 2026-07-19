from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from distribution.models import (
    AcquisitionAgreement,
    Cost,
    CostCategory,
    Counterparty,
    CounterpartyType,
    Currency,
    ExploitationField,
    LanguageVersion,
    ReportStatus,
    RightsSource,
    RightsStatus,
    RightsWindow,
    SalesAgreement,
    SalesReport,
    Territory,
    Title,
)


class Command(BaseCommand):
    help = "Tworzy przykładowe dane demonstracyjne."

    def handle(self, *args, **options):
        today = timezone.localdate()
        poland, _ = Territory.objects.get_or_create(name="Polska", defaults={"code": "PL"})
        world, _ = Territory.objects.get_or_create(name="World", defaults={"code": "WORLD"})
        Territory.objects.get_or_create(name="European Union", defaults={"code": "EU"})
        Territory.objects.get_or_create(name="Central and Eastern Europe", defaults={"code": "CEE"})
        Territory.objects.get_or_create(name="World excluding Poland", defaults={"code": "WORLD_EX_PL"})
        pl_ver, _ = LanguageVersion.objects.get_or_create(name="polskie napisy", defaults={"code": "PL-SUB"})
        all_versions, _ = LanguageVersion.objects.get_or_create(name="wszystkie wersje", defaults={"code": "ALL"})

        producer, _ = Counterparty.objects.get_or_create(
            name="Example Producer Sp. z o.o.",
            defaults={"counterparty_type": CounterpartyType.PRODUCER, "country": "Polska", "email": "producer@example.com"},
        )
        vod, _ = Counterparty.objects.get_or_create(
            name="Example VOD Platform",
            defaults={"counterparty_type": CounterpartyType.VOD, "country": "Polska", "email": "vod@example.com"},
        )
        cinema, _ = Counterparty.objects.get_or_create(
            name="Example Cinema Chain",
            defaults={"counterparty_type": CounterpartyType.CINEMA_CHAIN, "country": "Polska", "email": "cinema@example.com"},
        )
        supplier, _ = Counterparty.objects.get_or_create(
            name="Example DCP Lab",
            defaults={"counterparty_type": CounterpartyType.SUPPLIER, "country": "Polska", "email": "lab@example.com"},
        )

        title, _ = Title.objects.get_or_create(
            title_pl="Przykładowy Film",
            defaults={
                "original_title": "Sample Film",
                "production_year": today.year - 1,
                "countries": "Polska",
                "status": "distribution",
                "producer": producer,
            },
        )

        acq, _ = AcquisitionAgreement.objects.get_or_create(
            contract_number="ACQ-001",
            title=title,
            licensor=producer,
            defaults={
                "signed_date": today - timedelta(days=120),
                "rights_start": date(today.year, 1, 1),
                "rights_end": date(today.year + 5, 12, 31),
                "currency": Currency.PLN,
                "mg_advance": Decimal("50000.00"),
                "revenue_share_percent": Decimal("50.00"),
                "status": "signed",
            },
        )
        acq.territories.set([poland])

        acquired_cinema, _ = RightsWindow.objects.get_or_create(
            title=title,
            source=RightsSource.ACQUIRED,
            acquisition_agreement=acq,
            exploitation_field=ExploitationField.CINEMA,
            date_from=date(today.year, 1, 1),
            date_to=date(today.year + 5, 12, 31),
            defaults={"counterparty": producer, "exclusive": True, "status": RightsStatus.ACTIVE},
        )
        acquired_cinema.territories.set([poland])
        acquired_cinema.language_versions.set([all_versions])
        acquired_cinema.audit_rights()

        acquired_svod, _ = RightsWindow.objects.get_or_create(
            title=title,
            source=RightsSource.ACQUIRED,
            acquisition_agreement=acq,
            exploitation_field=ExploitationField.SVOD,
            date_from=date(today.year, 1, 1),
            date_to=date(today.year + 5, 12, 31),
            defaults={"counterparty": producer, "exclusive": True, "status": RightsStatus.ACTIVE},
        )
        acquired_svod.territories.set([poland])
        acquired_svod.language_versions.set([all_versions])
        acquired_svod.audit_rights()

        sale, _ = SalesAgreement.objects.get_or_create(
            contract_number="SVOD-001",
            title=title,
            licensee=vod,
            defaults={
                "signed_date": today,
                "status": "signed",
                "currency": Currency.PLN,
                "fixed_fee": Decimal("30000.00"),
                "payment_due_date": today + timedelta(days=30),
            },
        )

        sold_svod, _ = RightsWindow.objects.get_or_create(
            title=title,
            source=RightsSource.SOLD,
            sales_agreement=sale,
            exploitation_field=ExploitationField.SVOD,
            date_from=today + timedelta(days=30),
            date_to=today + timedelta(days=365),
            defaults={"counterparty": vod, "exclusive": True, "status": RightsStatus.SOLD},
        )
        sold_svod.territories.set([poland])
        sold_svod.language_versions.set([pl_ver])
        sold_svod.audit_rights()

        conflicting_offer, _ = RightsWindow.objects.get_or_create(
            title=title,
            source=RightsSource.OFFER,
            exploitation_field=ExploitationField.SVOD,
            date_from=today + timedelta(days=60),
            date_to=today + timedelta(days=400),
            defaults={"counterparty": vod, "exclusive": True, "status": RightsStatus.OFFER},
        )
        conflicting_offer.territories.set([poland])
        conflicting_offer.language_versions.set([pl_ver])
        conflicting_offer.audit_rights()

        SalesReport.objects.get_or_create(
            title=title,
            counterparty=cinema,
            exploitation_field=ExploitationField.CINEMA,
            territory=poland,
            period_start=today.replace(day=1),
            period_end=today,
            defaults={
                "currency": Currency.PLN,
                "gross_revenue": Decimal("125000.00"),
                "deductions": Decimal("62500.00"),
                "vat_withholding": Decimal("0.00"),
                "status": ReportStatus.CHECKED,
                "source_reference": "DEMO-CINEMA-001",
            },
        )

        Cost.objects.get_or_create(
            title=title,
            supplier=supplier,
            category=CostCategory.DCP,
            cost_date=today - timedelta(days=10),
            defaults={
                "currency": Currency.PLN,
                "net_amount": Decimal("4000.00"),
                "vat_amount": Decimal("920.00"),
                "recoupable": True,
                "paid": True,
            },
        )

        self.stdout.write(self.style.SUCCESS("Dane demonstracyjne utworzone. Zaloguj się do /admin/ i uruchom dashboard /."))
