from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from apps.appointments.models import Appointment
from .models import NotificationLog
from .providers import WhatsAppProvider


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_appointment_confirmation(self, appointment_id: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop, appointment=appointment, kind="CONFIRMATION",
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    message = f"Olá, {appointment.customer.name}! Seu {appointment.service.name} está marcado para {timezone.localtime(appointment.starts_at):%d/%m às %H:%M}."
    log.provider_response = WhatsAppProvider().send(log.recipient, message)
    log.status = "SENT"
    log.sent_at = timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])


@shared_task
def enqueue_due_reminders():
    now = timezone.now()
    for hours in (24, 1):
        start = now + timedelta(hours=hours, minutes=-5)
        end = now + timedelta(hours=hours, minutes=5)
        ids = Appointment.objects.filter(status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED], starts_at__range=(start, end)).values_list("id", flat=True)
        for appointment_id in ids:
            send_appointment_reminder.delay(appointment_id, hours)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_appointment_reminder(self, appointment_id: int, hours: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    kind = f"REMINDER_{hours}H"
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop, appointment=appointment, kind=kind,
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    log.provider_response = WhatsAppProvider().send(log.recipient, f"Lembrete: seu horário é em {hours} hora(s), às {timezone.localtime(appointment.starts_at):%H:%M}.")
    log.status, log.sent_at = "SENT", timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])
