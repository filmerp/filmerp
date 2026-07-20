from django.contrib.admin.models import LogEntry as AdminLogEntry
from django.core.management.base import BaseCommand

from distribution.models import AuditAction, AuditEvent
from distribution.security import record_audit_event


class Command(BaseCommand):
    help = "Importuje dotychczasowy dziennik panelu Django do historii FILMERP."

    def handle(self, *args, **options):
        created = 0
        action_map = {1: AuditAction.CREATE, 2: AuditAction.UPDATE, 3: AuditAction.DELETE}
        for entry in AdminLogEntry.objects.select_related("user", "content_type").order_by("action_time").iterator():
            legacy_reference = f"django-admin:{entry.pk}"
            if AuditEvent.objects.filter(legacy_reference=legacy_reference).exists():
                continue
            record_audit_event(
                action_map.get(entry.action_flag, AuditAction.SYSTEM),
                entry.change_message or f"Operacja administracyjna na {entry.object_repr}.",
                actor=entry.user,
                module=entry.content_type.model if entry.content_type else "admin",
                source="admin_legacy",
                metadata={"admin_action_time": entry.action_time.isoformat()},
                legacy_reference=legacy_reference,
                occurred_at=entry.action_time,
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Zaimportowano wpisy: {created}"))
