from __future__ import annotations

import hashlib
import hmac
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from user_agents import parse as parse_user_agent


@dataclass(frozen=True)
class RequestSecurityContext:
    actor_id: int | None = None
    request_id: uuid.UUID | None = None
    ip_address: str | None = None
    user_agent: str = ""
    source: str = "system"


_current_context: ContextVar[RequestSecurityContext] = ContextVar(
    "filmerp_security_context",
    default=RequestSecurityContext(),
)


def set_request_context(request):
    request_id = getattr(request, "filmerp_request_id", None) or uuid.uuid4()
    request.filmerp_request_id = request_id
    user = getattr(request, "user", None)
    actor_id = user.pk if user is not None and user.is_authenticated else None
    path = getattr(request, "path", "")
    if path.startswith("/admin/"):
        source = "admin"
    elif path.startswith("/konto/") or path.startswith("/security/"):
        source = "security"
    else:
        source = "dashboard"
    context = RequestSecurityContext(
        actor_id=actor_id,
        request_id=request_id,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:2000],
        source=source,
    )
    return _current_context.set(context)


def reset_request_context(token):
    _current_context.reset(token)


def current_request_context() -> RequestSecurityContext:
    return _current_context.get()


def get_client_ip(request) -> str | None:
    if request is None:
        return None
    meta = getattr(request, "META", {})
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    return meta.get("REMOTE_ADDR") or None


def mask_identifier(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "@" in value:
        local, domain = value.split("@", 1)
        visible = local[:2]
        return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(2, len(value) - 2)}"


def session_fingerprint(session_key: str | None) -> str:
    if not session_key:
        return ""
    key = str(getattr(settings, "AUDIT_SIGNING_KEY", settings.SECRET_KEY)).encode("utf-8")
    return hmac.new(key, session_key.encode("utf-8"), hashlib.sha256).hexdigest()


def describe_user_agent(value: str) -> dict[str, str]:
    if not value:
        return {"browser": "", "operating_system": "", "device": ""}
    parsed = parse_user_agent(value)
    device_family = parsed.device.family
    device = "" if device_family == "Other" else device_family
    if parsed.is_mobile:
        device = f"Telefon{f' - {device}' if device else ''}"
    elif parsed.is_tablet:
        device = f"Tablet{f' - {device}' if device else ''}"
    elif parsed.is_pc:
        device = f"Komputer{f' - {device}' if device else ''}"
    browser = parsed.browser.family
    if parsed.browser.version_string:
        browser = f"{browser} {parsed.browser.version_string}"
    operating_system = parsed.os.family
    if parsed.os.version_string:
        operating_system = f"{operating_system} {parsed.os.version_string}"
    return {
        "browser": browser[:120],
        "operating_system": operating_system[:120],
        "device": device[:120],
    }


def record_login_event(
    event_type: str,
    *,
    request=None,
    user=None,
    result: str = "success",
    reason: str = "",
    identifier: str = "",
    metadata: dict | None = None,
):
    from .models import LoginEvent, LoginEventType, SecurityProfile

    if request is not None:
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:2000]
        ip_address = get_client_ip(request)
        request_id = getattr(request, "filmerp_request_id", None)
        session_key = getattr(getattr(request, "session", None), "session_key", None)
    else:
        context = current_request_context()
        user_agent = context.user_agent
        ip_address = context.ip_address
        request_id = context.request_id
        session_key = None
    details = describe_user_agent(user_agent)
    event = LoginEvent.objects.create(
        user=user if getattr(user, "pk", None) else None,
        event_type=event_type,
        result=result,
        reason=reason[:255],
        identifier=mask_identifier(identifier),
        ip_address=ip_address,
        user_agent=user_agent,
        session_fingerprint=session_fingerprint(session_key),
        request_id=request_id,
        metadata=metadata or {},
        **details,
    )
    if user and getattr(user, "pk", None) and event_type == LoginEventType.LOGIN_SUCCESS:
        SecurityProfile.objects.update_or_create(
            user=user,
            defaults={
                "last_activity_at": timezone.now(),
                "last_login_ip": ip_address,
                "last_login_user_agent": user_agent,
            },
        )
    return event


def infer_retention_class(module: str, action: str) -> str:
    from .models import AuditAction, AuditRetentionClass

    if module in {"security", "users", "roles", "sessions", "login"} or action in {
        AuditAction.ROLE,
        AuditAction.PERMISSION,
        AuditAction.FORCE_LOGOUT,
        AuditAction.SECURITY,
    }:
        return AuditRetentionClass.SECURITY
    if module in {
        "agreements",
        "rights",
        "finance",
        "costs",
        "waterfall",
        "statements",
        "sales_reports",
        "cinema_reports",
    }:
        return AuditRetentionClass.LEGAL_FINANCIAL
    return AuditRetentionClass.ORDINARY


def record_audit_event(
    action: str,
    summary: str,
    *,
    request=None,
    actor=None,
    module: str = "system",
    instance=None,
    changes: dict | None = None,
    metadata: dict | None = None,
    source: str | None = None,
    retention_class: str | None = None,
    legacy_reference: str | None = None,
    occurred_at=None,
):
    from django.contrib.auth import get_user_model

    from .models import AuditEvent

    context = current_request_context()
    if request is not None:
        request_user = getattr(request, "user", None)
        if actor is None and request_user is not None and request_user.is_authenticated:
            actor = request_user
        request_id = getattr(request, "filmerp_request_id", None)
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:2000]
        event_source = source or ("admin" if request.path.startswith("/admin/") else "dashboard")
    else:
        if actor is None and context.actor_id:
            actor = get_user_model().objects.filter(pk=context.actor_id).first()
        request_id = context.request_id
        ip_address = context.ip_address
        user_agent = context.user_agent
        event_source = source or context.source

    content_type = None
    object_pk = ""
    object_repr = ""
    if instance is not None:
        content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)
        object_pk = str(instance.pk)
        object_repr = str(instance)[:255]

    event_kwargs = {
        "actor": actor if getattr(actor, "pk", None) else None,
        "action": action,
        "source": event_source,
        "module": module,
        "content_type": content_type,
        "object_pk": object_pk,
        "object_repr": object_repr,
        "summary": summary[:500],
        "changes": changes or {},
        "metadata": metadata or {},
        "request_id": request_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "retention_class": retention_class or infer_retention_class(module, action),
        "legacy_reference": legacy_reference,
    }
    if occurred_at is not None:
        event_kwargs["occurred_at"] = occurred_at
    return AuditEvent.objects.create(**event_kwargs)
