from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .models import LanguageVersion, RightsSource, RightsStatus, RightsWindow, Territory, Title
from .territories import scope_covers, scopes_overlap


ACTIVE_RIGHTS_STATUSES = [
    RightsStatus.AVAILABLE,
    RightsStatus.ACTIVE,
    RightsStatus.RESERVED,
    RightsStatus.SOLD,
    RightsStatus.OFFER,
    RightsStatus.CONFLICT,
]

BLOCKING_SOURCES = [RightsSource.SOLD, RightsSource.RESERVED, RightsSource.OFFER]


@dataclass
class AvailsResult:
    status: str
    headline: str
    detail: str
    acquisition_windows: list[RightsWindow]
    blocking_windows: list[RightsWindow]
    holdbacks: list[RightsWindow]
    territory_codes: set[str]
    language_ids: set[int]

    @property
    def is_available(self) -> bool:
        return self.status == "available"


def _territory_codes(territories: Iterable[Territory]) -> set[str]:
    return {territory.code.upper() for territory in territories if territory.code}


def _language_ids(languages: Iterable[LanguageVersion]) -> set[int]:
    return {language.pk for language in languages if language.pk}


def _window_territory_codes(window: RightsWindow) -> set[str]:
    return {territory.code.upper() for territory in window.territories.all() if territory.code}


def _window_language_ids(window: RightsWindow) -> set[int]:
    return {language.pk for language in window.language_versions.all() if language.pk}


def _covers_languages(window_language_ids: set[int], requested_language_ids: set[int]) -> bool:
    if not window_language_ids:
        return True
    if not requested_language_ids:
        return False
    return requested_language_ids.issubset(window_language_ids)


def _overlaps_languages(window_language_ids: set[int], requested_language_ids: set[int]) -> bool:
    if not window_language_ids or not requested_language_ids:
        return True
    return bool(window_language_ids & requested_language_ids)


def check_availability(
    *,
    title: Title,
    exploitation_field: str,
    territories: Iterable[Territory],
    languages: Iterable[LanguageVersion],
    date_from: date,
    date_to: date,
) -> AvailsResult:
    requested_territories = list(territories)
    requested_languages = list(languages)
    requested_codes = _territory_codes(requested_territories)
    requested_language_ids = _language_ids(requested_languages)

    acquisition_candidates = (
        RightsWindow.objects.filter(
            title=title,
            source=RightsSource.ACQUIRED,
            exploitation_field=exploitation_field,
            date_from__lte=date_from,
            date_to__gte=date_to,
        )
        .exclude(status__in=[RightsStatus.EXPIRED, RightsStatus.CANCELLED])
        .prefetch_related("territories", "language_versions")
        .select_related("counterparty", "acquisition_agreement", "sales_agreement")
    )

    acquisition_windows = []
    for window in acquisition_candidates:
        window_codes = _window_territory_codes(window)
        window_languages = _window_language_ids(window)
        territory_ok = not requested_codes or not window_codes or scope_covers(window_codes, requested_codes)
        language_ok = _covers_languages(window_languages, requested_language_ids)
        if territory_ok and language_ok:
            acquisition_windows.append(window)

    blocking_candidates = (
        RightsWindow.objects.filter(
            title=title,
            exploitation_field=exploitation_field,
            date_from__lte=date_to,
            date_to__gte=date_from,
            status__in=ACTIVE_RIGHTS_STATUSES,
        )
        .filter(source__in=BLOCKING_SOURCES)
        .prefetch_related("territories", "language_versions")
        .select_related("counterparty", "acquisition_agreement", "sales_agreement")
    )

    blocking_windows = []
    holdbacks = []
    for window in blocking_candidates:
        window_codes = _window_territory_codes(window)
        window_languages = _window_language_ids(window)
        territory_overlap = not requested_codes or not window_codes or scopes_overlap(window_codes, requested_codes)
        language_overlap = _overlaps_languages(window_languages, requested_language_ids)
        if territory_overlap and language_overlap:
            if window.holdback:
                holdbacks.append(window)
            else:
                blocking_windows.append(window)

    if not acquisition_windows:
        return AvailsResult(
            status="no_rights",
            headline="Brak pokrycia w nabytych prawach",
            detail="System nie znalazł nabytego rights window, które pokrywa wybrane daty, terytoria i wersje językowe.",
            acquisition_windows=[],
            blocking_windows=blocking_windows,
            holdbacks=holdbacks,
            territory_codes=requested_codes,
            language_ids=requested_language_ids,
        )

    if blocking_windows or holdbacks:
        return AvailsResult(
            status="blocked",
            headline="Nie oferować bez wyjaśnienia",
            detail="Istnieją sprzedaże, rezerwacje, oferty albo holdbacki nakładające się na zapytanie.",
            acquisition_windows=acquisition_windows,
            blocking_windows=blocking_windows,
            holdbacks=holdbacks,
            territory_codes=requested_codes,
            language_ids=requested_language_ids,
        )

    return AvailsResult(
        status="available",
        headline="Dostępne do oferty",
        detail="Nabyte prawa pokrywają zapytanie i nie znaleziono aktywnych blokad.",
        acquisition_windows=acquisition_windows,
        blocking_windows=[],
        holdbacks=[],
        territory_codes=requested_codes,
        language_ids=requested_language_ids,
    )
