import time
import uuid

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from allauth.mfa.models import Authenticator

from distribution.models import LoginEventType, SecurityProfile
from distribution.security import record_login_event, reset_request_context, set_request_context, user_requires_mfa


class SecurityContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_request_id = request.META.get("HTTP_X_REQUEST_ID", "")
        try:
            request.filmerp_request_id = uuid.UUID(raw_request_id)
        except (TypeError, ValueError, AttributeError):
            request.filmerp_request_id = uuid.uuid4()
        token = set_request_context(request)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = str(request.filmerp_request_id)
            return response
        finally:
            reset_request_context(token)


class SessionSecurityMiddleware:
    activity_write_interval = 300

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_security_path(path):
        return (
            path.startswith("/konto/login/")
            or path.startswith("/konto/logout/")
            or path.startswith("/konto/2fa/")
            or path.startswith("/konto/password/")
            or path.startswith("/security/mfa-required/")
            or path.startswith(settings.STATIC_URL if settings.STATIC_URL.startswith("/") else f"/{settings.STATIC_URL}")
            or path.startswith(settings.MEDIA_URL if settings.MEDIA_URL.startswith("/") else f"/{settings.MEDIA_URL}")
        )

    def __call__(self, request):
        if request.user.is_authenticated:
            profile, _ = SecurityProfile.objects.get_or_create(user=request.user)
            now_epoch = int(time.time())
            started_at = request.session.get("filmerp_absolute_session_started_at")
            if not started_at:
                request.session["filmerp_absolute_session_started_at"] = now_epoch
            elif now_epoch - int(started_at) >= settings.SESSION_ABSOLUTE_AGE:
                record_login_event(
                    LoginEventType.SESSION_EXPIRED,
                    request=request,
                    user=request.user,
                    reason="Przekroczono maksymalny czas sesji.",
                )
                logout(request)
                return redirect(f"{reverse('account_login')}?session=expired")

            last_activity_write = request.session.get("filmerp_activity_written_at", 0)
            if now_epoch - int(last_activity_write) >= self.activity_write_interval:
                SecurityProfile.objects.filter(pk=profile.pk).update(last_activity_at=timezone.now())
                request.session["filmerp_activity_written_at"] = now_epoch

            if profile.force_password_change and not self._is_security_path(request.path):
                return redirect("account_change_password")

            if user_requires_mfa(request.user):
                has_totp = Authenticator.objects.filter(
                    user=request.user,
                    type=Authenticator.Type.TOTP,
                ).exists()
                if not has_totp and not self._is_security_path(request.path):
                    return redirect("security:mfa_required")

        return self.get_response(request)

