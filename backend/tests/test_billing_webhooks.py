import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.barbershops.models import Barbershop
from apps.billing.models import BillingWebhookEvent, Subscription


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
