from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.core import mail
from django.core.signing import TimestampSigner

from apps.accounts.models import User
from apps.billing.models import Subscription
from apps.billing.providers.asaas import CheckoutResult


SUBSCRIPTION_REQUIRED = "subscription_required"
REGULARIZATION_MESSAGE = (
    "Se a conta precisar de regularização, enviaremos as instruções."
)


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


def subscription_error_code(response):
    assert response.data["error"]["details"]["code"] == SUBSCRIPTION_REQUIRED
    return response.data["code"]


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Subscription.Status.SUSPENDED, Subscription.Status.CANCELED])
def test_blocked_user_gets_no_jwt(client, user, subscription, status):
    subscription.status = status
    subscription.save(update_fields=["status", "updated_at"])

    response = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "Senha123"},
    )

    assert response.status_code == 403
    assert subscription_error_code(response) == SUBSCRIPTION_REQUIRED
    assert "access" not in response.data
    assert "refresh" not in response.data


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Subscription.Status.SUSPENDED, Subscription.Status.CANCELED])
def test_blocked_user_cannot_refresh_existing_jwt(client, user, subscription, status):
    active_login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "Senha123"},
    )
    subscription.status = status
    subscription.save(update_fields=["status", "updated_at"])

    response = client.post(
        "/api/v1/auth/refresh/", {"refresh": active_login.data["refresh"]}
    )

    assert response.status_code == 403
    assert subscription_error_code(response) == SUBSCRIPTION_REQUIRED
    assert "access" not in response.data


@pytest.mark.django_db
def test_regularization_request_does_not_enumerate_email_and_only_emails_admins(
    client, user, subscription
):
    employee = User.objects.create_user(
        username="employee",
        email="employee@example.com",
        password="Senha123",
        barbershop=subscription.barbershop,
        role=User.Role.EMPLOYEE,
    )
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    known = client.post(
        "/api/v1/billing/regularization/request/", {"email": user.email}
    )
    unknown = client.post(
        "/api/v1/billing/regularization/request/", {"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data == {"message": REGULARIZATION_MESSAGE}
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    assert employee.email not in mail.outbox[0].to
    token = parse_qs(urlparse(mail.outbox[0].body).query)["token"][0]
    assert TimestampSigner(salt="billing-regularization").unsign(token, max_age=3600) == str(
        subscription.external_reference
    )


@pytest.mark.django_db
def test_valid_regularization_token_returns_and_persists_hosted_checkout(
    client, user, subscription, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda _subscription, _user: CheckoutResult(
            id="chk_reg", url="https://asaas.test/reg"
        ),
        raising=False,
    )
    token = TimestampSigner(salt="billing-regularization").sign(
        str(subscription.external_reference)
    )

    response = client.post(
        "/api/v1/billing/regularization/checkout/", {"token": token}
    )

    assert response.status_code == 200
    assert response.data == {"checkout_url": "https://asaas.test/reg"}
    subscription.refresh_from_db()
    assert subscription.provider_checkout_id == "chk_reg"


@pytest.mark.django_db
def test_regularization_checkout_rejects_invalid_or_expired_tokens(client, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    signer = TimestampSigner(salt="billing-regularization")
    with patch("django.core.signing.time.time", return_value=1_000):
        expired_token = signer.sign(str(subscription.external_reference))

    invalid = client.post(
        "/api/v1/billing/regularization/checkout/", {"token": "invalid"}
    )
    with patch("django.core.signing.time.time", return_value=4_601):
        expired = client.post(
            "/api/v1/billing/regularization/checkout/", {"token": expired_token}
        )

    assert invalid.status_code == expired.status_code == 400


@pytest.mark.django_db
def test_regularization_checkout_requires_currently_blocked_subscription(
    client, subscription
):
    token = TimestampSigner(salt="billing-regularization").sign(
        str(subscription.external_reference)
    )

    response = client.post(
        "/api/v1/billing/regularization/checkout/", {"token": token}
    )

    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/billing/regularization/request/", {"email": "nobody@example.com"}),
        ("/api/v1/billing/regularization/checkout/", {"token": "invalid"}),
    ],
)
def test_regularization_endpoints_rate_limit_public_posts(client, path, payload):
    responses = [client.post(path, payload) for _ in range(6)]

    assert responses[-1].status_code == 403
