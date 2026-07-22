import hashlib
import hmac
import logging
import time as time_module
from collections.abc import Mapping
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.signing import TimestampSigner
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.audit import services as audit_services
from apps.barbershops.models import Barbershop, OperatingHour

from .models import (
    RegularizationEmailRequest,
    Subscription,
    SubscriptionPaymentCycle,
)
from .providers.asaas import (
    AsaasCheckoutError,
    AsaasCheckoutNotCreatedError,
    AsaasCheckoutOutcomeUnknownError,
    CheckoutResult,
    cancel_checkout,
    create_recurring_checkout,
    create_regularization_checkout,
    reconcile_paid_checkout,
    validate_checkout_url,
)

logger = logging.getLogger(__name__)

REGULARIZATION_TOKEN_SALT = "billing-regularization"
REGULARIZATION_TOKEN_MAX_AGE = 60 * 60
REGULARIZATION_CHECKOUT_WAIT_SECONDS = 12
REGULARIZATION_CHECKOUT_POLL_SECONDS = 0.05
REGULARIZATION_CLAIM_STALE_AFTER = timedelta(minutes=5)
REGULARIZATION_EMAIL_REQUEST_TTL = timedelta(hours=24)

SAFE_WEBHOOK_FIELDS = {
    "checkout": {
        "id": 100,
        "externalReference": 36,
        "status": 50,
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
        parsed_date_created = _normalize_provider_datetime(date_created)
        if parsed_date_created is not None:
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


def _normalize_provider_datetime(value):
    parsed = parse_datetime(value)
    if parsed is not None and timezone.is_aware(parsed):
        return parsed
    try:
        local_datetime = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return local_datetime.replace(tzinfo=ZoneInfo(settings.ASAAS_PROVIDER_TIMEZONE))


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


def checkout_subscription_from_webhook(event, *, lock=False):
    checkout = event.payload.get("checkout")
    if not isinstance(checkout, dict):
        return None
    checkout_id = checkout.get("id")
    if not isinstance(checkout_id, str) or not checkout_id:
        return None
    subscriptions = Subscription.objects.filter(
        Q(provider_checkout_id=checkout_id)
        | Q(regularization_checkout_id=checkout_id),
        provider=Subscription.Provider.ASAAS,
    ).order_by("id")
    if lock:
        subscriptions = subscriptions.select_for_update()
    matches = list(subscriptions[:2])
    if len(matches) > 1:
        raise ValueError("Checkout Asaas possui correlação local ambígua")
    return matches[0] if matches else None


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
    checkout_id = _required_provider_value(event, "checkout", "id")
    checkout_status = _required_provider_value(event, "checkout", "status")
    if checkout_status != "PAID":
        raise ValueError("CHECKOUT_PAID sem status PAID")
    subscription = checkout_subscription_from_webhook(event, lock=True)
    if subscription is None:
        return
    event_at = _provider_event_at(event)
    if _is_stale_provider_event(subscription, event_at):
        return

    external_reference = _expected_checkout_reference(subscription, checkout_id)
    if external_reference is None:
        return
    event_external_reference = event.payload.get("checkout", {}).get(
        "externalReference"
    )
    if (
        event_external_reference is not None
        and event_external_reference != external_reference
    ):
        raise ValueError("Referência do evento não corresponde ao checkout local")

    reconciliation = reconcile_paid_checkout(checkout_id, external_reference)
    if (
        reconciliation.checkout_id != checkout_id
        or reconciliation.external_reference != external_reference
    ):
        raise ValueError("Reconciliação Asaas não corresponde ao checkout local")
    provider_subscription_id = reconciliation.provider_subscription_id
    event_provider_subscription_id = event.payload.get("subscription", {}).get("id")
    if (
        event_provider_subscription_id is not None
        and event_provider_subscription_id != provider_subscription_id
    ):
        raise ValueError("Assinatura do evento diverge da reconciliação Asaas")

    if subscription.status == Subscription.Status.PENDING_CHECKOUT:
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
        _activate_subscription_owner(subscription)
        _audit_transition(event, subscription, "BILLING_TRIAL_ACTIVATED")
        return

    if (
        subscription.status not in {
            Subscription.Status.SUSPENDED,
            Subscription.Status.CANCELED,
        }
        or not _matches_regularization_checkout(
            subscription,
            checkout_id,
            external_reference,
        )
    ):
        return

    subscription.provider_checkout_id = checkout_id
    subscription.provider_subscription_id = provider_subscription_id
    subscription.regularization_checkout_state = (
        Subscription.RegularizationCheckoutState.PAID
    )
    subscription.regularization_checkout_claim = None
    subscription.regularization_checkout_claim_started_at = None
    subscription.regularization_checkout_id = checkout_id
    subscription.regularization_checkout_error = ""
    subscription.status = Subscription.Status.ACTIVE
    subscription.grace_ends_at = None
    subscription.suspended_at = None
    subscription.suspension_reason = ""
    subscription.canceled_at = None
    _save_transition(
        subscription,
        [
            "provider_checkout_id",
            "provider_subscription_id",
            "regularization_checkout_state",
            "regularization_checkout_claim",
            "regularization_checkout_claim_started_at",
            "regularization_checkout_id",
            "regularization_checkout_error",
            "status",
            "grace_ends_at",
            "suspended_at",
            "suspension_reason",
            "canceled_at",
        ],
        event_at,
    )
    _activate_subscription_owner(subscription)
    _audit_transition(event, subscription, "BILLING_SUBSCRIPTION_REACTIVATED")


def _activate_subscription_owner(subscription):
    owner = (
        User.objects.filter(
            barbershop_id=subscription.barbershop_id,
            role=User.Role.ADMIN,
        )
        .order_by("id")
        .first()
    )
    if owner is not None and not owner.is_active:
        User.objects.filter(pk=owner.pk, is_active=False).update(is_active=True)


def _expected_checkout_reference(subscription, checkout_id):
    if (
        subscription.status == Subscription.Status.PENDING_CHECKOUT
        and subscription.provider_checkout_id == checkout_id
    ):
        return str(subscription.external_reference)
    if (
        subscription.status
        in {Subscription.Status.SUSPENDED, Subscription.Status.CANCELED}
        and subscription.regularization_checkout_state
        == Subscription.RegularizationCheckoutState.CREATED
        and subscription.regularization_checkout_id == checkout_id
        and subscription.regularization_checkout_reference is not None
    ):
        return str(subscription.regularization_checkout_reference)
    return None


def end_checkout_from_webhook(event):
    checkout_id = _required_provider_value(event, "checkout", "id")
    checkout_status = _required_provider_value(event, "checkout", "status")
    expected_status = {
        "CHECKOUT_CANCELED": "CANCELED",
        "CHECKOUT_EXPIRED": "EXPIRED",
    }.get(event.event_type)
    if checkout_status != expected_status:
        raise ValueError("Status terminal não corresponde ao evento de checkout")

    subscription = checkout_subscription_from_webhook(event, lock=True)
    if subscription is None:
        return
    event_at = _provider_event_at(event)
    if _is_stale_provider_event(subscription, event_at):
        return

    is_initial_checkout = (
        subscription.status == Subscription.Status.PENDING_CHECKOUT
        and subscription.provider_checkout_id == checkout_id
    )
    is_regularization_checkout = (
        subscription.status
        in {
            Subscription.Status.PENDING_CHECKOUT,
            Subscription.Status.SUSPENDED,
            Subscription.Status.CANCELED,
        }
        and subscription.regularization_checkout_state
        == Subscription.RegularizationCheckoutState.CREATED
        and subscription.regularization_checkout_id == checkout_id
    )
    if not is_initial_checkout and not is_regularization_checkout:
        return

    update_fields = []
    if subscription.provider_checkout_id == checkout_id:
        subscription.provider_checkout_id = ""
        update_fields.append("provider_checkout_id")
    if is_regularization_checkout:
        subscription.regularization_checkout_state = (
            Subscription.RegularizationCheckoutState.READY
        )
        subscription.regularization_checkout_claim = None
        subscription.regularization_checkout_claim_started_at = None
        subscription.regularization_checkout_id = ""
        subscription.regularization_checkout_url = ""
        subscription.regularization_checkout_error = ""
        subscription.regularization_checkout_reference = None
        update_fields.extend(
            [
                "regularization_checkout_state",
                "regularization_checkout_claim",
                "regularization_checkout_claim_started_at",
                "regularization_checkout_id",
                "regularization_checkout_url",
                "regularization_checkout_error",
                "regularization_checkout_reference",
            ]
        )
    _save_transition(subscription, update_fields, event_at)


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
    try:
        checkout = create_recurring_checkout(subscription, user)
    except AsaasCheckoutOutcomeUnknownError as exc:
        checkout_id = exc.checkout_id
        if checkout_id:
            try:
                cancel_checkout(checkout_id)
            except Exception:
                logger.warning("Checkout compensation failed after unsafe Asaas URL")
                Subscription.objects.filter(pk=subscription.pk).update(
                    provider_checkout_id=checkout_id,
                    signup_checkout_state=(
                        Subscription.SignupCheckoutState.RECONCILIATION_REQUIRED
                    ),
                )
                raise
            barbershop.delete()
            raise
        Subscription.objects.filter(pk=subscription.pk).update(
            signup_checkout_state=(
                Subscription.SignupCheckoutState.RECONCILIATION_REQUIRED
            )
        )
        raise
    except Exception:
        barbershop.delete()
        raise

    try:
        validate_checkout_url(checkout.url)
        with transaction.atomic():
            subscription.provider_checkout_id = checkout.id
            subscription.signup_checkout_state = Subscription.SignupCheckoutState.CREATED
            subscription.save(
                update_fields=[
                    "provider_checkout_id",
                    "signup_checkout_state",
                    "updated_at",
                ]
            )
    except Exception as local_error:
        try:
            cancel_checkout(checkout.id)
        except Exception:
            logger.warning("Checkout compensation failed after local signup error")
            Subscription.objects.filter(pk=subscription.pk).update(
                provider_checkout_id=checkout.id,
                signup_checkout_state=(
                    Subscription.SignupCheckoutState.RECONCILIATION_REQUIRED
                ),
            )
            raise local_error
        barbershop.delete()
        raise local_error
    return subscription, checkout


def make_regularization_token(subscription):
    return TimestampSigner(salt=REGULARIZATION_TOKEN_SALT).sign(
        str(subscription.external_reference)
    )


def persist_regularization_email_request(normalized_email):
    normalized_email = normalized_email.strip().lower()
    user = (
        User.objects.filter(
            email__iexact=normalized_email,
            role=User.Role.ADMIN,
            barbershop_id__isnull=False,
        )
        .select_related("barbershop")
        .first()
    )
    if user is None:
        return None
    subscription = Subscription.objects.filter(
        barbershop_id=user.barbershop_id
    ).first()
    if subscription is None or subscription.allows_access:
        return None

    now = timezone.now()
    email_hash = regularization_email_hash(normalized_email)
    with transaction.atomic():
        RegularizationEmailRequest.objects.filter(
            subscription=subscription,
            email_hash=email_hash,
            expires_at__lte=now,
        ).delete()
        request, _ = RegularizationEmailRequest.objects.get_or_create(
            subscription=subscription,
            email_hash=email_hash,
            defaults={
                "user": user,
                "next_attempt_at": now,
                "expires_at": now + REGULARIZATION_EMAIL_REQUEST_TTL,
            },
        )
    return request


def regularization_email_hash(normalized_email):
    return hmac.new(
        settings.SECRET_KEY.encode(),
        normalized_email.encode(),
        hashlib.sha256,
    ).hexdigest()


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


def _claim_regularization_checkout(subscription_id):
    with transaction.atomic():
        subscription = (
            Subscription.objects.select_for_update()
            .select_related("barbershop", "plan")
            .get(pk=subscription_id)
        )
        if subscription.allows_access:
            return None, None, None
        if (
            subscription.regularization_checkout_state
            == Subscription.RegularizationCheckoutState.CREATED
            and subscription.regularization_checkout_id
            and subscription.regularization_checkout_url
        ):
            return (
                CheckoutResult(
                    id=subscription.regularization_checkout_id,
                    url=subscription.regularization_checkout_url,
                ),
                None,
                None,
            )
        if (
            subscription.regularization_checkout_state
            == Subscription.RegularizationCheckoutState.CREATING
        ):
            return None, subscription.regularization_checkout_claim, None
        if (
            subscription.regularization_checkout_state
            == Subscription.RegularizationCheckoutState.RECONCILIATION_REQUIRED
        ):
            raise AsaasCheckoutOutcomeUnknownError(
                "Checkout de regularização exige reconciliação operacional"
            )
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
        claim = uuid4()
        subscription.regularization_checkout_state = (
            Subscription.RegularizationCheckoutState.CREATING
        )
        subscription.regularization_checkout_claim = claim
        subscription.regularization_checkout_claim_started_at = timezone.now()
        subscription.regularization_checkout_id = ""
        subscription.regularization_checkout_url = ""
        subscription.regularization_checkout_error = ""
        subscription.regularization_checkout_reference = uuid4()
        subscription.save(
            update_fields=[
                "regularization_checkout_state",
                "regularization_checkout_claim",
                "regularization_checkout_claim_started_at",
                "regularization_checkout_id",
                "regularization_checkout_url",
                "regularization_checkout_error",
                "regularization_checkout_reference",
                "updated_at",
            ]
        )
    return None, claim, (subscription, admin)


def _persist_regularization_checkout(subscription_id, claim, checkout):
    validate_checkout_url(checkout.url)
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
        if (
            subscription.regularization_checkout_state
            != Subscription.RegularizationCheckoutState.CREATING
            or subscription.regularization_checkout_claim != claim
            or subscription.allows_access
        ):
            raise ValueError("Checkout de regularização não está mais disponível.")
        subscription.regularization_checkout_state = (
            Subscription.RegularizationCheckoutState.CREATED
        )
        subscription.regularization_checkout_claim = None
        subscription.regularization_checkout_claim_started_at = None
        subscription.regularization_checkout_id = checkout.id
        subscription.regularization_checkout_url = checkout.url
        subscription.regularization_checkout_error = ""
        subscription.provider_checkout_id = checkout.id
        subscription.save(
            update_fields=[
                "regularization_checkout_state",
                "regularization_checkout_claim",
                "regularization_checkout_claim_started_at",
                "regularization_checkout_id",
                "regularization_checkout_url",
                "regularization_checkout_error",
                "provider_checkout_id",
                "updated_at",
            ]
        )


def _release_regularization_checkout_claim(subscription_id, claim):
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
        if (
            subscription.regularization_checkout_state
            != Subscription.RegularizationCheckoutState.CREATING
            or subscription.regularization_checkout_claim != claim
        ):
            return
        subscription.regularization_checkout_state = (
            Subscription.RegularizationCheckoutState.READY
        )
        subscription.regularization_checkout_claim = None
        subscription.regularization_checkout_claim_started_at = None
        subscription.regularization_checkout_error = ""
        subscription.regularization_checkout_reference = None
        subscription.save(
            update_fields=[
                "regularization_checkout_state",
                "regularization_checkout_claim",
                "regularization_checkout_claim_started_at",
                "regularization_checkout_error",
                "regularization_checkout_reference",
                "updated_at",
            ]
        )


def _wait_for_regularization_checkout(subscription_id, claim):
    deadline = time_module.monotonic() + REGULARIZATION_CHECKOUT_WAIT_SECONDS
    while time_module.monotonic() < deadline:
        subscription = Subscription.objects.get(pk=subscription_id)
        if subscription.allows_access:
            return None
        if (
            subscription.regularization_checkout_state
            == Subscription.RegularizationCheckoutState.CREATED
            and subscription.regularization_checkout_id
            and subscription.regularization_checkout_url
        ):
            return CheckoutResult(
                id=subscription.regularization_checkout_id,
                url=subscription.regularization_checkout_url,
            )
        if (
            subscription.regularization_checkout_state
            != Subscription.RegularizationCheckoutState.CREATING
            or subscription.regularization_checkout_claim != claim
        ):
            return False
        time_module.sleep(REGULARIZATION_CHECKOUT_POLL_SECONDS)
    raise AsaasCheckoutError("Checkout de regularização ainda está sendo criado")


def _matches_regularization_checkout(subscription, checkout_id, external_reference):
    if str(subscription.regularization_checkout_reference) != external_reference:
        return False
    if (
        subscription.regularization_checkout_state
        == Subscription.RegularizationCheckoutState.CREATED
    ):
        return subscription.regularization_checkout_id == checkout_id
    return (
        subscription.regularization_checkout_state
        in {
            Subscription.RegularizationCheckoutState.CREATING,
            Subscription.RegularizationCheckoutState.RECONCILIATION_REQUIRED,
        }
        and not subscription.regularization_checkout_id
    )


def _mark_regularization_reconciliation_required(subscription_id, claim, error):
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
        if (
            subscription.regularization_checkout_state
            != Subscription.RegularizationCheckoutState.CREATING
            or subscription.regularization_checkout_claim != claim
        ):
            return
        subscription.regularization_checkout_state = (
            Subscription.RegularizationCheckoutState.RECONCILIATION_REQUIRED
        )
        subscription.regularization_checkout_error = error.__class__.__name__[:100]
        subscription.save(
            update_fields=[
                "regularization_checkout_state",
                "regularization_checkout_error",
                "updated_at",
            ]
        )


def reconcile_regularization_checkout(
    subscription_id,
    *,
    checkout_id="",
    checkout_url="",
    attempt_reference=None,
    reset_confirmed_no_active_checkout=False,
):
    attach_checkout = bool(checkout_id or checkout_url)
    if attach_checkout == reset_confirmed_no_active_checkout:
        raise ValueError("Escolha anexar checkout ou confirmar ausência de checkout ativo.")
    if attach_checkout:
        if not checkout_id or len(checkout_id) > 100:
            raise ValueError("ID de checkout verificado é inválido.")
        try:
            validate_checkout_url(checkout_url)
        except AsaasCheckoutError as exc:
            raise ValueError("URL de checkout verificada é inválida.") from exc
    if attempt_reference:
        try:
            attempt_reference = UUID(str(attempt_reference))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Referência da tentativa verificada é inválida.") from exc

    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
        if subscription.allows_access or subscription.regularization_checkout_state not in {
            Subscription.RegularizationCheckoutState.CREATING,
            Subscription.RegularizationCheckoutState.RECONCILIATION_REQUIRED,
        }:
            raise ValueError("Assinatura não exige reconciliação de checkout.")
        if (
            subscription.regularization_checkout_state
            == Subscription.RegularizationCheckoutState.CREATING
            and (
                subscription.regularization_checkout_claim_started_at is None
                or subscription.regularization_checkout_claim_started_at
                > timezone.now() - REGULARIZATION_CLAIM_STALE_AFTER
            )
        ):
            raise ValueError("Checkout em criação recente; aguarde reconciliação segura.")
        if attach_checkout:
            if subscription.regularization_checkout_reference is None:
                if attempt_reference is None:
                    raise ValueError(
                        "Checkout legado exige referência da tentativa verificada."
                    )
                subscription.regularization_checkout_reference = attempt_reference
            elif (
                attempt_reference is not None
                and subscription.regularization_checkout_reference != attempt_reference
            ):
                raise ValueError("Referência da tentativa não corresponde ao checkout.")
            subscription.regularization_checkout_state = (
                Subscription.RegularizationCheckoutState.CREATED
            )
            subscription.regularization_checkout_id = checkout_id
            subscription.regularization_checkout_url = checkout_url
            subscription.provider_checkout_id = checkout_id
            action = "BILLING_REGULARIZATION_CHECKOUT_ATTACHED"
            metadata = {
                "checkout_id": checkout_id,
                "attempt_reference": str(subscription.regularization_checkout_reference),
            }
        else:
            subscription.regularization_checkout_state = (
                Subscription.RegularizationCheckoutState.READY
            )
            subscription.regularization_checkout_id = ""
            subscription.regularization_checkout_url = ""
            action = "BILLING_REGULARIZATION_CLAIM_RESET"
            metadata = {"confirmed_no_active_checkout": True}
        subscription.regularization_checkout_claim = None
        subscription.regularization_checkout_claim_started_at = None
        subscription.regularization_checkout_error = ""
        if not attach_checkout:
            subscription.regularization_checkout_reference = None
        subscription.save(
            update_fields=[
                "regularization_checkout_state",
                "regularization_checkout_claim",
                "regularization_checkout_claim_started_at",
                "regularization_checkout_id",
                "regularization_checkout_url",
                "regularization_checkout_error",
                "regularization_checkout_reference",
                "provider_checkout_id",
                "updated_at",
            ]
        )
        audit_services.record_system_event(
            subscription.barbershop_id,
            action,
            target=subscription,
            metadata=metadata,
        )
    return subscription


def provision_regularization_checkout(subscription):
    for _ in range(2):
        existing_checkout, claim, creation_context = _claim_regularization_checkout(
            subscription.pk
        )
        if existing_checkout is not None:
            return existing_checkout
        if creation_context is None:
            waiting_checkout = _wait_for_regularization_checkout(subscription.pk, claim)
            if waiting_checkout is not False:
                return waiting_checkout
            continue

        claimed_subscription, admin = creation_context
        try:
            checkout = create_regularization_checkout(claimed_subscription, admin)
        except AsaasCheckoutNotCreatedError:
            _release_regularization_checkout_claim(subscription.pk, claim)
            raise
        except Exception as exc:
            _mark_regularization_reconciliation_required(
                subscription.pk,
                claim,
                exc,
            )
            raise
        try:
            _persist_regularization_checkout(subscription.pk, claim, checkout)
        except Exception as exc:
            try:
                cancel_checkout(checkout.id)
            except Exception:
                logger.warning(
                    "Checkout compensation failed after regularization persistence error"
                )
                _mark_regularization_reconciliation_required(
                    subscription.pk,
                    claim,
                    exc,
                )
            else:
                _release_regularization_checkout_claim(subscription.pk, claim)
            raise
        return checkout
    raise AsaasCheckoutError("Checkout de regularização indisponível")
