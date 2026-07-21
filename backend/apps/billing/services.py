import logging
from collections.abc import Mapping
from datetime import UTC, time, timedelta

from django.core.signing import TimestampSigner
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.audit import services as audit_services
from apps.barbershops.models import Barbershop, OperatingHour

from .models import Subscription, SubscriptionPaymentCycle
from .providers.asaas import (
    cancel_checkout,
    create_recurring_checkout,
    create_regularization_checkout,
)

logger = logging.getLogger(__name__)

REGULARIZATION_TOKEN_SALT = "billing-regularization"
REGULARIZATION_TOKEN_MAX_AGE = 60 * 60

SAFE_WEBHOOK_FIELDS = {
    "checkout": {
        "id": 100,
        "externalReference": 36,
    },
    "subscription": {"id": 100},
    "payment": {
        "id": 100,
        "subscription": 100,
        "status": 50,
        "dateCreated": 64,
        "paymentDate": 64,
        "confirmedDate": 64,
        "clientPaymentDate": 64,
        "dueDate": 64,
    },
}


def sanitize_asaas_webhook_payload(payload):
    """Return only scalar provider fields needed to reconcile transitions."""
    if not isinstance(payload, Mapping):
        return {}

    projection = {}
    date_created = payload.get("dateCreated")
    if isinstance(date_created, str) and len(date_created) <= 64:
        parsed_date_created = parse_datetime(date_created)
        if parsed_date_created is not None and timezone.is_aware(parsed_date_created):
            projection["dateCreated"] = parsed_date_created.astimezone(UTC).isoformat()
    for object_name, safe_fields in SAFE_WEBHOOK_FIELDS.items():
        provider_object = payload.get(object_name)
        if not isinstance(provider_object, Mapping):
            continue
        safe_object = {
            field: value
            for field, max_length in safe_fields.items()
            if isinstance((value := provider_object.get(field)), str)
            and value
            and len(value) <= max_length
        }
        if safe_object:
            projection[object_name] = safe_object
    return projection


def _required_provider_value(event, object_name, field):
    provider_object = event.payload.get(object_name)
    if not isinstance(provider_object, dict):
        raise ValueError(f"Missing {object_name} object")
    value = provider_object.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing {object_name}.{field}")
    return value


def _audit_transition(event, subscription, action, *, payment_id=None):
    metadata = {
        "provider": Subscription.Provider.ASAAS,
        "provider_event_id": event.provider_event_id,
    }
    if payment_id:
        metadata["provider_payment_id"] = payment_id
    audit_services.record_system_event(
        subscription.barbershop_id,
        action,
        target=subscription,
        metadata=metadata,
    )


def _provider_event_at(event):
    value = event.payload.get("dateCreated")
    if not isinstance(value, str):
        return None
    parsed = parse_datetime(value)
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed


def _is_stale_provider_event(subscription, event_at):
    return (
        event_at is not None
        and subscription.last_provider_event_at is not None
        and event_at < subscription.last_provider_event_at
    )


def _save_transition(subscription, update_fields, event_at):
    if event_at is not None:
        subscription.last_provider_event_at = event_at
        update_fields.append("last_provider_event_at")
    update_fields.append("updated_at")
    subscription.save(update_fields=update_fields)


def activate_checkout_from_webhook(event):
    external_reference = _required_provider_value(
        event, "checkout", "externalReference"
    )
    checkout_id = _required_provider_value(event, "checkout", "id")
    provider_subscription_id = _required_provider_value(event, "subscription", "id")
    subscription = Subscription.objects.select_for_update().get(
        external_reference=external_reference,
        provider=Subscription.Provider.ASAAS,
    )
    event_at = _provider_event_at(event)
    if (
        subscription.status != Subscription.Status.PENDING_CHECKOUT
        or _is_stale_provider_event(subscription, event_at)
    ):
        return
    subscription.provider_checkout_id = checkout_id
    subscription.provider_subscription_id = provider_subscription_id
    subscription.status = Subscription.Status.TRIAL
    _save_transition(
        subscription,
        [
            "provider_checkout_id",
            "provider_subscription_id",
            "status",
        ],
        event_at,
    )
    User.objects.filter(
        barbershop_id=subscription.barbershop_id,
        is_active=False,
    ).update(is_active=True)
    _audit_transition(event, subscription, "BILLING_TRIAL_ACTIVATED")


