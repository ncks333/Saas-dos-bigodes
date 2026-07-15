from datetime import UTC, datetime, timedelta
import json
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests
from celery.exceptions import Retry
from django.db import DatabaseError, OperationalError
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.customers.models import Customer
from apps.notifications import tasks as notification_tasks
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
def test_whatsapp_provider_normalizes_legacy_local_recipient(monkeypatch):
    response = Mock()
    response.json.return_value = {"messages": [{"id": "wamid.message-id"}]}
    requests_post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", requests_post)

    WhatsAppProvider().send_template(
        "(11) 99999-9999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "15/07 às 14:00"],
    )

    assert requests_post.call_args.kwargs["json"]["to"] == "5511999999999"


@override_settings(**META_SETTINGS)
def test_whatsapp_provider_rejects_invalid_recipient_before_post(monkeypatch):
    requests_post = Mock()
    monkeypatch.setattr("apps.notifications.providers.requests.post", requests_post)

    with pytest.raises(ValueError, match="WhatsApp inválido"):
        WhatsAppProvider().send_template(
            "+1 202 555 0123",
            "barberhub_agendamento_recebido",
            ["Nick", "Corte", "15/07 às 14:00"],
        )

    requests_post.assert_not_called()


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


def snapshot(appointment: Appointment) -> str:
    return appointment.starts_at.astimezone(UTC).isoformat()


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

    send_appointment_reminder.run(appointment.id, hours, snapshot(appointment))

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
def test_conditional_claim_can_only_be_obtained_once(barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    log = NotificationLog.objects.create(
        barbershop=barbershop,
        appointment=appointment,
        kind="CONFIRMATION",
        recipient=appointment.customer.whatsapp,
    )

    assert notification_tasks._claim_notification(log.id) is True
    assert notification_tasks._claim_notification(log.id) is False
    log.refresh_from_db()
    assert log.status == "SENDING"


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_worker_without_claim_does_not_post(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    NotificationLog.objects.create(
        barbershop=barbershop,
        appointment=appointment,
        kind="CONFIRMATION",
        recipient=appointment.customer.whatsapp,
        status="SENDING",
    )
    send_template = Mock()
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)

    send_template.assert_not_called()


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_timeout_marks_unknown_without_retry(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    retry = Mock()
    monkeypatch.setattr(send_appointment_confirmation, "retry", retry)
    monkeypatch.setattr(
        "apps.notifications.tasks.WhatsAppProvider.send_template",
        Mock(side_effect=requests.Timeout("raw recipient and credential material")),
    )

    send_appointment_confirmation.run(appointment.id)

    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "UNKNOWN"
    assert log.provider_response == {"error": {"class": "Timeout"}}
    retry.assert_not_called()


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_retryable_http_error_uses_controlled_retry(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    response = Mock(status_code=503)
    response.json.return_value = {"error": {"code": 2, "message": "raw sensitive material"}}
    http_error = requests.HTTPError("raw sensitive material", response=response)
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(send_appointment_confirmation, "retry", retry)
    monkeypatch.setattr(
        "apps.notifications.tasks.WhatsAppProvider.send_template",
        Mock(side_effect=http_error),
    )

    with pytest.raises(Retry):
        send_appointment_confirmation.run(appointment.id)

    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "PENDING"
    assert log.provider_response == {
        "error": {"class": "HTTPError", "http_status": 503, "meta_code": 2}
    }
    retry.assert_called_once()
    retry_exception = retry.call_args.kwargs["exc"]
    assert "raw sensitive material" not in str(retry_exception)


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_terminal_http_error_is_failed_with_sanitized_metadata(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    response = Mock(status_code=400)
    response.json.return_value = {
        "error": {"code": 131047, "message": "raw recipient, payload and credential material"}
    }
    http_error = requests.HTTPError(
        "raw recipient, payload and credential material",
        response=response,
    )
    monkeypatch.setattr(
        "apps.notifications.tasks.WhatsAppProvider.send_template",
        Mock(side_effect=http_error),
    )

    send_appointment_confirmation.run(appointment.id)

    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "FAILED"
    assert log.provider_response == {
        "error": {"class": "HTTPError", "http_status": 400, "meta_code": 131047}
    }
    serialized_metadata = json.dumps(log.provider_response)
    assert "raw recipient" not in serialized_metadata
    assert "credential" not in serialized_metadata


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_persistence_failure_after_acceptance_keeps_sending_and_prevents_second_post(
    monkeypatch,
    barbershop,
):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": "wamid.accepted"}]})
    retry = Mock()
    monkeypatch.setattr(send_appointment_confirmation, "retry", retry)
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)
    original_update = QuerySet.update

    def fail_sent_update(queryset, **kwargs):
        if kwargs.get("status") == "SENT":
            raise DatabaseError("database unavailable")
        return original_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", fail_sent_update)

    send_appointment_confirmation.run(appointment.id)
    send_appointment_confirmation.run(appointment.id)

    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "SENDING"
    send_template.assert_called_once()
    retry.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("failure_point", ["appointment_get", "log_get_or_create", "claim"])
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_database_failure_before_post_uses_bounded_retry(
    monkeypatch,
    barbershop,
    failure_point,
):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    database_error = OperationalError("sensitive database material")
    original_get = QuerySet.get
    original_get_or_create = QuerySet.get_or_create

    def maybe_fail_get(queryset, *args, **kwargs):
        if failure_point == "appointment_get" and queryset.model is Appointment:
            raise database_error
        return original_get(queryset, *args, **kwargs)

    def maybe_fail_get_or_create(queryset, *args, **kwargs):
        if failure_point == "log_get_or_create" and queryset.model is NotificationLog:
            raise database_error
        return original_get_or_create(queryset, *args, **kwargs)

    if failure_point == "appointment_get":
        monkeypatch.setattr(QuerySet, "get", maybe_fail_get)
    elif failure_point == "log_get_or_create":
        monkeypatch.setattr(QuerySet, "get_or_create", maybe_fail_get_or_create)
    else:
        monkeypatch.setattr(
            "apps.notifications.tasks._claim_notification",
            Mock(side_effect=database_error),
        )

    retry = Mock(side_effect=Retry())
    send_template = Mock()
    monkeypatch.setattr(send_appointment_confirmation, "retry", retry)
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    with pytest.raises(Retry):
        send_appointment_confirmation.run(appointment.id)

    send_template.assert_not_called()
    retry.assert_called_once()
    assert retry.call_args.kwargs["max_retries"] == 5
    assert retry.call_args.kwargs["countdown"] == 1
    assert "sensitive database material" not in str(retry.call_args.kwargs["exc"])


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_reminder_database_lookup_failure_retries_before_post(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    original_get = QuerySet.get

    def fail_appointment_get(queryset, *args, **kwargs):
        if queryset.model is Appointment:
            raise OperationalError("sensitive database material")
        return original_get(queryset, *args, **kwargs)

    retry = Mock(side_effect=Retry())
    send_template = Mock()
    monkeypatch.setattr(QuerySet, "get", fail_appointment_get)
    monkeypatch.setattr(send_appointment_reminder, "retry", retry)
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    with pytest.raises(Retry):
        send_appointment_reminder.run(appointment.id, 24, snapshot(appointment))

    send_template.assert_not_called()
    retry.assert_called_once()


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_template_parameters_use_barbershop_timezone(monkeypatch, barbershop):
    barbershop.timezone = "America/Manaus"
    barbershop.save(update_fields=["timezone", "updated_at"])
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=UTC)
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": "wamid.timezone"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)

    assert send_template.call_args.args[2] == ["Nick", "Corte", "16/07 às 10:00"]


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_cancelled_appointment_does_not_send_reminder(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    original_snapshot = snapshot(appointment)
    appointment.status = Appointment.Status.CANCELLED
    appointment.save(update_fields=["status", "updated_at"])
    send_template = Mock()
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_reminder.run(appointment.id, 24, original_snapshot)

    send_template.assert_not_called()


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_rescheduled_appointment_does_not_send_stale_reminder(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    original_snapshot = snapshot(appointment)
    appointment.starts_at += timedelta(hours=2)
    appointment.ends_at += timedelta(hours=2)
    appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
    send_template = Mock()
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_reminder.run(appointment.id, 24, original_snapshot)

    send_template.assert_not_called()


@pytest.mark.django_db
def test_reminder_rejects_unsupported_hours(barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)

    with pytest.raises(ValueError, match="hours"):
        send_appointment_reminder.run(appointment.id, 2, snapshot(appointment))


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=60)
def test_scheduler_enqueues_24h_and_1h_reminders_with_snapshot(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    reminder_24h = make_appointment(barbershop, now + timedelta(hours=24))
    reminder_1h = make_appointment(barbershop, now + timedelta(hours=1), sequence=2)
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    assert delay.call_count == 2
    delay.assert_any_call(reminder_24h.id, 24, snapshot(reminder_24h))
    delay.assert_any_call(reminder_1h.id, 1, snapshot(reminder_1h))


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=60)
def test_scheduler_catches_up_reminder_missed_30_minutes_ago(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, now + timedelta(hours=23, minutes=30))
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    delay.assert_called_once_with(appointment.id, 24, snapshot(appointment))


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=120)
def test_scheduler_does_not_enqueue_appointments_already_started(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    make_appointment(barbershop, now - timedelta(minutes=30))
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    delay.assert_not_called()


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=60)
def test_scheduler_reenqueues_preexisting_pending_log(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, now + timedelta(hours=24))
    NotificationLog.objects.create(
        barbershop=barbershop,
        appointment=appointment,
        kind="REMINDER_24H",
        recipient=appointment.customer.whatsapp,
        status="PENDING",
    )
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    delay.assert_called_once_with(appointment.id, 24, snapshot(appointment))


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=5)
def test_scheduler_recovers_pending_log_after_materialization_window(
    monkeypatch,
    barbershop,
):
    current_time = [
        datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    ]
    appointment = make_appointment(barbershop, current_time[0] + timedelta(hours=24))
    delay = Mock(side_effect=[RuntimeError("broker unavailable"), None])
    monkeypatch.setattr(timezone, "now", lambda: current_time[0])
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    with pytest.raises(RuntimeError, match="broker unavailable"):
        enqueue_due_reminders.run()

    assert NotificationLog.objects.filter(
        appointment=appointment,
        kind="REMINDER_24H",
        status="PENDING",
    ).exists()

    current_time[0] += timedelta(minutes=10)
    enqueue_due_reminders.run()

    assert delay.call_count == 2
    assert delay.call_args.args == (appointment.id, 24, snapshot(appointment))


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["SENT", "SENDING", "UNKNOWN", "FAILED"])
@override_settings(WHATSAPP_REMINDER_LOOKBACK_MINUTES=60)
def test_scheduler_does_not_reenqueue_non_pending_log(monkeypatch, barbershop, status):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, now + timedelta(hours=24))
    NotificationLog.objects.create(
        barbershop=barbershop,
        appointment=appointment,
        kind="REMINDER_24H",
        recipient=appointment.customer.whatsapp,
        status=status,
    )
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    delay.assert_not_called()


