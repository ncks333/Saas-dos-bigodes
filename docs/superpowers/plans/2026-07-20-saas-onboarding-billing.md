# SaaS Onboarding and Billing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build self-service barbershop signup, Asaas-hosted recurring checkout, 30-day trials, seven-day payment grace, access suspension, regularization, and transactional billing email.

**Architecture:** Add a focused `apps.billing` Django app that owns plans, subscriptions, provider events, access policy, Asaas integration, and billing email. Existing tenant resources consume one normalized access policy; the React frontend consumes public plan/signup endpoints and never supplies price or trial values.

**Tech Stack:** Django 5, Django REST Framework, PostgreSQL, Celery, Resend email backend, requests, React 19, TypeScript, TanStack Query, Axios, Playwright, pytest.

## Global Constraints

- Public trial defaults to exactly 30 days; the first pilot receives 60 days through a per-subscription override.
- Payment grace lasts exactly seven days from the first overdue event.
- Only `TRIAL`, `ACTIVE`, and `GRACE` permit authenticated or public tenant access.
- `Barbershop.active` remains the owner's public-booking preference and billing never overwrites it.
- Card entry happens only on Asaas-hosted Checkout; BarberHub never receives or stores card number, expiry, or CVV.
- Price and trial are resolved server-side from `SubscriptionPlan`; frontend values are display-only.
- Webhook callbacks, not browser redirects, activate subscriptions.
- WhatsApp remains appointment-only; billing notifications use existing Resend email infrastructure.
- Every webhook processor and scheduled notification must be idempotent.
- Existing barbershops receive `ACTIVE` subscriptions during migration and keep access.

---

## File Structure

- `backend/apps/billing/models.py`: plans, subscriptions, provider events, billing email logs.
- `backend/apps/billing/access.py`: one normalized tenant-access policy and queryset filters.
- `backend/apps/billing/providers/asaas.py`: Asaas HTTP payloads and response parsing only.
- `backend/apps/billing/services.py`: signup, state transitions, regularization tokens, checkout orchestration.
- `backend/apps/billing/serializers.py`: public plan, signup, and regularization request validation.
- `backend/apps/billing/views.py`: public plan/signup, webhook, and regularization endpoints.
- `backend/apps/billing/tasks.py`: webhook processing, lifecycle sweep, and billing email delivery.
- `frontend/src/BillingPages.tsx`: signup and billing-state pages.
- `frontend/src/billing.css`: billing/onboarding layout and responsive rules.
- Existing account/public views consume billing interfaces; they do not call Asaas directly.

---

### Task 1: Billing domain models and safe rollout

**Files:**
- Create: `backend/apps/billing/__init__.py`
- Create: `backend/apps/billing/apps.py`
- Create: `backend/apps/billing/models.py`
- Create: `backend/apps/billing/migrations/__init__.py`
- Create: `backend/apps/billing/migrations/0001_initial.py`
- Modify: `backend/core/settings/base.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/apps/barbershops/management/commands/create_tenant_admin.py`
- Test: `backend/tests/test_billing_models.py`

**Interfaces:**
- Consumes: `TimestampedModel`, `Barbershop`.
- Produces: `SubscriptionPlan`, `Subscription`, `BillingWebhookEvent`, `BillingNotificationLog`, `Subscription.allowed_statuses()`.

- [ ] **Step 1: Write failing model tests**

```python
# backend/tests/test_billing_models.py
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.billing.models import BillingWebhookEvent, Subscription, SubscriptionPlan


@pytest.mark.django_db
def test_subscription_access_statuses(barbershop, subscription):
    for status in (Subscription.Status.TRIAL, Subscription.Status.ACTIVE, Subscription.Status.GRACE):
        subscription.status = status
        subscription.save(update_fields=["status", "updated_at"])
        assert subscription.allows_access is True
    for status in (Subscription.Status.PENDING_CHECKOUT, Subscription.Status.SUSPENDED, Subscription.Status.CANCELED):
        subscription.status = status
        subscription.save(update_fields=["status", "updated_at"])
        assert subscription.allows_access is False


@pytest.mark.django_db
def test_plan_amount_must_be_positive():
    with pytest.raises(IntegrityError):
        SubscriptionPlan.objects.create(code="free", name="Free", amount=Decimal("0.00"))


@pytest.mark.django_db
def test_webhook_event_is_unique_per_provider(subscription):
    BillingWebhookEvent.objects.create(provider="ASAAS", provider_event_id="evt_1", event_type="CHECKOUT_PAID", payload={})
    with pytest.raises(IntegrityError):
        BillingWebhookEvent.objects.create(provider="ASAAS", provider_event_id="evt_1", event_type="CHECKOUT_PAID", payload={})


@pytest.mark.django_db
def test_grace_deadline_is_seven_days(subscription):
    start = timezone.now()
    subscription.start_grace(start)
    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_ends_at == start + timedelta(days=7)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && pytest tests/test_billing_models.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'apps.billing'`.

- [ ] **Step 3: Implement focused models**

