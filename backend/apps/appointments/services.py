from datetime import date, datetime, time, timedelta
from hashlib import sha256
import secrets
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.barbershops.models import OperatingHour
from apps.customers.models import Customer
from apps.services.models import Service
from .models import Appointment, ScheduleBlock

ACTIVE_STATUSES = [Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.AWAITING]
SLOT_INTERVAL_MINUTES = 30


def _lock_tenant_schedule(barbershop_id: int) -> None:
    """Serializa alterações da agenda do tenant e elimina corridas entre requisições."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [barbershop_id])


def _day_bounds(barbershop, day: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(barbershop.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def active_appointments_for_day(*, barbershop, customer_id: int, day: date):
    day_start, day_end = _day_bounds(barbershop, day)
    return Appointment.objects.filter(
        barbershop=barbershop,
        customer_id=customer_id,
        status__in=ACTIVE_STATUSES,
        starts_at__gte=day_start,
        starts_at__lt=day_end,
    ).order_by("starts_at")


def _assert_slot(barbershop, starts_at: datetime, ends_at: datetime, *, appointment_id=None) -> None:
    now = timezone.now()
    if starts_at <= now:
        raise ValidationError("Não é permitido agendar no passado.")
    tz = ZoneInfo(barbershop.timezone)
    local_start, local_end = starts_at.astimezone(tz), ends_at.astimezone(tz)
    hours = OperatingHour.objects.filter(barbershop=barbershop, weekday=local_start.weekday(), active=True).first()
    if not hours or local_start.date() != local_end.date() or local_start.time() < hours.opens_at or local_end.time() > hours.closes_at:
        raise ValidationError("Horário fora do funcionamento da barbearia.")
    overlap = Appointment.objects.select_for_update().filter(
        barbershop=barbershop, status__in=ACTIVE_STATUSES, starts_at__lt=ends_at, ends_at__gt=starts_at
    )
    if appointment_id:
        overlap = overlap.exclude(pk=appointment_id)
    if overlap.exists() or ScheduleBlock.objects.filter(barbershop=barbershop, starts_at__lt=ends_at, ends_at__gt=starts_at).exists():
        raise ValidationError("Horário indisponível.")


@transaction.atomic
def create_appointment(*, barbershop, customer_id: int, service_id: int, starts_at: datetime, **data):
    _lock_tenant_schedule(barbershop.id)
    customer = Customer.objects.select_for_update().filter(pk=customer_id, barbershop=barbershop, active=True).first()
    service = Service.objects.filter(pk=service_id, barbershop=barbershop, active=True).first()
    if not customer or not service:
        raise ValidationError("Cliente ou serviço inválido para esta barbearia.")
    employee = data.get("employee")
    if employee and employee.barbershop_id != barbershop.id:
        raise ValidationError("Funcionário inválido para esta barbearia.")
    appointment_day = starts_at.astimezone(ZoneInfo(barbershop.timezone)).date()
    if active_appointments_for_day(
        barbershop=barbershop,
        customer_id=customer.id,
        day=appointment_day,
    ).select_for_update().exists():
        raise ValidationError(
            "Usuário já possui reserva ativa nesta data. "
            "Cancele a reserva existente antes de criar uma nova."
        )
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    _assert_slot(barbershop, starts_at, ends_at)
    raw_token = secrets.token_urlsafe(32)
    appointment = Appointment.objects.create(
        barbershop=barbershop, customer=customer, service=service, starts_at=starts_at,
        ends_at=ends_at, duration_minutes=service.duration_minutes,
        cancellation_token_hash=sha256(raw_token.encode()).hexdigest(),
        cancellation_token_expires_at=starts_at,
        **data,
    )
    return appointment, raw_token


@transaction.atomic
def update_appointment(*, appointment: Appointment, validated_data: dict) -> Appointment:
    _lock_tenant_schedule(appointment.barbershop_id)
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    customer = validated_data.get("customer", appointment.customer)
    service = validated_data.get("service", appointment.service)
    employee = validated_data.get("employee", appointment.employee)
    if any(obj and obj.barbershop_id != appointment.barbershop_id for obj in (customer, service, employee)):
        raise ValidationError("Registro inválido para esta barbearia.")
    starts_at = validated_data.get("starts_at", appointment.starts_at)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    schedule_changed = any(field in validated_data for field in ("customer", "service", "employee", "starts_at"))
    if schedule_changed:
        appointment_day = starts_at.astimezone(ZoneInfo(appointment.barbershop.timezone)).date()
        if active_appointments_for_day(
            barbershop=appointment.barbershop,
            customer_id=customer.id,
            day=appointment_day,
        ).select_for_update().exclude(pk=appointment.pk).exists():
            raise ValidationError(
                "Usuário já possui reserva ativa nesta data. "
                "Cancele a reserva existente antes de criar uma nova."
            )
        _assert_slot(appointment.barbershop, starts_at, ends_at, appointment_id=appointment.pk)
    for field in ("notes", "status"):
        if field in validated_data:
            setattr(appointment, field, validated_data[field])
    appointment.customer, appointment.service, appointment.employee = customer, service, employee
    appointment.starts_at, appointment.ends_at, appointment.duration_minutes = starts_at, ends_at, service.duration_minutes
    appointment.save()
    return appointment


@transaction.atomic
def cancel_with_token(raw_token: str) -> Appointment:
    token_hash = sha256(raw_token.encode()).hexdigest()
    appointment = Appointment.objects.select_for_update().filter(cancellation_token_hash=token_hash).first()
    if not appointment or appointment.status not in ACTIVE_STATUSES or not appointment.cancellation_token_expires_at or appointment.cancellation_token_expires_at <= timezone.now():
        raise ValidationError("Token inválido ou expirado.")
    appointment.status = Appointment.Status.CANCELLED
    appointment.cancellation_token_hash = str()
    appointment.save(update_fields=["status", "cancellation_token_hash", "updated_at"])
    return appointment


@transaction.atomic
def cancel_appointment(*, appointment: Appointment) -> Appointment:
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if appointment.status not in ACTIVE_STATUSES:
        raise ValidationError("Esta reserva não está ativa e não pode ser cancelada.")
    appointment.status = Appointment.Status.CANCELLED
    appointment.cancellation_token_hash = str()
    appointment.save(update_fields=["status", "cancellation_token_hash", "updated_at"])
    return appointment


def available_slots(*, barbershop, day, service: Service) -> list[datetime]:
    tz = ZoneInfo(barbershop.timezone)
    hours = OperatingHour.objects.filter(barbershop=barbershop, weekday=day.weekday(), active=True).first()
    if not hours:
        return []
    cursor = datetime.combine(day, hours.opens_at, tzinfo=tz)
    close = datetime.combine(day, hours.closes_at, tzinfo=tz)
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    appointments = list(Appointment.objects.filter(
        barbershop=barbershop,
        status__in=ACTIVE_STATUSES,
        starts_at__lt=close,
        ends_at__gt=day_start,
    ).values_list("starts_at", "ends_at"))
    blocks = list(ScheduleBlock.objects.filter(
        barbershop=barbershop,
        starts_at__lt=close,
        ends_at__gt=day_start,
    ).values_list("starts_at", "ends_at"))

    def overlaps(intervals, candidate_start: datetime, candidate_end: datetime) -> bool:
        return any(
            interval_start < candidate_end and interval_end > candidate_start
            for interval_start, interval_end in intervals
        )

    now = timezone.now()
    slots = []
    while cursor + timedelta(minutes=service.duration_minutes) <= close:
        end = cursor + timedelta(minutes=service.duration_minutes)
        if cursor > now and not overlaps(appointments, cursor, end) and not overlaps(blocks, cursor, end):
            slots.append(cursor)
        cursor += timedelta(minutes=SLOT_INTERVAL_MINUTES)
    return slots
