import csv

from django.core.management.base import BaseCommand, CommandError

from distribution.sales_import import EXPECTED_HEADERS, import_sales_report_rows


class Command(BaseCommand):
    help = "Importuje raporty sprzedazy z CSV. Wymagane naglowki: " + ", ".join(EXPECTED_HEADERS)

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--create-missing", action="store_true", help="Tworz brakujace tytuly/kontrahentow/terytoria.")

    def handle(self, *args, **options):
        with open(options["csv_path"], newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing_headers = [header for header in EXPECTED_HEADERS if header not in reader.fieldnames]
            if missing_headers:
                raise CommandError(f"Brakuje kolumn: {', '.join(missing_headers)}")
            created, updated = import_sales_report_rows(enumerate(reader, start=2), create_missing=options["create_missing"])

        self.stdout.write(self.style.SUCCESS(f"Import zakonczony. Utworzono: {created}, zaktualizowano: {updated}."))