```python
# backend/apps/billing/models.py
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

    barbershop = models.OneToOneField("barbershops.Barbershop", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_CHECKOUT)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.ASAAS)
    provider_customer_id = models.CharField(max_length=100, blank=True)
    provider_subscription_id = models.CharField(max_length=100, blank=True, db_index=True)
    provider_checkout_id = models.CharField(max_length=100, blank=True)
    external_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    trial_days = models.PositiveSmallIntegerField(default=30)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)
    last_payment_status = models.CharField(max_length=50, blank=True)
    last_payment_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def allowed_statuses(cls):
        return (cls.Status.TRIAL, cls.Status.ACTIVE, cls.Status.GRACE)

    @property
    def allows_access(self):
        return self.status in self.allowed_statuses()

    def start_grace(self, now):
        self.status = self.Status.GRACE
        self.grace_ends_at = now + timedelta(days=7)


class BillingWebhookEvent(TimestampedModel):
    provider = models.CharField(max_length=20)
    provider_event_id = models.CharField(max_length=150)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "provider_event_id"], name="unique_billing_provider_event")]


class BillingNotificationLog(TimestampedModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="notification_logs")
    kind = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="PENDING")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subscription", "kind"], name="unique_billing_notification_kind")]
```

Register `apps.billing` after `apps.barbershops` in `LOCAL_APPS`. Generate migration, then add `RunPython` that creates plan code `barberhub` with amount `79.90`, trial `30`, and one `ACTIVE` subscription per existing barbershop. Update test fixtures to create that same plan and an active subscription. Update `create_tenant_admin` to use `get_or_create(code="barberhub", defaults={...})` and create an active subscription.

Use these fixture semantics so every pre-existing tenant test remains billable by default and only billing-specific tests opt into a blocked state:

```python
# additions/changes in backend/tests/conftest.py
from decimal import Decimal

from apps.billing.models import Subscription, SubscriptionPlan


@pytest.fixture
def plan(db):
    return SubscriptionPlan.objects.create(code="barberhub", name="BarberHub", amount=Decimal("79.90"), trial_days=30)


@pytest.fixture
def barbershop(db, plan):
    shop = Barbershop.objects.create(name="Bigodes", slug="bigodes")
    for weekday in range(7):
        OperatingHour.objects.create(barbershop=shop, weekday=weekday, opens_at=time(8), closes_at=time(18))
    Subscription.objects.create(barbershop=shop, plan=plan, status=Subscription.Status.ACTIVE)
    return shop


@pytest.fixture
def subscription(barbershop):
    return barbershop.subscription


@pytest.fixture
def pending_subscription(db, plan):
    shop = Barbershop.objects.create(name="Pendente", slug="pendente")
    User.objects.create_user(
        username="pending", email="pending@example.com", password="Senha123",
        barbershop=shop, role=User.Role.ADMIN, is_active=False,
    )
    return Subscription.objects.create(
        barbershop=shop, plan=plan, status=Subscription.Status.PENDING_CHECKOUT,
        provider_checkout_id="chk_pending",
    )
```

Make `other_barbershop` depend on `plan` and create its own `ACTIVE` subscription too. Keep one subscription per shop through the database one-to-one constraint.

- [ ] **Step 4: Generate migration and run tests**

Run: `cd backend && python manage.py makemigrations billing && pytest tests/test_billing_models.py tests/test_management_commands.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit domain foundation**

```bash
git add backend/apps/billing backend/core/settings/base.py backend/tests/conftest.py backend/apps/barbershops/management/commands/create_tenant_admin.py
git commit -m "feat: add subscription billing domain"
```

---

### Task 2: Central access policy for authenticated and public tenants

**Files:**
- Create: `backend/apps/billing/access.py`
- Modify: `backend/core/permissions/roles.py`
- Modify: `backend/apps/barbershops/views.py`
- Modify: `backend/apps/services/views.py`
- Modify: `backend/apps/appointments/views.py`
- Test: `backend/tests/test_subscription_access.py`

**Interfaces:**
- Consumes: `Subscription.allowed_statuses()`.
- Produces: `barbershops_with_access(queryset)`, `user_has_subscription_access(user)`.

- [ ] **Step 1: Write failing access tests**

```python
# backend/tests/test_subscription_access.py
import pytest

from apps.billing.models import Subscription


@pytest.mark.django_db
def test_suspended_tenant_cannot_use_authenticated_api(api_client, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    assert api_client.get("/api/v1/customers/").status_code == 403


@pytest.mark.django_db
def test_suspended_tenant_disappears_from_public_booking(client, barbershop, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    assert client.get(f"/api/v1/public/{barbershop.slug}/").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Subscription.Status.TRIAL, Subscription.Status.ACTIVE, Subscription.Status.GRACE])
def test_allowed_subscription_statuses_keep_public_access(client, barbershop, subscription, status):
    subscription.status = status
    subscription.save(update_fields=["status", "updated_at"])
    assert client.get(f"/api/v1/public/{barbershop.slug}/").status_code == 200
```

- [ ] **Step 2: Verify tests fail before gate exists**

Run: `cd backend && pytest tests/test_subscription_access.py -q`

Expected: suspended authenticated/public assertions fail.

- [ ] **Step 3: Implement one access policy**

```python
# backend/apps/billing/access.py
from apps.billing.models import Subscription


