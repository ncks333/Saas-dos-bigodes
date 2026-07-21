import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.barbershops.models import Barbershop
from apps.billing.models import BillingNotificationLog, BillingWebhookEvent, Subscription


WEBHOOK_URL = "/api/v1/billing/webhooks/asaas/"
WEBHOOK_TOKEN = "valid-token"


@pytest.fixture(autouse=True)
def asaas_webhook_token(settings):
    settings.ASAAS_WEBHOOK_TOKEN = WEBHOOK_TOKEN


def post_webhook(client, payload, *, token=WEBHOOK_TOKEN):
    headers = {"HTTP_ASAAS_ACCESS_TOKEN": token} if token is not None else {}
    return client.post(
        WEBHOOK_URL,
        payload,
        content_type="application/json",
        **headers,
    )


def attach_provider_subscription(subscription, provider_id="sub_asaas_1"):
    subscription.provider_subscription_id = provider_id
    subscription.save(update_fields=["provider_subscription_id", "updated_at"])
    return subscription


@pytest.mark.django_db
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_webhook_rejects_missing_or_invalid_token(client, token):
    response = post_webhook(
        client,
        {"id": "evt_unauthorized", "event": "CHECKOUT_PAID"},
        token=token,
    )

    assert response.status_code == 401
    assert BillingWebhookEvent.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "evt_missing_event"},
        {"event": "CHECKOUT_PAID"},
        {"id": "", "event": "CHECKOUT_PAID"},
        {"id": "evt_empty_event", "event": ""},
        {"id": 123, "event": "CHECKOUT_PAID"},
        {"id": "evt_non_string_event", "event": ["CHECKOUT_PAID"]},
        {"id": "   ", "event": "CHECKOUT_PAID"},
        {"id": " evt_surrounded ", "event": "CHECKOUT_PAID"},
        {"id": "evt_control\n", "event": "CHECKOUT_PAID"},
        {"id": "evt_whitespace_event", "event": " CHECKOUT_PAID"},
        {"id": "evt_control_event", "event": "CHECKOUT\tPAID"},
    ],
)
def test_webhook_rejects_missing_or_invalid_id_and_event(client, payload):
    response = post_webhook(client, payload)

    assert response.status_code == 400
    assert BillingWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_webhook_rejects_malformed_json_without_persisting(client):
    response = client.post(
        WEBHOOK_URL,
        data='{"id": "evt_bad_json",',
        content_type="application/json",
        HTTP_ASAAS_ACCESS_TOKEN=WEBHOOK_TOKEN,
    )

    assert response.status_code == 400
    assert BillingWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_valid_duplicate_is_acknowledged_without_duplicate_processing(client):
    payload = {"id": "evt_duplicate", "event": "UNMAPPED_EVENT"}

    first = post_webhook(client, payload)
    second = post_webhook(client, payload)

    assert first.status_code == second.status_code == 202
    event = BillingWebhookEvent.objects.get(provider_event_id="evt_duplicate")
    assert event.processed_at is not None
    assert BillingWebhookEvent.objects.count() == 1


@pytest.mark.django_db
def test_checkout_paid_activates_tenant_users_exactly_once_without_enabling_shop(
    client, pending_subscription
):
    shop = pending_subscription.barbershop
    shop.active = False
    shop.save(update_fields=["active", "updated_at"])
    User.objects.create_user(
        username="pending-employee",
        email="pending-employee@example.com",
        password="Senha123",
        barbershop=shop,
        is_active=False,
    )
    payload = {
        "id": "evt_checkout_paid",
        "event": "CHECKOUT_PAID",
        "checkout": {
            "id": pending_subscription.provider_checkout_id,
            "externalReference": str(pending_subscription.external_reference),
        },
        "subscription": {"id": "sub_asaas_checkout"},
    }

    first = post_webhook(client, payload)
    second = post_webhook(client, payload)

    pending_subscription.refresh_from_db()
    shop.refresh_from_db()
    assert first.status_code == second.status_code == 202
    assert pending_subscription.status == Subscription.Status.TRIAL
    assert pending_subscription.provider_checkout_id == "chk_pending"
    assert pending_subscription.provider_subscription_id == "sub_asaas_checkout"
    assert not shop.users.filter(is_active=False).exists()
    assert shop.active is False
    assert BillingWebhookEvent.objects.filter(
        provider_event_id="evt_checkout_paid"
    ).count() == 1
    assert AuditEvent.objects.filter(
        barbershop=shop,
        action="BILLING_TRIAL_ACTIVATED",
        target_id=str(pending_subscription.id),
    ).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "starting_status", [Subscription.Status.SUSPENDED, Subscription.Status.CANCELED]
)
def test_regularization_checkout_paid_reactivates_blocked_subscription_once(
    client, subscription, user, starting_status
):
    previous_provider_subscription_id = "sub_old"
    attempt_reference = uuid.uuid4()
    subscription.status = starting_status
    subscription.provider_subscription_id = previous_provider_subscription_id
    subscription.regularization_checkout_id = "chk_regularization"
    subscription.regularization_checkout_url = "https://asaas.test/regularization"
    subscription.regularization_checkout_state = "CREATED"
    subscription.regularization_checkout_reference = attempt_reference
    subscription.suspended_at = timezone.now()
    subscription.suspension_reason = "GRACE_EXPIRED"
    subscription.canceled_at = timezone.now()
    subscription.save(
        update_fields=[
            "status",
            "provider_subscription_id",
            "regularization_checkout_id",
            "regularization_checkout_url",
            "regularization_checkout_state",
            "regularization_checkout_reference",
            "suspended_at",
            "suspension_reason",
            "canceled_at",
            "updated_at",
        ]
    )
    user.is_active = False
    user.save(update_fields=["is_active"])
    payload = {
        "id": f"evt_regularization_{starting_status.lower()}",
        "event": "CHECKOUT_PAID",
        "checkout": {
            "id": "chk_regularization",
            "externalReference": str(attempt_reference),
        },
        "subscription": {"id": "sub_regularized"},
    }

    first = post_webhook(client, payload)
    second = post_webhook(client, payload)

    subscription.refresh_from_db()
    user.refresh_from_db()
    assert first.status_code == second.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.provider_checkout_id == "chk_regularization"
    assert subscription.provider_subscription_id == "sub_regularized"
    assert subscription.regularization_checkout_state == "PAID"
    assert subscription.suspended_at is None
    assert subscription.canceled_at is None
    assert user.is_active is True
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "Senha123"},
    )
    assert login.status_code == 200
    assert BillingNotificationLog.objects.filter(
        subscription=subscription, kind="REACTIVATED", status="SENT"
    ).count() == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Assinatura reativada"
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_SUBSCRIPTION_REACTIVATED",
        target_id=str(subscription.id),
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_checkout_paid_recovers_matching_uncertain_regularization_checkout(
    client, subscription, user
):
    subscription.status = Subscription.Status.SUSPENDED
    attempt_reference = uuid.uuid4()
    subscription.regularization_checkout_state = "RECONCILIATION_REQUIRED"
    subscription.regularization_checkout_claim = uuid.uuid4()
    subscription.regularization_checkout_reference = attempt_reference
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_reference",
            "updated_at",
        ]
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = post_webhook(
        client,
        {
            "id": "evt_recover_uncertain_regularization",
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": "chk_recovered",
                "externalReference": str(attempt_reference),
            },
            "subscription": {"id": "sub_recovered"},
        },
    )

    subscription.refresh_from_db()
    user.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.regularization_checkout_state == "PAID"
    assert subscription.regularization_checkout_id == "chk_recovered"
    assert subscription.provider_subscription_id == "sub_recovered"
    assert user.is_active is True


