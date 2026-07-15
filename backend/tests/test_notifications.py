from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.customers.models import Customer
from apps.notifications.models import NotificationLog
from apps.notifications.providers import WhatsAppProvider
from apps.notifications.tasks import (
    enqueue_due_reminders,
    send_appointment_confirmation,
    send_appointment_reminder,
)
from apps.services.models import Service


META_SETTINGS = {
    "WHATSAPP_GRAPH_API_VERSION": "v25.0",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789012345",
    "WHATSAPP_ACCESS_TOKEN": "secret-token",
    "WHATSAPP_TEMPLATE_LANGUAGE": "pt_BR",
}


@override_settings(**META_SETTINGS)
def test_whatsapp_provider_sends_meta_template(monkeypatch):
    response = Mock()
    response.json.return_value = {"messages": [{"id": "wamid.message-id"}]}
    requests_post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", requests_post)

    result = WhatsAppProvider().send_template(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "15/07 às 14:00"],
    )

    assert result == {"messages": [{"id": "wamid.message-id"}]}
    response.raise_for_status.assert_called_once_with()
    requests_post.assert_called_once_with(
        "https://graph.facebook.com/v25.0/123456789012345/messages",
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "5511999999999",
            "type": "template",
            "template": {
                "name": "barberhub_agendamento_recebido",
                "language": {"code": "pt_BR"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Nick"},
                        {"type": "text", "text": "Corte"},
                        {"type": "text", "text": "15/07 às 14:00"},
                    ],
                }],
            },
        },
        headers={
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
        },
        timeout=10,
    )


@override_settings(**META_SETTINGS)
def test_whatsapp_provider_propagates_meta_http_error(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
    monkeypatch.setattr("apps.notifications.providers.requests.post", Mock(return_value=response))

    with pytest.raises(requests.HTTPError, match="503 Server Error"):
        WhatsAppProvider().send_template(
            "5511999999999",
            "barberhub_agendamento_recebido",
            ["Nick", "Corte", "15/07 às 14:00"],
        )


@override_settings(
    DEBUG=True,
    WHATSAPP_GRAPH_API_VERSION="v25.0",
    WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_ACCESS_TOKEN="",
    WHATSAPP_TEMPLATE_LANGUAGE="pt_BR",
)
def test_whatsapp_provider_simulates_when_development_is_unconfigured():
    result = WhatsAppProvider().send_template(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "15/07 às 14:00"],
    )

    assert result == {"simulated": True}


def make_appointment(
    barbershop,
    starts_at,
    status=Appointment.Status.PENDING,
    sequence=1,
):
    customer_name = "Nick" if sequence == 1 else f"Nick {sequence}"
    whatsapp = "5511999999999" if sequence == 1 else f"55118888888{sequence:02d}"
    service_name = "Corte" if sequence == 1 else f"Corte {sequence}"

    customer = Customer.objects.create(
        barbershop=barbershop,
        name=customer_name,
        whatsapp=whatsapp,
    )
    service = Service.objects.create(
        barbershop=barbershop,
        name=service_name,
        price="50.00",
        duration_minutes=30,
    )
    return Appointment.objects.create(
        barbershop=barbershop,
        customer=customer,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        duration_minutes=30,
        status=status,
    )


@pytest.mark.django_db
@override_settings(
    WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido",
    WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento",
)
def test_confirmation_uses_booking_received_template(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at, Appointment.Status.AWAITING)
    send_template = Mock(return_value={"messages": [{"id": "wamid.confirmation"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)

    send_template.assert_called_once_with(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "16/07 às 14:00"],
    )
    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "SENT"
    assert log.provider_response == {"messages": [{"id": "wamid.confirmation"}]}


@pytest.mark.django_db
@pytest.mark.parametrize(("hours", "kind"), [(24, "REMINDER_24H"), (1, "REMINDER_1H")])
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_reminders_reuse_one_meta_template(monkeypatch, barbershop, hours, kind):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": f"wamid.{hours}h"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_reminder.run(appointment.id, hours)

    send_template.assert_called_once_with(
        "5511999999999",
        "barberhub_lembrete_agendamento",
        ["Nick", "Corte", "16/07 às 14:00"],
    )
    assert NotificationLog.objects.get(appointment=appointment, kind=kind).status == "SENT"


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_sent_confirmation_is_idempotent(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": "wamid.once"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)
    send_appointment_confirmation.run(appointment.id)

    send_template.assert_called_once()
    assert NotificationLog.objects.filter(appointment=appointment, kind="CONFIRMATION").count() == 1


@pytest.mark.django_db
def test_scheduler_enqueues_24h_and_1h_reminders(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    reminder_24h = make_appointment(barbershop, now + timedelta(hours=24))
    reminder_1h = make_appointment(barbershop, now + timedelta(hours=1), sequence=2)
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    assert delay.call_count == 2
    delay.assert_any_call(reminder_24h.id, 24)
    delay.assert_any_call(reminder_1h.id, 1)
