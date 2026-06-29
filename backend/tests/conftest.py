from datetime import time
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour


@pytest.fixture
def barbershop(db):
    shop = Barbershop.objects.create(name="Bigodes", slug="bigodes")
    for weekday in range(7):
        OperatingHour.objects.create(barbershop=shop, weekday=weekday, opens_at=time(8), closes_at=time(18))
    return shop


@pytest.fixture
def other_barbershop(db):
    return Barbershop.objects.create(name="Outra", slug="outra")


@pytest.fixture
def user(barbershop):
    return User.objects.create_user(username="admin", email="admin@example.com", password="Senha123", barbershop=barbershop, role=User.Role.ADMIN)


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client
