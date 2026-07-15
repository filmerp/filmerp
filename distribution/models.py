from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .territories import scope_covers, scopes_overlap


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Currency(models.TextChoices):
    PLN = "PLN", "PLN"
    EUR = "EUR", "EURO"
    USD = "USD", "US$"


class ReportingCycle(models.TextChoices):
    NONE = "none", "brak"
    MONTHLY = "monthly", "miesięczny"
    QUARTERLY = "quarterly", "kwartalny"
    SEMIANNUAL = "semiannual", "półroczny"
    ANNUAL = "annual", "roczny"
    EVENT = "event", "po evencie"


class ExploitationField(models.TextChoices):
    CINEMA = "cinema", "Kino"
    FESTIVALS = "festivals", "Festiwale"
    NON_THEATRICAL = "non_theatrical", "Non-theatrical / edukacja"
    LINEAR_TV = "linear_tv", "TV linearna"
    PAY_TV = "pay_tv", "Pay TV"
    FREE_TV = "free_tv", "Free TV"
    SVOD = "svod", "SVOD"
    TVOD = "tvod", "TVOD"
    EST = "est", "EST / DTO"
    AVOD = "avod", "AVOD"
    FAST = "fast", "FAST"
    AIRLINES = "airlines", "Linie lotnicze"
    HOTELS = "hotels", "Hotele / hospitality"
    CLIPS = "clips", "Clips / fragmenty"
    PROMO_INTERNET = "promo_internet", "Internet promocyjny"
    HOME_VIDEO = "home_video", "Home video / DVD / Blu-ray"
    OTHER = "other", "Inne"


class TitleStatus(models.TextChoices):
    DEVELOPMENT = "development", "w przygotowaniu"
    ACQUIRED = "acquired", "nabyty"
    DISTRIBUTION = "distribution", "w dystrybucji"
    CATALOG = "catalog", "katalog"
    ARCHIVED = "archived", "archiwalny"


class MarketplaceMediaType(models.TextChoices):
    DVD = "dvd", "DVD"
    BLURAY = "blu_ray", "Blu-ray"
    UHD_BLURAY = "uhd_blu_ray", "4K UHD Blu-ray"
    DVD_BLURAY = "dvd_blu_ray", "DVD + Blu-ray"
    DIGITAL = "digital", "Digital"
    VHS = "vhs", "VHS"
    OTHER = "other", "Inny"


class MarketplaceCondition(models.TextChoices):
    NEW = "new", "Nowy"
    USED = "used", "Uzywany"
    REFURBISHED = "refurbished", "Odnowiony"


class MarketplaceAgeRating(models.TextChoices):
    ALL = "all", "Bez ograniczen"
    AGE_7 = "7", "7+"
    AGE_12 = "12", "12+"
    AGE_15 = "15", "15+"
    AGE_16 = "16", "16+"
    AGE_18 = "18", "18+"


class CounterpartyType(models.TextChoices):
    PRODUCER = "producer", "producent"
    SALES_AGENT = "sales_agent", "sales agent"
    CINEMA = "cinema", "kino"
    CINEMA_CHAIN = "cinema_chain", "sieć kin"
    VOD = "vod", "VOD / OTT"
    BROADCASTER = "broadcaster", "TV / broadcaster"
    FESTIVAL = "festival", "festiwal"
    EDUCATION = "education", "edukacja / non-theatrical"
    SUPPLIER = "supplier", "dostawca"
    INVESTOR = "investor", "inwestor / koproducent"
    OTHER = "other", "inne"


class AgreementStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    NEGOTIATION = "negotiation", "negocjacje"
    SIGNED = "signed", "podpisana"
    EXPIRED = "expired", "wygasła"
    CANCELLED = "cancelled", "anulowana"


class RightsSource(models.TextChoices):
    ACQUIRED = "acquired", "nabyte"
    SOLD = "sold", "sprzedane/licencjonowane"
    RESERVED = "reserved", "rezerwacja"
    OFFER = "offer", "oferta"


class RightsStatus(models.TextChoices):
    AVAILABLE = "available", "available"
    ACTIVE = "active", "aktywne"
    RESERVED = "reserved", "reserved"
    SOLD = "sold", "sold"
    OFFER = "offer", "offer"
    EXPIRED = "expired", "expired"
    CONFLICT = "conflict", "conflict"
    CANCELLED = "cancelled", "cancelled"


class ReportStatus(models.TextChoices):
    IMPORTED = "imported", "zaimportowany"
    CHECKED = "checked", "sprawdzony"
    INVOICED = "invoiced", "zafakturowany"
    SETTLED = "settled", "rozliczony"
    REJECTED = "rejected", "odrzucony"


class ImportStatus(models.TextChoices):
    UPLOADED = "uploaded", "wgrany"
    PARSED = "parsed", "rozpoznany"
    NEEDS_REVIEW = "needs_review", "do weryfikacji"
    APPROVED = "approved", "zaakceptowany"
    REJECTED = "rejected", "odrzucony"
    IMPORTED = "imported", "zaimportowany"


class CostCategory(models.TextChoices):
    PA = "pa", "P&A"
    DIGITAL_MARKETING = "digital_marketing", "digital marketing"
    PR = "pr", "PR"
    KEY_ART = "key_art", "plakat / key art"
    TRAILER = "trailer", "trailer"
    DCP = "dcp", "DCP"
    KDM = "kdm", "KDM"
    SUBTITLES = "subtitles", "napisy"
    DUBBING = "dubbing", "dubbing / lektor"
    QC = "qc", "QC"
    DELIVERY = "delivery", "delivery"
    FESTIVALS = "festivals", "festiwale"
    PROMO_MATERIALS = "promo_materials", "materiały promocyjne"
    SALES_COMMISSION = "sales_commission", "prowizje sprzedażowe"
    LEGAL = "legal", "koszty prawne"
    OTHER = "other", "inne"


