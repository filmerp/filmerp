import hashlib
import re
from decimal import Decimal
from pathlib import Path

from django.db import IntegrityError, transaction

from .cinema_imports import DATE_RE, extract_pdf_text, find_known_title, normalize_text, parse_cinema_report_import, parse_date, parse_decimal
from .models import (
    CinemaReportImport,
    Counterparty,
    Currency,
    DocumentInboxItem,
    DocumentStatus,
    DocumentType,
    ImportStatus,
)


ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "xlsx", "jpg", "jpeg", "png", "webp"}


def uploaded_file_hash(upload) -> str:
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def _pdf_text(document: DocumentInboxItem) -> str:
    if not document.is_pdf:
        return ""
    try:
        return extract_pdf_text(document.source_file.path)
    except Exception:
        return ""


def _known_counterparty(text: str):
    normalized = normalize_text(text)
    if not normalized:
        return None
    for counterparty in Counterparty.objects.order_by("-name"):
        candidate = normalize_text(counterparty.name)
        if len(candidate) >= 3 and candidate in normalized:
            return counterparty
    return None


def classify_document(filename: str, text: str = "") -> tuple[str, Decimal]:
    extension = Path(filename).suffix.lower()
    haystack = normalize_text(f"{filename} {text[:12000]}")
    invoice_terms = ("faktura", "invoice", "sprzedawca", "nabywca", "razem netto", "do zaplaty")
    cinema_terms = (
        "cinema report", "raport kina", "raport kinowy", "raport seansow",
        "widzow", "widzowie", "seansow", "box office", "frekwencja", "admissions",
    )

    if re.search(r"\bfv\b", haystack) or any(term in haystack for term in invoice_terms):
        return DocumentType.COST_INVOICE, Decimal("88.00")
    if "statement kina" in haystack or "cinema statement" in haystack:
        return DocumentType.CINEMA_STATEMENT, Decimal("86.00")
    if "statement" in haystack or "rozliczenie kina" in haystack:
        if any(term in haystack for term in cinema_terms) or _known_counterparty(text):
            return DocumentType.CINEMA_STATEMENT, Decimal("82.00")
    if any(term in haystack for term in cinema_terms):
        return DocumentType.CINEMA_REPORT, Decimal("88.00")
    if extension == ".xlsx":
        return DocumentType.CINEMA_REPORT, Decimal("72.00")
    return DocumentType.UNKNOWN, Decimal("20.00")


def _labelled_amount(text: str, labels) -> str:
    for label in labels:
        pattern = rf"(?i){label}[^\d]{{0,30}}(\d[\d \u00a0.]*[,.]\d{{2}})"
        match = re.search(pattern, text)
        if match:
            return str(parse_decimal(match.group(1)))
    return ""


def extract_invoice_data(text: str) -> dict:
    title = find_known_title(text)
    supplier = _known_counterparty(text)
    dates = [parse_date(value) for value in DATE_RE.findall(text)]
    dates = [value for value in dates if value]
    invoice_number = ""
    number_match = re.search(
        r"(?i)(?:faktura(?:\s+vat)?|invoice)\s*(?:nr|no\.?)?\s*[:#]?\s*([A-Z0-9][A-Z0-9_./-]{2,})",
        text,
    )
    if number_match:
        invoice_number = number_match.group(1)

    normalized = normalize_text(text)
    currency = Currency.PLN
    if re.search(r"\bEUR\b|\beuro\b", text, re.IGNORECASE):
        currency = Currency.EUR
    elif re.search(r"\bUSD\b|\bUS\$\b", text, re.IGNORECASE):
        currency = Currency.USD

    return {
        "invoice_number": invoice_number,
        "cost_date": dates[0].isoformat() if dates else "",
        "currency": currency,
        "net_amount": _labelled_amount(text, (r"razem\s+netto", r"wartosc\s+netto", r"netto")),
        "vat_amount": _labelled_amount(text, (r"kwota\s+vat", r"podatek\s+vat", r"vat")),
        "gross_amount": _labelled_amount(text, (r"do\s+zaplaty", r"razem\s+brutto", r"brutto")),
        "title_id": title.pk if title else None,
        "title_name": title.title_pl if title else "",
        "supplier_id": supplier.pk if supplier else None,
        "supplier_name": supplier.name if supplier else "",
        "text_excerpt": text[:2000],
        "has_searchable_text": bool(normalized),
    }


