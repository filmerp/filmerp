from django.core.management.base import BaseCommand

from distribution.models import RightsWindow


class Command(BaseCommand):
    help = "Przelicza konflikty i ostrzeżenia dla wszystkich rights windows."

    def handle(self, *args, **options):
        total = 0
        count = 0
        for rights in RightsWindow.objects.all().iterator():
            issues = rights.audit_rights()
            total += len(issues)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Sprawdzono {count} rekordów rights windows. Nowe problemy/ostrzeżenia: {total}."))
