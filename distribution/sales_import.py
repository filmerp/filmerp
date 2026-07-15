from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import CommandError

from distribution.models import Counterparty, Currency, ExploitationField, SalesReport, Territory, Title


EXPECTED_HEADERS = [
    "title",
    "counterparty",
    "exploitation_field",
    "territory",
    "period_start",
    "period_end",
    "currency",
    "gross_revenue",
    "deductions",
    "vat_withholding",
    "source_reference",
]

FIELD_ALIASES = {
    "kino": ExploitationField.CINEMA,
    "cinema": ExploitationField.CINEMA,
    "svod": ExploitationField.SVOD,
    "tvod": ExploitationField.TVOD,
    "avod": ExploitationField.AVOD,
    "est": ExploitationField.EST,
    "tv": ExploitationField.LINEAR_TV,
    "linear_tv": ExploitationField.LINEAR_TV,
    "free_tv": ExploitationField.FREE_TV,
    "pay_tv": ExploitationField.PAY_TV,
}


def parse_date(value):
    if hasattr(value, "date"):
        return value.date()
    value = str(value or "").strip()
    for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Niepoprawna data: {value}")


def parse_decimal(value):
    value = str(value or "0").strip().replace(" ", "").replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Niepoprawna kwota: {value}") from exc


def import_sales_report_rows(rows, create_missing=False):
    created = 0
    updated = 0
    for line_no, row in rows:
        title_name = str(row["title"] or "").strip()
        counterparty_name = str(row["counterparty"] or "").strip()
        territory_name = str(row["territory"] or "").strip()
        field_key = str(row["exploitation_field"] or "").strip().lower()
        exploitation_field = FIELD_ALIASES.get(field_key, field_key)
        if exploitation_field not in ExploitationField.values:
            raise CommandError(f"Linia {line_no}: nieznane pole eksploatacji: {row['exploitation_field']}")

        title_qs = Title.objects.filter(title_pl=title_name)
        if create_missing:
            title, _ = Title.objects.get_or_create(title_pl=title_name)
        elif title_qs.exists():
            title = title_qs.first()
        else:
            raise CommandError(f"Linia {line_no}: brak tytulu: {title_name}")

        if create_missing:
            counterparty, _ = Counterparty.objects.get_or_create(name=counterparty_name)
            territory, _ = Territory.objects.get_or_create(name=territory_name, defaults={"code": territory_name[:20].upper()})
        else:
            try:
                counterparty = Counterparty.objects.get(name=counterparty_name)
                territory = Territory.objects.get(name=territory_name)
            except (Counterparty.DoesNotExist, Territory.DoesNotExist) as exc:
                raise CommandError(f"Linia {line_no}: brak kontrahenta lub terytorium") from exc

        period_start = parse_date(row["period_start"])
        period_end = parse_date(row["period_end"])
        source_reference = str(row["source_reference"] or "").strip()
        if not source_reference:
            source_reference = f"{title_name}-{counterparty_name}-{period_start}-{period_end}-{exploitation_field}"
        defaults = {
            "title": title,
            "counterparty": counterparty,
            "territory": territory,
            "exploitation_field": exploitation_field,
            "period_start": period_start,
            "period_end": period_end,
            "currency": str(row["currency"] or Currency.PLN).strip().upper(),
            "gross_revenue": parse_decimal(row["gross_revenue"]),
            "deductions": parse_decimal(row["deductions"]),
            "vat_withholding": parse_decimal(row["vat_withholding"]),
        }
        _, was_created = SalesReport.objects.update_or_create(source_reference=source_reference, defaults=defaults)
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated
