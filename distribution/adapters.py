import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter

from .security import get_client_ip, user_requires_mfa


class FilmerpAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

    def get_login_redirect_url(self, request):
        return reverse("distribution:dashboard")

    def get_logout_redirect_url(self, request):
        return reverse("account_login")

    def get_password_change_redirect_url(self, request):
        return reverse("security:account_detail", args=[request.user.pk])

    def get_client_ip(self, request):
        return get_client_ip(request) or "0.0.0.0"


class FilmerpMFAAdapter(DefaultMFAAdapter):
    @staticmethod
    def _fernet():
        configured = settings.MFA_ENCRYPTION_KEY.strip()
        if configured:
            try:
                key = configured.encode("ascii")
                Fernet(key)
                return Fernet(key)
            except (ValueError, TypeError):
                pass
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, text: str) -> str:
        return "fernet:" + self._fernet().encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted_text: str) -> str:
        if not encrypted_text.startswith("fernet:"):
            return encrypted_text
        try:
            return self._fernet().decrypt(encrypted_text.removeprefix("fernet:").encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Nie mozna odszyfrowac klucza MFA. Sprawdz MFA_ENCRYPTION_KEY.") from exc

    def can_delete_authenticator(self, authenticator) -> bool:
        if authenticator.type == authenticator.Type.TOTP and user_requires_mfa(authenticator.user):
            return False
        return super().can_delete_authenticator(authenticator)

