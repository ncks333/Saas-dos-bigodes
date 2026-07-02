from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.customers.models import Customer
from apps.services.models import Service


def future_start(barbershop, *, days=14, hour=10):
    return (
        datetime.now(ZoneInfo(barbershop.timezone))
        .replace(hour=hour, minute=0, second=0, microsecond=0)
        + timedelta(days=days)
    )


@pytest.mark.django_db
def test_management_crud_and_settings(api_client, barbershop):
    customer = api_client.post(
        "/api/v1/customers/",
        {"name": "Cliente Demo", "whatsapp": "(11) 99999-9999", "notes": "Primeira visita"},
    )
    assert customer.status_code == 201
    customer_id = customer.data["id"]
    assert customer.data["whatsapp"] == "11999999999"
    assert api_client.post(
        "/api/v1/customers/", {"name": "Duplicado", "whatsapp": "11999999999"}
    ).status_code == 400
    assert api_client.patch(
        f"/api/v1/customers/{customer_id}/", {"notes": "Cliente recorrente"}
    ).status_code == 200

    service = api_client.post(
        "/api/v1/services/",
        {"name": " Corte Premium ", "description": "Corte completo", "price": "65.00", "duration_minutes": 45},
    )
    assert service.status_code == 201
    assert service.data["name"] == "Corte Premium"
    assert api_client.post(
        "/api/v1/services/",
        {"name": "corte premium", "price": "65.00", "duration_minutes": 45},
    ).status_code == 400

    shop = api_client.get("/api/v1/barbershop/")
    assert shop.status_code == 200
    assert api_client.patch("/api/v1/barbershop/", {"whatsapp": "5511999999999"}).status_code == 200

    invalid_block = api_client.post(
        "/api/v1/schedule-blocks/",
        {"starts_at": future_start(barbershop).isoformat(), "ends_at": (future_start(barbershop) - timedelta(hours=1)).isoformat()},
    )
    assert invalid_block.status_code == 400
    assert api_client.delete(f"/api/v1/customers/{customer_id}/").status_code == 204
    assert Customer.objects.get(pk=customer_id).active is False


@pytest.mark.django_db
def test_staff_appointment_dashboard_and_summary(api_client, barbershop, monkeypatch):
    monkeypatch.setattr("apps.appointments.views.send_appointment_confirmation.delay", lambda _id: None)
    customer = Customer.objects.create(barbershop=barbershop, name="Agenda", whatsapp="5511988888888")
    service = Service.objects.create(
        barbershop=barbershop, name="Barba", price=Decimal("40.00"), duration_minutes=30
    )
    start = future_start(barbershop)
    response = api_client.post(
        "/api/v1/appointments/",
        {"customer": customer.id, "service": service.id, "starts_at": start.isoformat(), "notes": "Demo"},
        format="json",
    )
    assert response.status_code == 201
    appointment_id = response.data["id"]
    assert response.data["ends_at"]

    updated = api_client.patch(
        f"/api/v1/appointments/{appointment_id}/", {"notes": "Atualizado", "status": "CONFIRMADO"}
    )
    assert updated.status_code == 200
    day = start.date().isoformat()
    summary = api_client.get(f"/api/v1/appointments/daily_summary/?date={day}")
    assert summary.status_code == 200
    assert summary.data["confirmed"] == 1
    dashboard = api_client.get("/api/v1/dashboard/")
    assert dashboard.status_code == 200
    assert dashboard.data["appointments"] == 1
    cancelled = api_client.post(f"/api/v1/appointments/{appointment_id}/cancel/")
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == Appointment.Status.CANCELLED
    assert api_client.post(f"/api/v1/appointments/{appointment_id}/cancel/").status_code == 400