class RecoupmentItemType(models.TextChoices):
    MG = "mg", "MG / advance"
    PA = "pa", "P&A"
    DELIVERY = "delivery", "Delivery / materials"
    LEGAL = "legal", "Legal"
    COSTS = "costs", "Costs from ledger"
    OTHER = "other", "Other"


class ParticipationType(models.TextChoices):
    LICENSOR = "licensor", "Licensor"
    PRODUCER = "producer", "Producer"
    INVESTOR = "investor", "Investor"
    TALENT = "talent", "Talent"
    SALES_AGENT = "sales_agent", "Sales agent"
    OTHER = "other", "Other"


class DeliveryAssetType(models.TextChoices):
    DCP = "dcp", "DCP"
    KDM = "kdm", "KDM"
    TRAILER = "trailer", "Trailer"
    POSTER = "poster", "Plakat / key art"
    STILLS = "stills", "Fotosy"
    SUBTITLES = "subtitles", "Napisy"
    DUBBING = "dubbing", "Dubbing"
    VOICEOVER = "voiceover", "Lektor"
    AUDIO = "audio", "Audio"
    MASTER = "master", "Master / mezzanine"
    QC_REPORT = "qc_report", "Raport QC"
    CERTIFICATE = "certificate", "Certyfikat / klasyfikacja"
    PRESS_KIT = "press_kit", "Press kit"
    PLATFORM_PACKAGE = "platform_package", "Pakiet platformy"
    OTHER = "other", "Inne"


class DeliveryStatus(models.TextChoices):
    MISSING = "missing", "brak"
    ORDERED = "ordered", "zamówione"
    IN_PROGRESS = "in_progress", "w przygotowaniu"
    READY = "ready", "gotowe"
    SENT = "sent", "wysłane"
    ACCEPTED = "accepted", "zaakceptowane"
    REJECTED = "rejected", "odrzucone / do poprawy"


class StatementStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    SENT = "sent", "wysłany"
    APPROVED = "approved", "zaakceptowany"
    PAID = "paid", "opłacony"
    DISPUTED = "disputed", "sporny"


class IssueSeverity(models.TextChoices):
    INFO = "info", "info"
    WARNING = "warning", "warning"
    CONFLICT = "conflict", "conflict"


class IssueType(models.TextChoices):
    EXCLUSIVE_OVERLAP = "exclusive_overlap", "nakładanie wyłączności"
    MISSING_ACQUISITION = "missing_acquisition", "brak pokrycia w nabytych prawach"
    INVALID_DATES = "invalid_dates", "błędne daty"
    EXPIRED = "expired", "wygasłe prawo"


class Territory(TimestampedModel):
    name = models.CharField("nazwa", max_length=120, unique=True)
    code = models.CharField("kod", max_length=20, blank=True, help_text="Np. PL, EU, WORLD")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children", verbose_name="terytorium nadrzędne"
    )
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "terytorium"
        verbose_name_plural = "terytoria"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name


class LanguageVersion(TimestampedModel):
    name = models.CharField("nazwa", max_length=120, unique=True)
    code = models.CharField("kod", max_length=20, blank=True, help_text="Np. PL, EN-SUB, PL-DUB")
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "wersja językowa"
        verbose_name_plural = "wersje językowe"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name


class Counterparty(TimestampedModel):
    name = models.CharField("nazwa", max_length=255, unique=True)
    counterparty_type = models.CharField("typ", max_length=40, choices=CounterpartyType.choices, default=CounterpartyType.OTHER)
    country = models.CharField("kraj", max_length=120, blank=True)
    vat_id = models.CharField("NIP / VAT ID", max_length=80, blank=True)
    contact_person = models.CharField("osoba kontaktowa", max_length=255, blank=True)
    email = models.EmailField("email", blank=True)
    phone = models.CharField("telefon", max_length=80, blank=True)
    payment_terms_days = models.PositiveIntegerField("termin płatności dni", default=30)
    reporting_cycle = models.CharField("cykl raportowania", max_length=30, choices=ReportingCycle.choices, default=ReportingCycle.NONE)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "kontrahent"
        verbose_name_plural = "kontrahenci"

    def __str__(self) -> str:
        return self.name


