from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from distribution.models import RightsStatus, RightsWindow, SalesAgreement


class Command(BaseCommand):
    help = "Wysyla email reminders dla wygasajacych praw i przeterminowanych platnosci."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Ile dni naprzod sprawdzac wygasajace prawa.")
        parser.add_argument("--dry-run", action="store_true", help="Pokaz przypomnienia bez wysylania maili.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        expiring_until = today + timedelta(days=options["days"])
        dry_run = options["dry_run"]
        sent = 0

        expiring_rights = RightsWindow.objects.filter(
            date_to__gte=today,
            date_to__lte=expiring_until,
        ).exclude(status__in=[RightsStatus.EXPIRED, RightsStatus.CANCELLED]).select_related("title", "counterparty")
        for rights in expiring_rights:
            recipient = rights.counterparty.email if rights.counterparty else ""
            if not recipient:
                continue
            subject = f"Rights expiring: {rights.title}"
            body = (
                f"Rights window #{rights.pk} expires on {rights.date_to}.\n"
                f"Title: {rights.title}\n"
                f"Field: {rights.get_exploitation_field_display()}\n"
                f"Counterparty: {rights.counterparty}\n"
            )
            self._send_or_print(subject, body, recipient, dry_run)
            sent += 1

        overdue_agreements = SalesAgreement.objects.filter(
            invoice_paid=False,
            payment_due_date__lt=today,
        ).select_related("title", "licensee")
        for agreement in overdue_agreements:
            recipient = agreement.licensee.email
            if not recipient:
                continue
            subject = f"Payment overdue: {agreement.title}"
            body = (
                f"Payment for agreement {agreement.contract_number or agreement.pk} is overdue since {agreement.payment_due_date}.\n"
                f"Title: {agreement.title}\n"
                f"Licensee: {agreement.licensee}\n"
                f"Fixed fee: {agreement.fixed_fee} {agreement.currency}\n"
            )
            self._send_or_print(subject, body, recipient, dry_run)
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Reminder scan finished. Messages {'prepared' if dry_run else 'sent'}: {sent}."))

    def _send_or_print(self, subject, body, recipient, dry_run):
        if dry_run:
            self.stdout.write(f"[dry-run] To: {recipient} | {subject}")
            return
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
