from typing import Any
from .models import AuditEvent


def record_event(actor, action: str, *, target: Any = None, request=None, metadata: dict | None = None) -> AuditEvent | None:
    if not actor or not actor.barbershop_id:
        return None
    return AuditEvent.objects.create(
        barbershop_id=actor.barbershop_id,
        actor=actor,
        action=action,
        target_type=target._meta.label if target else "",
        target_id=str(target.pk) if target else "",
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        metadata=metadata or {},
    )


def record_system_event(barbershop_id: int, action: str, *, target: Any = None, request=None, metadata: dict | None = None) -> AuditEvent:
    return AuditEvent.objects.create(
        barbershop_id=barbershop_id,
        actor=None,
        action=action,
        target_type=target._meta.label if target else "",
        target_id=str(target.pk) if target else "",
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        metadata=metadata or {},
    )