@pytest.mark.django_db(transaction=True)
def test_unrelated_checkout_cannot_reactivate_persisted_regularization_checkout(
    client, subscription, user
):
    subscription.status = Subscription.Status.SUSPENDED
    attempt_reference = uuid.uuid4()
    subscription.regularization_checkout_state = "CREATED"
    subscription.regularization_checkout_id = "chk_expected"
    subscription.regularization_checkout_reference = attempt_reference
    subscription.regularization_checkout_url = "https://asaas.test/expected"
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_id",
            "regularization_checkout_reference",
            "regularization_checkout_url",
            "updated_at",
        ]
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = post_webhook(
        client,
        {
            "id": "evt_unrelated_regularization_checkout",
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": "chk_unrelated",
                "externalReference": str(subscription.external_reference),
            },
            "subscription": {"id": "sub_unrelated"},
        },
    )

    subscription.refresh_from_db()
    user.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.provider_subscription_id == ""
    assert user.is_active is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("checkout_id", "expected_status"),
    [
        ("chk_legacy", Subscription.Status.ACTIVE),
        ("chk_wrong", Subscription.Status.SUSPENDED),
    ],
)
def test_legacy_created_checkout_requires_its_static_reference_and_exact_id(
    client, subscription, user, checkout_id, expected_status
):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "CREATED"
    subscription.regularization_checkout_id = "chk_legacy"
    subscription.regularization_checkout_url = "https://asaas.test/legacy"
    subscription.regularization_checkout_reference = subscription.external_reference
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_id",
            "regularization_checkout_url",
            "regularization_checkout_reference",
            "updated_at",
        ]
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = post_webhook(
        client,
        {
            "id": f"evt_legacy_{checkout_id}",
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": checkout_id,
                "externalReference": str(subscription.external_reference),
            },
            "subscription": {"id": "sub_legacy"},
        },
    )

    subscription.refresh_from_db()
    user.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == expected_status
    assert user.is_active is (expected_status == Subscription.Status.ACTIVE)


@pytest.mark.django_db(transaction=True)
def test_legacy_attach_with_attempt_reference_allows_exact_webhook_recovery(
    client, subscription, user
):
    from django.core.management import call_command

    attempt_reference = uuid.uuid4()
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
    user.is_active = False
    user.save(update_fields=["is_active"])
    call_command(
        "reconcile_regularization_checkout",
        subscription_id=subscription.id,
        verified_checkout_id="chk_legacy_attached",
        verified_checkout_url="https://asaas.test/legacy-attached",
        attempt_reference=str(attempt_reference),
    )

    response = post_webhook(
        client,
        {
            "id": "evt_legacy_attached",
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": "chk_legacy_attached",
                "externalReference": str(attempt_reference),
            },
            "subscription": {"id": "sub_legacy_attached"},
        },
    )

    subscription.refresh_from_db()
    user.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.regularization_checkout_state == "PAID"
    assert user.is_active is True


@pytest.mark.django_db(transaction=True)
def test_old_attempt_checkout_cannot_reactivate_new_uncertain_attempt(
    client, subscription, user
):
    old_attempt_reference = uuid.uuid4()
    current_attempt_reference = uuid.uuid4()
    subscription.status = Subscription.Status.SUSPENDED
    subscription.regularization_checkout_state = "RECONCILIATION_REQUIRED"
    subscription.regularization_checkout_claim = uuid.uuid4()
    subscription.regularization_checkout_reference = current_attempt_reference
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_reference",
            "updated_at",
        ]
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = post_webhook(
        client,
        {
            "id": "evt_old_regularization_attempt",
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": "chk_old",
                "externalReference": str(old_attempt_reference),
            },
            "subscription": {"id": "sub_old"},
        },
    )

    subscription.refresh_from_db()
    user.refresh_from_db()
    event = BillingWebhookEvent.objects.get(
        provider_event_id="evt_old_regularization_attempt"
    )
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.regularization_checkout_state == "RECONCILIATION_REQUIRED"
    assert user.is_active is False
    assert event.processed_at is not None


