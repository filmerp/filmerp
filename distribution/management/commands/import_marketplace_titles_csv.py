from django.core.management.base import BaseCommand

from distribution.marketplace import import_marketplace_rows, load_csv_rows


class Command(BaseCommand):
    help = "Importuje metadane marketplace tytulow z CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--create-missing", action="store_true", help="Tworz brakujace tytuly.")

    def handle(self, *args, **options):
        created, updated = import_marketplace_rows(load_csv_rows(options["csv_path"]), create_missing=options["create_missing"])
        self.stdout.write(self.style.SUCCESS(f"Import zakonczony. Utworzono: {created}, zaktualizowano: {updated}."))
