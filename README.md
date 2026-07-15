# Film Distribution Manager — MVP

Back-office dla małej/średniej firmy dystrybucyjnej: katalog filmów, kontrahenci, umowy, rights windows / pola eksploatacji, bookingi kinowe, raporty sprzedaży, koszty P&A, royalty statements oraz audyt konfliktów praw.

## Stack

- Django 5.2 LTS
- SQLite lokalnie; można później przenieść na PostgreSQL
- Panel admina Django jako główny interfejs CRUD
- Prosty dashboard pod `/`

## Co jest gotowe

- Tytuły
- Kontrahenci
- Terytoria i wersje językowe
- Umowy nabycia praw
- Umowy sprzedaży/licencji
- Rights windows / pola eksploatacji
- Problemy praw / konflikty
- Booking kinowy
- Raporty sprzedaży i wpływów
- Koszty P&A / delivery / materiały
- Royalty statements / rozliczenia
- Import CSV raportów sprzedaży
- Komenda audytu praw
- Dane demonstracyjne

## Najszybsze uruchomienie lokalne

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations distribution
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver
```

Potem wejdź:

- Dashboard: http://127.0.0.1:8000/
- Panel admina: http://127.0.0.1:8000/admin/

## Uruchomienie przez Docker

```bash
docker compose up --build
```

W osobnym terminalu:

```bash
docker compose exec app python manage.py createsuperuser
docker compose exec app python manage.py seed_demo
```

## Jak działa logika konfliktów praw

Tabela `RightsWindow` jest sercem systemu. Jeden rekord oznacza jedno prawo lub licencję w układzie:

```text
film + pole eksploatacji + terytorium + wersja językowa + data od/do + wyłączność + kontrahent
```

System oznacza konflikt, jeśli:

- jest ten sam film,
- to samo pole eksploatacji,
- daty się nakładają,
- terytoria się nakładają,
- wersje językowe się nakładają,
- przynajmniej jedna z licencji jest wyłączna.

System tworzy też ostrzeżenie, jeśli próbujesz sprzedać / zarezerwować / zaoferować rights window, którego nie pokrywa żadne nabyte prawo.

Audyt możesz uruchomić:

```bash
python manage.py audit_rights
```

Albo w panelu admina: zaznacz rights windows → akcja „Sprawdź konflikty praw dla wybranych rekordów”.

## Import CSV raportów sprzedaży

Wymagane kolumny:

```text
title,counterparty,exploitation_field,territory,period_start,period_end,currency,gross_revenue,deductions,vat_withholding,source_reference
```

Przykład:

```bash
python manage.py import_sales_reports_csv sample_sales_reports.csv --create-missing
```

Obsługiwane aliasy `exploitation_field`:

- kino / cinema
- svod
- tvod
- avod
- est
- tv / linear_tv
- free_tv
- pay_tv

## Rekomendowany workflow operacyjny

1. Wprowadź tytuły.
2. Wprowadź kontrahentów.
3. Wprowadź umowy nabycia praw.
4. Dla każdej umowy stwórz nabyte `Rights windows`.
5. Przy sprzedaży / ofercie / rezerwacji twórz osobne `Rights windows` ze statusem `offer`, `reserved` albo `sold`.
6. Uruchamiaj audyt praw.
7. Importuj raporty sprzedaży z kin/VOD/TV.
8. Dodawaj koszty P&A / delivery.
9. Twórz royalty statements dla okresów miesięcznych/kwartalnych.

## Ważne ograniczenia MVP

- To jest MVP/back-office, a nie gotowy produkt SaaS z rolami, billingiem i pełnym frontendem.
- Waluty nie są automatycznie przeliczane.
- Terytoria nadrzędne są uproszczone. `WORLD` pokrywa wszystko, a identyczne terytoria są traktowane jako overlap.
- Royalty statements liczą podstawowy model: net revenue - koszty recoupable - prowizja dystrybutora, potem udział odbiorcy.
- Nie generuje jeszcze PDF statementów; można dodać WeasyPrint/ReportLab albo eksport do Google Docs.

## Następne rzeczy do dorobienia

- Role użytkowników: prawny / sprzedaż / finanse / read-only.
- Eksport royalty statement do PDF.
- Import XLSX oprócz CSV.
- Integracja z fakturownią / systemem księgowym.
- Integracja z n8n/Make do automatycznych maili i przypomnień.
- Bardziej zaawansowana logika terytoriów: EU, CEE, World excluding Poland.
- API REST dla zewnętrznego frontu albo integracji.

## Added in this MVP pass

### Reporting module

The reporting module is available at:

```text
http://127.0.0.1:8000/reports/
```

It includes date/title/counterparty filters, revenue summaries, cost summaries, overdue payments, open rights issues, and CSV export:

```text
http://127.0.0.1:8000/reports/export/
```

Waterfall / recoupment rules are managed in Django admin under `waterfall / recoupment`.
Each rule is assigned to one title, one exploitation field, and one currency. The report calculates net revenue, recoupment pool, recovered amount, remaining unrecouped balance, distributor fee, split base, partner share, and distributor remainder.

Costs can be assigned to waterfall by exploitation field. In the cost admin form, use:

- `dotyczy wszystkich pol eksploatacji?` when the cost should be included in every field waterfall for the title;
- `Pola eksploatacji dla waterfall` when the cost should be included only in selected fields.

The old single `pole eksploatacji` field is still kept for compatibility with earlier data.

Exports:

```text
http://127.0.0.1:8000/reports/export/
http://127.0.0.1:8000/reports/export/?section=waterfall
http://127.0.0.1:8000/reports/export/?format=xlsx
```

### XLSX sales report import

XLSX files use the same columns as the CSV importer. The first row must contain headers.

```bash
python manage.py import_sales_reports_xlsx sample_sales_reports.xlsx --create-missing
python manage.py import_sales_reports_xlsx reports.xlsx --sheet Sheet1 --create-missing
```

### Royalty statement PDF export

In Django admin, select royalty statements and run the action `Wygeneruj PDF royalty statement`.
The generated PDF is saved on the statement in `statement_file`.

Command-line export is also available:

```bash
python manage.py export_royalty_statement_pdf 1
```

### User roles

Create or refresh the built-in role groups:

```bash
python manage.py setup_roles
```

Roles: `legal`, `sales`, `finance`, `readonly`.
Assign users to these groups in Django admin.

### Currencies and title MG

Core currency choices are:

- `PLN`
- `EURO`
- `US$`

New acquired titles can store `MG / minimum guarantee` and `waluta nabycia / MG` directly on the title form. Acquisition agreements still keep their own MG field for detailed contract-level values.

### Marketplace / Allegro catalog metadata

Titles include marketplace metadata useful for export to sales platforms:

- EAN / GTIN
- category id and category name
- media type, e.g. DVD, Blu-ray, 4K UHD Blu-ray
- condition
- genre, director, cast, screenwriter, music
- audio languages, subtitles, dubbing, lector
- age rating, region code, package type, edition, discs count
- marketplace description and tags

Admin actions on selected titles:

- `Eksport marketplace CSV dla zaznaczonych tytulow`
- `Eksport marketplace XLSX dla zaznaczonych tytulow`

Command-line import/export:

```bash
python manage.py export_marketplace_titles marketplace_titles.xlsx
python manage.py export_marketplace_titles marketplace_titles.csv
python manage.py import_marketplace_titles_xlsx marketplace_titles.xlsx --create-missing
python manage.py import_marketplace_titles_csv marketplace_titles.csv --create-missing
```

### Cinema report PDF/XLSX import with review

Cinema PDF and XLSX reports can be uploaded into a staging area before they create bookings.

In Django admin:

1. Create `import raportu kina` and upload a PDF.
2. Select the import and run `Rozpoznaj raport kina PDF/XLSX`.
3. Review generated `wiersze importu raportow kin`.
4. Correct missing fields if needed.
5. Select reviewed rows and run `Zaakceptuj zweryfikowane wiersze i utworz bookingi`.

Command-line import:

```bash
python manage.py import_cinema_report report.xlsx
python manage.py import_cinema_report_pdf report.pdf
```

The parser tries to infer title, cinema, dates, screenings, admissions, and box office gross. XLSX reports with matrix-style columns such as `Widzów`, `Brutto`, `Netto`, `PISF` are supported. Rows are not imported into `CinemaBooking` until approved.

### Stronger territory logic

Rights overlap/coverage now recognizes special territory codes:

- `EU`
- `CEE`
- `WORLD`
- `WORLD_EX_PL`

`WORLD_EX_PL` means World excluding Poland: it does not overlap `PL`, but covers territories such as `CZ`.

### Email reminders

```bash
python manage.py send_reminders --days 30
python manage.py send_reminders --days 30 --dry-run
```

The command checks rights expiring within the selected window and sales agreements with overdue payments.
By default, Django prints emails to the console; configure SMTP settings for production delivery.
