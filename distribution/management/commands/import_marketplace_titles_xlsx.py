from django.core.management.base import BaseCommand

from distribution.marketplace import import_marketplace_rows, load_xlsx_rows


class Command(BaseCommand):
    help = "Importuje metadane marketplace tytulow z XLSX."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path")
        parser.add_argument("--sheet", help="Nazwa arkusza. Domyslnie aktywny arkusz.")
        parser.add_argument("--create-missing", action="store_true", help="Tworz brakujace tytuly.")

    def handle(self, *args, **options):
        rows = load_xlsx_rows(options["xlsx_path"], sheet_name=options["sheet"])
        created, updated = import_marketplace_rows(rows, create_missing=options["create_missing"])
        self.stdout.write(self.style.SUCCESS(f"Import zakonczony. Utworzono: {created}, zaktualizowano: {updated}."))