@pytest.mark.django_db(transaction=True)
def test_distinct_regularization_reactivations_send_one_email_per_provider_event(
    client, subscription, user
):
    subscription.status = Subscription.Status.SUSPENDED
    first_attempt_reference = uuid.uuid4()
    second_attempt_reference = uuid.uuid4()
    subscription.regularization_checkout_state = "CREATED"
    subscription.regularization_checkout_id = "chk_reactivate_one"
    subscription.regularization_checkout_reference = first_attempt_reference
    subscription.regularization_checkout_url = "https://asaas.test/one"
    subscription.save(
        update_fields=[
            "status",
            "regularization_checkout_state",
            "regularization_checkout_id",
            "regularization_checkout_reference",
            "regularization_checkout_url",
            "updated_at",
        ]
    )
    for event_id, checkout_id, provider_subscription_id, attempt_reference in (
        (
            "evt_reactivate_one",
            "chk_reactivate_one",
            "sub_reactivate_one",
            first_attempt_reference,
        ),
        (
            "evt_reactivate_two",
            "chk_reactivate_two",
            "sub_reactivate_two",
            second_attempt_reference,
        ),
    ):
        response = post_webhook(
            client,
            {
                "id": event_id,
                "event": "CHECKOUT_PAID",
                "checkout": {
                    "id": checkout_id,
                    "externalReference": str(attempt_reference),
                },
                "subscription": {"id": provider_subscription_id},
            },
        )
        assert response.status_code == 202
        if event_id == "evt_reactivate_one":
            subscription.refresh_from_db()
            subscription.status = Subscription.Status.SUSPENDED
            subscription.regularization_checkout_state = "CREATED"
            subscription.regularization_checkout_id = "chk_reactivate_two"
            subscription.regularization_checkout_reference = second_attempt_reference
            subscription.regularization_checkout_url = "https://asaas.test/two"
            subscription.save(
                update_fields=[
                    "status",
                    "regularization_checkout_state",
                    "regularization_checkout_id",
                    "regularization_checkout_reference",
                    "regularization_checkout_url",
                    "updated_at",
                ]
            )

    assert BillingNotificationLog.objects.filter(
        subscription=subscription,
        kind="REACTIVATED",
        status="SENT",
    ).count() == 2
    assert len(mail.outbox) == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event_type", "payment_status"),
    [
        ("PAYMENT_CONFIRMED", "CONFIRMED"),
        ("PAYMENT_RECEIVED", "RECEIVED"),
    ],
)
def test_payment_success_activates_subscription(
    client, subscription, event_type, payment_status
):
    attach_provider_subscription(subscription)
    subscription.status = Subscription.Status.TRIAL
    subscription.save(update_fields=["status", "updated_at"])
    before = timezone.now()

    response = post_webhook(
        client,
        {
            "id": f"evt_{payment_status.lower()}",
            "event": event_type,
            "payment": {
                "id": f"pay_{payment_status.lower()}",
                "subscription": subscription.provider_subscription_id,
                "status": payment_status,
            },
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.last_payment_status == payment_status
    assert before <= subscription.last_payment_at <= timezone.now()
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_PAYMENT_CONFIRMED",
        target_id=str(subscription.id),
    ).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "starting_status", [Subscription.Status.GRACE, Subscription.Status.SUSPENDED]
)
def test_payment_success_reactivates_and_clears_restrictions(
    client, subscription, starting_status
):
    attach_provider_subscription(subscription)
    subscription.status = starting_status
    subscription.grace_ends_at = timezone.now() + timedelta(days=2)
    subscription.suspended_at = timezone.now() - timedelta(days=1)
    subscription.save(
        update_fields=[
            "status",
            "grace_ends_at",
            "suspended_at",
            "updated_at",
        ]
    )

    response = post_webhook(
        client,
        {
            "id": f"evt_reactivate_{starting_status.lower()}",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_reactivate",
                "subscription": subscription.provider_subscription_id,
                "status": "RECEIVED",
            },
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.grace_ends_at is None
    assert subscription.suspended_at is None
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_SUBSCRIPTION_REACTIVATED",
        target_id=str(subscription.id),
    ).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event_type", "payment_status"),
    [
        ("PAYMENT_OVERDUE", "OVERDUE"),
        ("PAYMENT_REPROVED_BY_RISK_ANALYSIS", "REPROVED_BY_RISK_ANALYSIS"),
    ],
)
def test_payment_failure_starts_exact_grace(
    client, subscription, event_type, payment_status
):
    attach_provider_subscription(subscription)
    before = timezone.now()

    response = post_webhook(
        client,
        {
            "id": f"evt_{payment_status.lower()}",
            "event": event_type,
            "payment": {
                "id": "pay_failed",
                "subscription": subscription.provider_subscription_id,
                "status": payment_status,
            },
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.GRACE
    assert subscription.last_payment_status == payment_status
    assert before + timedelta(days=7) <= subscription.grace_ends_at
    assert subscription.grace_ends_at <= timezone.now() + timedelta(days=7)


@pytest.mark.django_db
def test_repeated_overdue_events_preserve_first_grace_deadline(client, subscription):
    attach_provider_subscription(subscription)
    payment = {
        "id": "pay_overdue",
        "subscription": subscription.provider_subscription_id,
        "status": "OVERDUE",
    }

    first = post_webhook(
        client,
        {"id": "evt_overdue_first", "event": "PAYMENT_OVERDUE", "payment": payment},
    )
    subscription.refresh_from_db()
    first_deadline = subscription.grace_ends_at
    second = post_webhook(
        client,
        {"id": "evt_overdue_second", "event": "PAYMENT_OVERDUE", "payment": payment},
    )

    subscription.refresh_from_db()
    assert first.status_code == second.status_code == 202
    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_ends_at == first_deadline


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event_type",
    ["PAYMENT_CHARGEBACK_REQUESTED", "PAYMENT_CHARGEBACK_DISPUTE"],
)
def test_chargeback_suspends_subscription_immediately(
    client, subscription, event_type
):
    attach_provider_subscription(subscription)
    subscription.start_grace(timezone.now())
    subscription.save(update_fields=["status", "grace_ends_at", "updated_at"])

    response = post_webhook(
        client,
        {
            "id": f"evt_{event_type.lower()}",
            "event": event_type,
            "payment": {
                "id": "pay_chargeback",
                "subscription": subscription.provider_subscription_id,
                "status": "CHARGEBACK_REQUESTED",
            },
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.suspended_at is not None
    assert subscription.grace_ends_at is None
    assert AuditEvent.objects.filter(
        barbershop=subscription.barbershop,
        action="BILLING_SUBSCRIPTION_SUSPENDED",
        target_id=str(subscription.id),
    ).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event_type", ["SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"]
)
def test_subscription_cancellation_preserves_tenant_data(
    client, subscription, event_type
):
    attach_provider_subscription(subscription)
    shop_id = subscription.barbershop_id

    response = post_webhook(
        client,
        {
            "id": f"evt_{event_type.lower()}",
            "event": event_type,
            "subscription": {"id": subscription.provider_subscription_id},
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.CANCELED
    assert subscription.canceled_at is not None
    assert Barbershop.objects.filter(pk=shop_id).exists()
    assert AuditEvent.objects.filter(
        barbershop_id=shop_id,
        action="BILLING_SUBSCRIPTION_CANCELED",
        target_id=str(subscription.id),
    ).count() == 1


@pytest.mark.django_db
def test_unknown_event_is_safely_marked_processed(client, subscription):
    original_status = subscription.status

    response = post_webhook(
        client,
        {
            "id": "evt_unknown",
            "event": "PAYMENT_REFUNDED",
            "payment": {
                "id": "pay_unknown",
                "subscription": "sub_unknown",
                "status": "REFUNDED",
            },
        },
    )

    subscription.refresh_from_db()
    event = BillingWebhookEvent.objects.get(provider_event_id="evt_unknown")
    assert response.status_code == 202
    assert event.processed_at is not None
    assert event.processing_error == ""
    assert subscription.status == original_status
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_webhook_persists_only_sanitized_projection(client):
    secret_values = ["4111111111111111", "123", "api-secret", "card-token"]
    payload = {
        "id": "evt_sanitized",
        "event": "UNMAPPED_EVENT",
        "dateCreated": "2026-07-20T12:30:00Z",
        "checkout": {
            "id": "chk_safe",
            "externalReference": str(uuid.uuid4()),
            "creditCard": {"number": secret_values[0], "ccv": secret_values[1]},
        },
        "subscription": {"id": "sub_safe", "creditCardToken": secret_values[3]},
        "payment": {
            "id": "pay_safe",
            "subscription": "sub_safe",
            "status": "CONFIRMED",
            "value": 79.9,
            "creditCard": {"creditCardToken": secret_values[3]},
        },
        "asaas-access-token": secret_values[2],
        "arbitrary": {"raw": "must-not-be-stored"},
    }

    response = post_webhook(client, payload)

    event = BillingWebhookEvent.objects.get(provider_event_id="evt_sanitized")
    assert response.status_code == 202
    assert event.payload == {
        "dateCreated": "2026-07-20T12:30:00+00:00",
        "checkout": {
            "id": "chk_safe",
            "externalReference": payload["checkout"]["externalReference"],
        },
        "subscription": {"id": "sub_safe"},
        "payment": {
            "id": "pay_safe",
            "subscription": "sub_safe",
            "status": "CONFIRMED",
        },
    }
    serialized_projection = json.dumps(event.payload)
    assert all(secret not in serialized_projection for secret in secret_values)
    assert "must-not-be-stored" not in serialized_projection


@pytest.mark.django_db
def test_malformed_known_event_is_stored_safely_for_processor_retry(client):
    response = post_webhook(
        client,
        {
            "id": "evt_malformed_checkout",
            "event": "CHECKOUT_PAID",
            "checkout": ["not", "an", "object"],
            "subscription": "sub_not_an_object",
            "creditCard": {"number": "4111111111111111", "ccv": "123"},
        },
    )

    event = BillingWebhookEvent.objects.get(
        provider_event_id="evt_malformed_checkout"
    )
    assert response.status_code == 202
    assert event.payload == {}
    assert event.processed_at is None
    assert event.processing_error == "ValueError"


@pytest.mark.django_db
def test_processor_rolls_back_failure_and_can_retry(plan, monkeypatch):
    from apps.billing.tasks import process_billing_webhook

    external_reference = uuid.uuid4()
    event = BillingWebhookEvent.objects.create(
        provider="ASAAS",
        provider_event_id="evt_retry",
        event_type="CHECKOUT_PAID",
        payload={
            "checkout": {
                "id": "chk_retry",
                "externalReference": str(external_reference),
            },
            "subscription": {"id": "sub_retry"},
        },
    )
    shop = Barbershop.objects.create(name="Retry", slug="retry")
    user = User.objects.create_user(
        username="retry-admin",
        email="retry@example.com",
        password="Senha123",
        barbershop=shop,
        is_active=False,
    )
    subscription = Subscription.objects.create(
        barbershop=shop,
        plan=plan,
        status=Subscription.Status.PENDING_CHECKOUT,
        external_reference=external_reference,
    )
    original_record = __import__(
        "apps.audit.services", fromlist=["record_system_event"]
    ).record_system_event
    monkeypatch.setattr(
        "apps.audit.services.record_system_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("secret card 4111111111111111")
        ),
    )

    with pytest.raises(RuntimeError, match="secret card"):
        process_billing_webhook.run(event.id)

    event.refresh_from_db()
    subscription.refresh_from_db()
    user.refresh_from_db()
    assert event.processed_at is None
    assert event.processing_error == "RuntimeError"
    assert "secret" not in event.processing_error
    assert subscription.status == Subscription.Status.PENDING_CHECKOUT
    assert subscription.provider_subscription_id == ""
    assert user.is_active is False
    assert AuditEvent.objects.count() == 0

    monkeypatch.setattr("apps.audit.services.record_system_event", original_record)
    process_billing_webhook.run(event.id)

    event.refresh_from_db()
    subscription.refresh_from_db()
    user.refresh_from_db()
    assert event.processed_at is not None
    assert event.processing_error == ""
    assert subscription.status == Subscription.Status.TRIAL
    assert subscription.provider_subscription_id == "sub_retry"
    assert user.is_active is True
    assert AuditEvent.objects.filter(action="BILLING_TRIAL_ACTIVATED").count() == 1


@pytest.mark.django_db
def test_non_ascii_webhook_token_is_rejected_without_error(client):
    response = post_webhook(
        client,
        {"id": "evt_non_ascii_token", "event": "UNMAPPED_EVENT"},
        token="inválido",
    )

    assert response.status_code == 401
    assert BillingWebhookEvent.objects.count() == 0


@pytest.mark.django_db
def test_publish_failure_returns_503_and_redelivery_processes_same_row(
    client, pending_subscription, monkeypatch
):
    from apps.billing.tasks import process_billing_webhook

    payload = {
        "id": "evt_publish_recovery",
        "event": "CHECKOUT_PAID",
        "dateCreated": "2026-07-20T10:00:00Z",
        "checkout": {
            "id": pending_subscription.provider_checkout_id,
            "externalReference": str(pending_subscription.external_reference),
        },
        "subscription": {"id": "sub_publish_recovery"},
    }
    monkeypatch.setattr(
        "apps.billing.views.process_billing_webhook.delay",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("broker secret")),
    )

    first = post_webhook(client, payload)

    event = BillingWebhookEvent.objects.get(provider_event_id=payload["id"])
    assert first.status_code == 503
    assert event.processed_at is None
    assert event.processing_error == ""
    assert BillingWebhookEvent.objects.count() == 1

    monkeypatch.setattr(
        "apps.billing.views.process_billing_webhook.delay",
        lambda event_id: process_billing_webhook.run(event_id),
    )
    second = post_webhook(client, payload)

    event.refresh_from_db()
    pending_subscription.refresh_from_db()
    assert second.status_code == 202
    assert event.processed_at is not None
    assert BillingWebhookEvent.objects.count() == 1
    assert pending_subscription.status == Subscription.Status.TRIAL
    assert AuditEvent.objects.filter(action="BILLING_TRIAL_ACTIVATED").count() == 1


@pytest.mark.django_db
def test_processed_duplicate_does_not_republish(client, monkeypatch):
    payload = {"id": "evt_processed_duplicate", "event": "UNMAPPED_EVENT"}
    assert post_webhook(client, payload).status_code == 202

    monkeypatch.setattr(
        "apps.billing.views.process_billing_webhook.delay",
        lambda *_args: pytest.fail("processed duplicate must not republish"),
    )

    assert post_webhook(client, payload).status_code == 202


@pytest.mark.django_db
def test_recovery_task_redispatches_only_bounded_unprocessed_events(monkeypatch):
    from apps.billing.tasks import redispatch_unprocessed_billing_webhooks

    events = [
        BillingWebhookEvent.objects.create(
            provider="ASAAS",
            provider_event_id=f"evt_recovery_{index:03d}",
            event_type="UNMAPPED_EVENT",
            payload={},
        )
        for index in range(102)
    ]
    processed = events[0]
    processed.processed_at = timezone.now()
    processed.save(update_fields=["processed_at", "updated_at"])
    dispatched = []
    monkeypatch.setattr(
        "apps.billing.tasks.process_billing_webhook.delay", dispatched.append
    )

    count = redispatch_unprocessed_billing_webhooks.run()

    assert count == 100
    assert len(dispatched) == 100
    assert processed.id not in dispatched
    assert events[-1].id not in dispatched


def test_recovery_task_has_short_beat_schedule(settings):
    schedule = settings.CELERY_BEAT_SCHEDULE["billing-webhook-recovery-every-minute"]

    assert schedule == {
        "task": "apps.billing.tasks.redispatch_unprocessed_billing_webhooks",
        "schedule": 60.0,
    }


def payment_webhook_payload(
    event_id,
    event_type,
    subscription,
    payment_id,
    status,
    *,
    created_at=None,
):
    payload = {
        "id": event_id,
        "event": event_type,
        "payment": {
            "id": payment_id,
            "subscription": subscription.provider_subscription_id,
            "status": status,
        },
    }
    if created_at is not None:
        payload["dateCreated"] = created_at.isoformat().replace("+00:00", "Z")
    return payload


@pytest.mark.django_db
def test_canceled_subscription_ignores_delayed_overdue(client, subscription):
    attach_provider_subscription(subscription)
    newer = datetime(2026, 7, 20, 12, tzinfo=UTC)
    older = newer - timedelta(hours=1)
    cancel = {
        "id": "evt_cancel_terminal",
        "event": "SUBSCRIPTION_DELETED",
        "dateCreated": newer.isoformat().replace("+00:00", "Z"),
        "subscription": {"id": subscription.provider_subscription_id},
    }
    overdue = payment_webhook_payload(
        "evt_overdue_after_cancel",
        "PAYMENT_OVERDUE",
        subscription,
        "pay_canceled",
        "OVERDUE",
        created_at=older,
    )

    assert post_webhook(client, cancel).status_code == 202
    assert post_webhook(client, overdue).status_code == 202

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.CANCELED
    assert subscription.grace_ends_at is None


@pytest.mark.django_db
def test_chargeback_suspension_ignores_delayed_overdue(client, subscription):
    attach_provider_subscription(subscription)
    chargeback_at = datetime(2026, 7, 20, 12, tzinfo=UTC)

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_chargeback_before_overdue",
            "PAYMENT_CHARGEBACK_REQUESTED",
            subscription,
            "pay_chargeback_guard",
            "CHARGEBACK_REQUESTED",
            created_at=chargeback_at,
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_delayed_overdue_after_chargeback",
            "PAYMENT_OVERDUE",
            subscription,
            "pay_chargeback_guard",
            "OVERDUE",
            created_at=chargeback_at - timedelta(minutes=1),
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.suspension_reason == "CHARGEBACK"
    assert subscription.grace_ends_at is None


@pytest.mark.django_db
def test_chargeback_suspension_ignores_same_payment_success(client, subscription):
    attach_provider_subscription(subscription)
    chargeback_at = datetime(2026, 7, 20, 12, tzinfo=UTC)

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_chargeback_same_payment",
            "PAYMENT_CHARGEBACK_DISPUTE",
            subscription,
            "pay_same",
            "CHARGEBACK_DISPUTE",
            created_at=chargeback_at,
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_success_same_payment",
            "PAYMENT_RECEIVED",
            subscription,
            "pay_same",
            "RECEIVED",
            created_at=chargeback_at + timedelta(hours=1),
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.last_payment_id == "pay_same"
    assert subscription.suspension_reason == "CHARGEBACK"


@pytest.mark.django_db
def test_stale_provider_timestamp_is_ignored(client, subscription):
    attach_provider_subscription(subscription)
    newest = datetime(2026, 7, 20, 12, tzinfo=UTC)

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_newest_success",
            "PAYMENT_CONFIRMED",
            subscription,
            "pay_newest",
            "CONFIRMED",
            created_at=newest,
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_stale_overdue",
            "PAYMENT_OVERDUE",
            subscription,
            "pay_stale",
            "OVERDUE",
            created_at=newest - timedelta(hours=1),
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.last_payment_id == "pay_newest"
    assert subscription.last_provider_event_at == newest


@pytest.mark.django_db
def test_newer_different_payment_reactivates_chargeback_suspension(
    client, subscription
):
    attach_provider_subscription(subscription)
    chargeback_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    newer_success_at = chargeback_at + timedelta(days=1)

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_chargeback_old_cycle",
            "PAYMENT_CHARGEBACK_REQUESTED",
            subscription,
            "pay_old_cycle",
            "CHARGEBACK_REQUESTED",
            created_at=chargeback_at,
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_new_cycle_success",
            "PAYMENT_RECEIVED",
            subscription,
            "pay_new_cycle",
            "RECEIVED",
            created_at=newer_success_at,
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.last_payment_id == "pay_new_cycle"
    assert subscription.last_provider_event_at == newer_success_at
    assert subscription.suspension_reason == ""


@pytest.mark.django_db
def test_checkout_paid_only_activates_pending_checkout(client, subscription):
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["status", "updated_at"])

    response = post_webhook(
        client,
        {
            "id": "evt_late_checkout",
            "event": "CHECKOUT_PAID",
            "dateCreated": "2026-07-20T12:00:00Z",
            "checkout": {
                "id": "chk_late",
                "externalReference": str(subscription.external_reference),
            },
            "subscription": {"id": "sub_late"},
        },
    )

    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.provider_subscription_id == ""


@pytest.mark.django_db
def test_same_payment_cannot_start_second_grace_after_success(client, subscription):
    attach_provider_subscription(subscription)
    payment_id = "pay_cycle_one"
    overdue = payment_webhook_payload(
        "evt_cycle_one_overdue",
        "PAYMENT_OVERDUE",
        subscription,
        payment_id,
        "OVERDUE",
    )
    success = payment_webhook_payload(
        "evt_cycle_one_success",
        "PAYMENT_RECEIVED",
        subscription,
        payment_id,
        "RECEIVED",
    )
    delayed = payment_webhook_payload(
        "evt_cycle_one_delayed_overdue",
        "PAYMENT_OVERDUE",
        subscription,
        payment_id,
        "OVERDUE",
    )

    post_webhook(client, overdue)
    post_webhook(client, success)
    post_webhook(client, delayed)

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.grace_payment_id == payment_id
    assert subscription.last_payment_id == payment_id


@pytest.mark.django_db
def test_new_payment_cycle_can_start_fresh_exact_grace(
    client, subscription, monkeypatch
):
    attach_provider_subscription(subscription)
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_old_cycle_overdue",
            "PAYMENT_OVERDUE",
            subscription,
            "pay_old",
            "OVERDUE",
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_old_cycle_success",
            "PAYMENT_RECEIVED",
            subscription,
            "pay_old",
            "RECEIVED",
        ),
    )
    new_cycle_at = timezone.now() + timedelta(days=2)
    monkeypatch.setattr("apps.billing.services.timezone.now", lambda: new_cycle_at)

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_new_cycle_overdue",
            "PAYMENT_OVERDUE",
            subscription,
            "pay_new",
            "OVERDUE",
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_payment_id == "pay_new"
    assert subscription.last_payment_id == "pay_new"
    assert subscription.grace_ends_at == new_cycle_at + timedelta(days=7)


