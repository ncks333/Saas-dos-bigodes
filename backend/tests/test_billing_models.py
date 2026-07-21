from datetime import UTC, datetime, timedelta
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


@pytest.mark.django_db
def test_grace_deadline_resets_after_reactivation(subscription):
    start = timezone.now()
    subscription.start_grace(start)
    subscription.status = Subscription.Status.ACTIVE
    next_cycle_start = start + timedelta(days=2)

    subscription.start_grace(next_cycle_start)

    assert subscription.status == Subscription.Status.GRACE
    assert subscription.grace_ends_at == next_cycle_start + timedelta(days=7)


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


@pytest.mark.django_db(transaction=True)
def test_0008_backfills_only_known_legacy_regularization_checkouts():
    executor = MigrationExecutor(connection)
    original_targets = executor.loader.graph.leaf_nodes()
    migration_from = ("billing", "0007_regularization_reconciliation_and_notification_dedupe")
    migration_to = ("billing", "0008_regularization_attempt_reference_and_claim_started")
    try:
        executor.migrate([migration_from])
        old_apps = executor.loader.project_state([migration_from]).apps
        barbershop_model = old_apps.get_model("barbershops", "Barbershop")
        plan_model = old_apps.get_model("billing", "SubscriptionPlan")
        subscription_model = old_apps.get_model("billing", "Subscription")
        plan = plan_model.objects.create(
            code="legacy-regularization",
            name="Legacy regularization",
            amount=Decimal("79.90"),
        )

        def create_subscription(slug, state, checkout_id="", checkout_url=""):
            barbershop = barbershop_model.objects.create(name=slug, slug=slug)
            return subscription_model.objects.create(
                barbershop_id=barbershop.id,
                plan_id=plan.id,
                status="SUSPENDED",
                regularization_checkout_state=state,
                regularization_checkout_id=checkout_id,
                regularization_checkout_url=checkout_url,
            )

        created = create_subscription(
            "legacy-created",
            "CREATED",
            "chk_legacy",
            "https://sandbox.asaas.com/chk_legacy",
        )
        creating = create_subscription("legacy-creating", "CREATING")
        reconciliation = create_subscription(
            "legacy-reconciliation", "RECONCILIATION_REQUIRED"
        )

        executor = MigrationExecutor(connection)
        executor.migrate([migration_to])
        migrated_apps = executor.loader.project_state([migration_to]).apps
        migrated_subscription = migrated_apps.get_model("billing", "Subscription")

        assert (
            migrated_subscription.objects.get(pk=created.id).regularization_checkout_reference
            == created.external_reference
        )
        assert (
            migrated_subscription.objects.get(pk=creating.id).regularization_checkout_reference
            is None
        )
        assert (
            migrated_subscription.objects.get(
                pk=reconciliation.id
            ).regularization_checkout_reference
            is None
        )
    finally:
        MigrationExecutor(connection).migrate(original_targets)


