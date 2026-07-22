from datetime import time
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour
from apps.billing.models import Subscription, SubscriptionPlan


@pytest.fixture
def plan(db):
    plan, _ = SubscriptionPlan.objects.get_or_create(
        code="barberhub",
        defaults={"name": "BarberHub", "amount": Decimal("79.90"), "trial_days": 30},
    )
    return plan


@pytest.fixture
def barbershop(db, plan):
    shop = Barbershop.objects.create(name="Bigodes", slug="bigodes")
    for weekday in range(7):
        OperatingHour.objects.create(barbershop=shop, weekday=weekday, opens_at=time(8), closes_at=time(18))
    Subscription.objects.create(barbershop=shop, plan=plan, status=Subscription.Status.ACTIVE)
    return shop


@pytest.fixture
def other_barbershop(db, plan):
    shop = Barbershop.objects.create(name="Outra", slug="outra")
    Subscription.objects.create(barbershop=shop, plan=plan, status=Subscription.Status.ACTIVE)
    return shop


@pytest.fixture
def subscription(barbershop):
    return barbershop.subscription


@pytest.fixture
def pending_subscription(db, plan):
    shop = Barbershop.objects.create(name="Pendente", slug="pendente")
    User.objects.create_user(
        username="pending",
        email="pending@example.com",
        password="Senha123",
        barbershop=shop,
        role=User.Role.ADMIN,
        is_active=False,
    )
    return Subscription.objects.create(
        barbershop=shop,
        plan=plan,
        status=Subscription.Status.PENDING_CHECKOUT,
        provider_checkout_id="chk_pending",
    )


@pytest.fixture
def user(barbershop):
    return User.objects.create_user(username="admin", email="admin@example.com", password="Senha123", barbershop=barbershop, role=User.Role.ADMIN)


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client