@pytest.mark.django_db
def test_chargeback_ignores_different_payment_success_without_provider_timestamp(
    client, subscription
):
    attach_provider_subscription(subscription)
    chargeback_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_chargeback_before_undated_success",
            "PAYMENT_CHARGEBACK_REQUESTED",
            subscription,
            "pay_chargeback_dated",
            "CHARGEBACK_REQUESTED",
            created_at=chargeback_at,
        ),
    )

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_undated_success_after_chargeback",
            "PAYMENT_RECEIVED",
            subscription,
            "pay_different_undated",
            "RECEIVED",
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.last_payment_id == "pay_chargeback_dated"
    assert subscription.last_provider_event_at == chargeback_at
    assert subscription.suspension_reason == "CHARGEBACK"


@pytest.mark.django_db
def test_chargeback_wins_over_different_payment_success_at_equal_timestamp(
    client, subscription
):
    attach_provider_subscription(subscription)
    tied_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_chargeback_before_tied_success",
            "PAYMENT_CHARGEBACK_DISPUTE",
            subscription,
            "pay_chargeback_tied",
            "CHARGEBACK_DISPUTE",
            created_at=tied_at,
        ),
    )

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_tied_success_after_chargeback",
            "PAYMENT_CONFIRMED",
            subscription,
            "pay_different_tied",
            "CONFIRMED",
            created_at=tied_at,
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.last_payment_id == "pay_chargeback_tied"
    assert subscription.last_provider_event_at == tied_at
    assert subscription.suspension_reason == "CHARGEBACK"