def _process_cinema_document(document: DocumentInboxItem):
    if document.extension not in {"pdf", "xlsx"}:
        document.notes = "Raporty kinowe można automatycznie odczytać z PDF lub XLSX. Uzupełnij typ albo wgraj właściwy plik."
        return
    if document.cinema_import_id:
        return

    report_import = CinemaReportImport.objects.create(
        source_file=document.source_file.name,
        original_filename=document.original_filename,
    )
    document.cinema_import = report_import
    try:
        row_count = parse_cinema_report_import(report_import)
    except Exception:
        report_import.status = ImportStatus.NEEDS_REVIEW
        report_import.parser_notes = "Nie udało się automatycznie odczytać struktury pliku. Sprawdź dokument i jego format."
        report_import.save(update_fields=["status", "parser_notes", "updated_at"])
        document.notes = report_import.parser_notes
        row_count = 0

    title_ids = list(report_import.rows.exclude(title=None).values_list("title_id", flat=True).distinct())
    cinema_ids = list(report_import.rows.exclude(cinema=None).values_list("cinema_id", flat=True).distinct())
    if len(title_ids) == 1:
        document.title_id = title_ids[0]
    if len(cinema_ids) == 1:
        document.counterparty_id = cinema_ids[0]
    document.extracted_data = {
        **(document.extracted_data or {}),
        "row_count": row_count,
        "matched_title_count": len(title_ids),
        "matched_cinema_count": len(cinema_ids),
    }


def analyze_document(document: DocumentInboxItem, forced_type: str = "") -> DocumentInboxItem:
    report_types = {DocumentType.CINEMA_REPORT, DocumentType.CINEMA_STATEMENT}
    if forced_type and document.cinema_import_id and forced_type not in report_types:
        if document.cinema_import.rows.filter(status=ImportStatus.IMPORTED).exists():
            raise ValueError("Dokument ma już zaimportowane bookingi i nie można zmienić jego typu.")
        document.cinema_import.delete()
        document.cinema_import = None
        document.title = None
        document.counterparty = None

    text = _pdf_text(document)
    detected_type, confidence = classify_document(document.original_filename, text)
    document.document_type = forced_type or detected_type
    document.classification_confidence = Decimal("100.00") if forced_type else confidence
    document.status = DocumentStatus.NEEDS_REVIEW
    document.notes = ""

    if document.document_type == DocumentType.COST_INVOICE:
        extracted = extract_invoice_data(text)
        document.extracted_data = extracted
        document.title_id = extracted.get("title_id")
        document.counterparty_id = extracted.get("supplier_id")
        if document.is_image:
            document.notes = "Obraz faktury zapisano. Uzupełnij dane ręcznie; automatyczny OCR obrazów nie jest jeszcze włączony."
    elif document.document_type in {DocumentType.CINEMA_REPORT, DocumentType.CINEMA_STATEMENT}:
        _process_cinema_document(document)
    else:
        document.extracted_data = {"text_excerpt": text[:2000], "has_searchable_text": bool(text.strip())}

    document.save()
    return document


@transaction.atomic
def ingest_document(upload, user=None) -> tuple[DocumentInboxItem, bool]:
    extension = Path(upload.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValueError("Obsługiwane formaty: PDF, XLSX, JPG, PNG i WEBP.")

    file_hash = uploaded_file_hash(upload)
    existing = DocumentInboxItem.objects.filter(file_hash=file_hash).first()
    if existing:
        return existing, False

    try:
        document = DocumentInboxItem.objects.create(
            source_file=upload,
            original_filename=Path(upload.name).name,
            file_hash=file_hash,
            content_type=getattr(upload, "content_type", "") or "",
            file_size=upload.size,
            uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        )
    except IntegrityError:
        return DocumentInboxItem.objects.get(file_hash=file_hash), False
    analyze_document(document)
    return document, True
