from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest
from rest_framework.exceptions import ValidationError

from apps.appointments.models import Appointment
from apps.appointments.services import create_appointment
from apps.customers.models import Customer
from apps.services.models import Service


@pytest.mark.django_db
def test_creates_appointment_with_service_duration(barbershop):
    customer = Customer.objects.create(barbershop=barbershop, name="Nick", whatsapp="5511999999999")
    service = Service.objects.create(barbershop=barbershop, name="Corte", price=Decimal("50"), duration_minutes=30)
    start = datetime.now(ZoneInfo(barbershop.timezone)).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=7)
    appointment, token = create_appointment(barbershop=barbershop, customer_id=customer.id, service_id=service.id, starts_at=start)
    assert appointment.ends_at - appointment.starts_at == timedelta(minutes=30)
    assert token and appointment.cancellation_token_hash != token


@pytest.mark.django_db
def test_rejects_cross_tenant_customer(barbershop, other_barbershop):
    customer = Customer.objects.create(barbershop=other_barbershop, name="Outro", whatsapp="5511888888888")
    service = Service.objects.create(barbershop=barbershop, name="Corte", price=50, duration_minutes=30)
    start = datetime.now(ZoneInfo(barbershop.timezone)).replace(hour=10, minute=0) + timedelta(days=7)
    with pytest.raises(ValidationError):
        create_appointment(barbershop=barbershop, customer_id=customer.id, service_id=service.id, starts_at=start)


@pytest.mark.django_db
def test_rejects_overlapping_slot(barbershop):
    first = Customer.objects.create(barbershop=barbershop, name="Um", whatsapp="5511999999999")
    second = Customer.objects.create(barbershop=barbershop, name="Dois", whatsapp="5511888888888")
    service = Service.objects.create(barbershop=barbershop, name="Corte", price=50, duration_minutes=30)
    start = datetime.now(ZoneInfo(barbershop.timezone)).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=7)
    create_appointment(barbershop=barbershop, customer_id=first.id, service_id=service.id, starts_at=start)
    with pytest.raises(ValidationError):
        create_appointment(barbershop=barbershop, customer_id=second.id, service_id=service.id, starts_at=start + timedelta(minutes=15))
