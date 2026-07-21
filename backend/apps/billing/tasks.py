from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User

from .models import BillingNotificationLog, BillingWebhookEvent, Subscription
from .services import (
    activate_checkout_from_webhook,
    activate_payment_from_webhook,
    cancel_subscription_from_webhook,
    make_regularization_token,
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
LIFECYCLE_SWEEP_WINDOW = timedelta(hours=1)
NOTIFICATION_RECOVERY_BATCH_SIZE = 100
NOTIFICATION_SENDING_LEASE = timedelta(minutes=5)
BILLING_IDEMPOTENCY_KEY_PREFIX = "billing-notification-"
MAX_RESEND_IDEMPOTENCY_KEY_LENGTH = 256

BILLING_EMAIL_TEMPLATES = {
    "TRIAL_ACTIVATED": (
        "Seu período de teste foi ativado",
        "Seu período de teste está ativo.",
        False,
    ),
    "TRIAL_ENDS_7D": (
        "Seu período de teste termina em 7 dias",
        "Faltam 7 dias para o fim do período de teste.",
        True,
    ),
    "TRIAL_ENDS_3D": (
        "Seu período de teste termina em 3 dias",
        "Faltam 3 dias para o fim do período de teste.",
        True,
    ),
    "TRIAL_ENDS_1D": (
        "Seu período de teste termina amanhã",
        "Seu período de teste termina em 1 dia.",
        True,
    ),
    "PAYMENT_RECEIVED": (
        "Pagamento recebido",
        "Recebemos seu pagamento e sua assinatura segue ativa.",
        False,
    ),
    "PAYMENT_FAILED": (
        "Pagamento não confirmado",
        "Não confirmamos seu pagamento. Regularize para evitar suspensão.",
        True,
    ),
    "SUSPENDED": (
        "Assinatura suspensa",
        "Sua assinatura está suspensa. Regularize para recuperar acesso.",
        True,
    ),
    "REACTIVATED": (
        "Assinatura reativada",
        "Pagamento confirmado. Sua assinatura foi reativada.",
        False,
    ),
    "CANCELED": ("Assinatura cancelada", "Sua assinatura foi cancelada.", True),
}


@shared_task
def send_regularization_request_email(normalized_email):
    user = (
        User.objects.filter(email__iexact=normalized_email, role=User.Role.ADMIN)
        .select_related("barbershop")
        .first()
    )
    if user is None or user.barbershop_id is None:
        return False
    subscription = Subscription.objects.filter(barbershop_id=user.barbershop_id).first()
    if subscription is None or subscription.allows_access:
        return False
    token = make_regularization_token(subscription)
    regularization_url = f"{settings.FRONTEND_URL.rstrip('/')}/regularizar?token={token}"
    send_mail(
        "Regularização de assinatura",
        "Use este link para regularizar sua assinatura:\n\n" f"{regularization_url}",
        None,
        [user.email],
    )
    return True


def _event_subscription(event):
    if event.event_type == "CHECKOUT_PAID":
        external_reference = event.payload.get("checkout", {}).get("externalReference")
        if not external_reference:
            return None
        return Subscription.objects.filter(
            external_reference=external_reference,
            provider=Subscription.Provider.ASAAS,
        ).first()
    if (
        event.event_type
        in PAYMENT_SUCCESS_EVENTS | PAYMENT_FAILURE_EVENTS | IMMEDIATE_SUSPENSION_EVENTS
    ):
        provider_subscription_id = event.payload.get("payment", {}).get("subscription")
    elif event.event_type in CANCEL_EVENTS:
        provider_subscription_id = event.payload.get("subscription", {}).get("id")
    else:
        return None
    if not provider_subscription_id:
        return None
    return Subscription.objects.filter(
        provider=Subscription.Provider.ASAAS,
        provider_subscription_id=provider_subscription_id,
    ).first()


def _apply_transition(event):
    subscription = _event_subscription(event)
    prior_status = subscription.status if subscription is not None else None
    if event.event_type == "CHECKOUT_PAID":
        activate_checkout_from_webhook(event)
        if subscription is not None:
            subscription.refresh_from_db()
            if (
                prior_status == Subscription.Status.PENDING_CHECKOUT
                and subscription.status == Subscription.Status.TRIAL
            ):
                return "TRIAL_ACTIVATED"
            if (
                prior_status
                in {Subscription.Status.SUSPENDED, Subscription.Status.CANCELED}
                and subscription.status == Subscription.Status.ACTIVE
                and subscription.provider_checkout_id
                == event.payload.get("checkout", {}).get("id")
                and subscription.regularization_checkout_state
                == Subscription.RegularizationCheckoutState.PAID
            ):
                return "REACTIVATED"
    elif event.event_type in PAYMENT_SUCCESS_EVENTS:
        activate_payment_from_webhook(event)
        if subscription is not None:
            payment_id = event.payload.get("payment", {}).get("id")
            subscription.refresh_from_db()
            if (
                subscription.status == Subscription.Status.ACTIVE
                and subscription.last_payment_id == payment_id
            ):
                if prior_status in {
                    Subscription.Status.GRACE,
                    Subscription.Status.SUSPENDED,
                }:
                    return "REACTIVATED"
                return "PAYMENT_RECEIVED"
    elif event.event_type in PAYMENT_FAILURE_EVENTS:
        start_payment_grace_from_webhook(event)
        if subscription is not None:
            payment_id = event.payload.get("payment", {}).get("id")
            subscription.refresh_from_db()
            if (
                prior_status != Subscription.Status.GRACE
                and subscription.status == Subscription.Status.GRACE
                and subscription.grace_payment_id == payment_id
            ):
                return "PAYMENT_FAILED"
    elif event.event_type in IMMEDIATE_SUSPENSION_EVENTS:
        suspend_chargeback_from_webhook(event)
        if subscription is not None:
            subscription.refresh_from_db()
            if (
                prior_status != Subscription.Status.SUSPENDED
                and subscription.status == Subscription.Status.SUSPENDED
                and subscription.suspension_reason == "CHARGEBACK"
            ):
                return "SUSPENDED"
    elif event.event_type in CANCEL_EVENTS:
        cancel_subscription_from_webhook(event)
        if subscription is not None:
            subscription.refresh_from_db()
            if (
                prior_status != Subscription.Status.CANCELED
                and subscription.status == Subscription.Status.CANCELED
            ):
                return "CANCELED"
    return None


def _regularization_url():
    frontend_url = urlsplit(settings.FRONTEND_URL)
    return urlunsplit(
        (
            "https",
            frontend_url.netloc,
            f"{frontend_url.path.rstrip('/')}/regularizar",
            "",
            "",
        )
    )


def _billing_email_content(subscription, kind):
    subject, message, includes_regularization_url = BILLING_EMAIL_TEMPLATES[kind]
    due_at = (
        subscription.trial_ends_at
        or subscription.grace_ends_at
        or subscription.next_billing_at
        or subscription.current_period_ends_at
    )
    due_date = (
        timezone.localtime(due_at).strftime("%d/%m/%Y %H:%M")
        if due_at
        else "Não informada"
    )
    amount = Decimal(subscription.plan.amount).quantize(Decimal("0.01"))
    lines = [
        message,
        "",
        f"Barbearia: {subscription.barbershop.name}",
        f"Plano: {subscription.plan.name}",
        f"Valor: R$ {amount:.2f}".replace(".", ","),
        f"Status: {subscription.get_status_display()}",
        f"Vencimento: {due_date}",
    ]
    if includes_regularization_url:
        lines.extend(["", f"Regularize em: {_regularization_url()}"])
    return subject, "\n".join(lines)


def _billing_idempotency_key(notification_id):
    key = f"{BILLING_IDEMPOTENCY_KEY_PREFIX}{notification_id}"
    if len(key) > MAX_RESEND_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError("Billing idempotency key exceeds Resend limit")
    return key


def _billing_email_snapshot(notification_id, claim_token):
    with transaction.atomic():
        notification = BillingNotificationLog.objects.select_for_update().get(
            pk=notification_id
        )
        if (
            notification.status != "SENDING"
            or notification.claim_token != claim_token
        ):
            return None
        if notification.email_snapshot is None:
            subscription = Subscription.objects.select_related("barbershop", "plan").get(
                pk=notification.subscription_id
            )
            recipients = list(
                User.objects.filter(
                    barbershop_id=subscription.barbershop_id,
                    role=User.Role.ADMIN,
                )
                .exclude(email="")
                .order_by("id")
                .values_list("email", flat=True)
            )
            if not recipients:
                raise RuntimeError("Billing subscription has no admin email recipient")
            subject, body = _billing_email_content(subscription, notification.kind)
            notification.email_snapshot = {
                "to": recipients,
                "from": settings.DEFAULT_FROM_EMAIL,
                "subject": subject,
                "body": body,
            }
            notification.save(update_fields=["email_snapshot", "updated_at"])
        return notification.email_snapshot


def _notification_log(subscription_id, kind, dedupe_key=""):
    notification = BillingNotificationLog.objects.filter(
        subscription_id=subscription_id,
        kind=kind,
        dedupe_key=dedupe_key,
    ).first()
    if notification is not None:
        return notification
    try:
        with transaction.atomic():
            return BillingNotificationLog.objects.create(
                subscription_id=subscription_id,
                kind=kind,
                dedupe_key=dedupe_key,
            )
    except IntegrityError:
        return BillingNotificationLog.objects.get(
            subscription_id=subscription_id,
            kind=kind,
            dedupe_key=dedupe_key,
        )


def _enqueue_billing_email_after_commit(subscription_id, kind, dedupe_key=""):
    notification = _notification_log(subscription_id, kind, dedupe_key)
    if notification.status == "SENT":
        return
    if dedupe_key:
        transaction.on_commit(
            lambda: send_billing_email.delay(subscription_id, kind, dedupe_key)
        )
    else:
        transaction.on_commit(lambda: send_billing_email.delay(subscription_id, kind))


@shared_task
def send_billing_email(subscription_id, kind, dedupe_key=""):
    if kind not in BILLING_EMAIL_TEMPLATES:
        raise ValueError(f"Unknown billing email kind: {kind}")
    notification = _notification_log(subscription_id, kind, dedupe_key)
    claim_token = uuid4()
    claimed = BillingNotificationLog.objects.filter(
        pk=notification.pk,
        status__in=("PENDING", "FAILED"),
    ).update(
        status="SENDING",
        claim_token=claim_token,
        sent_at=None,
        updated_at=timezone.now(),
    )
    if not claimed:
        return False
    try:
        snapshot = _billing_email_snapshot(notification.pk, claim_token)
        if snapshot is None:
            return False
        message = EmailMultiAlternatives(
            snapshot["subject"],
            snapshot["body"],
            snapshot["from"],
            snapshot["to"],
            headers={"Idempotency-Key": _billing_idempotency_key(notification.pk)},
        )
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("Billing email backend did not confirm delivery")
    except Exception:
        BillingNotificationLog.objects.filter(
            pk=notification.pk,
            status="SENDING",
            claim_token=claim_token,
        ).update(
            status="FAILED",
            claim_token=None,
            updated_at=timezone.now(),
        )
        raise
    BillingNotificationLog.objects.filter(
        pk=notification.pk,
        status="SENDING",
        claim_token=claim_token,
    ).update(
        status="SENT",
        claim_token=None,
        sent_at=timezone.now(),
        updated_at=timezone.now(),
    )
    return True


def prepare_billing_webhook_dispatch(event_id, *, now=None):
    dispatch_at = now or timezone.now()
    with transaction.atomic():
        event = BillingWebhookEvent.objects.select_for_update().get(pk=event_id)
        if event.processed_at is not None or event.dead_lettered_at is not None:
            return False
        if (
            event.next_dispatch_at is not None
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
            notification_kind = _apply_transition(event)
            if notification_kind is not None:
                _enqueue_billing_email_after_commit(
                    _event_subscription(event).id,
                    notification_kind,
                    event.provider_event_id,
                )
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


def _prepare_billing_notification_recovery(notification_id, *, now):
    with transaction.atomic():
        notification = BillingNotificationLog.objects.select_for_update().get(
            pk=notification_id
        )
        if notification.status == "SENT":
            return None
        if notification.status == "SENDING":
            if notification.updated_at > now - NOTIFICATION_SENDING_LEASE:
                return None
            notification.status = "PENDING"
            notification.claim_token = None
            notification.save(
                update_fields=["status", "claim_token", "updated_at"]
            )
        elif notification.status not in {"PENDING", "FAILED"}:
            return None
        return notification.subscription_id, notification.kind, notification.dedupe_key


@shared_task
def recover_billing_notification_emails():
    now = timezone.now()
    notification_ids = list(
        BillingNotificationLog.objects.filter(
            Q(status__in=("PENDING", "FAILED"))
            | Q(
                status="SENDING",
                updated_at__lte=now - NOTIFICATION_SENDING_LEASE,
            )
        )
        .order_by("id")
        .values_list("id", flat=True)[:NOTIFICATION_RECOVERY_BATCH_SIZE]
    )
    dispatched_count = 0
    for notification_id in notification_ids:
        dispatch = _prepare_billing_notification_recovery(notification_id, now=now)
        if dispatch is None:
            continue
        try:
            if dispatch[2]:
                send_billing_email.delay(*dispatch)
            else:
                send_billing_email.delay(*dispatch[:2])
        except Exception:
            continue
        dispatched_count += 1
    return dispatched_count


@shared_task
def sweep_subscription_lifecycle():
    now = timezone.now()
    queued_count = 0
    with transaction.atomic():
        for days, kind in (
            (7, "TRIAL_ENDS_7D"),
            (3, "TRIAL_ENDS_3D"),
            (1, "TRIAL_ENDS_1D"),
        ):
            window_start = now + timedelta(days=days)
            window_end = window_start + LIFECYCLE_SWEEP_WINDOW
            subscription_ids = Subscription.objects.filter(
                status=Subscription.Status.TRIAL,
                trial_ends_at__gte=window_start,
                trial_ends_at__lt=window_end,
            ).values_list("id", flat=True)
            for subscription_id in subscription_ids:
                _enqueue_billing_email_after_commit(subscription_id, kind)
                queued_count += 1

        expired_subscriptions = Subscription.objects.select_for_update().filter(
            status=Subscription.Status.GRACE,
            grace_ends_at__lte=now,
        )
        for subscription in expired_subscriptions:
            subscription.status = Subscription.Status.SUSPENDED
            subscription.grace_ends_at = None
            subscription.suspended_at = now
            subscription.suspension_reason = "GRACE_EXPIRED"
            subscription.save(
                update_fields=[
                    "status",
                    "grace_ends_at",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            _enqueue_billing_email_after_commit(subscription.id, "SUSPENDED")
            queued_count += 1
    return queued_count
