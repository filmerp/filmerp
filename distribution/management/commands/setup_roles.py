from django.core.management.base import BaseCommand

from distribution.roles import sync_role_groups


class Command(BaseCommand):
    help = "Tworzy i synchronizuje grupy rol: legal, sales, finance, readonly."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Przywroc dokladny zestaw uprawnien bazowych")

    def handle(self, *args, **options):
        synced = sync_role_groups(reset=options["reset"])
        for role, permission_count in synced:
            self.stdout.write(f"{role}: {permission_count} permissions")
        self.stdout.write(self.style.SUCCESS("Role zsynchronizowane. Przypisz uzytkownikow do grup w panelu admina."))