@pytest.mark.django_db(transaction=True)
def test_0003_migration_backfills_payment_cycle_history_and_blocks_delayed_grace():
    executor = MigrationExecutor(connection)
    original_targets = executor.loader.graph.leaf_nodes()
    migration_from = ("billing", "0002_subscription_provider_cycle_fields")
    migration_to = ("billing", "0003_webhook_recovery_and_payment_cycles")
    try:
        executor.migrate([migration_from])
        old_apps = executor.loader.project_state([migration_from]).apps
        barbershop = old_apps.get_model("barbershops", "Barbershop").objects.create(
            name="Migração ciclos",
            slug="migracao-ciclos",
        )
        plan = old_apps.get_model("billing", "SubscriptionPlan").objects.create(
            code="migration-cycles",
            name="Migration Cycles",
            amount=Decimal("79.90"),
        )
        base_at = datetime(2026, 7, 20, 10, tzinfo=UTC)
        subscription = old_apps.get_model("billing", "Subscription").objects.create(
            barbershop_id=barbershop.id,
            plan_id=plan.id,
            status="ACTIVE",
            provider_subscription_id="sub_migration_cycles",
            last_payment_id="pay_b_migration",
            grace_payment_id="pay_b_migration",
            last_payment_status="RECEIVED",
            last_payment_at=base_at + timedelta(hours=3),
            last_provider_event_at=base_at + timedelta(hours=3),
        )
        failed_subscriptions = []
        for suffix, payment_status in (
            ("overdue", "OVERDUE"),
            ("risk", "REPROVED_BY_RISK_ANALYSIS"),
        ):
            failed_barbershop = old_apps.get_model(
                "barbershops", "Barbershop"
            ).objects.create(
                name=f"Migração falha {suffix}",
                slug=f"migracao-falha-{suffix}",
            )
            failed_subscriptions.append(
                old_apps.get_model("billing", "Subscription").objects.create(
                    barbershop_id=failed_barbershop.id,
                    plan_id=plan.id,
                    status="GRACE",
                    provider_subscription_id=f"sub_failed_{suffix}",
                    last_payment_id=f"pay_failed_{suffix}",
                    grace_payment_id=f"pay_failed_{suffix}",
                    last_payment_status=payment_status,
                    last_payment_at=base_at,
                    grace_ends_at=base_at + timedelta(days=7),
                )
            )
        old_event = old_apps.get_model("billing", "BillingWebhookEvent")
        for index, (event_type, payment_id, payment_status) in enumerate(
            [
                ("PAYMENT_OVERDUE", "pay_a_migration", "OVERDUE"),
                ("PAYMENT_RECEIVED", "pay_a_migration", "RECEIVED"),
                ("PAYMENT_OVERDUE", "pay_b_migration", "OVERDUE"),
                ("PAYMENT_RECEIVED", "pay_b_migration", "RECEIVED"),
            ]
        ):
            event_at = base_at + timedelta(hours=index)
            old_event.objects.create(
                provider="ASAAS",
                provider_event_id=f"evt_migration_{index}",
                event_type=event_type,
                payload={
                    "dateCreated": event_at.isoformat(),
                    "payment": {
                        "id": payment_id,
                        "subscription": subscription.provider_subscription_id,
                        "status": payment_status,
                    },
                },
                processed_at=event_at,
            )

        executor = MigrationExecutor(connection)
        executor.migrate([migration_to])
        migrated_apps = executor.loader.project_state([migration_to]).apps
        cycle_model = migrated_apps.get_model(
            "billing", "SubscriptionPaymentCycle"
        )
        cycles = {
            cycle.provider_payment_id: cycle
            for cycle in cycle_model.objects.filter(subscription_id=subscription.id)
        }
        assert set(cycles) == {"pay_a_migration", "pay_b_migration"}
        assert cycles["pay_a_migration"].grace_started_at == base_at
        assert cycles["pay_a_migration"].succeeded_at == base_at + timedelta(hours=1)
        assert cycles["pay_b_migration"].grace_started_at == base_at + timedelta(
            hours=2
        )
        assert cycles["pay_b_migration"].succeeded_at == base_at + timedelta(
            hours=3
        )
        for failed_subscription in failed_subscriptions:
            failed_cycle = cycle_model.objects.get(
                subscription_id=failed_subscription.id,
                provider_payment_id=failed_subscription.last_payment_id,
            )
            assert failed_cycle.grace_started_at == base_at
            assert failed_cycle.succeeded_at is None

        executor = MigrationExecutor(connection)
        executor.migrate(original_targets)
        delayed = BillingWebhookEvent.objects.create(
            provider="ASAAS",
            provider_event_id="evt_delayed_a_after_migration",
            event_type="PAYMENT_OVERDUE",
            payload={
                "payment": {
                    "id": "pay_a_migration",
                    "subscription": subscription.provider_subscription_id,
                    "status": "OVERDUE",
                }
            },
        )
        from apps.billing.tasks import process_billing_webhook

        process_billing_webhook.run(delayed.id)

        migrated_subscription = Subscription.objects.get(pk=subscription.id)
        assert migrated_subscription.status == Subscription.Status.ACTIVE
        assert migrated_subscription.grace_ends_at is None
    finally:
        MigrationExecutor(connection).migrate(original_targets)