def _locked_payment_subscription(event):
    payment_id = _required_provider_value(event, "payment", "id")
    provider_subscription_id = _required_provider_value(
        event, "payment", "subscription"
    )
    payment_status = _required_provider_value(event, "payment", "status")
    subscription = Subscription.objects.select_for_update().get(
        provider=Subscription.Provider.ASAAS,
        provider_subscription_id=provider_subscription_id,
    )
    return subscription, payment_id, payment_status


def _locked_payment_cycle(subscription, payment_id):
    return SubscriptionPaymentCycle.objects.select_for_update().get_or_create(
        subscription=subscription,
        provider_payment_id=payment_id,
    )[0]


def activate_payment_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    event_at = _provider_event_at(event)
    if subscription.status == Subscription.Status.CANCELED or _is_stale_provider_event(
        subscription, event_at
    ):
        return
    if (
        subscription.status == Subscription.Status.SUSPENDED
        and subscription.suspension_reason == "CHARGEBACK"
    ):
        if (
            subscription.last_payment_id == payment_id
            or event_at is None
            or subscription.last_provider_event_at is None
            or event_at <= subscription.last_provider_event_at
        ):
            return
    payment_cycle = _locked_payment_cycle(subscription, payment_id)
    if payment_cycle.succeeded_at is None:
        payment_cycle.succeeded_at = event_at or timezone.now()
        payment_cycle.save(update_fields=["succeeded_at", "updated_at"])
    was_restricted = subscription.status in {
        Subscription.Status.GRACE,
        Subscription.Status.SUSPENDED,
    }
    subscription.status = Subscription.Status.ACTIVE
    subscription.grace_ends_at = None
    subscription.suspended_at = None
    subscription.suspension_reason = ""
    subscription.last_payment_id = payment_id
    subscription.last_payment_status = payment_status
    subscription.last_payment_at = event_at or timezone.now()
    _save_transition(
        subscription,
        [
            "status",
            "grace_ends_at",
            "suspended_at",
            "suspension_reason",
            "last_payment_id",
            "last_payment_status",
            "last_payment_at",
        ],
        event_at,
    )
    action = (
        "BILLING_SUBSCRIPTION_REACTIVATED"
        if was_restricted
        else "BILLING_PAYMENT_CONFIRMED"
    )
    _audit_transition(event, subscription, action, payment_id=payment_id)


def start_payment_grace_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    event_at = _provider_event_at(event)
    if (
        subscription.status == Subscription.Status.CANCELED
        or _is_stale_provider_event(subscription, event_at)
        or (
            subscription.status == Subscription.Status.SUSPENDED
            and subscription.suspension_reason == "CHARGEBACK"
        )
    ):
        return
    payment_cycle = _locked_payment_cycle(subscription, payment_id)
    if payment_cycle.grace_started_at is not None or payment_cycle.succeeded_at is not None:
        return
    grace_started_at = timezone.now()
    payment_cycle.grace_started_at = grace_started_at
    payment_cycle.save(update_fields=["grace_started_at", "updated_at"])
    subscription.status = Subscription.Status.GRACE
    subscription.grace_ends_at = grace_started_at + timedelta(days=7)
    subscription.last_payment_id = payment_id
    subscription.grace_payment_id = payment_id
    subscription.last_payment_status = payment_status
    _save_transition(
        subscription,
        [
            "status",
            "grace_ends_at",
            "last_payment_id",
            "grace_payment_id",
            "last_payment_status",
        ],
        event_at,
    )
    _audit_transition(
        event,
        subscription,
        "BILLING_PAYMENT_FAILED",
        payment_id=payment_id,
    )


