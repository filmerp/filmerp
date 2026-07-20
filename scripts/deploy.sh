#!/usr/bin/env bash
set -euo pipefail

cd /opt/filmerp

compose=(docker compose -f docker-compose.prod.yml --env-file .env.production)

echo "FILMERP: pobieram zmiany z GitHuba..."
git fetch origin main
git pull --ff-only origin main

echo "FILMERP: buduje i uruchamiam aplikacje..."
"${compose[@]}" up -d --build

echo "FILMERP: czekam na zakonczenie migracji..."
ready=0
for _ in $(seq 1 60); do
  if "${compose[@]}" exec -T web python -c \
    "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" != "1" ]]; then
  echo "FILMERP: aplikacja nie uruchomila sie w wymaganym czasie."
  "${compose[@]}" logs --tail=100 web
  exit 1
fi

echo "FILMERP: odswiezam role uzytkownikow..."
"${compose[@]}" exec -T web python manage.py setup_roles

echo "FILMERP: uzupelniam historie dotychczasowych operacji administracyjnych..."
"${compose[@]}" exec -T web python manage.py import_legacy_admin_log

echo "FILMERP: sprawdzam aplikacje..."
"${compose[@]}" exec -T web python manage.py check

echo "FILMERP: status uslug:"
"${compose[@]}" ps

echo "Gotowe: https://app.filmerp.pl/"
