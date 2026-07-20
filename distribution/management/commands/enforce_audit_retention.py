from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from auditlog.models import LogEntry

from distribution.models import AuditEvent, AuditRetentionClass, LoginEvent


class Command(BaseCommand):
    help = "Stosuje polityke retencji i pseudonimizacji dziennikow."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        ip_cutoff = now - timedelta(days=settings.AUDIT_LOGIN_IP_RETENTION_DAYS)
        login_cutoff = now - timedelta(days=settings.AUDIT_LOGIN_RETENTION_DAYS)
        ordinary_cutoff = now - timedelta(days=settings.AUDIT_ORDINARY_RETENTION_DAYS)
        legal_cutoff = now - timedelta(days=settings.AUDIT_LEGAL_RETENTION_DAYS)

        ip_events = list(LoginEvent.objects.filter(occurred_at__lt=ip_cutoff, ip_address__isnull=False))
        old_logins = LoginEvent.objects.filter(occurred_at__lt=login_cutoff)
        old_ordinary = AuditEvent.objects.filter(retention_class=AuditRetentionClass.ORDINARY, occurred_at__lt=ordinary_cutoff)
        old_protected = AuditEvent.objects.filter(retention_class__in=[AuditRetentionClass.LEGAL_FINANCIAL, AuditRetentionClass.SECURITY], occurred_at__lt=legal_cutoff)
        old_automatic = LogEntry.objects.filter(timestamp__lt=legal_cutoff)

        self.stdout.write(
            f"Do pseudonimizacji IP: {len(ip_events)}; do usuniecia: logowania={old_logins.count()}, "
            f"zwykle={old_ordinary.count()}, chronione={old_protected.count()}, automatyczne={old_automatic.count()}"
        )
        if options["dry_run"]:
            return

        for event in ip_events:
            event.ip_address = None
            event.integrity_hash = event.calculate_integrity_hash()
            LoginEvent.objects.filter(pk=event.pk).update(ip_address=None, integrity_hash=event.integrity_hash)
        old_logins.delete()
        old_ordinary.delete()
        old_protected.delete()
        old_automatic.delete()
        self.stdout.write(self.style.SUCCESS("Polityka retencji zostala zastosowana."))

