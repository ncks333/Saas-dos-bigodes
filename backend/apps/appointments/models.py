from django.conf import settings
from django.db import models
from core.utils.models import TenantModel


class Appointment(TenantModel):
    class Status(models.TextChoices):
        PENDING = "PENDENTE", "Pendente"
        CONFIRMED = "CONFIRMADO", "Confirmado"
        COMPLETED = "CONCLUIDO", "Concluído"
        CANCELLED = "CANCELADO", "Cancelado"
        NO_SHOW = "NAO_COMPARECEU", "Não compareceu"
        AWAITING = "AGUARDANDO_CONFIRMACAO", "Aguardando confirmação"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        ONLINE = "ONLINE", "Online"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="appointments")
    service = models.ForeignKey("services.Service", on_delete=models.PROTECT, related_name="appointments")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="appointments")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    cancellation_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    cancellation_token_expires_at = models.DateTimeField(null=True, blank=True)
    privacy_notice_accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["barbershop", "starts_at", "status"], name="appt_tenant_start_status_idx")]
        constraints = [models.UniqueConstraint(fields=["barbershop", "starts_at", "employee"], name="unique_employee_start_per_tenant")]


class ScheduleBlock(TenantModel):
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="block_end_after_start")]
