import logging
from collections.abc import Mapping
from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit_services
from apps.barbershops.models import Barbershop, OperatingHour

from .models import Subscription
from .providers.asaas import cancel_checkout, create_recurring_checkout

logger = logging.getLogger(__name__)

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
    subscription.provider_checkout_id = checkout_id
    subscription.provider_subscription_id = provider_subscription_id
    subscription.status = Subscription.Status.TRIAL
    subscription.save(
        update_fields=[
            "provider_checkout_id",
            "provider_subscription_id",
            "status",
            "updated_at",
        ]
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


def activate_payment_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    was_restricted = subscription.status in {
        Subscription.Status.GRACE,
        Subscription.Status.SUSPENDED,
    }
    subscription.status = Subscription.Status.ACTIVE
    subscription.grace_ends_at = None
    subscription.suspended_at = None
    subscription.last_payment_status = payment_status
    subscription.last_payment_at = timezone.now()
    subscription.save(
        update_fields=[
            "status",
            "grace_ends_at",
            "suspended_at",
            "last_payment_status",
            "last_payment_at",
            "updated_at",
        ]
    )
    action = (
        "BILLING_SUBSCRIPTION_REACTIVATED"
        if was_restricted
        else "BILLING_PAYMENT_CONFIRMED"
    )
    _audit_transition(event, subscription, action, payment_id=payment_id)


def start_payment_grace_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    if (
        subscription.status != Subscription.Status.GRACE
        or subscription.grace_ends_at is None
    ):
        subscription.start_grace(timezone.now())
    subscription.last_payment_status = payment_status
    subscription.save(
        update_fields=[
            "status",
            "grace_ends_at",
            "last_payment_status",
            "updated_at",
        ]
    )
    _audit_transition(
        event,
        subscription,
        "BILLING_PAYMENT_FAILED",
        payment_id=payment_id,
    )


def suspend_chargeback_from_webhook(event):
    subscription, payment_id, payment_status = _locked_payment_subscription(event)
    subscription.status = Subscription.Status.SUSPENDED
    subscription.grace_ends_at = None
    subscription.suspended_at = timezone.now()
    subscription.last_payment_status = payment_status
    subscription.save(
        update_fields=[
            "status",
            "grace_ends_at",
            "suspended_at",
            "last_payment_status",
            "updated_at",
        ]
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
    subscription.status = Subscription.Status.CANCELED
    subscription.canceled_at = timezone.now()
    subscription.save(update_fields=["status", "canceled_at", "updated_at"])
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
