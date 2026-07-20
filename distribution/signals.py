from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from allauth.account import signals as account_signals
from allauth.mfa import signals as mfa_signals
from allauth.usersessions.signals import session_client_changed
from axes.signals import user_locked_out

from .models import AuditAction, LoginEventType, SecurityProfile
from .security import record_audit_event, record_login_event


User = get_user_model()


@receiver(post_save, sender=User)
def ensure_security_profile(sender, instance, **kwargs):
    SecurityProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def log_successful_login(sender, request, user, **kwargs):
    request.session["filmerp_absolute_session_started_at"] = int(timezone.now().timestamp())
    record_login_event(LoginEventType.LOGIN_SUCCESS, request=request, user=user)


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    identifier = credentials.get("username") or credentials.get("email") or ""
    record_login_event(
        LoginEventType.LOGIN_FAILURE,
        request=request,
        result="failure",
        reason="Nieprawidlowe dane logowania.",
        identifier=identifier,
    )


@receiver(user_locked_out)
def log_account_lock(sender, request, username, ip_address, **kwargs):
    record_login_event(
        LoginEventType.LOCKED,
        request=request,
        result="blocked",
        reason="Przekroczono limit nieudanych prob logowania.",
        identifier=username,
        metadata={"lock_ip": ip_address},
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if not user or not getattr(user, "pk", None):
        return
    reason = getattr(request, "filmerp_logout_reason", "") or request.POST.get("logout_reason", "")
    if reason == "idle":
        event_type = LoginEventType.LOGOUT_IDLE
    elif reason == "forced":
        event_type = LoginEventType.LOGOUT_FORCED
    else:
        event_type = LoginEventType.LOGOUT_MANUAL
    record_login_event(event_type, request=request, user=user, reason=reason)


@receiver(session_client_changed)
def log_session_client_change(sender, request, from_session, to_session, **kwargs):
    record_login_event(
        LoginEventType.SESSION_CHANGED,
        request=request,
        user=to_session.user,
        result="warning",
        reason="W trakcie sesji zmienil sie adres IP lub identyfikator urzadzenia.",
        metadata={
            "from_ip": from_session.ip,
            "to_ip": to_session.ip,
            "from_user_agent": from_session.user_agent,
            "to_user_agent": to_session.user_agent,
        },
    )
    record_audit_event(
        AuditAction.SECURITY,
        f"Wykryto zmiane urzadzenia aktywnej sesji konta {to_session.user}.",
        request=request,
        module="sessions",
        instance=to_session.user,
    )


@receiver(account_signals.password_changed)
def log_password_change(sender, request, user, **kwargs):
    SecurityProfile.objects.filter(user=user).update(force_password_change=False)
    record_login_event(LoginEventType.PASSWORD_CHANGED, request=request, user=user)
    record_audit_event(
        AuditAction.SECURITY,
        "Uzytkownik zmienil haslo.",
        request=request,
        actor=user,
        module="security",
        instance=user,
    )


@receiver(account_signals.password_reset)
def log_password_reset(sender, request, user, **kwargs):
    SecurityProfile.objects.filter(user=user).update(force_password_change=False)
    record_login_event(LoginEventType.PASSWORD_RESET, request=request, user=user)


@receiver(mfa_signals.authenticator_added)
def log_mfa_added(sender, request, user, authenticator, **kwargs):
    record_login_event(
        LoginEventType.MFA_ENABLED,
        request=request,
        user=user,
        metadata={"type": authenticator.type},
    )
    record_audit_event(
        AuditAction.SECURITY,
        "Wlaczono uwierzytelnianie wieloskladnikowe.",
        request=request,
        module="security",
        instance=user,
        metadata={"type": authenticator.type},
    )


@receiver(mfa_signals.authenticator_removed)
def log_mfa_removed(sender, request, user, authenticator, **kwargs):
    record_login_event(
        LoginEventType.MFA_DISABLED,
        request=request,
        user=user,
        metadata={"type": authenticator.type},
    )
    record_audit_event(
        AuditAction.SECURITY,
        "Wylaczono uwierzytelnianie wieloskladnikowe.",
        request=request,
        module="security",
        instance=user,
        metadata={"type": authenticator.type},
    )


@receiver(mfa_signals.authenticator_used)
def log_mfa_use(sender, request, user, authenticator, **kwargs):
    event_type = LoginEventType.MFA_RECOVERY_USED if authenticator.type == authenticator.Type.RECOVERY_CODES else LoginEventType.MFA_SUCCESS
    record_login_event(
        event_type,
        request=request,
        user=user,
        metadata={"type": authenticator.type, "reauthenticated": bool(kwargs.get("reauthenticated"))},
    )


@receiver(mfa_signals.authentication_failed)
def log_mfa_failure(sender, request, user, authenticator, **kwargs):
    record_login_event(
        LoginEventType.MFA_FAILURE,
        request=request,
        user=user,
        result="failure",
        reason="Nieprawidlowy kod MFA.",
        metadata={"type": getattr(authenticator, "type", "unknown")},
    )
