from django.core.management.base import BaseCommand

from distribution.roles import sync_role_groups


class Command(BaseCommand):
    help = "Tworzy i synchronizuje grupy rol: legal, sales, finance, readonly."

    def handle(self, *args, **options):
        synced = sync_role_groups()
        for role, permission_count in synced:
            self.stdout.write(f"{role}: {permission_count} permissions")
        self.stdout.write(self.style.SUCCESS("Role zsynchronizowane. Przypisz uzytkownikow do grup w panelu admina."))
