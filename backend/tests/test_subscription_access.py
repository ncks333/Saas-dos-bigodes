from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.billing.models import Subscription
from apps.services.models import Service


@pytest.mark.django_db
def test_suspended_tenant_cannot_use_authenticated_api(api_client, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    assert api_client.get("/api/v1/customers/").status_code == 403


@pytest.mark.django_db
def test_suspended_tenant_cannot_use_admin_api(api_client, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    assert api_client.patch("/api/v1/barbershop/", {"name": "Bloqueada"}).status_code == 403


@pytest.mark.django_db
def test_suspended_tenant_disappears_from_public_booking(client, barbershop, subscription):
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    assert client.get(f"/api/v1/public/{barbershop.slug}/").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [Subscription.Status.TRIAL, Subscription.Status.ACTIVE, Subscription.Status.GRACE],
)
def test_allowed_subscription_statuses_keep_public_access(client, barbershop, subscription, status):
    subscription.status = status
    subscription.save(update_fields=["status", "updated_at"])

    assert client.get(f"/api/v1/public/{barbershop.slug}/").status_code == 200


@pytest.mark.django_db
def test_suspended_tenant_public_services_are_hidden(client, barbershop, subscription):
    Service.objects.create(barbershop=barbershop, name="Corte", price="50.00", duration_minutes=30)
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    response = client.get(f"/api/v1/public/{barbershop.slug}/services/")

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_suspended_tenant_cannot_check_availability_or_book(client, barbershop, subscription, monkeypatch):
    monkeypatch.setattr("apps.appointments.views.verify_turnstile", lambda *_args: True)
    service = Service.objects.create(barbershop=barbershop, name="Corte", price="50.00", duration_minutes=30)
    day = timezone.localdate() + timedelta(days=14)
    starts_at = datetime.combine(day, time(10), tzinfo=ZoneInfo(barbershop.timezone))
    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    availability = client.get(
        f"/api/v1/public/{barbershop.slug}/availability/",
        {"day": day.isoformat(), "service_id": service.id},
    )
    booking = client.post(
        f"/api/v1/public/{barbershop.slug}/book/",
        {
            "name": "Cliente Público",
            "whatsapp": "5511977777777",
            "service_id": service.id,
            "starts_at": starts_at.isoformat(),
            "captcha_token": "development",
            "privacy_notice_accepted": True,
        },
        content_type="application/json",
    )

    assert availability.status_code == 400
    assert booking.status_code == 400
    assert not Appointment.objects.filter(barbershop=barbershop).exists()