@pytest.mark.django_db
def test_historical_payment_cycle_cannot_reopen_grace_after_later_cycle_succeeds(
    client, subscription, monkeypatch
):
    from apps.billing.models import SubscriptionPaymentCycle

    attach_provider_subscription(subscription)
    for event_id, event_type, payment_id, payment_status in [
        ("evt_a_overdue", "PAYMENT_OVERDUE", "pay_a", "OVERDUE"),
        ("evt_a_success", "PAYMENT_RECEIVED", "pay_a", "RECEIVED"),
        ("evt_b_overdue", "PAYMENT_OVERDUE", "pay_b", "OVERDUE"),
        ("evt_b_success", "PAYMENT_RECEIVED", "pay_b", "RECEIVED"),
        ("evt_a_delayed_overdue", "PAYMENT_OVERDUE", "pay_a", "OVERDUE"),
    ]:
        post_webhook(
            client,
            payment_webhook_payload(
                event_id,
                event_type,
                subscription,
                payment_id,
                payment_status,
            ),
        )

    subscription.refresh_from_db()
    cycle_a = SubscriptionPaymentCycle.objects.get(
        subscription=subscription, provider_payment_id="pay_a"
    )
    cycle_b = SubscriptionPaymentCycle.objects.get(
        subscription=subscription, provider_payment_id="pay_b"
    )
    assert subscription.status == Subscription.Status.ACTIVE
    assert cycle_a.grace_started_at is not None
    assert cycle_a.succeeded_at is not None
    assert cycle_b.grace_started_at is not None
    assert cycle_b.succeeded_at is not None

    new_cycle_at = timezone.now() + timedelta(days=2)
    monkeypatch.setattr("apps.billing.services.timezone.now", lambda: new_cycle_at)
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_c_overdue",
            "PAYMENT_OVERDUE",
            subscription,
            "pay_c",
            "OVERDUE",
        ),
    )

    subscription.refresh_from_db()
    cycle_c = SubscriptionPaymentCycle.objects.get(
        subscription=subscription, provider_payment_id="pay_c"
    )
    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_ends_at == new_cycle_at + timedelta(days=7)
    assert cycle_c.grace_started_at == new_cycle_at
    assert cycle_c.succeeded_at is None