@pytest.mark.django_db
def test_public_booking_availability_and_cancellation(client, barbershop, monkeypatch):
    monkeypatch.setattr("apps.appointments.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr("apps.appointments.views.send_appointment_confirmation.delay", lambda _id: None)
    service = Service.objects.create(
        barbershop=barbershop, name="Corte", price=Decimal("50.00"), duration_minutes=30
    )
    start = future_start(barbershop, days=21)

    assert client.get("/api/v1/public/bigodes/").status_code == 200
    services = client.get("/api/v1/public/bigodes/services/")
    assert services.status_code == 200
    assert services.data[0]["id"] == service.id
    availability = client.get(
        "/api/v1/public/bigodes/availability/",
        {"day": start.date().isoformat(), "service_id": service.id},
    )
    assert availability.status_code == 200
    assert start.isoformat() in availability.data["slots"]

    rejected = client.post(
        "/api/v1/public/bigodes/book/",
        {
            "name": "Cliente Público",
            "whatsapp": "+55 (11) 97777-7777",
            "service_id": service.id,
            "starts_at": start.isoformat(),
            "captcha_token": "development",
        },
        content_type="application/json",
    )
    assert rejected.status_code == 400

    booked = client.post(
        "/api/v1/public/bigodes/book/",
        {
            "name": "  Cliente   Público ",
            "whatsapp": "+55 (11) 97777-7777",
            "service_id": service.id,
            "starts_at": start.isoformat(),
            "captcha_token": "development",
            "privacy_notice_accepted": True,
        },
        content_type="application/json",
    )
    assert booked.status_code == 201
    assert booked.data["status"] == Appointment.Status.AWAITING
    assert Appointment.objects.get(pk=booked.data["id"]).privacy_notice_accepted_at is not None
    token = booked.data["cancellation_token"]
    cancelled = client.post("/api/v1/public/cancel/", {"token": token})
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == Appointment.Status.CANCELLED
    assert client.post("/api/v1/public/cancel/", {"token": token}).status_code == 400


@pytest.mark.django_db
def test_password_user_and_session_flows(api_client, client, user):
    assert api_client.post(
        "/api/v1/auth/change-password/",
        {"current_password": "errada", "new_password": "NovaSenha456"},
    ).status_code == 400
    assert api_client.post(
        "/api/v1/auth/change-password/",
        {"current_password": "Senha123", "new_password": "NovaSenha456"},
    ).status_code == 200
    user.refresh_from_db()
    assert user.check_password("NovaSenha456")

    created = api_client.post(
        "/api/v1/users/",
        {"username": "funcionario", "email": "funcionario@example.com", "password": "EquipeSenha456", "role": "FUNCIONARIO"},
    )
    assert created.status_code == 201

    reset = client.post("/api/v1/auth/password-reset/", {"email": user.email})
    assert reset.status_code == 200
    assert len(mail.outbox) == 1
    assert "http://localhost:5173/redefinir-senha?" in mail.outbox[0].body
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    assert client.post(
        "/api/v1/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": "ResetSenha789"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/password-reset/confirm/",
        {"uid": "invalido", "token": "invalido", "password": "ResetSenha789"},
    ).status_code == 400

    login = client.post(
        "/api/v1/auth/login/", {"username": user.username, "password": "ResetSenha789"}
    )
    authenticated = APIClient()
    authenticated.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert authenticated.post("/api/v1/auth/logout/", {}).status_code == 400
    assert authenticated.post(
        "/api/v1/auth/logout/", {"refresh": login.data["refresh"]}
    ).status_code == 204


@pytest.mark.django_db
def test_agent_tool_complete_flow(api_client, barbershop, monkeypatch):
    monkeypatch.setattr("apps.appointments.agent_views.send_appointment_confirmation.delay", lambda _id: None)
    customer = Customer.objects.create(barbershop=barbershop, name="Agente", whatsapp="5511966666666")
    service = Service.objects.create(
        barbershop=barbershop, name="Corte IA", price=Decimal("55.00"), duration_minutes=30
    )
    start = future_start(barbershop, days=28, hour=11)
    availability = api_client.post(
        "/api/v1/agent-tools/consultar-disponibilidade/",
        {"data": start.date().isoformat(), "servico_id": service.id},
    )
    assert availability.status_code == 200
    created = api_client.post(
        "/api/v1/agent-tools/criar-reserva/",
        {
            "usuario_id": customer.id,
            "servico_id": service.id,
            "data": start.date().isoformat(),
            "horario": "11:00",
        },
    )
    assert created.status_code == 201
    appointment_id = created.data["reserva_id"]
    listed = api_client.post(
        "/api/v1/agent-tools/listar-reservas-usuario/",
        {"usuario_id": customer.id, "data": start.date().isoformat()},
    )
    assert listed.status_code == 200
    assert listed.data["reservas"][0]["reserva_id"] == appointment_id
    cancelled = api_client.post(
        "/api/v1/agent-tools/cancelar-reserva/",
        {"reserva_id": appointment_id, "confirmacao_explicita": True},
    )
    assert cancelled.status_code == 200
    assert cancelled.data["status"] == Appointment.Status.CANCELLED
