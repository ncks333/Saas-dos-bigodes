from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from apps.billing.providers import asaas
from apps.billing.providers.asaas import (
    AsaasCheckoutError,
    AsaasCheckoutNotCreatedError,
    AsaasCheckoutOutcomeUnknownError,
    create_recurring_checkout,
    create_regularization_checkout,
)


ASAAS_SETTINGS = {
    "ASAAS_API_URL": "https://api-sandbox.asaas.com/v3",
    "ASAAS_CHECKOUT_BASE_URL": "https://sandbox.asaas.com/checkoutSession/show",
    "ASAAS_API_KEY": "asaas-test-token",
    "ASAAS_CHECKOUT_EXPIRES_MINUTES": 60,
    "FRONTEND_URL": "https://app.example.com/",
}


class CheckoutResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"id": "chk_1", "link": "https://sandbox.asaas.com/checkout/chk_1"}


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_uses_server_plan_and_credit_card(monkeypatch, subscription, user):
    subscription.plan.amount = Decimal("79.90")
    subscription.plan.save(update_fields=["amount", "updated_at"])
    subscription.trial_ends_at = timezone.now() + timedelta(days=30)
    subscription.next_billing_at = subscription.trial_ends_at + timedelta(days=1)
    subscription.save(update_fields=["trial_ends_at", "next_billing_at", "updated_at"])
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return CheckoutResponse()

    monkeypatch.setattr("apps.billing.providers.asaas.requests.post", fake_post)

    result = create_recurring_checkout(subscription, user)

    assert result.id == "chk_1"
    assert result.url == "https://sandbox.asaas.com/checkout/chk_1"
    assert captured == {
        "url": "https://api-sandbox.asaas.com/v3/checkouts",
        "json": {
            "billingTypes": ["CREDIT_CARD"],
            "chargeTypes": ["RECURRENT"],
            "minutesToExpire": 60,
            "externalReference": str(subscription.external_reference),
            "callback": {
                "successUrl": "https://app.example.com/checkout/concluido",
                "cancelUrl": "https://app.example.com/checkout/cancelado",
                "expiredUrl": "https://app.example.com/checkout/expirado",
            },
            "items": [
                {
                    "name": subscription.plan.name,
                    "description": "Assinatura mensal M&R BarberHub",
                    "quantity": 1,
                    "value": 79.9,
                }
            ],
            "customerData": {
                "name": user.username,
                "email": user.email,
                "phone": subscription.barbershop.whatsapp,
            },
            "subscription": {
                "cycle": "MONTHLY",
                "nextDueDate": subscription.next_billing_at.date().isoformat(),
            },
        },
        "headers": {
            "accept": "application/json",
            "content-type": "application/json",
            "access_token": "asaas-test-token",
        },
        "timeout": 10,
    }


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_regularization_checkout_uses_current_server_date(
    monkeypatch, subscription, user
):
    captured = {}
    now = timezone.now()

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return CheckoutResponse()

    monkeypatch.setattr("apps.billing.providers.asaas.requests.post", fake_post)
    monkeypatch.setattr("apps.billing.providers.asaas.timezone.now", lambda: now)

    create_regularization_checkout(subscription, user)

    assert captured["json"]["subscription"]["nextDueDate"] == now.date().isoformat()


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_uses_checkout_session_url_when_asaas_omits_link(
    monkeypatch, subscription, user
):
    class ResponseWithoutLink:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "chk_2"}

    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda url, json, headers, timeout: ResponseWithoutLink(),
    )

    result = create_regularization_checkout(subscription, user)

    assert result.url == "https://sandbox.asaas.com/checkoutSession/show?id=chk_2"


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_error_does_not_expose_api_key(monkeypatch, subscription, user):
    response = type("Response", (), {})()
    response.raise_for_status = lambda: (_ for _ in ()).throw(
        requests.HTTPError("503 Server Error")
    )
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda url, json, headers, timeout: response,
    )

    with pytest.raises(AsaasCheckoutError) as exc_info:
        create_regularization_checkout(subscription, user)

    assert "asaas-test-token" not in str(exc_info.value)


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_timeout_has_unknown_creation_outcome(monkeypatch, subscription, user):
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout()),
    )

    with pytest.raises(AsaasCheckoutOutcomeUnknownError):
        create_regularization_checkout(subscription, user)


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_validation_failure_is_definitely_not_created(
    monkeypatch, subscription, user
):
    response = type("Response", (), {"status_code": 422})()
    response.raise_for_status = lambda: (_ for _ in ()).throw(
        requests.HTTPError(response=response)
    )
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(AsaasCheckoutNotCreatedError):
        create_regularization_checkout(subscription, user)


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_checkout_invalid_json_becomes_safe_provider_error(
    monkeypatch, subscription, user
):
    response = type("Response", (), {})()
    response.raise_for_status = lambda: None
    response.json = lambda: (_ for _ in ()).throw(ValueError("invalid JSON"))
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda url, json, headers, timeout: response,
    )

    with pytest.raises(AsaasCheckoutError) as exc_info:
        create_regularization_checkout(subscription, user)

    assert "asaas-test-token" not in str(exc_info.value)


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
@pytest.mark.parametrize("payload", [{}, {"id": 1}, {"id": ""}])
def test_checkout_malformed_success_payload_becomes_safe_provider_error(
    monkeypatch, subscription, user, payload
):
    response = type("Response", (), {})()
    response.raise_for_status = lambda: None
    response.json = lambda: payload
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda url, json, headers, timeout: response,
    )

    with pytest.raises(AsaasCheckoutError):
        create_regularization_checkout(subscription, user)


@pytest.mark.django_db
@override_settings(**ASAAS_SETTINGS)
def test_cancel_checkout_uses_asaas_cancel_endpoint(monkeypatch):
    captured = {}
    response = type("Response", (), {"raise_for_status": lambda self: None})()

    def fake_post(url, headers, timeout):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return response

    monkeypatch.setattr("apps.billing.providers.asaas.requests.post", fake_post)

    asaas.cancel_checkout("chk_1")

    assert captured == {
        "url": "https://api-sandbox.asaas.com/v3/checkouts/chk_1/cancel",
        "headers": {
            "accept": "application/json",
            "access_token": "asaas-test-token",
        },
        "timeout": 10,
    }
