import logging
from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit_services
from apps.barbershops.models import Barbershop, OperatingHour

from .models import Subscription
from .providers.asaas import cancel_checkout, create_recurring_checkout

logger = logging.getLogger(__name__)


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
