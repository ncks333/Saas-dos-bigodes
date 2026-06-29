from django.db import models
from core.utils.models import TenantModel


class NotificationLog(TenantModel):
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30)
    recipient = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="PENDING")
    provider_response = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["barbershop", "status", "created_at"], name="notif_tenant_status_time_idx")]
        constraints = [models.UniqueConstraint(fields=["appointment", "kind"], name="unique_notification_kind_per_appointment")]
