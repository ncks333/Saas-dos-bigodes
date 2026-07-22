from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.billing.models import (
    BillingNotificationLog,
    BillingWebhookEvent,
    Subscription,
)
from apps.billing.tasks import (
    process_billing_webhook,
    recover_billing_notification_emails,
    send_billing_email,
    sweep_subscription_lifecycle,
)


@pytest.mark.django_db
def test_billing_email_is_idempotent_and_reaches_inactive_admin(
    subscription, user, settings
):
    user.is_active = False
    user.save(update_fields=["is_active"])
    settings.FRONTEND_URL = "https://app.example.com"

    send_billing_email(subscription.id, "TRIAL_ACTIVATED")
    send_billing_email(subscription.id, "TRIAL_ACTIVATED")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    assert subscription.barbershop.name in mail.outbox[0].body
    assert "79,90" in mail.outbox[0].body
    assert (
        BillingNotificationLog.objects.filter(
            subscription=subscription,
            kind="TRIAL_ACTIVATED",
            status="SENT",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_failed_billing_email_can_retry_without_marking_first_attempt_sent(
    subscription, user, monkeypatch
):
    def fail_once(*_args, **_kwargs):
        raise RuntimeError("Resend unavailable")

    monkeypatch.setattr("apps.billing.tasks.EmailMultiAlternatives.send", fail_once)
    with pytest.raises(RuntimeError, match="Resend unavailable"):
        send_billing_email(subscription.id, "PAYMENT_FAILED")

    notification = BillingNotificationLog.objects.get(
        subscription=subscription,
        kind="PAYMENT_FAILED",
    )
    assert notification.status == "FAILED"
    assert notification.sent_at is None

    monkeypatch.undo()
    send_billing_email(subscription.id, "PAYMENT_FAILED")

    notification.refresh_from_db()
    assert len(mail.outbox) == 1
    assert "https://localhost:5173/regularizar" in mail.outbox[0].body
    assert notification.status == "SENT"
    assert notification.sent_at is not None


@pytest.mark.django_db(transaction=True)
def test_billing_retry_reuses_stable_resend_idempotency_key(
    subscription, user, monkeypatch
):
    keys = []

    def fail_then_send(message, **_kwargs):
        keys.append(message.extra_headers["Idempotency-Key"])
        if len(keys) == 1:
            raise RuntimeError("Resend unavailable")
        return 1

    monkeypatch.setattr(
        "apps.billing.tasks.EmailMultiAlternatives.send",
        fail_then_send,
    )
    with pytest.raises(RuntimeError, match="Resend unavailable"):
        send_billing_email(subscription.id, "PAYMENT_FAILED")

    notification = BillingNotificationLog.objects.get(
        subscription=subscription,
        kind="PAYMENT_FAILED",
    )
    assert recover_billing_notification_emails.run() == 1
    assert keys == [
        f"billing-notification-{notification.id}",
        f"billing-notification-{notification.id}",
    ]


@pytest.mark.django_db(transaction=True)
@override_settings(
    EMAIL_BACKEND="core.email_backends.ResendEmailBackend",
    RESEND_API_KEY="resend-test-key",
    DEFAULT_FROM_EMAIL="billing@example.com",
)
def test_billing_recovery_reuses_immutable_resend_payload_snapshot(
    subscription, user, monkeypatch
):
    payloads = []

    def fail_then_send(url, *, json, headers, timeout):
        payloads.append(
            {
                "url": url,
                "json": {**json, "to": list(json["to"])},
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if len(payloads) == 1:
            raise requests.Timeout("Ambiguous Resend result")
        return Mock()

    monkeypatch.setattr(
        "core.email_backends.requests.post",
        fail_then_send,
    )
    with pytest.raises(requests.Timeout, match="Ambiguous Resend result"):
        send_billing_email(subscription.id, "PAYMENT_FAILED")

    notification = BillingNotificationLog.objects.get(
        subscription=subscription,
        kind="PAYMENT_FAILED",
    )
    original_snapshot = notification.email_snapshot
    user.email = "changed-admin@example.com"
    user.save(update_fields=["email"])
    subscription.plan.name = "Plano alterado"
    subscription.plan.amount = Decimal("199.90")
    subscription.plan.save(update_fields=["name", "amount", "updated_at"])
    subscription.status = Subscription.Status.SUSPENDED
    subscription.trial_ends_at = timezone.now() + timedelta(days=90)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])

    with override_settings(DEFAULT_FROM_EMAIL="changed-sender@example.com"):
        assert recover_billing_notification_emails.run() == 1

    notification.refresh_from_db()
    assert notification.email_snapshot == original_snapshot
    assert payloads == [payloads[0], payloads[0]]
    assert payloads[0]["json"]["to"] == ["admin@example.com"]
    assert payloads[0]["json"]["from"] == "billing@example.com"
    assert payloads[0]["headers"]["Idempotency-Key"] == (
        f"billing-notification-{notification.id}"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("days", "kind"),
    [
        (7, "TRIAL_ENDS_7D"),
        (3, "TRIAL_ENDS_3D"),
        (1, "TRIAL_ENDS_1D"),
    ],
)
def test_trial_warning_sends_once_inside_its_exact_hour_window(
    subscription, user, days, kind
):
    subscription.status = Subscription.Status.TRIAL
    subscription.trial_ends_at = timezone.now() + timedelta(days=days, minutes=30)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])

    sweep_subscription_lifecycle()
    sweep_subscription_lifecycle()

    assert len(mail.outbox) == 1
    assert (
        BillingNotificationLog.objects.filter(
            subscription=subscription,
            kind=kind,
            status="SENT",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_expired_grace_suspends_without_deleting_data_or_disabling_barbershop(
    subscription, user
):
    subscription.status = Subscription.Status.GRACE
    subscription.grace_ends_at = timezone.now() - timedelta(minutes=1)
    subscription.save(update_fields=["status", "grace_ends_at", "updated_at"])
    barbershop = subscription.barbershop
    barbershop.active = True
    barbershop.save(update_fields=["active", "updated_at"])

    sweep_subscription_lifecycle()

    subscription.refresh_from_db()
    barbershop.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.barbershop_id == barbershop.id
    assert barbershop.active is True
    assert (
        BillingNotificationLog.objects.filter(
            subscription=subscription,
            kind="SUSPENDED",
            status="SENT",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_grace_suspension_email_is_deduped_per_payment_cycle(subscription, user):
    for payment_id in ("pay_grace_cycle_one", "pay_grace_cycle_two"):
        subscription.status = Subscription.Status.GRACE
        subscription.grace_payment_id = payment_id
        subscription.grace_ends_at = timezone.now() - timedelta(minutes=1)
        subscription.suspended_at = None
        subscription.suspension_reason = ""
        subscription.save(
            update_fields=[
                "status",
                "grace_payment_id",
                "grace_ends_at",
                "suspended_at",
                "suspension_reason",
                "updated_at",
            ]
        )

        sweep_subscription_lifecycle()
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.SUSPENDED

    notifications = BillingNotificationLog.objects.filter(
        subscription=subscription,
        kind="SUSPENDED",
        status="SENT",
    ).order_by("id")
    assert list(notifications.values_list("dedupe_key", flat=True)) == [
        "grace:pay_grace_cycle_one",
        "grace:pay_grace_cycle_two",
    ]
    assert len(mail.outbox) == 2


@pytest.mark.django_db(transaction=True)
def test_webhook_email_enqueues_only_after_successful_transaction(
    pending_subscription, monkeypatch
):
    event = BillingWebhookEvent.objects.create(
        provider=Subscription.Provider.ASAAS,
        provider_event_id="evt_notification_checkout",
        event_type="CHECKOUT_PAID",
        payload={
            "checkout": {
                "id": pending_subscription.provider_checkout_id,
                "externalReference": str(pending_subscription.external_reference),
                "status": "PAID",
            },
            "subscription": {"id": "sub_notification_checkout"},
        },
    )
    queued = []
    monkeypatch.setattr(
        "apps.billing.services.reconcile_paid_checkout",
        lambda checkout_id, external_reference: SimpleNamespace(
            checkout_id=checkout_id,
            external_reference=external_reference,
            provider_subscription_id="sub_notification_checkout",
        ),
    )
    monkeypatch.setattr(
        "apps.billing.tasks.send_billing_email.delay",
        lambda *args: queued.append(args),
    )
    original_save = BillingWebhookEvent.save
    should_fail = True

    def fail_processed_event_save(instance, *args, **kwargs):
        nonlocal should_fail
        if (
            instance.pk == event.pk
            and instance.processed_at is not None
            and should_fail
        ):
            should_fail = False
            raise RuntimeError("rollback webhook")
        return original_save(instance, *args, **kwargs)

    monkeypatch.setattr(BillingWebhookEvent, "save", fail_processed_event_save)
    with pytest.raises(RuntimeError, match="rollback webhook"):
        process_billing_webhook.run(event.id)

    assert queued == []
    assert not BillingNotificationLog.objects.filter(
        subscription=pending_subscription
    ).exists()

    process_billing_webhook.run(event.id)

    assert queued == [
        (pending_subscription.id, "TRIAL_ACTIVATED", "evt_notification_checkout")
    ]


def test_lifecycle_sweep_has_hourly_beat_schedule(settings):
    assert settings.CELERY_BEAT_SCHEDULE["billing-lifecycle-sweep-hourly"] == {
        "task": "apps.billing.tasks.sweep_subscription_lifecycle",
        "schedule": 3600.0,
    }


@pytest.mark.django_db(transaction=True)
def test_periodic_recovery_retries_failed_billing_email(subscription, user):
    BillingNotificationLog.objects.create(
        subscription=subscription,
        kind="PAYMENT_FAILED",
        status="FAILED",
    )

    assert recover_billing_notification_emails.run() == 1

    notification = BillingNotificationLog.objects.get(
        subscription=subscription,
        kind="PAYMENT_FAILED",
    )
    assert len(mail.outbox) == 1
    assert notification.status == "SENT"


@pytest.mark.django_db
def test_recovery_does_not_steal_fresh_sending_claim(subscription, user, monkeypatch):
    notification = BillingNotificationLog.objects.create(
        subscription=subscription,
        kind="PAYMENT_FAILED",
        status="SENDING",
        claim_token=uuid4(),
    )
    queued = []
    monkeypatch.setattr(
        "apps.billing.tasks.send_billing_email.delay",
        lambda *args: queued.append(args),
    )

    assert recover_billing_notification_emails.run() == 0
    assert send_billing_email(subscription.id, "PAYMENT_FAILED") is False

    notification.refresh_from_db()
    assert notification.status == "SENDING"
    assert queued == []
    assert mail.outbox == []


@pytest.mark.django_db
def test_recovery_releases_stale_sending_claim_and_keeps_retry_idempotent(
    subscription, user, monkeypatch
):
    notification = BillingNotificationLog.objects.create(
        subscription=subscription,
        kind="PAYMENT_FAILED",
        status="SENDING",
        claim_token=uuid4(),
    )
    BillingNotificationLog.objects.filter(pk=notification.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )
    queued = []
    monkeypatch.setattr(
        "apps.billing.tasks.send_billing_email.delay",
        lambda *args: queued.append(args),
    )

    assert recover_billing_notification_emails.run() == 1

    notification.refresh_from_db()
    assert notification.status == "PENDING"
    assert notification.claim_token is None
    assert queued == [(subscription.id, "PAYMENT_FAILED")]

    monkeypatch.undo()
    assert send_billing_email(subscription.id, "PAYMENT_FAILED") is True
    assert send_billing_email(subscription.id, "PAYMENT_FAILED") is False
    assert len(mail.outbox) == 1


def test_billing_notification_recovery_beat_coexists_with_other_billing_schedules(
    settings,
):
    assert settings.CELERY_BEAT_SCHEDULE[
        "billing-notification-recovery-every-minute"
    ] == {
        "task": "apps.billing.tasks.recover_billing_notification_emails",
        "schedule": 60.0,
    }
    assert settings.CELERY_BEAT_SCHEDULE["billing-webhook-recovery-every-minute"] == {
        "task": "apps.billing.tasks.redispatch_unprocessed_billing_webhooks",
        "schedule": 60.0,
    }
