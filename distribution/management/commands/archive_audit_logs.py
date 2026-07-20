import gzip
import hashlib
import hmac
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from auditlog.models import LogEntry

from distribution.models import AuditEvent, LoginEvent


class Command(BaseCommand):
    help = "Tworzy podpisane, skompresowane archiwa dziennikow FILMERP."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="archive_date", help="Dzien w formacie RRRR-MM-DD")
        parser.add_argument("--force", action="store_true", help="Nadpisz istniejace archiwum")

    @staticmethod
    def _event_dict(event, source):
        if source == "login":
            return {
                "source": source,
                "id": str(event.pk),
                "occurred_at": event.occurred_at.isoformat(),
                "user_id": event.user_id,
                "event_type": event.event_type,
                "result": event.result,
                "reason": event.reason,
                "identifier": event.identifier,
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "session_fingerprint": event.session_fingerprint,
                "request_id": str(event.request_id or ""),
                "metadata": event.metadata,
                "integrity_hash": event.integrity_hash,
            }
        if source == "audit":
            return {
                "source": source,
                "id": str(event.pk),
                "occurred_at": event.occurred_at.isoformat(),
                "actor_id": event.actor_id,
                "action": event.action,
                "event_source": event.source,
                "module": event.module,
                "content_type_id": event.content_type_id,
                "object_pk": event.object_pk,
                "object_repr": event.object_repr,
                "summary": event.summary,
                "changes": event.changes,
                "metadata": event.metadata,
                "request_id": str(event.request_id or ""),
                "ip_address": event.ip_address,
                "retention_class": event.retention_class,
                "integrity_hash": event.integrity_hash,
            }
        return {
            "source": source,
            "id": event.pk,
            "occurred_at": event.timestamp.isoformat(),
            "actor_id": event.actor_id,
            "action": event.action,
            "content_type_id": event.content_type_id,
            "object_pk": event.object_pk,
            "object_repr": event.object_repr,
            "changes": event.changes_dict,
            "ip_address": event.remote_addr,
            "request_id": event.cid,
        }

    def _dates_to_archive(self, requested):
        if requested:
            return [date.fromisoformat(requested)]
        latest = timezone.localdate() - timedelta(days=1)
        dates = set(LoginEvent.objects.filter(occurred_at__date__lte=latest).dates("occurred_at", "day"))
        dates.update(AuditEvent.objects.filter(occurred_at__date__lte=latest).dates("occurred_at", "day"))
        dates.update(LogEntry.objects.filter(timestamp__date__lte=latest).dates("timestamp", "day"))
        return sorted(value.date() if hasattr(value, "date") else value for value in dates)

    def handle(self, *args, **options):
        archive_dir = Path(settings.AUDIT_ARCHIVE_DIR)
        archive_dir.mkdir(parents=True, exist_ok=True)
        mirror_dir = Path(settings.AUDIT_ARCHIVE_MIRROR_DIR) if settings.AUDIT_ARCHIVE_MIRROR_DIR else None
        if mirror_dir:
            mirror_dir.mkdir(parents=True, exist_ok=True)
        signing_key = str(settings.AUDIT_SIGNING_KEY).encode("utf-8")
        created = 0

        for archive_date in self._dates_to_archive(options["archive_date"]):
            stem = f"filmerp-audit-{archive_date.isoformat()}"
            data_path = archive_dir / f"{stem}.ndjson.gz"
            manifest_path = archive_dir / f"{stem}.manifest.json"
            if data_path.exists() and manifest_path.exists() and not options["force"]:
                continue

            rows = []
            rows.extend(self._event_dict(event, "login") for event in LoginEvent.objects.filter(occurred_at__date=archive_date).iterator())
            rows.extend(self._event_dict(event, "audit") for event in AuditEvent.objects.filter(occurred_at__date=archive_date).iterator())
            rows.extend(self._event_dict(event, "automatic") for event in LogEntry.objects.filter(timestamp__date=archive_date).iterator())
            rows.sort(key=lambda item: (item["occurred_at"], item["source"], str(item["id"])))
            raw = b"".join((json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8") for row in rows)
            compressed = gzip.compress(raw, compresslevel=9, mtime=0)
            digest = hashlib.sha256(compressed).hexdigest()
            signature = hmac.new(signing_key, compressed, hashlib.sha256).hexdigest()
            manifest = {
                "format": "FILMERP_AUDIT_ARCHIVE_V1",
                "date": archive_date.isoformat(),
                "created_at": timezone.now().isoformat(),
                "records": len(rows),
                "sha256": digest,
                "hmac_sha256": signature,
                "file": data_path.name,
            }
            data_path.write_bytes(compressed)
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            if mirror_dir:
                shutil.copy2(data_path, mirror_dir / data_path.name)
                shutil.copy2(manifest_path, mirror_dir / manifest_path.name)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Archiwum {archive_date}: {len(rows)} rekordow"))
        self.stdout.write(f"Utworzono archiwa: {created}")

