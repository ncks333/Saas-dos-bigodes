from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

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
    "ASAAS_CHECKOUT_ALLOWED_ORIGINS": ["https://sandbox.asaas.com"],
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
    attempt_reference = uuid4()
    subscription.regularization_checkout_reference = attempt_reference
    subscription.save(
        update_fields=["regularization_checkout_reference", "updated_at"]
    )

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return CheckoutResponse()

    monkeypatch.setattr("apps.billing.providers.asaas.requests.post", fake_post)
    monkeypatch.setattr("apps.billing.providers.asaas.timezone.now", lambda: now)

    create_regularization_checkout(subscription, user)

    assert captured["json"]["subscription"]["nextDueDate"] == now.date().isoformat()
    assert captured["json"]["externalReference"] == str(attempt_reference)


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
def test_checkout_400_validation_failure_is_definitely_not_created(
    monkeypatch, subscription, user
):
    response = type("Response", (), {"status_code": 400})()
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
@pytest.mark.parametrize("status_code", [409, 422, 429])
def test_checkout_ambiguous_client_failures_have_unknown_creation_outcome(
    monkeypatch, subscription, user, status_code
):
    response = type("Response", (), {"status_code": status_code})()
    response.raise_for_status = lambda: (_ for _ in ()).throw(
        requests.HTTPError(response=response)
    )
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(AsaasCheckoutOutcomeUnknownError):
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
@pytest.mark.parametrize(
    "link",
    [
        "http://sandbox.asaas.com/checkout/chk_1",
        "https://evil.example/checkout/chk_1",
        "https://sandbox.asaas.com.evil.example/checkout/chk_1",
        "https://user:password@sandbox.asaas.com/checkout/chk_1",
    ],
)
def test_checkout_rejects_non_allowlisted_provider_link(
    monkeypatch, subscription, user, link
):
    subscription.next_billing_at = timezone.now() + timedelta(days=30)
    subscription.save(update_fields=["next_billing_at", "updated_at"])

    class UnsafeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "chk_unsafe", "link": link}

    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.post",
        lambda *_args, **_kwargs: UnsafeResponse(),
    )

    with pytest.raises(AsaasCheckoutOutcomeUnknownError) as exc_info:
        create_recurring_checkout(subscription, user)

    assert exc_info.value.checkout_id == "chk_unsafe"


@override_settings(**ASAAS_SETTINGS)
def test_checkout_url_validator_accepts_exact_configured_sandbox_origin():
    assert asaas.validate_checkout_url(
        "https://sandbox.asaas.com/checkoutSession/show/chk_1"
    ) == "https://sandbox.asaas.com/checkoutSession/show/chk_1"


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


@override_settings(**ASAAS_SETTINGS)
def test_paid_checkout_reconciliation_retrieves_id_then_exact_subscription(
    monkeypatch,
):
    external_reference = str(uuid4())
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, *, headers, timeout, params=None):
        calls.append(
            {"url": url, "headers": headers, "timeout": timeout, "params": params}
        )
        if url.endswith("/checkouts/chk_paid"):
            return Response(
                {
                    "id": "chk_paid",
                    "status": "PAID",
                    "externalReference": external_reference,
                }
            )
        return Response(
            {
                "object": "list",
                "hasMore": False,
                "totalCount": 1,
                "limit": 2,
                "offset": 0,
                "data": [
                    {
                        "id": "sub_verified",
                        "status": "ACTIVE",
                        "externalReference": external_reference,
                    }
                ],
            }
        )

    monkeypatch.setattr("apps.billing.providers.asaas.requests.get", fake_get)

    result = asaas.reconcile_paid_checkout("chk_paid", external_reference)

    assert result.checkout_id == "chk_paid"
    assert result.external_reference == external_reference
    assert result.provider_subscription_id == "sub_verified"
    assert calls == [
        {
            "url": "https://api-sandbox.asaas.com/v3/checkouts/chk_paid",
            "headers": {
                "accept": "application/json",
                "access_token": "asaas-test-token",
            },
            "timeout": 10,
            "params": None,
        },
        {
            "url": "https://api-sandbox.asaas.com/v3/subscriptions",
            "headers": {
                "accept": "application/json",
                "access_token": "asaas-test-token",
            },
            "timeout": 10,
            "params": {"externalReference": external_reference, "limit": 2},
        },
    ]


@override_settings(**ASAAS_SETTINGS)
@pytest.mark.parametrize(
    "checkout_payload",
    [
        {"id": "chk_other", "status": "PAID", "externalReference": "expected"},
        {"id": "chk_paid", "status": "ACTIVE", "externalReference": "expected"},
        {"id": "chk_paid", "status": "PAID", "externalReference": "other"},
        {"id": "chk_paid", "status": "PAID"},
    ],
)
def test_paid_checkout_reconciliation_fails_closed_on_checkout_mismatch(
    monkeypatch, checkout_payload
):
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: checkout_payload,
        },
    )()
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.get",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(AsaasCheckoutError):
        asaas.reconcile_paid_checkout("chk_paid", "expected")


@override_settings(**ASAAS_SETTINGS)
@pytest.mark.parametrize(
    "subscription_payload",
    [
        {"data": []},
        {
            "data": [
                {"id": "sub_1", "status": "ACTIVE", "externalReference": "expected"},
                {"id": "sub_2", "status": "ACTIVE", "externalReference": "expected"},
            ]
        },
        {"data": [{"id": "sub_1", "status": "INACTIVE", "externalReference": "expected"}]},
        {"data": [{"id": "sub_1", "status": "ACTIVE", "externalReference": "other"}]},
    ],
)
def test_paid_checkout_reconciliation_fails_closed_on_ambiguous_subscription(
    monkeypatch, subscription_payload
):
    responses = iter(
        [
            {
                "id": "chk_paid",
                "status": "PAID",
                "externalReference": "expected",
            },
            subscription_payload,
        ]
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return next(responses)

    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.get",
        lambda *_args, **_kwargs: Response(),
    )

    with pytest.raises(AsaasCheckoutError):
        asaas.reconcile_paid_checkout("chk_paid", "expected")


@override_settings(**ASAAS_SETTINGS)
def test_paid_checkout_reconciliation_hides_api_key_on_transport_failure(monkeypatch):
    monkeypatch.setattr(
        "apps.billing.providers.asaas.requests.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            requests.Timeout("asaas-test-token")
        ),
    )

    with pytest.raises(AsaasCheckoutError) as exc_info:
        asaas.reconcile_paid_checkout("chk_paid", "expected")

    assert "asaas-test-token" not in str(exc_info.value)
