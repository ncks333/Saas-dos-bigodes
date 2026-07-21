from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.core import mail
from django.core.management import CommandError, call_command
from django.utils import timezone
from django.core.signing import TimestampSigner

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.billing.models import Subscription
from apps.billing.providers.asaas import CheckoutResult
from apps.billing.providers.asaas import (
    AsaasCheckoutError,
    AsaasCheckoutNotCreatedError,
    AsaasCheckoutOutcomeUnknownError,
)
from apps.billing.services import provision_regularization_checkout
from apps.billing.tasks import send_regularization_request_email


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
def test_regularization_request_enqueues_every_normalized_email_with_identical_response(
    client, user, subscription, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    queued = []
    monkeypatch.setattr(
        "apps.billing.views.send_regularization_request_email.delay",
        lambda email: queued.append(email),
    )

    known = client.post(
        "/api/v1/billing/regularization/request/", {"email": user.email.upper()}
    )
    unknown = client.post(
        "/api/v1/billing/regularization/request/", {"email": "NOBODY@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data == {"message": REGULARIZATION_MESSAGE}
    assert queued == [user.email, "nobody@example.com"]
    assert mail.outbox == []


@pytest.mark.django_db
def test_regularization_request_task_emails_only_blocked_admin(user, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    send_regularization_request_email.run(user.email)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]


@pytest.mark.django_db
def test_regularization_request_hides_mail_task_failure(client, user, subscription, monkeypatch):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr(
        "apps.billing.tasks.send_mail",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("mail unavailable")),
    )

    response = client.post(
        "/api/v1/billing/regularization/request/", {"email": user.email}
    )

    assert response.status_code == 200
    assert response.data == {"message": REGULARIZATION_MESSAGE}


@pytest.mark.django_db
def test_regularization_request_hides_broker_failure(client, monkeypatch):
    monkeypatch.setattr(
        "apps.billing.views.send_regularization_request_email.delay",
        lambda _email: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )

    response = client.post(
        "/api/v1/billing/regularization/request/", {"email": "nobody@example.com"}
    )

    assert response.status_code == 200
    assert response.data == {"message": REGULARIZATION_MESSAGE}


@pytest.mark.django_db
def test_valid_regularization_token_returns_and_persists_hosted_checkout(
    client, user, subscription, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda _subscription, _user: CheckoutResult(
            id="chk_reg", url="https://sandbox.asaas.com/reg"
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
    assert response.data == {"checkout_url": "https://sandbox.asaas.com/reg"}
    subscription.refresh_from_db()
    assert subscription.provider_checkout_id == "chk_reg"


@pytest.mark.django_db
def test_regularization_checkout_reuses_persisted_checkout_without_provider_retry(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    calls = []
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda _subscription, _user: calls.append(True)
        or CheckoutResult(id="chk_reused", url="https://sandbox.asaas.com/reused"),
    )

    first = provision_regularization_checkout(subscription)
    second = provision_regularization_checkout(subscription)

    subscription.refresh_from_db()
    assert first == second == CheckoutResult(
        id="chk_reused", url="https://sandbox.asaas.com/reused"
    )
    assert calls == [True]
    assert subscription.regularization_checkout_id == "chk_reused"
    assert subscription.regularization_checkout_url == "https://sandbox.asaas.com/reused"


@pytest.mark.django_db
def test_regularization_checkout_uses_new_attempt_reference_for_provider_call(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    captured_references = []
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda claimed_subscription, _user: captured_references.append(
            claimed_subscription.regularization_checkout_reference
        )
        or CheckoutResult(id="chk_attempt", url="https://sandbox.asaas.com/attempt"),
    )

    provision_regularization_checkout(subscription)

    subscription.refresh_from_db()
    assert captured_references == [subscription.regularization_checkout_reference]
    assert subscription.regularization_checkout_reference != subscription.external_reference


@pytest.mark.django_db
def test_regularization_checkout_waits_for_concurrent_claim_without_provider_retry(
    subscription, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "CREATING"
    subscription.regularization_checkout_claim = uuid4()
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "updated_at",
        ]
    )
    monkeypatch.setattr(
        "apps.billing.services._wait_for_regularization_checkout",
        lambda *_args: CheckoutResult(
            id="chk_concurrent", url="https://sandbox.asaas.com/concurrent"
        ),
    )
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda *_args: (_ for _ in ()).throw(AssertionError("provider called twice")),
    )

    checkout = provision_regularization_checkout(subscription)

    assert checkout == CheckoutResult(
        id="chk_concurrent", url="https://sandbox.asaas.com/concurrent"
    )


@pytest.mark.django_db(transaction=True)
def test_regularization_checkout_provider_call_runs_outside_transaction(
    subscription, user, monkeypatch
):
    from django.db import connection

    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    def create_checkout(_subscription, _user):
        assert connection.in_atomic_block is False
        return CheckoutResult(id="chk_unlocked", url="https://sandbox.asaas.com/unlocked")

    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout", create_checkout
    )

    checkout = provision_regularization_checkout(subscription)

    assert checkout.id == "chk_unlocked"


@pytest.mark.django_db
def test_regularization_checkout_cancels_provider_checkout_when_persistence_fails(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    canceled = []
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda _subscription, _user: CheckoutResult(
            id="chk_compensate", url="https://sandbox.asaas.com/compensate"
        ),
    )
    monkeypatch.setattr(
        "apps.billing.services._persist_regularization_checkout",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        "apps.billing.services.cancel_checkout", lambda checkout_id: canceled.append(checkout_id)
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        provision_regularization_checkout(subscription)

    assert canceled == ["chk_compensate"]
    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "READY"


@pytest.mark.django_db
def test_uncertain_regularization_checkout_failure_requires_reconciliation_and_no_retry(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    calls = []

    def timeout(*_args):
        calls.append(True)
        raise AsaasCheckoutOutcomeUnknownError("timeout")

    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout", timeout
    )

    with pytest.raises(AsaasCheckoutError):
        provision_regularization_checkout(subscription)
    with pytest.raises(AsaasCheckoutError):
        provision_regularization_checkout(subscription)

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "RECONCILIATION_REQUIRED"
    assert subscription.regularization_checkout_error == "AsaasCheckoutOutcomeUnknownError"
    assert calls == [True]


@pytest.mark.django_db
def test_definitely_not_created_regularization_checkout_returns_to_ready(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda *_args: (_ for _ in ()).throw(
            AsaasCheckoutNotCreatedError("validation failed")
        ),
    )

    with pytest.raises(AsaasCheckoutNotCreatedError):
        provision_regularization_checkout(subscription)

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "READY"


@pytest.mark.django_db
def test_compensation_failure_requires_reconciliation_and_no_retry(
    subscription, user, monkeypatch
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    provider_calls = []
    monkeypatch.setattr(
        "apps.billing.services.create_regularization_checkout",
        lambda *_args: provider_calls.append(True)
        or CheckoutResult(id="chk_uncertain", url="https://sandbox.asaas.com/uncertain"),
    )
    monkeypatch.setattr(
        "apps.billing.services._persist_regularization_checkout",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        "apps.billing.services.cancel_checkout",
        lambda *_args: (_ for _ in ()).throw(AsaasCheckoutError("cancel timeout")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        provision_regularization_checkout(subscription)
    with pytest.raises(AsaasCheckoutError):
        provision_regularization_checkout(subscription)

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "RECONCILIATION_REQUIRED"
    assert subscription.regularization_checkout_error == "RuntimeError"
    assert provider_calls == [True]


@pytest.mark.django_db
def test_reconciliation_command_attaches_verified_checkout(subscription):
    attempt_reference = uuid4()
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "CREATING"
    subscription.regularization_checkout_claim = uuid4()
    subscription.regularization_checkout_reference = attempt_reference
    subscription.regularization_checkout_claim_started_at = timezone.now() - timedelta(
        minutes=6
    )
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_reference",
            "regularization_checkout_claim_started_at",
            "updated_at",
        ]
    )

    call_command(
        "reconcile_regularization_checkout",
        subscription_id=subscription.id,
        verified_checkout_id="chk_verified",
        verified_checkout_url="https://sandbox.asaas.com/verified",
    )

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "CREATED"
    assert subscription.regularization_checkout_id == "chk_verified"
    assert subscription.regularization_checkout_url == "https://sandbox.asaas.com/verified"
    assert subscription.regularization_checkout_claim is None
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_REGULARIZATION_CHECKOUT_ATTACHED",
        target_id=str(subscription.id),
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "checkout_url",
    [
        "http://sandbox.asaas.com/checkout/chk_verified",
        "https://evil.example/checkout/chk_verified",
    ],
)
def test_reconciliation_command_rejects_non_allowlisted_checkout_url(
    subscription, checkout_url
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "RECONCILIATION_REQUIRED"
    subscription.regularization_checkout_reference = uuid4()
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_reference",
            "updated_at",
        ]
    )

    with pytest.raises(CommandError, match="URL de checkout"):
        call_command(
            "reconcile_regularization_checkout",
            subscription_id=subscription.id,
            verified_checkout_id="chk_verified",
            verified_checkout_url=checkout_url,
        )


@pytest.mark.django_db
def test_legacy_unknown_checkout_requires_explicit_attempt_reference_to_attach(
    subscription,
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "RECONCILIATION_REQUIRED"
    subscription.regularization_checkout_reference = None
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_reference",
            "updated_at",
        ]
    )

    with pytest.raises(CommandError, match="referência da tentativa"):
        call_command(
            "reconcile_regularization_checkout",
            subscription_id=subscription.id,
            verified_checkout_id="chk_legacy_verified",
            verified_checkout_url="https://sandbox.asaas.com/legacy-verified",
        )

    attempt_reference = uuid4()
    call_command(
        "reconcile_regularization_checkout",
        subscription_id=subscription.id,
        verified_checkout_id="chk_legacy_verified",
        verified_checkout_url="https://sandbox.asaas.com/legacy-verified",
        attempt_reference=str(attempt_reference),
    )

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_reference == attempt_reference
    audit_event = AuditEvent.objects.get(
        barbershop=subscription.barbershop,
        action="BILLING_REGULARIZATION_CHECKOUT_ATTACHED",
        target_id=str(subscription.id),
    )
    assert audit_event.metadata["attempt_reference"] == str(attempt_reference)


