from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.appointments.models import Appointment

from .models import NotificationLog
from .providers import WhatsAppProvider


def _template_parameters(appointment: Appointment) -> list[str]:
    local_start = timezone.localtime(appointment.starts_at)
    return [
        appointment.customer.name,
        appointment.service.name,
        local_start.strftime("%d/%m às %H:%M"),
    ]


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_appointment_confirmation(self, appointment_id: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind="CONFIRMATION",
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    log.provider_response = WhatsAppProvider().send_template(
        log.recipient,
        settings.WHATSAPP_CONFIRMATION_TEMPLATE,
        _template_parameters(appointment),
    )
    log.status = "SENT"
    log.sent_at = timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])


@shared_task
def enqueue_due_reminders():
    now = timezone.now()
    for hours in (24, 1):
        start = now + timedelta(hours=hours, minutes=-5)
        end = now + timedelta(hours=hours, minutes=5)
        ids = Appointment.objects.filter(
            status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
            starts_at__range=(start, end),
        ).values_list("id", flat=True)
        for appointment_id in ids:
            send_appointment_reminder.delay(appointment_id, hours)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_appointment_reminder(self, appointment_id: int, hours: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    kind = f"REMINDER_{hours}H"
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind=kind,
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    log.provider_response = WhatsAppProvider().send_template(
        log.recipient,
        settings.WHATSAPP_REMINDER_TEMPLATE,
        _template_parameters(appointment),
    )
    log.status = "SENT"
    log.sent_at = timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])
