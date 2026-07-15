from django.core.management.base import BaseCommand, CommandError

from distribution.models import RoyaltyStatement
from distribution.pdf import build_royalty_statement_pdf


class Command(BaseCommand):
    help = "Generuje PDF dla wybranego royalty statement i zapisuje go w polu statement_file."

    def add_arguments(self, parser):
        parser.add_argument("statement_id", type=int)

    def handle(self, *args, **options):
        try:
            statement = RoyaltyStatement.objects.get(pk=options["statement_id"])
        except RoyaltyStatement.DoesNotExist as exc:
            raise CommandError("Nie znaleziono royalty statement.") from exc
        pdf_file = build_royalty_statement_pdf(statement)
        statement.statement_file.save(pdf_file.name, pdf_file, save=True)
        self.stdout.write(self.style.SUCCESS(f"PDF zapisany: {statement.statement_file.name}"))