@pytest.mark.django_db
def test_reconciliation_command_resets_claim_only_with_explicit_confirmation(subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "RECONCILIATION_REQUIRED"
    subscription.regularization_checkout_claim = uuid4()
    subscription.regularization_checkout_error = "AsaasCheckoutError"
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_error",
            "updated_at",
        ]
    )

    call_command(
        "reconcile_regularization_checkout",
        subscription_id=subscription.id,
        reset_confirmed_no_active_checkout=True,
    )

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "READY"
    assert subscription.regularization_checkout_claim is None
    assert subscription.regularization_checkout_error == ""
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_REGULARIZATION_CLAIM_RESET",
        target_id=str(subscription.id),
    ).exists()


@pytest.mark.django_db
def test_reconciliation_command_rejects_fresh_creating_claim(subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "CREATING"
    subscription.regularization_checkout_claim = uuid4()
    subscription.regularization_checkout_claim_started_at = timezone.now()
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_claim_started_at",
            "updated_at",
        ]
    )

    with pytest.raises(CommandError, match="em criação recente"):
        call_command(
            "reconcile_regularization_checkout",
            subscription_id=subscription.id,
            reset_confirmed_no_active_checkout=True,
        )

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "CREATING"


@pytest.mark.django_db
def test_fresh_claim_provider_completion_survives_reconciliation_rejection(
    subscription, user
):
    from apps.billing.services import _persist_regularization_checkout

    claim = uuid4()
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "CREATING"
    subscription.regularization_checkout_claim = claim
    subscription.regularization_checkout_claim_started_at = timezone.now()
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_claim_started_at",
            "updated_at",
        ]
    )

    with pytest.raises(CommandError):
        call_command(
            "reconcile_regularization_checkout",
            subscription_id=subscription.id,
            reset_confirmed_no_active_checkout=True,
        )
    _persist_regularization_checkout(
        subscription.id,
        claim,
        CheckoutResult(id="chk_live", url="https://sandbox.asaas.com/live"),
    )

    subscription.refresh_from_db()
    assert subscription.regularization_checkout_state == "CREATED"
    assert subscription.regularization_checkout_id == "chk_live"


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