def suspend_chargeback_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    event_at = _provider_event_at(event)
    if subscription.status == Subscription.Status.CANCELED or _is_stale_provider_event(
        subscription, event_at
    ):
        return
    subscription.status = Subscription.Status.SUSPENDED
    subscription.grace_ends_at = None
    subscription.suspended_at = event_at or timezone.now()
    subscription.suspension_reason = "CHARGEBACK"
    subscription.last_payment_id = payment_id
    subscription.last_payment_status = payment_status
    update_fields = [
        "status",
        "grace_ends_at",
        "suspended_at",
        "suspension_reason",
        "last_payment_id",
        "last_payment_status",
    ]
    if event_at is None:
        subscription.last_provider_event_at = None
        update_fields.append("last_provider_event_at")
    _save_transition(
        subscription,
        update_fields,
        event_at,
    )
    _audit_transition(
        event,
        subscription,
        "BILLING_SUBSCRIPTION_SUSPENDED",
        payment_id=payment_id,
    )


def cancel_subscription_from_webhook(event):
    provider_subscription_id = _required_provider_value(event, "subscription", "id")
    subscription = Subscription.objects.select_for_update().get(
        provider=Subscription.Provider.ASAAS,
        provider_subscription_id=provider_subscription_id,
    )
    event_at = _provider_event_at(event)
    if subscription.status == Subscription.Status.CANCELED or _is_stale_provider_event(
        subscription, event_at
    ):
        return
    subscription.status = Subscription.Status.CANCELED
    subscription.grace_ends_at = None
    subscription.suspended_at = None
    subscription.suspension_reason = ""
    subscription.canceled_at = event_at or timezone.now()
    _save_transition(
        subscription,
        [
            "status",
            "grace_ends_at",
            "suspended_at",
            "suspension_reason",
            "canceled_at",
        ],
        event_at,
    )
    _audit_transition(event, subscription, "BILLING_SUBSCRIPTION_CANCELED")


def provision_signup(data, plan, *, request=None):
    checkout = None
    try:
        with transaction.atomic():
            barbershop = Barbershop.objects.create(
                name=data["barbershop_name"],
                slug=data["slug"],
                whatsapp=data["whatsapp"],
            )
            for weekday in range(6):
                OperatingHour.objects.create(
                    barbershop=barbershop,
                    weekday=weekday,
                    opens_at=time(8),
                    closes_at=time(18),
                )
            user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                password=data["password"],
                first_name=data["first_name"],
                barbershop=barbershop,
                role=User.Role.ADMIN,
                is_active=False,
            )
            trial_ends_at = timezone.now() + timedelta(days=plan.trial_days)
            subscription = Subscription.objects.create(
                barbershop=barbershop,
                plan=plan,
                trial_days=plan.trial_days,
                trial_ends_at=trial_ends_at,
                next_billing_at=trial_ends_at + timedelta(days=1),
            )
            audit_services.record_event(
                user,
                "BILLING_SIGNUP_CREATED",
                target=subscription,
                request=request,
            )
            checkout = create_recurring_checkout(subscription, user)
            subscription.provider_checkout_id = checkout.id
            subscription.save(update_fields=["provider_checkout_id", "updated_at"])
        return subscription, checkout
    except Exception:
        if checkout is not None:
            try:
                cancel_checkout(checkout.id)
            except Exception:
                logger.warning("Checkout compensation failed after local signup error")
        raise


def make_regularization_token(subscription):
    return TimestampSigner(salt=REGULARIZATION_TOKEN_SALT).sign(
        str(subscription.external_reference)
    )


def regularization_subscription_from_token(token):
    external_reference = TimestampSigner(salt=REGULARIZATION_TOKEN_SALT).unsign(
        token,
        max_age=REGULARIZATION_TOKEN_MAX_AGE,
    )
    return (
        Subscription.objects.select_related("barbershop", "plan")
        .filter(external_reference=external_reference)
        .first()
    )


def provision_regularization_checkout(subscription):
    with transaction.atomic():
        subscription = (
            Subscription.objects.select_for_update()
            .select_related("barbershop", "plan")
            .get(pk=subscription.pk)
        )
        if subscription.allows_access:
            return None
        admin = (
            User.objects.filter(
                barbershop_id=subscription.barbershop_id,
                role=User.Role.ADMIN,
            )
            .order_by("id")
            .first()
        )
        if admin is None:
            raise ValueError("Assinatura sem administrador para regularização.")
        checkout = create_regularization_checkout(subscription, admin)
        subscription.provider_checkout_id = checkout.id
        subscription.save(update_fields=["provider_checkout_id", "updated_at"])
    return checkout
