from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.barbershops.models import Barbershop, OperatingHour
from apps.billing.models import Subscription, SubscriptionPlan
from apps.billing.providers.asaas import (
    AsaasCheckoutError,
    AsaasCheckoutOutcomeUnknownError,
    CheckoutResult,
)
from apps.billing.services import provision_signup


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
def test_public_plan_uses_canonical_server_code_not_first_active_plan(
    client, plan, settings
):
    plan.code = "internal-first"
    plan.save(update_fields=["code", "updated_at"])
    canonical = SubscriptionPlan.objects.create(
        code="barberhub",
        name="BarberHub público",
        amount=Decimal("89.90"),
        trial_days=30,
    )
    settings.BILLING_PUBLIC_PLAN_CODE = canonical.code

    response = client.get("/api/v1/billing/plans/current/")

    assert response.status_code == 200
    assert response.data["code"] == canonical.code
    assert response.data["amount"] == "89.90"


@pytest.mark.django_db
def test_signup_cannot_select_internal_active_plan(client, plan, monkeypatch, settings):
    internal = SubscriptionPlan.objects.create(
        code="internal-60",
        name="Oferta interna",
        amount=Decimal("1.00"),
        trial_days=60,
    )
    settings.BILLING_PUBLIC_PLAN_CODE = plan.code
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda subscription, _user: CheckoutResult(
            id="chk_public",
            url="https://sandbox.asaas.com/checkoutSession/show/chk_public",
        ),
    )

    response = client.post(
        "/api/v1/billing/signup/",
        signup_payload(plan_code=internal.code),
        content_type="application/json",
    )

    assert response.status_code == 201
    subscription = Subscription.objects.get(barbershop__slug="barbearia-joao")
    assert subscription.plan_id == plan.id
    assert subscription.trial_days == plan.trial_days


@pytest.mark.django_db
def test_trusted_server_plan_preserves_preprovisioned_60_day_pilot(
    monkeypatch, plan
):
    pilot_plan = SubscriptionPlan.objects.create(
        code="pilot-60-server-only",
        name="Piloto 60 dias",
        amount=plan.amount,
        trial_days=60,
        active=False,
    )
    now = timezone.now()
    captured = {}
    monkeypatch.setattr("apps.billing.services.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda subscription, _user: captured.update(
            {"next_billing_at": subscription.next_billing_at}
        )
        or CheckoutResult(
            id="chk_pilot",
            url="https://sandbox.asaas.com/checkoutSession/show/chk_pilot",
        ),
    )
    data = signup_payload(
        email="pilot@example.com",
        username="pilot",
        slug="piloto-60",
        whatsapp="5511999999999",
    )

    subscription, _checkout = provision_signup(data, pilot_plan)

    assert subscription.plan_id == pilot_plan.id
    assert subscription.trial_days == 60
    assert subscription.trial_ends_at == now + timedelta(days=60)
    assert captured["next_billing_at"] == subscription.trial_ends_at + timedelta(
        days=1
    )


@pytest.mark.django_db
def test_signup_creates_pending_tenant_and_hosted_checkout(client, plan, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr("apps.billing.services.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda subscription, user: CheckoutResult(
            id="chk_1", url="https://sandbox.asaas.com/checkoutSession/show/chk_1"
        ),
    )

    response = client.post(
        "/api/v1/billing/signup/",
        signup_payload(amount="0.01"),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert set(response.data) == {"checkout_url", "external_reference"}
    assert response.data["checkout_url"] == "https://sandbox.asaas.com/checkoutSession/show/chk_1"
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
def test_signup_unknown_checkout_outcome_persists_reconciliation_record(
    plan, monkeypatch
):
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: (_ for _ in ()).throw(
            AsaasCheckoutOutcomeUnknownError("timeout")
        ),
    )

    with pytest.raises(AsaasCheckoutOutcomeUnknownError, match="timeout"):
        provision_signup(signup_payload(), plan)

    subscription = Subscription.objects.get(barbershop__slug="barbearia-joao")
    assert subscription.status == Subscription.Status.PENDING_CHECKOUT
    assert subscription.signup_checkout_state == "RECONCILIATION_REQUIRED"
    assert subscription.provider_checkout_id == ""


@pytest.mark.django_db
def test_provider_failure_returns_503_and_rolls_back_local_tenant(
    client, plan, monkeypatch
):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    canceled_checkouts = []
    monkeypatch.setattr(
        "apps.billing.services.cancel_checkout",
        lambda checkout_id: canceled_checkouts.append(checkout_id),
    )
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
    assert canceled_checkouts == []


@pytest.mark.django_db
def test_signup_api_rejects_non_asaas_checkout_url_and_rolls_back(
    client, plan, monkeypatch
):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: CheckoutResult(
            id="chk_evil", url="https://evil.example/checkout/chk_evil"
        ),
    )
    monkeypatch.setattr("apps.billing.services.cancel_checkout", lambda *_args: None)

    response = client.post(
        "/api/v1/billing/signup/", signup_payload(), content_type="application/json"
    )

    assert response.status_code == 503
    assert Subscription.objects.count() == 0
    assert Barbershop.objects.count() == 0


@pytest.mark.django_db
def test_audit_failure_prevents_provider_call_and_rolls_back_tenant(
    client, plan, monkeypatch
):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.audit.services.record_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit failed")),
    )
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: pytest.fail("provider must not run after audit failure"),
    )

    with pytest.raises(RuntimeError, match="audit failed"):
        client.post(
            "/api/v1/billing/signup/", signup_payload(), content_type="application/json"
        )

    assert Barbershop.objects.count() == 0
    assert User.objects.count() == 0
    assert Subscription.objects.count() == 0
    assert OperatingHour.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_local_failure_after_checkout_cancels_remote_checkout_and_rolls_back_tenant(
    client, plan, monkeypatch
):
    original_save = Subscription.save
    canceled_checkouts = []
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: CheckoutResult(
            id="chk_1", url="https://sandbox.asaas.com/checkoutSession/show/chk_1"
        ),
    )
    monkeypatch.setattr(
        "apps.billing.services.cancel_checkout",
        lambda checkout_id: canceled_checkouts.append(checkout_id),
        raising=False,
    )

    def fail_provider_checkout_save(self, *args, **kwargs):
        if "provider_checkout_id" in kwargs.get("update_fields", []):
            raise DatabaseError("local persistence failed")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(Subscription, "save", fail_provider_checkout_save)

    with pytest.raises(DatabaseError, match="local persistence failed"):
        client.post(
            "/api/v1/billing/signup/", signup_payload(), content_type="application/json"
        )

    assert canceled_checkouts == ["chk_1"]
    assert Barbershop.objects.count() == 0
    assert User.objects.count() == 0
    assert Subscription.objects.count() == 0
    assert OperatingHour.objects.count() == 0
    assert AuditEvent.objects.count() == 0
