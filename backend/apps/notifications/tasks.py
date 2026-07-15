from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.appointments.models import Appointment

from .models import NotificationLog
from .providers import WhatsAppProvider


REMINDER_HOURS = (24, 1)
ACTIVE_REMINDER_STATUSES = (Appointment.Status.PENDING, Appointment.Status.CONFIRMED)
RETRYABLE_HTTP_STATUSES = {408, 429}


class RetryableWhatsAppDeliveryError(Exception):
    pass


def _starts_at_snapshot(starts_at) -> str:
    return starts_at.astimezone(UTC).isoformat()


def _template_parameters(appointment: Appointment) -> list[str]:
    local_start = appointment.starts_at.astimezone(
        ZoneInfo(appointment.barbershop.timezone)
    )
    return [
        appointment.customer.name,
        appointment.service.name,
        local_start.strftime("%d/%m às %H:%M"),
    ]


def _claim_notification(log_id: int) -> bool:
    claimed = NotificationLog.objects.filter(pk=log_id, status="PENDING").update(
        status="SENDING",
        provider_response={},
        updated_at=timezone.now(),
    )
    return claimed == 1


def _safe_error_metadata(exc: Exception) -> dict:
    error = {"class": exc.__class__.__name__}
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            error["http_status"] = status_code
        try:
            body = response.json()
        except (TypeError, ValueError, requests.RequestException):
            body = None
        if isinstance(body, dict):
            meta_error = body.get("error")
            meta_code = meta_error.get("code") if isinstance(meta_error, dict) else None
            if (
                isinstance(meta_code, (int, str))
                and not isinstance(meta_code, bool)
                and len(str(meta_code)) <= 50
            ):
                error["meta_code"] = meta_code
    return {"error": error}


def _safe_success_metadata(response: dict) -> dict:
    if not isinstance(response, dict):
        return {"accepted": True}
    messages = response.get("messages")
    if not isinstance(messages, list):
        return {"accepted": True}
    safe_messages = []
    for message in messages:
        message_id = message.get("id") if isinstance(message, dict) else None
        if isinstance(message_id, str) and len(message_id) <= 512:
            safe_messages.append({"id": message_id})
    return {"messages": safe_messages} if safe_messages else {"accepted": True}


def _transition_notification(log_id: int, status: str, metadata: dict) -> bool:
    try:
        updated = NotificationLog.objects.filter(pk=log_id, status="SENDING").update(
            status=status,
            provider_response=metadata,
            sent_at=timezone.now() if status == "SENT" else None,
            updated_at=timezone.now(),
        )
    except Exception:
        return False
    return updated == 1


def _is_retryable_http_error(exc: requests.HTTPError) -> bool:
    response = exc.response
    status_code = getattr(response, "status_code", None) if response is not None else None
    return status_code in RETRYABLE_HTTP_STATUSES or (
        isinstance(status_code, int) and status_code >= 500
    )


def _deliver_notification(
    task,
    log: NotificationLog,
    template_name: str,
    parameters: list[str],
) -> None:
    if not _claim_notification(log.id):
        return

    try:
        response = WhatsAppProvider().send_template(
            log.recipient,
            template_name,
            parameters,
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        _transition_notification(log.id, "UNKNOWN", _safe_error_metadata(exc))
        return
    except requests.HTTPError as exc:
        metadata = _safe_error_metadata(exc)
        if _is_retryable_http_error(exc):
            if task.request.retries >= task.max_retries:
                _transition_notification(log.id, "FAILED", metadata)
                return
            if _transition_notification(log.id, "PENDING", metadata):
                raise task.retry(
                    exc=RetryableWhatsAppDeliveryError(
                        "Retryable WhatsApp HTTP delivery failure"
                    ),
                    countdown=min(2 ** task.request.retries, 60),
                )
            return
        _transition_notification(log.id, "FAILED", metadata)
        return
    except Exception as exc:
        _transition_notification(log.id, "FAILED", _safe_error_metadata(exc))
        return

    _transition_notification(log.id, "SENT", _safe_success_metadata(response))


@shared_task(bind=True, max_retries=5)
def send_appointment_confirmation(self, appointment_id: int):
    appointment = Appointment.objects.select_related(
        "customer",
        "service",
        "barbershop",
    ).get(pk=appointment_id)
    log, _ = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind="CONFIRMATION",
        defaults={"recipient": appointment.customer.whatsapp},
    )
    _deliver_notification(
        self,
        log,
        settings.WHATSAPP_CONFIRMATION_TEMPLATE,
        _template_parameters(appointment),
    )


@shared_task
def enqueue_due_reminders():
    now = timezone.now()
    lookback = timedelta(minutes=settings.WHATSAPP_REMINDER_LOOKBACK_MINUTES)
    for hours in REMINDER_HOURS:
        appointments = Appointment.objects.select_related("customer").filter(
            status__in=ACTIVE_REMINDER_STATUSES,
            starts_at__gt=now,
            starts_at__gte=now + timedelta(hours=hours) - lookback,
            starts_at__lte=now + timedelta(hours=hours),
        )
        kind = f"REMINDER_{hours}H"
        for appointment in appointments:
            log, _ = NotificationLog.objects.get_or_create(
                barbershop=appointment.barbershop,
                appointment=appointment,
                kind=kind,
                defaults={"recipient": appointment.customer.whatsapp},
            )
            if log.status == "PENDING":
                send_appointment_reminder.delay(
                    appointment.id,
                    hours,
                    _starts_at_snapshot(appointment.starts_at),
                )


@shared_task(bind=True, max_retries=5)
def send_appointment_reminder(
    self,
    appointment_id: int,
    hours: int,
    starts_at_snapshot: str,
):
    if hours not in REMINDER_HOURS:
        raise ValueError("Reminder hours must be 1 or 24")

    kind = f"REMINDER_{hours}H"
    appointment = Appointment.objects.select_related(
        "customer",
        "service",
        "barbershop",
    ).get(pk=appointment_id)
    if (
        appointment.status not in ACTIVE_REMINDER_STATUSES
        or _starts_at_snapshot(appointment.starts_at) != starts_at_snapshot
    ):
        NotificationLog.objects.filter(
            appointment=appointment,
            kind=kind,
            status="PENDING",
        ).delete()
        return

    log, _ = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind=kind,
        defaults={"recipient": appointment.customer.whatsapp},
    )
    _deliver_notification(
        self,
        log,
        settings.WHATSAPP_REMINDER_TEMPLATE,
        _template_parameters(appointment),
    )