class Title(TimestampedModel):
    title_pl = models.CharField("tytuł PL", max_length=255)
    original_title = models.CharField("tytuł oryginalny", max_length=255, blank=True)
    production_year = models.PositiveIntegerField("rok produkcji", null=True, blank=True)
    countries = models.CharField("kraje produkcji", max_length=255, blank=True)
    runtime_minutes = models.PositiveIntegerField("czas trwania min", null=True, blank=True)
    status = models.CharField("status", max_length=40, choices=TitleStatus.choices, default=TitleStatus.ACQUIRED)
    polish_premiere_date = models.DateField("data premiery PL", null=True, blank=True)
    acquisition_currency = models.CharField("waluta nabycia / MG", max_length=3, choices=Currency.choices, default=Currency.PLN)
    mg_advance = models.DecimalField("MG / minimum guarantee", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    imdb_url = models.URLField("IMDb / link", blank=True)
    producer = models.ForeignKey(
        Counterparty, null=True, blank=True, on_delete=models.SET_NULL, related_name="produced_titles", verbose_name="producent/licencjodawca"
    )
    marketplace_category_id = models.CharField("ID kategorii marketplace", max_length=80, blank=True)
    marketplace_category_name = models.CharField("kategoria marketplace", max_length=255, blank=True, default="Filmy")
    ean = models.CharField("EAN / GTIN", max_length=32, blank=True)
    media_type = models.CharField("rodzaj nosnika", max_length=40, choices=MarketplaceMediaType.choices, blank=True)
    marketplace_condition = models.CharField("stan produktu", max_length=40, choices=MarketplaceCondition.choices, default=MarketplaceCondition.NEW)
    release_edition = models.CharField("wydanie", max_length=120, blank=True, help_text="Np. standard, steelbook, kolekcjonerskie.")
    package_type = models.CharField("opakowanie", max_length=120, blank=True, help_text="Np. plastikowe, steelbook, digipack.")
    discs_count = models.PositiveIntegerField("liczba nosnikow", null=True, blank=True)
    region_code = models.CharField("kod regionu", max_length=40, blank=True, help_text="Np. 2, B, region free.")
    genre = models.CharField("gatunek", max_length=255, blank=True)
    director = models.CharField("rezyser", max_length=255, blank=True)
    cast = models.TextField("obsada", blank=True)
    screenwriter = models.CharField("scenariusz", max_length=255, blank=True)
    music_by = models.CharField("muzyka", max_length=255, blank=True)
    audio_languages = models.CharField("jezyki audio", max_length=255, blank=True)
    subtitle_languages = models.CharField("napisy", max_length=255, blank=True)
    dubbing_languages = models.CharField("dubbing", max_length=255, blank=True)
    lector_languages = models.CharField("lektor", max_length=255, blank=True)
    age_rating = models.CharField("ograniczenie wiekowe", max_length=20, choices=MarketplaceAgeRating.choices, blank=True)
    color_mode = models.CharField("kolor", max_length=80, blank=True, help_text="Np. kolor, czarno-bialy.")
    aspect_ratio = models.CharField("format obrazu", max_length=80, blank=True, help_text="Np. 16:9, 2.39:1.")
    marketplace_description = models.TextField("opis marketplace", blank=True)
    marketplace_tags = models.CharField("tagi marketplace", max_length=255, blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["title_pl"]
        verbose_name = "tytuł"
        verbose_name_plural = "tytuły"

    def __str__(self) -> str:
        return self.title_pl

    @property
    def gross_revenue_total(self) -> Decimal:
        return sum((r.gross_revenue for r in self.sales_reports.all()), Decimal("0.00"))

    @property
    def net_revenue_total(self) -> Decimal:
        return sum((r.net_revenue for r in self.sales_reports.all()), Decimal("0.00"))

    @property
    def recoupable_costs_total(self) -> Decimal:
        return sum((c.net_amount for c in self.costs.filter(recoupable=True)), Decimal("0.00"))

    @property
    def result_before_royalties(self) -> Decimal:
        return self.net_revenue_total - self.recoupable_costs_total


class AcquisitionAgreement(TimestampedModel):
    contract_number = models.CharField("nr umowy", max_length=120, blank=True)
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="acquisition_agreements", verbose_name="tytuł")
    licensor = models.ForeignKey(Counterparty, on_delete=models.PROTECT, related_name="acquisition_agreements", verbose_name="licencjodawca")
    signed_date = models.DateField("data podpisania", null=True, blank=True)
    rights_start = models.DateField("start praw", null=True, blank=True)
    rights_end = models.DateField("koniec praw", null=True, blank=True)
    territories = models.ManyToManyField(Territory, blank=True, related_name="acquisition_agreements", verbose_name="terytoria")
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    mg_advance = models.DecimalField("MG / advance", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    revenue_share_percent = models.DecimalField("revenue share licencjodawcy %", max_digits=5, decimal_places=2, default=Decimal("0.00"))
    pa_recoupable = models.BooleanField("P&A recoupable?", default=True)
    status = models.CharField("status", max_length=30, choices=AgreementStatus.choices, default=AgreementStatus.DRAFT)
    agreement_file = models.FileField("plik umowy", upload_to="agreements/acquisition/", blank=True)
    notes = models.TextField("uwagi prawne", blank=True)

    class Meta:
        ordering = ["-signed_date", "title__title_pl"]
        verbose_name = "umowa nabycia praw"
        verbose_name_plural = "umowy nabycia praw"

    def __str__(self) -> str:
        return self.contract_number or f"Nabycie: {self.title} / {self.licensor}"


class SalesAgreement(TimestampedModel):
    contract_number = models.CharField("nr licencji", max_length=120, blank=True)
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="sales_agreements", verbose_name="tytuł")
    licensee = models.ForeignKey(Counterparty, on_delete=models.PROTECT, related_name="sales_agreements", verbose_name="licencjobiorca")
    signed_date = models.DateField("data podpisania", null=True, blank=True)
    status = models.CharField("status", max_length=30, choices=AgreementStatus.choices, default=AgreementStatus.NEGOTIATION)
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    fixed_fee = models.DecimalField("license fee / fixed", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    revenue_share_percent = models.DecimalField("revenue share %", max_digits=5, decimal_places=2, default=Decimal("0.00"))
    reporting_cycle = models.CharField("raportowanie", max_length=30, choices=ReportingCycle.choices, default=ReportingCycle.QUARTERLY)
    payment_due_date = models.DateField("termin płatności", null=True, blank=True)
    invoice_issued = models.BooleanField("faktura wystawiona?", default=False)
    invoice_paid = models.BooleanField("faktura zapłacona?", default=False)
    agreement_file = models.FileField("plik umowy", upload_to="agreements/sales/", blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["-signed_date", "title__title_pl"]
        verbose_name = "umowa sprzedaży/licencji"
        verbose_name_plural = "umowy sprzedaży/licencji"

    def __str__(self) -> str:
        return self.contract_number or f"Sprzedaż: {self.title} / {self.licensee}"

    @property
    def is_payment_overdue(self) -> bool:
        return bool(self.payment_due_date and not self.invoice_paid and self.payment_due_date < timezone.localdate())


def _ids(values: Iterable[models.Model]) -> set[int]:
    return {v.pk for v in values if v.pk is not None}


class RightsWindow(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="rights_windows", verbose_name="tytuł")
    source = models.CharField("źródło", max_length=30, choices=RightsSource.choices, default=RightsSource.ACQUIRED)
    acquisition_agreement = models.ForeignKey(
        AcquisitionAgreement, null=True, blank=True, on_delete=models.SET_NULL, related_name="rights_windows", verbose_name="umowa nabycia"
    )
    sales_agreement = models.ForeignKey(
        SalesAgreement, null=True, blank=True, on_delete=models.SET_NULL, related_name="rights_windows", verbose_name="umowa sprzedaży"
    )
    counterparty = models.ForeignKey(
        Counterparty, null=True, blank=True, on_delete=models.SET_NULL, related_name="rights_windows", verbose_name="kontrahent"
    )
    exploitation_field = models.CharField("pole eksploatacji", max_length=40, choices=ExploitationField.choices)
    territories = models.ManyToManyField(Territory, blank=True, related_name="rights_windows", verbose_name="terytoria")
    language_versions = models.ManyToManyField(LanguageVersion, blank=True, related_name="rights_windows", verbose_name="wersje językowe")
    date_from = models.DateField("data od")
    date_to = models.DateField("data do")
    exclusive = models.BooleanField("wyłączność", default=False)
    holdback = models.BooleanField("holdback", default=False)
    status = models.CharField("status", max_length=30, choices=RightsStatus.choices, default=RightsStatus.ACTIVE)
    conflict_notes = models.TextField("notatki konfliktów", blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["title__title_pl", "exploitation_field", "date_from"]
        indexes = [
            models.Index(fields=["title", "exploitation_field", "date_from", "date_to"]),
            models.Index(fields=["source", "status"]),
        ]
        verbose_name = "rights window / pole eksploatacji"
        verbose_name_plural = "rights windows / pola eksploatacji"

    def __str__(self) -> str:
        return f"{self.title} | {self.get_exploitation_field_display()} | {self.date_from}–{self.date_to}"

    def clean(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError({"date_to": "Data końca nie może być wcześniejsza niż data startu."})

    @property
    def is_expired(self) -> bool:
        return self.date_to < timezone.localdate()

    def _territory_codes(self) -> set[str]:
        return {t.code.upper() for t in self.territories.all() if t.code}

    def _territory_ids(self) -> set[int]:
        return _ids(self.territories.all())

    def _language_ids(self) -> set[int]:
        return _ids(self.language_versions.all())

    def overlaps_dates(self, other: "RightsWindow") -> bool:
        return self.date_from <= other.date_to and other.date_from <= self.date_to

    def overlaps_territories(self, other: "RightsWindow") -> bool:
        self_codes = self._territory_codes()
        other_codes = other._territory_codes()
        self_ids = self._territory_ids()
        other_ids = other._territory_ids()
        # Puste terytorium traktujemy ostrożnościowo jako „wszystkie/nieokreślone”.
        if not self_ids or not other_ids:
            return True
        if self_codes or other_codes:
            return scopes_overlap(self_codes, other_codes)
        return bool(self_ids & other_ids)

    def covers_territories(self, other: "RightsWindow") -> bool:
        """Czy self pokrywa terytoria other. WORLD pokrywa wszystko; puste = nieokreślone/wszystko."""
        self_codes = self._territory_codes()
        self_ids = self._territory_ids()
        other_ids = other._territory_ids()
        if not self_ids:
            return True
        if not other_ids:
            return False
        other_codes = other._territory_codes()
        if self_codes or other_codes:
            return scope_covers(self_codes, other_codes)
        return other_ids.issubset(self_ids)

    def overlaps_languages(self, other: "RightsWindow") -> bool:
        self_ids = self._language_ids()
        other_ids = other._language_ids()
        # Puste wersje językowe traktujemy jako wszystkie/nieokreślone.
        if not self_ids or not other_ids:
            return True
        return bool(self_ids & other_ids)

    def covers_languages(self, other: "RightsWindow") -> bool:
        self_ids = self._language_ids()
        other_ids = other._language_ids()
        if not self_ids:
            return True
        if not other_ids:
            return False
        return other_ids.issubset(self_ids)

    def find_exclusive_overlaps(self):
        if not self.pk:
            return RightsWindow.objects.none()
        active_statuses = [RightsStatus.ACTIVE, RightsStatus.RESERVED, RightsStatus.SOLD, RightsStatus.OFFER, RightsStatus.AVAILABLE]
        candidates = RightsWindow.objects.filter(
            title=self.title,
            exploitation_field=self.exploitation_field,
            date_from__lte=self.date_to,
            date_to__gte=self.date_from,
            status__in=active_statuses,
        ).exclude(pk=self.pk)
        if not self.exclusive:
            candidates = candidates.filter(exclusive=True)
        overlaps = []
        for other in candidates:
            if self.overlaps_territories(other) and self.overlaps_languages(other) and (self.exclusive or other.exclusive):
                overlaps.append(other.pk)
        return RightsWindow.objects.filter(pk__in=overlaps)

    def find_covering_acquisitions(self):
        if not self.pk or self.source == RightsSource.ACQUIRED:
            return RightsWindow.objects.none()
        candidates = RightsWindow.objects.filter(
            title=self.title,
            source=RightsSource.ACQUIRED,
            exploitation_field=self.exploitation_field,
            date_from__lte=self.date_from,
            date_to__gte=self.date_to,
        ).exclude(status__in=[RightsStatus.EXPIRED, RightsStatus.CANCELLED])
        covered = []
        for candidate in candidates:
            if candidate.covers_territories(self) and candidate.covers_languages(self):
                covered.append(candidate.pk)
        return RightsWindow.objects.filter(pk__in=covered)

    def audit_rights(self) -> list["RightsIssue"]:
        """Odświeża konflikty/warnings dla tego rekordu i zwraca aktywne problemy."""
        if not self.pk:
            return []
        RightsIssue.objects.filter(rights_window=self, resolved=False).delete()
        issues = []
        if self.date_from > self.date_to:
            issues.append(RightsIssue.objects.create(
                rights_window=self,
                severity=IssueSeverity.CONFLICT,
                issue_type=IssueType.INVALID_DATES,
                message="Data końca jest wcześniejsza niż data startu.",
            ))
        if self.is_expired and self.status != RightsStatus.EXPIRED:
            issues.append(RightsIssue.objects.create(
                rights_window=self,
                severity=IssueSeverity.INFO,
                issue_type=IssueType.EXPIRED,
                message="Rights window jest po dacie końca. Rozważ zmianę statusu na expired.",
            ))
        for other in self.find_exclusive_overlaps():
            issues.append(RightsIssue.objects.create(
                rights_window=self,
                conflicting_window=other,
                severity=IssueSeverity.CONFLICT,
                issue_type=IssueType.EXCLUSIVE_OVERLAP,
                message=f"Nakładanie wyłączności z rekordem #{other.pk}: {other}",
            ))
        if self.source in [RightsSource.SOLD, RightsSource.RESERVED, RightsSource.OFFER]:
            if not self.find_covering_acquisitions().exists():
                issues.append(RightsIssue.objects.create(
                    rights_window=self,
                    severity=IssueSeverity.WARNING,
                    issue_type=IssueType.MISSING_ACQUISITION,
                    message="Nie znaleziono nabytego rights window, który w pełni pokrywa tę sprzedaż/rezerwację/ofertę.",
                ))
        if any(issue.severity == IssueSeverity.CONFLICT for issue in issues):
            self.status = RightsStatus.CONFLICT
            self.conflict_notes = "\n".join(issue.message for issue in issues)
            RightsWindow.objects.filter(pk=self.pk).update(status=self.status, conflict_notes=self.conflict_notes)
        else:
            self.conflict_notes = "\n".join(issue.message for issue in issues)
            RightsWindow.objects.filter(pk=self.pk).update(conflict_notes=self.conflict_notes)
        return issues


class RightsIssue(TimestampedModel):
    rights_window = models.ForeignKey(RightsWindow, on_delete=models.CASCADE, related_name="issues", verbose_name="rights window")
    conflicting_window = models.ForeignKey(
        RightsWindow, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflicting_issues", verbose_name="rekord konfliktowy"
    )
    severity = models.CharField("poziom", max_length=20, choices=IssueSeverity.choices, default=IssueSeverity.WARNING)
    issue_type = models.CharField("typ", max_length=40, choices=IssueType.choices)
    message = models.TextField("komunikat")
    resolved = models.BooleanField("rozwiązany?", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "problem praw / konflikt"
        verbose_name_plural = "problemy praw / konflikty"

    def __str__(self) -> str:
        return f"{self.get_severity_display()}: {self.get_issue_type_display()}"


class CinemaBooking(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="cinema_bookings", verbose_name="tytuł")
    cinema = models.ForeignKey(Counterparty, on_delete=models.PROTECT, related_name="cinema_bookings", verbose_name="kino/sieć")
    city = models.CharField("miasto", max_length=120, blank=True)
    date_from = models.DateField("data od")
    date_to = models.DateField("data do")
    exploitation_week = models.PositiveIntegerField("tydzień eksploatacji", null=True, blank=True)
    screenings = models.PositiveIntegerField("liczba seansów", default=0)
    admissions = models.PositiveIntegerField("widzowie", default=0)
    box_office_gross = models.DecimalField("box office brutto", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    distributor_share_percent = models.DecimalField("udział dystrybutora %", max_digits=5, decimal_places=2, default=Decimal("50.00"))
    invoice_issued = models.BooleanField("faktura?", default=False)
    source_file = models.FileField("raport źródłowy", upload_to="cinema_reports/", blank=True)
    source_reference = models.CharField("Import ID / ref", max_length=255, blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["-date_from", "title__title_pl"]
        verbose_name = "booking kinowy / seans"
        verbose_name_plural = "bookingi kinowe / seanse"

    def __str__(self) -> str:
        return f"{self.title} / {self.cinema} / {self.date_from}"

    def save(self, *args, **kwargs):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            self.date_from, self.date_to = self.date_to, self.date_from
        super().save(*args, **kwargs)

    @property
    def distributor_share_amount(self) -> Decimal:
        return (self.box_office_gross or Decimal("0.00")) * (self.distributor_share_percent or Decimal("0.00")) / Decimal("100.00")

    def sync_sales_report(self):
        if not self.pk:
            return None
        source_reference = self.source_reference or f"cinema-booking-{self.pk}"
        distributor_share = self.distributor_share_amount
        gross_revenue = self.box_office_gross or Decimal("0.00")
        deductions = max(gross_revenue - distributor_share, Decimal("0.00"))
        report, _ = SalesReport.objects.update_or_create(
            source_reference=source_reference,
            defaults={
                "title": self.title,
                "counterparty": self.cinema,
                "sales_agreement": None,
                "exploitation_field": ExploitationField.CINEMA,
                "territory": None,
                "period_start": self.date_from,
                "period_end": self.date_to,
                "currency": Currency.PLN,
                "gross_revenue": gross_revenue,
                "deductions": deductions,
                "vat_withholding": Decimal("0.00"),
                "status": ReportStatus.IMPORTED,
                "source_file": self.source_file,
                "notes": f"Automatycznie utworzone z bookingu kinowego #{self.pk}. {self.notes}".strip(),
            },
        )
        return report


class CinemaReportImport(TimestampedModel):
    source_file = models.FileField("plik raportu kina", upload_to="cinema_report_imports/")
    original_filename = models.CharField("oryginalna nazwa pliku", max_length=255, blank=True)
    status = models.CharField("status", max_length=30, choices=ImportStatus.choices, default=ImportStatus.UPLOADED)
    parsed_at = models.DateTimeField("data rozpoznania", null=True, blank=True)
    imported_at = models.DateTimeField("data importu", null=True, blank=True)
    parser_notes = models.TextField("uwagi parsera", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "import raportu kina"
        verbose_name_plural = "importy raportow kin"

    def __str__(self) -> str:
        return self.original_filename or self.source_file.name


class CinemaReportImportRow(TimestampedModel):
    report_import = models.ForeignKey(CinemaReportImport, on_delete=models.CASCADE, related_name="rows", verbose_name="import")
    status = models.CharField("status", max_length=30, choices=ImportStatus.choices, default=ImportStatus.NEEDS_REVIEW)
    title = models.ForeignKey(Title, null=True, blank=True, on_delete=models.SET_NULL, related_name="cinema_import_rows", verbose_name="tytul")
    cinema = models.ForeignKey(Counterparty, null=True, blank=True, on_delete=models.SET_NULL, related_name="cinema_import_rows", verbose_name="kino/siec")
    city = models.CharField("miasto", max_length=120, blank=True)
    date_from = models.DateField("data od", null=True, blank=True)
    date_to = models.DateField("data do", null=True, blank=True)
    screenings = models.PositiveIntegerField("liczba seansow", default=0)
    admissions = models.PositiveIntegerField("widzowie", default=0)
    box_office_gross = models.DecimalField("box office brutto", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    distributor_share_percent = models.DecimalField("udzial dystrybutora %", max_digits=5, decimal_places=2, default=Decimal("50.00"))
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    confidence = models.DecimalField("pewnosc rozpoznania %", max_digits=5, decimal_places=2, default=Decimal("0.00"))
    source_line = models.TextField("linia zrodla", blank=True)
    raw_payload = models.JSONField("surowe dane", default=dict, blank=True)
    booking = models.ForeignKey(CinemaBooking, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_rows", verbose_name="utworzony booking")
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["report_import", "date_from", "title__title_pl"]
        verbose_name = "wiersz importu raportu kina"
        verbose_name_plural = "wiersze importu raportow kin"

    def __str__(self) -> str:
        return f"{self.title or 'brak tytulu'} / {self.cinema or 'brak kina'} / {self.date_from or 'brak daty'}"

    def can_approve(self) -> bool:
        return bool(self.title and self.cinema and self.date_from and self.date_to)

    def approve(self) -> CinemaBooking:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            self.date_from, self.date_to = self.date_to, self.date_from
            self.save(update_fields=["date_from", "date_to", "updated_at"])
        if self.booking_id:
            self.status = ImportStatus.IMPORTED
            self.save(update_fields=["status", "updated_at"])
            self.booking.sync_sales_report()
            return self.booking
        if not self.can_approve():
            raise ValidationError("Wiersz wymaga tytulu, kina oraz dat od/do przed akceptacja.")
        source_reference = f"cinema-import-row-{self.pk}"
        existing = CinemaBooking.objects.filter(source_reference=source_reference).first()
        if existing:
            self.booking = existing
            self.status = ImportStatus.IMPORTED
            self.save(update_fields=["booking", "status", "updated_at"])
            existing.sync_sales_report()
            return existing
        booking = CinemaBooking.objects.create(
            title=self.title,
            cinema=self.cinema,
            city=self.city,
            date_from=self.date_from,
            date_to=self.date_to,
            screenings=self.screenings,
            admissions=self.admissions,
            box_office_gross=self.box_office_gross,
            distributor_share_percent=self.distributor_share_percent,
            source_reference=source_reference,
            notes=f"Utworzono z importu raportu kina #{self.report_import_id}. {self.notes}".strip(),
        )
        self.booking = booking
        self.status = ImportStatus.IMPORTED
        self.save(update_fields=["booking", "status", "updated_at"])
        booking.sync_sales_report()
        return booking


class SalesReport(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="sales_reports", verbose_name="tytuł")
    counterparty = models.ForeignKey(Counterparty, on_delete=models.PROTECT, related_name="sales_reports", verbose_name="kontrahent")
    sales_agreement = models.ForeignKey(SalesAgreement, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_reports", verbose_name="umowa/licencja")
    exploitation_field = models.CharField("pole eksploatacji", max_length=40, choices=ExploitationField.choices)
    territory = models.ForeignKey(Territory, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_reports", verbose_name="terytorium")
    period_start = models.DateField("okres od")
    period_end = models.DateField("okres do")
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    gross_revenue = models.DecimalField("przychód brutto", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    deductions = models.DecimalField("potrącenia / fees", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vat_withholding = models.DecimalField("VAT / withholding", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField("status", max_length=30, choices=ReportStatus.choices, default=ReportStatus.IMPORTED)
    source_reference = models.CharField("Import ID / ref", max_length=255, blank=True)
    source_file = models.FileField("plik źródłowy", upload_to="sales_reports/", blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["-period_end", "title__title_pl"]
        indexes = [
            models.Index(fields=["title", "exploitation_field", "period_start", "period_end"]),
            models.Index(fields=["source_reference"]),
        ]
        verbose_name = "raport sprzedaży i wpływów"
        verbose_name_plural = "raporty sprzedaży i wpływów"

    def __str__(self) -> str:
        return f"{self.title} / {self.get_exploitation_field_display()} / {self.period_start}–{self.period_end}"

    @property
    def net_revenue(self) -> Decimal:
        return (self.gross_revenue or Decimal("0.00")) - (self.deductions or Decimal("0.00")) - (self.vat_withholding or Decimal("0.00"))


class Cost(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="costs", verbose_name="tytuł")
    category = models.CharField("kategoria", max_length=40, choices=CostCategory.choices, default=CostCategory.OTHER)
    supplier = models.ForeignKey(Counterparty, null=True, blank=True, on_delete=models.SET_NULL, related_name="costs", verbose_name="dostawca")
    cost_date = models.DateField("data kosztu")
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    net_amount = models.DecimalField("kwota netto", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField("VAT", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    recoupable = models.BooleanField("recoupable?", default=True)
    exploitation_field = models.CharField("pole eksploatacji", max_length=40, choices=ExploitationField.choices, blank=True)
    applies_to_all_exploitation_fields = models.BooleanField("dotyczy wszystkich pol eksploatacji?", default=False)
    exploitation_fields = models.TextField(
        "pola eksploatacji dla waterfall",
        blank=True,
        help_text="Lista pol oddzielona przecinkami. Uzywane do przypisania kosztu do wielu pol w waterfall.",
    )
    invoice_file = models.FileField("faktura", upload_to="costs/", blank=True)
    paid = models.BooleanField("zapłacone?", default=False)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["-cost_date", "title__title_pl"]
        verbose_name = "koszt P&A / delivery / materiały"
        verbose_name_plural = "koszty P&A / delivery / materiały"

    def __str__(self) -> str:
        return f"{self.title} / {self.get_category_display()} / {self.net_amount} {self.currency}"

    @property
    def gross_amount(self) -> Decimal:
        return (self.net_amount or Decimal("0.00")) + (self.vat_amount or Decimal("0.00"))

    def waterfall_exploitation_fields(self) -> set[str]:
        values = {value.strip() for value in self.exploitation_fields.split(",") if value.strip()}
        if self.exploitation_field:
            values.add(self.exploitation_field)
        return values

    def applies_to_exploitation_field(self, exploitation_field: str) -> bool:
        if self.applies_to_all_exploitation_fields:
            return True
        return exploitation_field in self.waterfall_exploitation_fields()


class TitleMaterial(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="materials", verbose_name="tytuł")
    asset_type = models.CharField("typ materiału", max_length=40, choices=DeliveryAssetType.choices)
    exploitation_field = models.CharField("pole eksploatacji", max_length=40, choices=ExploitationField.choices, blank=True)
    language_version = models.ForeignKey(
        LanguageVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="materials",
        verbose_name="wersja językowa",
    )
    supplier = models.ForeignKey(
        Counterparty,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivered_materials",
        verbose_name="dostawca",
    )
    status = models.CharField("status", max_length=30, choices=DeliveryStatus.choices, default=DeliveryStatus.MISSING)
    required_for_release = models.BooleanField("wymagane do startu eksploatacji?", default=True)
    due_date = models.DateField("termin", null=True, blank=True)
    delivered_at = models.DateField("data dostarczenia", null=True, blank=True)
    file = models.FileField("plik", upload_to="title_materials/", blank=True)
    external_reference = models.CharField("link / ID zewnętrzne", max_length=255, blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["title__title_pl", "asset_type", "exploitation_field", "due_date"]
        indexes = [
            models.Index(fields=["title", "status"]),
            models.Index(fields=["asset_type", "status"]),
            models.Index(fields=["due_date"]),
        ]
        verbose_name = "materiał / delivery"
        verbose_name_plural = "materiały / delivery"

    def __str__(self) -> str:
        field = self.get_exploitation_field_display() if self.exploitation_field else "ogólne"
        return f"{self.title} / {self.get_asset_type_display()} / {field}"

    @property
    def is_overdue(self) -> bool:
        open_statuses = {DeliveryStatus.MISSING, DeliveryStatus.ORDERED, DeliveryStatus.IN_PROGRESS, DeliveryStatus.REJECTED}
        return bool(self.due_date and self.status in open_statuses and self.due_date < timezone.localdate())


class WaterfallRecoupmentRule(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="waterfall_rules", verbose_name="tytul")
    exploitation_field = models.CharField("pole eksploatacji", max_length=40, choices=ExploitationField.choices)
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    recoupment_pool = models.DecimalField(
        "pula do recoupmentu",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Np. MG, P&A, delivery albo inna kwota odzyskiwana przed splitem.",
    )
    distributor_fee_percent = models.DecimalField("prowizja dystrybutora %", max_digits=5, decimal_places=2, default=Decimal("25.00"))
    participant_share_percent = models.DecimalField("udzial partnera %", max_digits=5, decimal_places=2, default=Decimal("50.00"))
    include_recoupable_costs = models.BooleanField("dolicz koszty recoupable z kosztow?", default=True)
    fee_after_recoupment = models.BooleanField("licz fee po recoupment?", default=True)
    active = models.BooleanField("aktywny?", default=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["title__title_pl", "exploitation_field"]
        unique_together = ("title", "exploitation_field", "currency")
        verbose_name = "waterfall / recoupment"
        verbose_name_plural = "waterfall / recoupment"

    def __str__(self) -> str:
        return f"{self.title} / {self.get_exploitation_field_display()} / {self.currency}"


class WaterfallRecoupmentItem(TimestampedModel):
    rule = models.ForeignKey(
        WaterfallRecoupmentRule,
        on_delete=models.CASCADE,
        related_name="recoupment_items",
        verbose_name="waterfall / recoupment",
    )
    item_type = models.CharField("typ pozycji", max_length=30, choices=RecoupmentItemType.choices, default=RecoupmentItemType.OTHER)
    name = models.CharField("nazwa", max_length=160)
    priority = models.PositiveIntegerField("priorytet", default=100, help_text="Nizszy numer oznacza wczesniejsze odzyskiwanie.")
    amount = models.DecimalField("kwota do odzyskania", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    recouped_to_date = models.DecimalField("odzyskane przed tym okresem", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    active = models.BooleanField("aktywny?", default=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["rule", "priority", "item_type", "name"]
        indexes = [
            models.Index(fields=["rule", "active", "priority"]),
            models.Index(fields=["item_type"]),
        ]
        verbose_name = "pozycja recoupmentu"
        verbose_name_plural = "pozycje recoupmentu"

    def __str__(self) -> str:
        return f"{self.rule} / {self.name}"

    @property
    def opening_balance(self) -> Decimal:
        return max((self.amount or Decimal("0.00")) - (self.recouped_to_date or Decimal("0.00")), Decimal("0.00"))


class WaterfallParticipant(TimestampedModel):
    rule = models.ForeignKey(
        WaterfallRecoupmentRule,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="waterfall / recoupment",
    )
    recipient = models.ForeignKey(
        Counterparty,
        on_delete=models.PROTECT,
        related_name="waterfall_participations",
        verbose_name="uczestnik / odbiorca",
    )
    participation_type = models.CharField("typ uczestnika", max_length=30, choices=ParticipationType.choices, default=ParticipationType.LICENSOR)
    share_percent = models.DecimalField("udzial %", max_digits=6, decimal_places=2, default=Decimal("0.00"))
    payout_cap = models.DecimalField(
        "limit wyplaty / cap",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="0 oznacza brak limitu.",
    )
    paid_to_date = models.DecimalField("wyplacone przed tym okresem", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    sort_order = models.PositiveIntegerField("kolejnosc", default=100)
    active = models.BooleanField("aktywny?", default=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["rule", "sort_order", "recipient__name"]
        indexes = [
            models.Index(fields=["rule", "active", "sort_order"]),
            models.Index(fields=["recipient"]),
        ]
        verbose_name = "uczestnik waterfall"
        verbose_name_plural = "uczestnicy waterfall"

    def __str__(self) -> str:
        return f"{self.rule} / {self.recipient} / {self.share_percent}%"

    @property
    def remaining_cap(self) -> Decimal | None:
        if not self.payout_cap:
            return None
        return max((self.payout_cap or Decimal("0.00")) - (self.paid_to_date or Decimal("0.00")), Decimal("0.00"))


class RoyaltyStatement(TimestampedModel):
    title = models.ForeignKey(Title, on_delete=models.CASCADE, related_name="royalty_statements", verbose_name="tytuł")
    recipient = models.ForeignKey(Counterparty, on_delete=models.PROTECT, related_name="royalty_statements", verbose_name="odbiorca statementu")
    period_start = models.DateField("okres od")
    period_end = models.DateField("okres do")
    currency = models.CharField("waluta", max_length=3, choices=Currency.choices, default=Currency.PLN)
    distributor_fee_percent = models.DecimalField("prowizja dystrybutora %", max_digits=5, decimal_places=2, default=Decimal("25.00"))
    recipient_share_percent = models.DecimalField("udział odbiorcy %", max_digits=5, decimal_places=2, default=Decimal("50.00"))
    status = models.CharField("status", max_length=30, choices=StatementStatus.choices, default=StatementStatus.DRAFT)
    statement_file = models.FileField("PDF statement", upload_to="royalty_statements/", blank=True)
    sent_at = models.DateField("data wysyłki", null=True, blank=True)
    paid_at = models.DateField("data płatności", null=True, blank=True)
    notes = models.TextField("uwagi", blank=True)

    class Meta:
        ordering = ["-period_end", "title__title_pl"]
        verbose_name = "royalty statement / rozliczenie"
        verbose_name_plural = "royalty statements / rozliczenia"

    def __str__(self) -> str:
        return f"{self.title} / {self.recipient} / {self.period_start}–{self.period_end}"

    def sales_queryset(self):
        return SalesReport.objects.filter(
            title=self.title,
            currency=self.currency,
            period_start__gte=self.period_start,
            period_start__lte=self.period_end,
        ).exclude(status=ReportStatus.REJECTED)

    def recoupable_costs_queryset(self):
        return Cost.objects.filter(
            title=self.title,
            currency=self.currency,
            recoupable=True,
            cost_date__gte=self.period_start,
            cost_date__lte=self.period_end,
        )

    @property
    def gross_revenue(self) -> Decimal:
        return sum((r.gross_revenue for r in self.sales_queryset()), Decimal("0.00"))

    @property
    def net_revenue(self) -> Decimal:
        return sum((r.net_revenue for r in self.sales_queryset()), Decimal("0.00"))

    @property
    def recoupable_costs(self) -> Decimal:
        return sum((c.net_amount for c in self.recoupable_costs_queryset()), Decimal("0.00"))

    @property
    def distributor_fee_amount(self) -> Decimal:
        return self.net_revenue * (self.distributor_fee_percent or Decimal("0.00")) / Decimal("100.00")

    @property
    def net_receipts(self) -> Decimal:
        return self.net_revenue - self.recoupable_costs - self.distributor_fee_amount

    @property
    def amount_due(self) -> Decimal:
        amount = self.net_receipts * (self.recipient_share_percent or Decimal("0.00")) / Decimal("100.00")
        return max(amount, Decimal("0.00"))
