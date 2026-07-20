import hashlib
import hmac
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Weryfikuje sumy kontrolne i podpisy archiwow audytowych."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="Plik manifestu lub katalog; domyslnie AUDIT_ARCHIVE_DIR")

    def handle(self, *args, **options):
        target = Path(options["path"] or settings.AUDIT_ARCHIVE_DIR)
        manifests = [target] if target.is_file() else sorted(target.glob("*.manifest.json"))
        if not manifests:
            self.stdout.write("Brak archiwow do weryfikacji.")
            return
        key = str(settings.AUDIT_SIGNING_KEY).encode("utf-8")
        failures = []
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            data_path = manifest_path.parent / manifest["file"]
            if not data_path.exists():
                failures.append(f"{manifest_path.name}: brak pliku danych")
                continue
            data = data_path.read_bytes()
            digest_ok = hmac.compare_digest(hashlib.sha256(data).hexdigest(), manifest["sha256"])
            signature_ok = hmac.compare_digest(hmac.new(key, data, hashlib.sha256).hexdigest(), manifest["hmac_sha256"])
            if digest_ok and signature_ok:
                self.stdout.write(self.style.SUCCESS(f"OK: {manifest_path.name}"))
            else:
                failures.append(f"{manifest_path.name}: bledna suma lub podpis")
        if failures:
            raise CommandError("; ".join(failures))

