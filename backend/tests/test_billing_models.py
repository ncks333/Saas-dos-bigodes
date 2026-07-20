from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
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


@pytest.mark.django_db
def test_grace_deadline_is_preserved_by_duplicate_start(subscription):
    start = timezone.now()
    subscription.start_grace(start)
    original_deadline = subscription.grace_ends_at

    subscription.start_grace(start + timedelta(days=1))

    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_ends_at == original_deadline


@pytest.mark.django_db(transaction=True)
def test_initial_migration_backfills_existing_barbershops():
    executor = MigrationExecutor(connection)
    original_targets = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("billing", None)])
        old_apps = executor.loader.project_state([("barbershops", "0001_initial")]).apps
        barbershop = old_apps.get_model("barbershops", "Barbershop").objects.create(
            name="Existente",
            slug="existente",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("billing", "0001_initial")])
        new_apps = executor.loader.project_state([("billing", "0001_initial")]).apps
        plan = new_apps.get_model("billing", "SubscriptionPlan").objects.get(code="barberhub")
        subscription = new_apps.get_model("billing", "Subscription").objects.get(barbershop_id=barbershop.id)

        assert plan.name == "BarberHub"
        assert plan.amount == Decimal("79.90")
        assert plan.trial_days == 30
        assert subscription.plan_id == plan.id
        assert subscription.status == "ACTIVE"
    finally:
        MigrationExecutor(connection).migrate(original_targets)