@pytest.mark.django_db
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_duplicate_reminder_jobs_with_pending_log_post_once(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    NotificationLog.objects.create(
        barbershop=barbershop,
        appointment=appointment,
        kind="REMINDER_24H",
        recipient=appointment.customer.whatsapp,
        status="PENDING",
    )
    send_template = Mock(return_value={"messages": [{"id": "wamid.once"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_reminder.run(appointment.id, 24, snapshot(appointment))
    send_appointment_reminder.run(appointment.id, 24, snapshot(appointment))

    send_template.assert_called_once()
    assert NotificationLog.objects.get(
        appointment=appointment,
        kind="REMINDER_24H",
    ).status == "SENT"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "meta_code",
    ["sensitive-recipient-payload-material", True],
)
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_non_integer_meta_error_code_is_omitted(monkeypatch, barbershop, meta_code):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    response = Mock(status_code=400)
    response.json.return_value = {"error": {"code": meta_code}}
    http_error = requests.HTTPError("generic terminal error", response=response)
    monkeypatch.setattr(
        "apps.notifications.tasks.WhatsAppProvider.send_template",
        Mock(side_effect=http_error),
    )

    send_appointment_confirmation.run(appointment.id)

    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "FAILED"
    assert log.provider_response == {
        "error": {"class": "HTTPError", "http_status": 400}
    }
    assert "sensitive-recipient-payload-material" not in json.dumps(
        log.provider_response
    )
