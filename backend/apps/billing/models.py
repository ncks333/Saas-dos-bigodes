import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.utils.models import TimestampedModel


class SubscriptionPlan(TimestampedModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="BRL")
    trial_days = models.PositiveSmallIntegerField(default=30)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="billing_plan_amount_positive")]


class Subscription(TimestampedModel):
    class Status(models.TextChoices):
        PENDING_CHECKOUT = "PENDING_CHECKOUT", "Checkout pendente"
        TRIAL = "TRIAL", "Período de teste"
        ACTIVE = "ACTIVE", "Ativa"
        GRACE = "GRACE", "Tolerância"
        SUSPENDED = "SUSPENDED", "Suspensa"
        CANCELED = "CANCELED", "Cancelada"

    class Provider(models.TextChoices):
        ASAAS = "ASAAS", "Asaas"

    class RegularizationCheckoutState(models.TextChoices):
        READY = "READY", "Pronto"
        CREATING = "CREATING", "Criando"
        CREATED = "CREATED", "Criado"
        PAID = "PAID", "Pago"

    barbershop = models.OneToOneField("barbershops.Barbershop", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_CHECKOUT)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.ASAAS)
    provider_customer_id = models.CharField(max_length=100, blank=True)
    provider_subscription_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_checkout_id = models.CharField(max_length=100, blank=True)
    regularization_checkout_state = models.CharField(
        max_length=16,
        choices=RegularizationCheckoutState.choices,
        default=RegularizationCheckoutState.READY,
    )
    regularization_checkout_claim = models.UUIDField(null=True, blank=True, editable=False)
    regularization_checkout_id = models.CharField(max_length=100, blank=True)
    regularization_checkout_url = models.URLField(max_length=500, blank=True)
    external_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    trial_days = models.PositiveSmallIntegerField(default=30)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)
    last_payment_id = models.CharField(max_length=100, blank=True)
    grace_payment_id = models.CharField(max_length=100, blank=True)
    last_payment_status = models.CharField(max_length=50, blank=True)
    last_payment_at = models.DateTimeField(null=True, blank=True)
    last_provider_event_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=50, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def allowed_statuses(cls):
        return (cls.Status.TRIAL, cls.Status.ACTIVE, cls.Status.GRACE)

    @property
    def allows_access(self):
        return self.status in self.allowed_statuses()

    def start_grace(self, now):
        if self.status != self.Status.GRACE or self.grace_ends_at is None:
            self.grace_ends_at = now + timedelta(days=7)
        self.status = self.Status.GRACE


class SubscriptionPaymentCycle(TimestampedModel):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="payment_cycles",
    )
    provider_payment_id = models.CharField(max_length=100)
    grace_started_at = models.DateTimeField(null=True, blank=True)
    succeeded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "provider_payment_id"],
                name="unique_sub_provider_payment",
            )
        ]


class BillingWebhookEvent(TimestampedModel):
    provider = models.CharField(max_length=20)
    provider_event_id = models.CharField(max_length=150)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.CharField(max_length=300, blank=True)
    dispatch_attempts = models.PositiveIntegerField(default=0)
    processing_attempts = models.PositiveIntegerField(default=0)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    last_processing_attempt_at = models.DateTimeField(null=True, blank=True)
    next_dispatch_at = models.DateTimeField(null=True, blank=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "provider_event_id"], name="unique_billing_provider_event")]
        indexes = [
            models.Index(
                fields=[
                    "processed_at",
                    "dead_lettered_at",
                    "next_dispatch_at",
                    "id",
                ],
                name="billing_wh_recovery_idx",
            )
        ]


class BillingNotificationLog(TimestampedModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="notification_logs")
    kind = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="PENDING")
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    email_snapshot = models.JSONField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subscription", "kind"], name="unique_billing_notification_kind")]
