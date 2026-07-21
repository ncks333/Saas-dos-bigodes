from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.billing.models import (
    BillingNotificationLog,
    BillingWebhookEvent,
    Subscription,
)
from apps.billing.tasks import (
    process_billing_webhook,
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

    monkeypatch.setattr("apps.billing.tasks.send_mail", fail_once)
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
            },
            "subscription": {"id": "sub_notification_checkout"},
        },
    )
    queued = []
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

    assert queued == [(pending_subscription.id, "TRIAL_ACTIVATED")]


def test_lifecycle_sweep_has_hourly_beat_schedule(settings):
    assert settings.CELERY_BEAT_SCHEDULE["billing-lifecycle-sweep-hourly"] == {
        "task": "apps.billing.tasks.sweep_subscription_lifecycle",
        "schedule": 3600.0,
    }