@pytest.mark.django_db
def test_payment_cycle_is_unique_per_subscription_and_provider_payment(subscription):
    from apps.billing.models import SubscriptionPaymentCycle

    cycle = SubscriptionPaymentCycle.objects.create(
        subscription=subscription,
        provider_payment_id="pay_unique",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        SubscriptionPaymentCycle.objects.create(
            subscription_id=cycle.subscription_id,
            provider_payment_id=cycle.provider_payment_id,
        )


def create_unprocessed_event(provider_event_id, **metadata):
    return BillingWebhookEvent.objects.create(
        provider="ASAAS",
        provider_event_id=provider_event_id,
        event_type="UNMAPPED_EVENT",
        payload={},
        **metadata,
    )


@pytest.mark.django_db
def test_recovery_backoff_does_not_starve_newer_eligible_events(monkeypatch):
    from apps.billing.tasks import redispatch_unprocessed_billing_webhooks

    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    for index in range(100):
        create_unprocessed_event(
            f"evt_backoff_{index:03d}",
            next_dispatch_at=now + timedelta(hours=1),
        )
    eligible = [
        create_unprocessed_event("evt_eligible_newer_1"),
        create_unprocessed_event("evt_eligible_newer_2"),
    ]
    dispatched = []
    monkeypatch.setattr("apps.billing.tasks.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.tasks.process_billing_webhook.delay", dispatched.append
    )

    count = redispatch_unprocessed_billing_webhooks.run()

    assert count == 2
    assert dispatched == [event.id for event in eligible]


@pytest.mark.django_db
def test_recovery_excludes_dead_lettered_events(monkeypatch):
    from apps.billing.tasks import redispatch_unprocessed_billing_webhooks

    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    dead_lettered = create_unprocessed_event(
        "evt_dead_lettered",
        dead_lettered_at=now - timedelta(minutes=1),
    )
    eligible = create_unprocessed_event("evt_after_dead_letter")
    dispatched = []
    monkeypatch.setattr("apps.billing.tasks.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.tasks.process_billing_webhook.delay", dispatched.append
    )

    count = redispatch_unprocessed_billing_webhooks.run()

    assert count == 1
    assert dispatched == [eligible.id]
    assert dead_lettered.id not in dispatched


@pytest.mark.django_db
def test_recovery_leases_dispatched_event_until_next_eligible_time(monkeypatch):
    from apps.billing.tasks import redispatch_unprocessed_billing_webhooks

    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    event = create_unprocessed_event("evt_dispatch_lease")
    dispatched = []
    monkeypatch.setattr("apps.billing.tasks.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.billing.tasks.process_billing_webhook.delay", dispatched.append
    )

    first_count = redispatch_unprocessed_billing_webhooks.run()
    second_count = redispatch_unprocessed_billing_webhooks.run()

    event.refresh_from_db()
    assert first_count == 1
    assert second_count == 0
    assert dispatched == [event.id]
    assert event.dispatch_attempts == 1
    assert event.last_dispatched_at == now
    assert event.next_dispatch_at > now


@pytest.mark.django_db
def test_repeated_processing_failure_backs_off_then_dead_letters():
    from apps.billing.tasks import (
        WEBHOOK_MAX_PROCESSING_ATTEMPTS,
        process_billing_webhook,
    )

    event = BillingWebhookEvent.objects.create(
        provider="ASAAS",
        provider_event_id="evt_bounded_poison",
        event_type="CHECKOUT_PAID",
        payload={},
    )
    retry_times = []
    for expected_attempt in range(1, WEBHOOK_MAX_PROCESSING_ATTEMPTS):
        with pytest.raises(ValueError):
            process_billing_webhook.run(event.id)
        event.refresh_from_db()
        assert event.processing_attempts == expected_attempt
        assert event.last_processing_attempt_at is not None
        assert event.next_dispatch_at > event.last_processing_attempt_at
        assert event.dead_lettered_at is None
        assert event.processing_error == "ValueError"
        retry_times.append(event.next_dispatch_at)

    process_billing_webhook.run(event.id)

    event.refresh_from_db()
    assert retry_times == sorted(retry_times)
    assert event.processing_attempts == WEBHOOK_MAX_PROCESSING_ATTEMPTS
    assert event.dead_lettered_at is not None
    assert event.next_dispatch_at is None
    assert event.processed_at is None
    assert event.processing_error == "ValueError"


@pytest.mark.django_db
def test_successful_processing_atomically_clears_retry_schedule():
    from apps.billing.tasks import process_billing_webhook

    now = timezone.now()
    event = BillingWebhookEvent.objects.create(
        provider="ASAAS",
        provider_event_id="evt_success_after_retry",
        event_type="UNMAPPED_EVENT",
        payload={},
        processing_attempts=2,
        processing_error="ValueError",
        last_processing_attempt_at=now - timedelta(minutes=1),
        next_dispatch_at=now + timedelta(minutes=1),
    )

    process_billing_webhook.run(event.id)

    event.refresh_from_db()
    assert event.processed_at is not None
    assert event.processing_error == ""
    assert event.next_dispatch_at is None
    assert event.dead_lettered_at is None


def test_webhook_recovery_has_eligibility_index():
    index_fields = {tuple(index.fields) for index in BillingWebhookEvent._meta.indexes}

    assert (
        "processed_at",
        "dead_lettered_at",
        "next_dispatch_at",
        "id",
    ) in index_fields


@pytest.mark.django_db
def test_duplicate_during_dispatch_lease_does_not_enqueue_or_increment_attempts(
    client, monkeypatch
):
    lease_ends_at = timezone.now() + timedelta(minutes=5)
    event = create_unprocessed_event(
        "evt_duplicate_active_lease",
        dispatch_attempts=1,
        last_dispatched_at=timezone.now(),
        next_dispatch_at=lease_ends_at,
    )
    dispatched = []
    monkeypatch.setattr(
        "apps.billing.views.process_billing_webhook.delay", dispatched.append
    )

    response = post_webhook(
        client,
        {"id": event.provider_event_id, "event": event.event_type},
    )

    event.refresh_from_db()
    assert response.status_code == 202
    assert dispatched == []
    assert event.dispatch_attempts == 1
    assert event.next_dispatch_at == lease_ends_at


@pytest.mark.django_db
def test_duplicate_during_processing_backoff_does_not_enqueue_or_consume_attempt(
    client, monkeypatch
):
    retry_at = timezone.now() + timedelta(minutes=4)
    event = create_unprocessed_event(
        "evt_duplicate_processing_backoff",
        dispatch_attempts=2,
        processing_attempts=2,
        processing_error="ValueError",
        last_processing_attempt_at=timezone.now(),
        next_dispatch_at=retry_at,
    )
    dispatched = []
    monkeypatch.setattr(
        "apps.billing.views.process_billing_webhook.delay", dispatched.append
    )

    response = post_webhook(
        client,
        {"id": event.provider_event_id, "event": event.event_type},
    )

    event.refresh_from_db()
    assert response.status_code == 202
    assert dispatched == []
    assert event.dispatch_attempts == 2
    assert event.processing_attempts == 2
    assert event.next_dispatch_at == retry_at


@pytest.mark.django_db
def test_undated_chargeback_clears_known_chronology_and_blocks_dated_reactivation(
    client, subscription
):
    attach_provider_subscription(subscription)
    prior_payment_at = datetime(2026, 7, 20, 10, tzinfo=UTC)
    later_success_at = prior_payment_at + timedelta(hours=2)
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_prior_dated_payment",
            "PAYMENT_RECEIVED",
            subscription,
            "pay_prior_dated",
            "RECEIVED",
            created_at=prior_payment_at,
        ),
    )
    post_webhook(
        client,
        payment_webhook_payload(
            "evt_undated_chargeback",
            "PAYMENT_CHARGEBACK_REQUESTED",
            subscription,
            "pay_undated_chargeback",
            "CHARGEBACK_REQUESTED",
        ),
    )

    post_webhook(
        client,
        payment_webhook_payload(
            "evt_dated_success_after_undated_chargeback",
            "PAYMENT_CONFIRMED",
            subscription,
            "pay_later_different",
            "CONFIRMED",
            created_at=later_success_at,
        ),
    )

    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.suspension_reason == "CHARGEBACK"
    assert subscription.last_payment_id == "pay_undated_chargeback"
    assert subscription.last_provider_event_at is None
