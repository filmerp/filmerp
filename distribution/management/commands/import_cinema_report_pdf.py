from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from distribution.cinema_imports import parse_cinema_report_pdf
from distribution.models import CinemaReportImport


class Command(BaseCommand):
    help = "Wgrywa PDF raportu kina i tworzy wiersze robocze do weryfikacji."

    def add_arguments(self, parser):
        parser.add_argument("pdf_path")

    def handle(self, *args, **options):
        path = Path(options["pdf_path"])
        with path.open("rb") as handle:
            report_import = CinemaReportImport.objects.create(original_filename=path.name)
            report_import.source_file.save(path.name, File(handle), save=True)
        rows_count = parse_cinema_report_pdf(report_import)
        self.stdout.write(self.style.SUCCESS(f"Utworzono import #{report_import.pk}. Wiersze do weryfikacji: {rows_count}."))
