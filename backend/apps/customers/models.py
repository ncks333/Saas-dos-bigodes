from django.db import models
from core.utils.models import TenantModel


class Customer(TenantModel):
    name = models.CharField(max_length=150)
    whatsapp = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["barbershop", "whatsapp"], name="unique_customer_whatsapp_per_tenant")]
