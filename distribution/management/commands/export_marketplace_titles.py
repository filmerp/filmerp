from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from distribution.marketplace import export_marketplace_csv, export_marketplace_xlsx
from distribution.models import Title


class Command(BaseCommand):
    help = "Eksportuje katalog tytulow pod marketplace do CSV albo XLSX."

    def add_arguments(self, parser):
        parser.add_argument("output_path")
        parser.add_argument("--format", choices=["csv", "xlsx"], help="Format eksportu. Domyslnie z rozszerzenia pliku.")

    def handle(self, *args, **options):
        output_path = Path(options["output_path"])
        export_format = options["format"] or output_path.suffix.lower().lstrip(".")
        queryset = Title.objects.all()
        if export_format == "csv":
            output_path.write_text(export_marketplace_csv(queryset), encoding="utf-8")
        elif export_format == "xlsx":
            output_path.write_bytes(export_marketplace_xlsx(queryset))
        else:
            raise CommandError("Podaj format csv albo xlsx.")
        self.stdout.write(self.style.SUCCESS(f"Eksport zapisany: {output_path}"))
