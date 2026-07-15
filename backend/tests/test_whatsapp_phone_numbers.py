from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from apps.appointments.models import Appointment
from apps.appointments.schemas import PublicBookingInput
from apps.customers.models import Customer
from apps.services.models import Service


def booking_payload(whatsapp: str) -> dict:
    return {
        "name": "Cliente",
        "whatsapp": whatsapp,
        "service_id": 1,
        "starts_at": datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        "captcha_token": "test",
        "privacy_notice_accepted": True,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(11) 3333-4444", "551133334444"),
        ("(11) 99999-9999", "5511999999999"),
        ("+55 (11) 99999-9999", "5511999999999"),
        ("5511999999999", "5511999999999"),
    ],
)
def test_public_booking_normalizes_brazilian_whatsapp(raw, expected):
    payload = PublicBookingInput.model_validate(booking_payload(raw))

    assert payload.whatsapp == expected


@pytest.mark.parametrize("raw", ["123456789", "+1 202 555 0123", "telefone 11999999999"])
def test_public_booking_rejects_invalid_whatsapp(raw):
    with pytest.raises(ValidationError, match="WhatsApp inválido"):
        PublicBookingInput.model_validate(booking_payload(raw))


@pytest.mark.django_db
def test_customer_serializer_persists_normalized_whatsapp(api_client):
    response = api_client.post(
        "/api/v1/customers/",
        {"name": "Cliente Local", "whatsapp": "(11) 3333-4444"},
    )

    assert response.status_code == 201
    assert response.data["whatsapp"] == "551133334444"


@pytest.mark.django_db
def test_customer_serializer_rejects_invalid_whatsapp(api_client):
    response = api_client.post(
        "/api/v1/customers/",
        {"name": "Cliente Inválido", "whatsapp": "+1 202 555 0123"},
    )

    assert response.status_code == 400
    assert "whatsapp" in response.data["error"]["details"]


@pytest.mark.django_db
def test_customer_serializer_rejects_canonical_duplicate_of_legacy_local_row(
    api_client,
    barbershop,
):
    legacy = Customer.objects.create(
        barbershop=barbershop,
        name="Cliente Legado",
        whatsapp="11999999999",
    )

    response = api_client.post(
        "/api/v1/customers/",
        {"name": "Cliente Duplicado", "whatsapp": "+55 (11) 99999-9999"},
    )

    assert response.status_code == 400
    assert Customer.objects.filter(barbershop=barbershop).count() == 1
    assert Customer.objects.get(pk=legacy.pk).whatsapp == "11999999999"


@pytest.mark.django_db
def test_public_booking_reuses_and_canonicalizes_legacy_local_customer(
    client,
    barbershop,
    monkeypatch,
):
    legacy = Customer.objects.create(
        barbershop=barbershop,
        name="Cliente Legado",
        whatsapp="11977777777",
    )
    service = Service.objects.create(
        barbershop=barbershop,
        name="Corte Legado",
        price=Decimal("50.00"),
        duration_minutes=30,
    )
    starts_at = (
        datetime.now(ZoneInfo(barbershop.timezone))
        .replace(hour=10, minute=0, second=0, microsecond=0)
        + timedelta(days=14)
    )
    monkeypatch.setattr("apps.appointments.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.appointments.views.send_appointment_confirmation.delay",
        lambda _appointment_id: None,
    )

    response = client.post(
        "/api/v1/public/bigodes/book/",
        {
            "name": "Cliente Legado Atualizado",
            "whatsapp": "+55 (11) 97777-7777",
            "service_id": service.id,
            "starts_at": starts_at.isoformat(),
            "captcha_token": "test",
            "privacy_notice_accepted": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    legacy.refresh_from_db()
    assert legacy.whatsapp == "5511977777777"
    assert Customer.objects.filter(barbershop=barbershop).count() == 1
    assert Appointment.objects.get(pk=response.data["id"]).customer_id == legacy.id