def user_has_subscription_access(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.barbershop_id:
        return False
    return Subscription.objects.filter(
        barbershop_id=user.barbershop_id,
        status__in=Subscription.allowed_statuses(),
    ).exists()


def barbershops_with_access(queryset):
    return queryset.filter(subscription__status__in=Subscription.allowed_statuses())
```

Change `IsTenantMember.has_permission` to require both tenant membership and `user_has_subscription_access`. Wrap every public barbershop lookup with `barbershops_with_access`, including public shop, service list, availability, and booking. Keep `active=True` filters unchanged.

- [ ] **Step 4: Run access and multitenancy tests**

Run: `cd backend && pytest tests/test_subscription_access.py tests/test_multitenancy.py tests/test_api_flows.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit access gate**

```bash
git add backend/apps/billing/access.py backend/core/permissions/roles.py backend/apps/barbershops/views.py backend/apps/services/views.py backend/apps/appointments/views.py backend/tests/test_subscription_access.py
git commit -m "feat: enforce subscription access policy"
```

---

### Task 3: Asaas hosted recurring checkout adapter

**Files:**
- Create: `backend/apps/billing/providers/__init__.py`
- Create: `backend/apps/billing/providers/asaas.py`
- Modify: `backend/core/settings/base.py`
- Modify: `backend/core/settings/production.py`
- Modify: `backend/core/settings/test.py`
- Modify: `backend/.env.production.example`
- Test: `backend/tests/test_asaas_provider.py`

**Interfaces:**
- Consumes: `Subscription`, its plan, owner user, `FRONTEND_URL`.
- Produces: `CheckoutResult(id: str, url: str)`, `create_recurring_checkout(subscription, user)`, `create_regularization_checkout(subscription, user)`.

- [ ] **Step 1: Write failing provider contract tests**

```python
# backend/tests/test_asaas_provider.py
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.providers.asaas import create_recurring_checkout


@pytest.mark.django_db
def test_checkout_uses_server_plan_and_credit_card(monkeypatch, subscription, user):
    subscription.trial_ends_at = timezone.now() + timedelta(days=30)
    subscription.next_billing_at = subscription.trial_ends_at + timedelta(days=1)
    subscription.save(update_fields=["trial_ends_at", "next_billing_at", "updated_at"])
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "chk_1", "link": "https://sandbox.asaas.com/checkout/chk_1"}

    def fake_post(url, json, headers, timeout):
        captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return Response()

    monkeypatch.setattr("apps.billing.providers.asaas.requests.post", fake_post)
    result = create_recurring_checkout(subscription, user)
    assert result.id == "chk_1"
    assert captured["json"]["billingTypes"] == ["CREDIT_CARD"]
    assert captured["json"]["chargeTypes"] == ["RECURRENT"]
    assert captured["json"]["items"][0]["value"] == float(subscription.plan.amount)
    assert captured["json"]["subscription"]["cycle"] == "MONTHLY"
    assert captured["json"]["subscription"]["nextDueDate"] == subscription.next_billing_at.date().isoformat()
    assert captured["json"]["externalReference"] == str(subscription.external_reference)
```

- [ ] **Step 2: Verify provider test fails**

Run: `cd backend && pytest tests/test_asaas_provider.py -q`

Expected: import failure for missing provider module.

- [ ] **Step 3: Implement adapter with strict payload ownership**

```python
# backend/apps/billing/providers/asaas.py
from dataclasses import dataclass

import requests
from django.conf import settings


@dataclass(frozen=True)
class CheckoutResult:
    id: str
    url: str


def _create_checkout(subscription, user, next_due_date) -> CheckoutResult:
    payload = {
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": settings.ASAAS_CHECKOUT_EXPIRES_MINUTES,
        "externalReference": str(subscription.external_reference),
        "callback": {
            "successUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/concluido",
            "cancelUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/cancelado",
            "expiredUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/expirado",
        },
        "items": [{"name": subscription.plan.name, "description": "Assinatura mensal M&R BarberHub", "quantity": 1, "value": float(subscription.plan.amount)}],
        "customerData": {"name": user.get_full_name() or user.username, "email": user.email, "phone": subscription.barbershop.whatsapp},
        "subscription": {"cycle": "MONTHLY", "nextDueDate": next_due_date.date().isoformat()},
    }
    response = requests.post(
        f"{settings.ASAAS_API_URL.rstrip('/')}/checkouts",
        json=payload,
        headers={"accept": "application/json", "content-type": "application/json", "access_token": settings.ASAAS_API_KEY},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    checkout_id = data["id"]
    url = data.get("link") or f"{settings.ASAAS_CHECKOUT_BASE_URL}?id={checkout_id}"
    return CheckoutResult(id=checkout_id, url=url)


def create_recurring_checkout(subscription, user) -> CheckoutResult:
    return _create_checkout(subscription, user, subscription.next_billing_at)


def create_regularization_checkout(subscription, user) -> CheckoutResult:
    from django.utils import timezone
    return _create_checkout(subscription, user, timezone.now())
```

Add settings with local sandbox defaults: `ASAAS_API_URL=https://api-sandbox.asaas.com/v3`, `ASAAS_CHECKOUT_BASE_URL=https://sandbox.asaas.com/checkoutSession/show`, empty API/token, and checkout expiry `60`. Production must reject missing API key/token and non-HTTPS URL. Test settings use safe fake values.

- [ ] **Step 4: Run provider and production-config tests**

Run: `cd backend && pytest tests/test_asaas_provider.py tests/test_health.py -q`

Expected: tests pass without real network calls.

- [ ] **Step 5: Commit provider adapter**

```bash
git add backend/apps/billing/providers backend/core/settings backend/.env.production.example backend/tests/test_asaas_provider.py
git commit -m "feat: add Asaas recurring checkout adapter"
```

---

### Task 4: Public plan and atomic signup API

**Files:**
- Create: `backend/apps/billing/serializers.py`
- Create: `backend/apps/billing/services.py`
- Create: `backend/apps/billing/views.py`
- Modify: `backend/core/urls.py`
- Test: `backend/tests/test_onboarding.py`

**Interfaces:**
- Consumes: `SubscriptionPlan`, `create_recurring_checkout`.
- Produces: `GET /api/v1/billing/plans/current/`, `POST /api/v1/billing/signup/`, `provision_signup(validated_data)`.

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/test_onboarding.py
from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.barbershops.models import Barbershop
from apps.billing.models import Subscription, SubscriptionPlan


@pytest.mark.django_db
def test_public_plan_exposes_server_price(client, plan):
    response = client.get("/api/v1/billing/plans/current/")
    assert response.status_code == 200
    assert response.data == {"code": "barberhub", "name": "BarberHub", "amount": "79.90", "currency": "BRL", "trial_days": 30}


@pytest.mark.django_db
def test_signup_ignores_client_price_and_returns_checkout(client, plan, monkeypatch):
    monkeypatch.setattr("apps.billing.views.verify_turnstile", lambda *_args: True)
    monkeypatch.setattr("apps.billing.services.create_recurring_checkout", lambda subscription, user: type("Result", (), {"id": "chk_1", "url": "https://asaas.test/chk_1"})())
    response = client.post("/api/v1/billing/signup/", {
        "first_name": "João", "email": "joao@example.com", "username": "joao", "password": "SenhaForte123",
        "barbershop_name": "Barbearia João", "slug": "barbearia-joao", "whatsapp": "11999999999",
        "plan_code": "barberhub", "amount": "0.01", "captcha_token": "development", "terms_accepted": True,
    })
    assert response.status_code == 201
    assert response.data["checkout_url"] == "https://asaas.test/chk_1"
    subscription = Subscription.objects.get(barbershop__slug="barbearia-joao")
    assert subscription.plan.amount == Decimal("79.90")
    assert subscription.status == Subscription.Status.PENDING_CHECKOUT
    assert User.objects.get(username="joao").is_active is False


@pytest.mark.django_db
def test_invalid_signup_creates_no_partial_tenant(client, plan):
    response = client.post("/api/v1/billing/signup/", {"email": "inválido"})
    assert response.status_code == 400
    assert Barbershop.objects.count() == 0
```

- [ ] **Step 2: Verify API routes fail**

Run: `cd backend && pytest tests/test_onboarding.py -q`

Expected: 404 responses for both endpoints.

- [ ] **Step 3: Implement serializers and transactional provisioning**

Implement `SignupSerializer` with explicit fields, `validate_password`, slug uniqueness, email/username uniqueness, phone normalization through `normalize_brazilian_whatsapp`, `terms_accepted=True`, and `captcha_token`. Do not declare `amount` so DRF discards it. Implement `PublicPlanSerializer` with only display fields.

```python
# backend/apps/billing/services.py
from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour
from apps.billing.models import Subscription
from apps.billing.providers.asaas import create_recurring_checkout


@transaction.atomic
def provision_signup(data, plan):
    shop = Barbershop.objects.create(name=data["barbershop_name"], slug=data["slug"], whatsapp=data["whatsapp"])
    for weekday in range(6):
        OperatingHour.objects.create(barbershop=shop, weekday=weekday, opens_at=time(8), closes_at=time(18))
    user = User.objects.create_user(
        username=data["username"], email=data["email"], password=data["password"], first_name=data["first_name"],
        barbershop=shop, role=User.Role.ADMIN, is_active=False,
    )
    trial_ends_at = timezone.now() + timedelta(days=plan.trial_days)
    next_billing_at = trial_ends_at + timedelta(days=1)
    subscription = Subscription.objects.create(
        barbershop=shop, plan=plan, trial_days=plan.trial_days,
        trial_ends_at=trial_ends_at, next_billing_at=next_billing_at,
    )
    checkout = create_recurring_checkout(subscription, user)
    subscription.provider_checkout_id = checkout.id
    subscription.save(update_fields=["provider_checkout_id", "updated_at"])
    return subscription, checkout
```

The signup view calls Turnstile, resolves `plan_code` among active plans, calls `provision_signup`, records `BILLING_SIGNUP_CREATED`, and returns only checkout URL and public reference. Provider exceptions return 503 through the project exception handler; the database transaction rolls back local records.

- [ ] **Step 4: Run onboarding and auth tests**

Run: `cd backend && pytest tests/test_onboarding.py tests/test_auth.py tests/test_management_commands.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit onboarding API**

```bash
git add backend/apps/billing/serializers.py backend/apps/billing/services.py backend/apps/billing/views.py backend/core/urls.py backend/tests/test_onboarding.py
git commit -m "feat: add self-service barbershop signup"
```

---

### Task 5: Authenticated, idempotent Asaas webhook transitions

**Files:**
- Modify: `backend/apps/billing/services.py`
- Modify: `backend/apps/billing/views.py`
- Create: `backend/apps/billing/tasks.py`
- Modify: `backend/core/urls.py`
- Test: `backend/tests/test_billing_webhooks.py`

**Interfaces:**
- Consumes: Asaas `id`, `event`, `checkout`, `subscription`, and `payment` payload objects.
- Produces: `POST /api/v1/billing/webhooks/asaas/`, `process_billing_webhook(event_id)`.

- [ ] **Step 1: Write failing webhook tests**

```python
# backend/tests/test_billing_webhooks.py
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.models import BillingWebhookEvent, Subscription


@pytest.mark.django_db
def test_webhook_rejects_invalid_token(client, settings):
    settings.ASAAS_WEBHOOK_TOKEN = "valid-token"
    response = client.post("/api/v1/billing/webhooks/asaas/", {"id": "evt_1", "event": "CHECKOUT_PAID"}, format="json", HTTP_ASAAS_ACCESS_TOKEN="wrong")
    assert response.status_code == 401


@pytest.mark.django_db
def test_checkout_paid_activates_trial_once(client, settings, pending_subscription):
    settings.ASAAS_WEBHOOK_TOKEN = "valid-token"
    payload = {
        "id": "evt_paid_1", "event": "CHECKOUT_PAID",
        "checkout": {"id": pending_subscription.provider_checkout_id, "externalReference": str(pending_subscription.external_reference)},
        "subscription": {"id": "sub_asaas_1"},
    }
    first = client.post("/api/v1/billing/webhooks/asaas/", payload, format="json", HTTP_ASAAS_ACCESS_TOKEN="valid-token")
    second = client.post("/api/v1/billing/webhooks/asaas/", payload, format="json", HTTP_ASAAS_ACCESS_TOKEN="valid-token")
    pending_subscription.refresh_from_db()
    assert first.status_code == second.status_code == 202
    assert pending_subscription.status == Subscription.Status.TRIAL
    assert pending_subscription.provider_subscription_id == "sub_asaas_1"
    assert pending_subscription.barbershop.users.get().is_active is True
    assert BillingWebhookEvent.objects.filter(provider_event_id="evt_paid_1").count() == 1


@pytest.mark.django_db
def test_overdue_starts_exact_grace(client, settings, subscription):
    settings.ASAAS_WEBHOOK_TOKEN = "valid-token"
    subscription.provider_subscription_id = "sub_1"
    subscription.save(update_fields=["provider_subscription_id", "updated_at"])
    before = timezone.now()
    payload = {"id": "evt_overdue", "event": "PAYMENT_OVERDUE", "payment": {"id": "pay_1", "subscription": "sub_1", "status": "OVERDUE"}}
    response = client.post("/api/v1/billing/webhooks/asaas/", payload, format="json", HTTP_ASAAS_ACCESS_TOKEN="valid-token")
    subscription.refresh_from_db()
    assert response.status_code == 202
    assert subscription.status == Subscription.Status.GRACE
    assert before + timedelta(days=7) <= subscription.grace_ends_at <= timezone.now() + timedelta(days=7)
```

- [ ] **Step 2: Verify webhook tests fail**

Run: `cd backend && pytest tests/test_billing_webhooks.py -q`

Expected: webhook endpoint returns 404.

- [ ] **Step 3: Implement secure ingestion and normalized transitions**

The view uses `hmac.compare_digest`, requires `id` and `event`, stores a sanitized projection of payload, uses `get_or_create(provider="ASAAS", provider_event_id=id)`, queues only newly created events, and always returns 202 for duplicate valid events.

```python
# event mapping in backend/apps/billing/tasks.py
PAYMENT_SUCCESS_EVENTS = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
PAYMENT_FAILURE_EVENTS = {"PAYMENT_OVERDUE", "PAYMENT_REPROVED_BY_RISK_ANALYSIS"}
IMMEDIATE_SUSPENSION_EVENTS = {"PAYMENT_CHARGEBACK_REQUESTED", "PAYMENT_CHARGEBACK_DISPUTE"}
CANCEL_EVENTS = {"SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"}
```

`CHECKOUT_PAID` locates by `checkout.externalReference`, sets provider IDs, sets `TRIAL`, enables tenant users, and records audit. Success payment events locate by `payment.subscription`, set `ACTIVE`, clear grace/suspension, and record payment timestamp. Failure events preserve an existing earlier grace deadline, call `start_grace` only once, and record audit. Chargeback events set `SUSPENDED` immediately. Cancel events set `CANCELED`. Set `processed_at` only after transition commits; store safe exception class on failure and re-raise for Celery retry.

- [ ] **Step 4: Run webhook, access, and notification regression tests**

Run: `cd backend && pytest tests/test_billing_webhooks.py tests/test_subscription_access.py tests/test_notifications.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit webhook processing**

```bash
git add backend/apps/billing/services.py backend/apps/billing/views.py backend/apps/billing/tasks.py backend/core/urls.py backend/tests/test_billing_webhooks.py
git commit -m "feat: synchronize Asaas billing webhooks"
```

---

### Task 6: Billing lifecycle sweep and idempotent Resend email

**Files:**
- Modify: `backend/apps/billing/tasks.py`
- Modify: `backend/core/settings/base.py`
- Test: `backend/tests/test_billing_notifications.py`

**Interfaces:**
- Consumes: `BillingNotificationLog`, subscription dates/status, existing Django email backend.
- Produces: `send_billing_email(subscription_id, kind)`, `sweep_subscription_lifecycle()`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
# backend/tests/test_billing_notifications.py
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.billing.models import BillingNotificationLog, Subscription
from apps.billing.tasks import send_billing_email, sweep_subscription_lifecycle


@pytest.mark.django_db
def test_billing_email_is_idempotent(subscription, user):
    send_billing_email(subscription.id, "TRIAL_ACTIVATED")
    send_billing_email(subscription.id, "TRIAL_ACTIVATED")
    assert len(mail.outbox) == 1
    assert BillingNotificationLog.objects.filter(subscription=subscription, kind="TRIAL_ACTIVATED", status="SENT").count() == 1
    assert "79,90" in mail.outbox[0].body


@pytest.mark.django_db
def test_expired_grace_suspends_without_deleting_data(subscription):
    subscription.status = Subscription.Status.GRACE
    subscription.grace_ends_at = timezone.now() - timedelta(minutes=1)
    subscription.save(update_fields=["status", "grace_ends_at", "updated_at"])
    sweep_subscription_lifecycle()
    subscription.refresh_from_db()
    assert subscription.status == Subscription.Status.SUSPENDED
    assert subscription.barbershop_id is not None


@pytest.mark.django_db
def test_trial_warning_sent_at_seven_days(subscription):
    subscription.status = Subscription.Status.TRIAL
    subscription.trial_ends_at = timezone.now() + timedelta(days=7)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])
    sweep_subscription_lifecycle()
    assert BillingNotificationLog.objects.filter(subscription=subscription, kind="TRIAL_ENDS_7D").exists()
```

- [ ] **Step 2: Verify lifecycle tests fail**

Run: `cd backend && pytest tests/test_billing_notifications.py -q`

Expected: missing task imports.

- [ ] **Step 3: Implement email kinds and lifecycle sweep**

Use a fixed mapping for subject/body builders: `TRIAL_ACTIVATED`, `TRIAL_ENDS_7D`, `TRIAL_ENDS_3D`, `TRIAL_ENDS_1D`, `PAYMENT_RECEIVED`, `PAYMENT_FAILED`, `SUSPENDED`, `REACTIVATED`, `CANCELED`. Format BRL through `Decimal`, include barbershop, plan, due date, and `FRONTEND_URL/regularizar`; never include provider payload.

`send_billing_email` claims a `PENDING` log with conditional update, sends to admin emails (including an inactive owner awaiting checkout confirmation), then marks `SENT`; failures mark `FAILED` and retry. `sweep_subscription_lifecycle` creates warning logs only inside each exact date window and transitions expired `GRACE` rows to `SUSPENDED` in a transaction. Wire the normalized webhook transitions from Task 5 to enqueue the corresponding email kind only after the state transaction commits. Add Celery Beat entry every 3600 seconds.

- [ ] **Step 4: Run billing email and existing email tests**

Run: `cd backend && pytest tests/test_billing_notifications.py tests/test_email_backend.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit lifecycle notifications**

```bash
git add backend/apps/billing/tasks.py backend/core/settings/base.py backend/tests/test_billing_notifications.py
git commit -m "feat: send subscription lifecycle emails"
```

---

### Task 7: Login blocking and public regularization

**Files:**
- Modify: `backend/apps/accounts/serializers.py`
- Create: `backend/apps/accounts/views.py`
- Modify: `backend/apps/billing/serializers.py`
- Modify: `backend/apps/billing/services.py`
- Modify: `backend/apps/billing/views.py`
- Modify: `backend/core/urls.py`
- Test: `backend/tests/test_billing_regularization.py`

**Interfaces:**
- Consumes: subscription access policy, Asaas regularization checkout.
- Produces: `POST /api/v1/billing/regularization/request/`, `POST /api/v1/billing/regularization/checkout/`, signed one-hour billing token.

- [ ] **Step 1: Write failing login and regularization tests**

```python
# backend/tests/test_billing_regularization.py
import pytest
from django.core import mail

from apps.billing.models import Subscription


@pytest.mark.django_db
def test_suspended_user_gets_no_jwt(client, user, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    response = client.post("/api/v1/auth/login/", {"username": user.username, "password": "Senha123"})
    assert response.status_code == 403
    assert response.data["code"] == "subscription_required"
    assert "access" not in response.data


@pytest.mark.django_db
def test_suspended_user_cannot_refresh_existing_jwt(client, user, subscription):
    active_login = client.post("/api/v1/auth/login/", {"username": user.username, "password": "Senha123"})
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    response = client.post("/api/v1/auth/refresh/", {"refresh": active_login.data["refresh"]})
    assert response.status_code == 403
    assert response.data["code"] == "subscription_required"


@pytest.mark.django_db
def test_regularization_request_does_not_enumerate_email(client, user, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    known = client.post("/api/v1/billing/regularization/request/", {"email": user.email})
    unknown = client.post("/api/v1/billing/regularization/request/", {"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_valid_regularization_token_returns_hosted_checkout(client, user, subscription, monkeypatch):
    from apps.billing.services import make_regularization_token
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])
    monkeypatch.setattr("apps.billing.services.create_regularization_checkout", lambda subscription, user: type("Result", (), {"id": "chk_reg", "url": "https://asaas.test/reg"})())
    response = client.post("/api/v1/billing/regularization/checkout/", {"token": make_regularization_token(subscription)})
    assert response.status_code == 200
    assert response.data["checkout_url"] == "https://asaas.test/reg"
```

- [ ] **Step 2: Verify regularization tests fail**

Run: `cd backend && pytest tests/test_billing_regularization.py -q`

Expected: suspended login still returns tokens or generic 401; regularization endpoints return 404.

- [ ] **Step 3: Implement explicit gate and signed retry flow**

After `TokenObtainPairSerializer` validates credentials, inspect subscription. If blocked, raise `PermissionDenied({"code": "subscription_required", "detail": "Assinatura precisa ser regularizada."})` before returning token data. Add `SubscriptionTokenRefreshView` around SimpleJWT refresh: decode the refresh token, resolve its user, run the same access policy, and reject blocked subscriptions before calling the parent implementation. Point `/api/v1/auth/refresh/` at this view. Existing access tokens may remain cryptographically valid until expiry, but every tenant permission also rejects them through Task 2.

Use `django.core.signing.TimestampSigner(salt="billing-regularization")` to sign the subscription UUID/reference. Request endpoint always returns `{"message": "Se a conta precisar de regularização, enviaremos as instruções."}` and emails only blocked accounts. Checkout endpoint calls `unsign(..., max_age=3600)`, rejects invalid/expired tokens, creates hosted checkout, and stores its ID. Apply existing rate-limit pattern to both endpoints.

- [ ] **Step 4: Run auth and regularization tests**

Run: `cd backend && pytest tests/test_billing_regularization.py tests/test_auth.py tests/test_api_flows.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit access recovery flow**

```bash
git add backend/apps/accounts/serializers.py backend/apps/accounts/views.py backend/apps/billing/serializers.py backend/apps/billing/services.py backend/apps/billing/views.py backend/core/urls.py backend/tests/test_billing_regularization.py
git commit -m "feat: block and recover unpaid subscriptions"
```

---

### Task 8: React onboarding, pricing, and billing-state pages

**Files:**
- Create: `frontend/src/BillingPages.tsx`
- Create: `frontend/src/billing.css`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/MarketingPages.tsx`
- Modify: `frontend/src/ProductApp.tsx`
- Modify: `frontend/tests/mobile.spec.ts`

**Interfaces:**
- Consumes: public plan/signup/regularization APIs.
- Produces: `/cadastro`, `/checkout/concluido`, `/checkout/cancelado`, `/checkout/expirado`, `/regularizar`.

- [ ] **Step 1: Add failing Playwright tests**

```typescript
// append to frontend/tests/mobile.spec.ts
test("landing leva ao cadastro e mostra plano do servidor", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: {code: "barberhub", name: "BarberHub", amount: "79.90", currency: "BRL", trial_days: 30}}));
  await page.goto("/");
  await expect(page.getByText("30 dias grátis").first()).toBeVisible();
  await expect(page.getByRole("link", {name: /Começar grátis/}).first()).toHaveAttribute("href", "/cadastro");
});

