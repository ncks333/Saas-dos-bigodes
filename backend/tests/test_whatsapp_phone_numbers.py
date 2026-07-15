from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from apps.appointments.schemas import PublicBookingInput


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
