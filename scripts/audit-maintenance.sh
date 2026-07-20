#!/usr/bin/env sh
set -eu

sleep "${AUDIT_MAINTENANCE_INITIAL_DELAY:-120}"
while true; do
  python manage.py archive_audit_logs
  python manage.py verify_audit_archive
  python manage.py enforce_audit_retention
  sleep "${AUDIT_MAINTENANCE_INTERVAL:-86400}"
done