test("cadastro redireciona somente para checkout devolvido pelo servidor", async ({page}) => {
  await page.route("**/api/v1/billing/plans/current/", route => route.fulfill({json: {code: "barberhub", name: "BarberHub", amount: "79.90", currency: "BRL", trial_days: 30}}));
  await page.route("**/api/v1/billing/signup/", route => route.fulfill({status: 201, json: {checkout_url: "/checkout/concluido"}}));
  await page.goto("/cadastro");
  await page.getByLabel("Nome").fill("João");
  await page.getByLabel("E-mail").fill("joao@example.com");
  await page.getByLabel("Usuário").fill("joao");
  await page.getByLabel("Senha").fill("SenhaForte123");
  await page.getByLabel("Nome da barbearia").fill("Barbearia João");
  await page.getByLabel("Endereço público").fill("barbearia-joao");
  await page.getByLabel("WhatsApp").fill("11999999999");
  await page.getByRole("checkbox", {name: /termos/}).check();
  const requestPromise = page.waitForRequest("**/api/v1/billing/signup/");
  await page.getByRole("button", {name: /Continuar para pagamento/}).click();
  const request = await requestPromise;
  expect(request.postDataJSON()).not.toHaveProperty("amount");
});

test("login bloqueado oferece regularização", async ({page}) => {
  await page.route("**/api/v1/auth/login/", route => route.fulfill({status: 403, json: {code: "subscription_required", detail: "Assinatura precisa ser regularizada."}}));
  await page.goto("/login");
  await page.getByLabel("Usuário").fill("admin");
  await page.getByLabel("Senha").fill("Senha123");
  await page.getByRole("button", {name: "Entrar"}).click();
  await expect(page.getByRole("link", {name: /Regularizar assinatura/})).toHaveAttribute("href", "/regularizar");
});
```

- [ ] **Step 2: Verify frontend tests fail**

Run: `cd frontend && npm run test:e2e -- --grep "cadastro|plano do servidor|regularização"`

Expected: missing links/routes and signup page.

- [ ] **Step 3: Implement billing pages and route wiring**

`BillingPages.tsx` defines shared `Plan` type, fetches current plan through `api`, derives slug from barbershop name but leaves it editable, sends only declared signup fields, then assigns `location.href = checkout_url`. Reuse the existing Turnstile loading pattern; when `VITE_TURNSTILE_SITE_KEY` is absent in local/test mode, send the explicit `development` token accepted only by non-production backend settings. Checkout status pages explicitly say access waits for confirmation. Regularization page requests email, reads signed `token` from query string, calls checkout endpoint, and redirects only to the returned provider URL.

Update `App.tsx` lazy routes. Replace landing's direct demo/panel primary CTAs with `/cadastro`, add one pricing section fed by public plan endpoint, keep `/login` as secondary existing-customer action. Update login error parsing so `subscription_required` shows the regularization CTA and does not attempt JWT refresh.

`billing.css` must keep form width at `min(560px, calc(100% - 32px))`, use existing black/gold tokens, provide visible focus, stack fields below 720px, and never create horizontal overflow.

- [ ] **Step 4: Run frontend build, lint, and mobile tests**

Run: `cd frontend && npm run build && npm run lint && npm run test:e2e`

Expected: build, lint, and all Playwright tests pass.

- [ ] **Step 5: Commit frontend onboarding**

```bash
git add frontend/src/BillingPages.tsx frontend/src/billing.css frontend/src/App.tsx frontend/src/MarketingPages.tsx frontend/src/ProductApp.tsx frontend/tests/mobile.spec.ts
git commit -m "feat: add subscription onboarding UI"
```

---

### Task 9: Deployment documentation and full verification

**Files:**
- Modify: `docs/DEPLOY.md`
- Modify: `docs/SECURITY.md`
- Modify: `README.md`
- Modify: `backend/.env.production.example`
- Modify: `frontend/scripts/validate-production-env.mjs`
- Test: `frontend/config-tests/production-config.test.mjs`

**Interfaces:**
- Consumes: final backend/frontend configuration.
- Produces: exact Asaas Sandbox/production setup and release checklist.

- [ ] **Step 1: Extend config tests before docs/config change**

Add assertions that production docs/example contain `ASAAS_API_URL`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, and HTTPS `FRONTEND_URL`; frontend production validation continues to reject missing public variables without accepting Asaas secrets.

- [ ] **Step 2: Run config tests and verify failure**

Run: `cd frontend && npm run test:config`

Expected: new Asaas documentation/config assertions fail.

- [ ] **Step 3: Document exact operational setup**

Document Sandbox API key, hosted recurring checkout, webhook URL `/api/v1/billing/webhooks/asaas/`, strong independent webhook token, required events (`CHECKOUT_PAID`, payment success/overdue/risk/chargeback, subscription inactive/deleted), Resend verification, trial/grace behavior, and test-user cleanup. State that production secrets live only in Railway and that browser redirects never prove payment.

- [ ] **Step 4: Run complete verification**

Run:

```bash
cd backend && pytest
cd backend && ruff check .
cd frontend && npm run test:config
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run test:e2e
```

Expected: every command exits 0 and backend coverage remains at or above configured 80%.

- [ ] **Step 5: Commit docs and config**

```bash
git add docs/DEPLOY.md docs/SECURITY.md README.md backend/.env.production.example frontend/scripts/validate-production-env.mjs frontend/config-tests/production-config.test.mjs
git commit -m "docs: document subscription deployment"
```

---

## Final Acceptance

- Signup creates one pending tenant and redirects only to Asaas-hosted checkout.
- Valid checkout webhook activates 30-day trial; pilot can be set to 60 days through subscription data.
- Existing tenants remain active after migration.
- Subscription status gates every tenant API and public booking path.
- Seven-day grace is stable across duplicate overdue events.
- Suspended users receive no JWT and can regularize without panel access.
- Price cannot be changed from browser payload.
- Billing email is idempotent and contains no payment secrets.
- Duplicate webhooks cause no duplicate transitions or email.
- All backend/frontend quality gates pass.
