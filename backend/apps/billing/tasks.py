from celery import shared_task
from django.db import transaction
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


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_billing_webhook(event_id):
    try:
        with transaction.atomic():
            event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
            if event.processed_at is not None:
                return
            _apply_transition(event)
            event.processed_at = timezone.now()
            event.processing_error = ""
            event.save(
                update_fields=["processed_at", "processing_error", "updated_at"]
            )
    except Exception as exc:
        BillingWebhookEvent.objects.filter(
            pk=event_id,
            processed_at__isnull=True,
        ).update(
            processing_error=exc.__class__.__name__[:300],
            updated_at=timezone.now(),
        )
        raise


@shared_task
def redispatch_unprocessed_billing_webhooks():
    event_ids = list(
        BillingWebhookEvent.objects.filter(processed_at__isnull=True)
        .order_by("id")
        .values_list("id", flat=True)[:WEBHOOK_RECOVERY_BATCH_SIZE]
    )
    for event_id in event_ids:
        process_billing_webhook.delay(event_id)
    return len(event_ids)
