import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour


@pytest.mark.django_db
def test_create_tenant_admin_bootstraps_production_tenant(monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SenhaInicial789")

    call_command(
        "create_tenant_admin",
        shop_name="Barbearia Central",
        slug="central",
        username="owner",
        email="owner@example.com",
    )

    shop = Barbershop.objects.get(slug="central")
    user = User.objects.get(username="owner")
    assert user.barbershop == shop
    assert user.role == User.Role.ADMIN
    assert user.check_password("SenhaInicial789")
    assert OperatingHour.objects.filter(barbershop=shop).count() == 6
