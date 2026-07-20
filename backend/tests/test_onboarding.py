from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.barbershops.models import Barbershop, OperatingHour
from apps.billing.models import Subscription
from apps.billing.providers.asaas import AsaasCheckoutError, CheckoutResult


def signup_payload(**overrides):
    payload = {
        "first_name": "João",
        "email": "joao@example.com",
        "username": "joao",
        "password": "SenhaForte123",
        "barbershop_name": "Barbearia João",
        "slug": "barbearia-joao",
        "whatsapp": "(11) 99999-9999",
        "plan_code": "barberhub",
        "captcha_token": "development",
        "terms_accepted": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_public_plan_exposes_server_owned_price(client, plan):
    response = client.get("/api/v1/billing/plans/current/")

    assert response.status_code == 200
    assert response.data == {
        "code": "barberhub",
        "name": "BarberHub",
        "amount": "79.90",
        "currency": "BRL",
        "trial_days": 30,
    }


@pytest.mark.django_db
def test_signup_creates_pending_tenant_and_hosted_checkout(client, plan, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr("apps.billing.services.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda subscription, user: CheckoutResult(
            id="chk_1", url="https://asaas.test/chk_1"
        ),
    )

    response = client.post(
        "/api/v1/billing/signup/",
        signup_payload(amount="0.01"),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert set(response.data) == {"checkout_url", "external_reference"}
    assert response.data["checkout_url"] == "https://asaas.test/chk_1"
    subscription = Subscription.objects.get(barbershop__slug="barbearia-joao")
    assert subscription.plan_id == plan.id
    assert subscription.plan.amount == Decimal("79.90")
    assert subscription.status == Subscription.Status.PENDING_CHECKOUT
    assert subscription.trial_ends_at == now + timedelta(days=plan.trial_days)
    assert subscription.next_billing_at == subscription.trial_ends_at + timedelta(
        days=1
    )
    assert subscription.provider_checkout_id == "chk_1"
    user = User.objects.get(username="joao")
    assert user.is_active is False
    assert user.role == User.Role.ADMIN
    assert user.barbershop_id == subscription.barbershop_id
    assert subscription.barbershop.whatsapp == "5511999999999"
    assert OperatingHour.objects.filter(barbershop=subscription.barbershop).count() == 6
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        actor=user,
        action="BILLING_SIGNUP_CREATED",
        target_id=str(subscription.id),
    ).exists()


@pytest.mark.django_db
def test_signup_rejects_invalid_payload_without_partial_tenant(client):
    response = client.post(
        "/api/v1/billing/signup/",
        signup_payload(email="inválido", terms_accepted=False),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert Barbershop.objects.count() == 0
    assert User.objects.count() == 0
    assert Subscription.objects.count() == 0
    assert OperatingHour.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_signup_rejects_failed_turnstile_without_provider_or_tenant(
    client, monkeypatch
):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: False)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: pytest.fail("provider must not run after failed captcha"),
    )

    response = client.post(
        "/api/v1/billing/signup/", signup_payload(), content_type="application/json"
    )

    assert response.status_code == 400
    assert Barbershop.objects.count() == 0
    assert User.objects.count() == 0
    assert Subscription.objects.count() == 0


@pytest.mark.django_db
def test_provider_failure_returns_503_and_rolls_back_local_tenant(
    client, plan, monkeypatch
):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: (_ for _ in ()).throw(AsaasCheckoutError("Asaas indisponível")),
    )

    response = client.post(
        "/api/v1/billing/signup/", signup_payload(), content_type="application/json"
    )

    assert response.status_code == 503
    assert Barbershop.objects.count() == 0
    assert User.objects.count() == 0
    assert Subscription.objects.count() == 0
    assert OperatingHour.objects.count() == 0
    assert AuditEvent.objects.count() == 0
