import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from allauth.usersessions.models import UserSession

from .models import AuditAction, AuditEvent, LoginEvent, LoginEventType
from .roles import sync_role_groups
from .security import record_audit_event, record_login_event


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SecurityModuleTests(TestCase):
    def setUp(self):
        sync_role_groups()
        self.admin = User.objects.create_superuser("security-admin", "security@example.com", "test-pass-123")
        self.admin.security_profile.mfa_required = False
        self.admin.security_profile.save(update_fields=["mfa_required", "updated_at"])
        self.client.force_login(self.admin)

    def test_account_creation_sends_invitation_and_records_audit(self):
        finance = Group.objects.get(name="finance")
        response = self.client.post(
            reverse("security:account_create"),
            {
                "username": "finance-user",
                "first_name": "Anna",
                "last_name": "Nowak",
                "email": "anna@example.com",
                "is_active": "on",
                "roles": [finance.pk],
                "mfa_required": "on",
                "send_invitation": "on",
            },
        )
        account = User.objects.get(username="finance-user")
        self.assertRedirects(response, reverse("security:account_detail", args=[account.pk]))
        self.assertFalse(account.has_usable_password())
        self.assertTrue(account.security_profile.mfa_required)
        self.assertEqual(list(account.groups.values_list("name", flat=True)), ["finance"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/konto/password/reset/key/", mail.outbox[0].body)
        self.assertTrue(AuditEvent.objects.filter(action=AuditAction.CREATE, object_pk=str(account.pk)).exists())

    def test_finance_account_must_enroll_mfa(self):
        account = User.objects.create_user("finance-no-mfa", password="test-pass-123")
        account.groups.add(Group.objects.get(name="finance"))
        self.client.force_login(account)
        response = self.client.get(reverse("distribution:dashboard"))
        self.assertRedirects(response, reverse("security:mfa_required"), fetch_redirect_response=False)

    def test_login_success_failure_and_lockout_are_recorded(self):
        account = User.objects.create_user("login-user", password="test-pass-123")
        self.client.logout()
        failed = self.client.post(
            reverse("account_login"),
            {"login": account.username, "password": "bad-password"},
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertEqual(failed.status_code, 200)
        self.assertTrue(LoginEvent.objects.filter(event_type=LoginEventType.LOGIN_FAILURE, ip_address="10.20.30.40").exists())
        success = self.client.post(
            reverse("account_login"),
            {"login": account.username, "password": "test-pass-123"},
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertRedirects(success, reverse("distribution:dashboard"))
        self.assertTrue(LoginEvent.objects.filter(user=account, event_type=LoginEventType.LOGIN_SUCCESS).exists())

    def test_forced_session_end_is_visible_in_history(self):
        account = User.objects.create_user("session-user", email="session@example.com", password="test-pass-123")
        other_client = self.client_class()
        login_response = other_client.post(
            reverse("account_login"),
            {"login": account.username, "password": "test-pass-123"},
            REMOTE_ADDR="10.10.10.10",
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertTrue(UserSession.objects.filter(user=account).exists())

        response = self.client.post(
            reverse("security:account_action", args=[account.pk]),
            {"action": "revoke_sessions"},
        )
        self.assertRedirects(response, reverse("security:account_detail", args=[account.pk]))
        self.assertFalse(UserSession.objects.filter(user=account).exists())
        self.assertTrue(LoginEvent.objects.filter(user=account, event_type=LoginEventType.LOGOUT_FORCED).exists())
        self.assertFalse(other_client.get(reverse("distribution:dashboard")).wsgi_request.user.is_authenticated)

    def test_role_matrix_and_security_exports_are_available(self):
        role = Group.objects.get(name="legal")
        response = self.client.get(reverse("security:role_detail", args=[role.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "view_business_audit")

        record_audit_event(AuditAction.UPDATE, "Zmiana testowa", actor=self.admin, module="titles")
        response = self.client.get(reverse("security:audit_history"), {"format": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response = self.client.get(reverse("security:login_history"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith("\ufeff".encode("utf-8")))

    def test_readonly_user_cannot_open_security_module(self):
        account = User.objects.create_user("readonly-security", password="test-pass-123")
        account.groups.add(Group.objects.get(name="readonly"))
        self.client.force_login(account)
        self.assertEqual(self.client.get(reverse("security:account_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("security:login_history")).status_code, 403)

    def test_signed_event_detects_changes_and_cannot_be_saved_twice(self):
        event = record_login_event(LoginEventType.LOGIN_SUCCESS, user=self.admin)
        self.assertTrue(event.verify_integrity())
        event.reason = "proba manipulacji"
        self.assertFalse(event.verify_integrity())
        with self.assertRaises(ValidationError):
            event.save()

    def test_absolute_session_limit_logs_expiry(self):
        session = self.client.session
        session["filmerp_absolute_session_started_at"] = int((timezone.now() - timedelta(hours=13)).timestamp())
        session.save()
        response = self.client.get(reverse("distribution:dashboard"))
        self.assertRedirects(response, f"{reverse('account_login')}?session=expired", fetch_redirect_response=False)
        self.assertTrue(LoginEvent.objects.filter(user=self.admin, event_type=LoginEventType.SESSION_EXPIRED).exists())


class AuditArchiveTests(TestCase):
    def test_archive_is_created_and_verified(self):
        user = User.objects.create_user("archive-user")
        record_audit_event(AuditAction.UPDATE, "Archiwizowana zmiana", actor=user, module="titles")
        record_login_event(LoginEventType.LOGIN_SUCCESS, user=user)
        with tempfile.TemporaryDirectory() as directory:
            with override_settings(AUDIT_ARCHIVE_DIR=Path(directory), AUDIT_ARCHIVE_MIRROR_DIR=""):
                call_command("archive_audit_logs", "--date", timezone.localdate().isoformat())
                manifests = list(Path(directory).glob("*.manifest.json"))
                self.assertEqual(len(manifests), 1)
                call_command("verify_audit_archive", str(manifests[0]))
