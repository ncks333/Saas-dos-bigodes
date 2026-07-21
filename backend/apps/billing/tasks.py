from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import BillingWebhookEvent
from .services import (
    activate_checkout_from_webhook,
    activate_payment_from_webhook,
    cancel_subscription_from_webhook,
    start_payment_grace_from_webhook,
    suspend_chargeback_from_webhook,
)


PAYMENT_SUCCESS_EVENTS = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
PAYMENT_FAILURE_EVENTS = {
    "PAYMENT_OVERDUE",
    "PAYMENT_REPROVED_BY_RISK_ANALYSIS",
}
IMMEDIATE_SUSPENSION_EVENTS = {
    "PAYMENT_CHARGEBACK_REQUESTED",
    "PAYMENT_CHARGEBACK_DISPUTE",
}
CANCEL_EVENTS = {"SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"}
WEBHOOK_RECOVERY_BATCH_SIZE = 100
WEBHOOK_DISPATCH_LEASE = timedelta(minutes=5)
WEBHOOK_RETRY_BASE_SECONDS = 60
WEBHOOK_MAX_PROCESSING_ATTEMPTS = 5


def _apply_transition(event):
    if event.event_type == "CHECKOUT_PAID":
        activate_checkout_from_webhook(event)
    elif event.event_type in PAYMENT_SUCCESS_EVENTS:
        activate_payment_from_webhook(event)
    elif event.event_type in PAYMENT_FAILURE_EVENTS:
        start_payment_grace_from_webhook(event)
    elif event.event_type in IMMEDIATE_SUSPENSION_EVENTS:
        suspend_chargeback_from_webhook(event)
    elif event.event_type in CANCEL_EVENTS:
        cancel_subscription_from_webhook(event)


def prepare_billing_webhook_dispatch(event_id, *, force=False, now=None):
    dispatch_at = now or timezone.now()
    with transaction.atomic():
        event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
        if event.processed_at is not None or event.dead_lettered_at is not None:
            return False
        if (
            not force
            and event.next_dispatch_at is not None
            and event.next_dispatch_at > dispatch_at
        ):
            return False
        event.dispatch_attempts += 1
        event.last_dispatched_at = dispatch_at
        event.next_dispatch_at = dispatch_at + WEBHOOK_DISPATCH_LEASE
        event.save(
            update_fields=[
                "dispatch_attempts",
                "last_dispatched_at",
                "next_dispatch_at",
                "updated_at",
            ]
        )
    return True


def release_billing_webhook_dispatch(event_id):
    with transaction.atomic():
        event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
        if event.processed_at is not None or event.dead_lettered_at is not None:
            return
        event.next_dispatch_at = timezone.now()
        event.save(update_fields=["next_dispatch_at", "updated_at"])


def _record_processing_failure(event_id, exc):
    with transaction.atomic():
        event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
        if event.processed_at is not None or event.dead_lettered_at is not None:
            return True
        failed_at = timezone.now()
        event.processing_attempts += 1
        event.last_processing_attempt_at = failed_at
        event.processing_error = exc.__class__.__name__[:300]
        if event.processing_attempts >= WEBHOOK_MAX_PROCESSING_ATTEMPTS:
            event.dead_lettered_at = failed_at
            event.next_dispatch_at = None
        else:
            backoff_seconds = WEBHOOK_RETRY_BASE_SECONDS * 2 ** (
                event.processing_attempts - 1
            )
            event.next_dispatch_at = failed_at + timedelta(seconds=backoff_seconds)
        event.save(
            update_fields=[
                "processing_attempts",
                "last_processing_attempt_at",
                "processing_error",
                "dead_lettered_at",
                "next_dispatch_at",
                "updated_at",
            ]
        )
        return event.dead_lettered_at is not None


@shared_task
def process_billing_webhook(event_id):
    try:
        with transaction.atomic():
            event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
            if event.processed_at is not None or event.dead_lettered_at is not None:
                return
            processed_at = timezone.now()
            event.processing_attempts += 1
            event.last_processing_attempt_at = processed_at
            _apply_transition(event)
            event.processed_at = processed_at
            event.processing_error = ""
            event.next_dispatch_at = None
            event.save(
                update_fields=[
                    "processing_attempts",
                    "last_processing_attempt_at",
                    "processed_at",
                    "processing_error",
                    "next_dispatch_at",
                    "updated_at",
                ]
            )
    except Exception as exc:
        if not _record_processing_failure(event_id, exc):
            raise


@shared_task
def redispatch_unprocessed_billing_webhooks():
    now = timezone.now()
    event_ids = list(
        BillingWebhookEvent.objects.filter(
            Q(next_dispatch_at__isnull=True) | Q(next_dispatch_at__lte=now),
            processed_at__isnull=True,
            dead_lettered_at__isnull=True,
        )
        .order_by("id")
        .values_list("id", flat=True)[:WEBHOOK_RECOVERY_BATCH_SIZE]
    )
    dispatched_count = 0
    for event_id in event_ids:
        if not prepare_billing_webhook_dispatch(event_id, now=now):
            continue
        try:
            process_billing_webhook.delay(event_id)
        except Exception:
            release_billing_webhook_dispatch(event_id)
            continue
        dispatched_count += 1
    return dispatched_count
