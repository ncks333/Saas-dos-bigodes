from django.core.validators import MinValueValidator
from django.db import models
from core.utils.models import TenantModel


class Service(TenantModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(5)])
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["barbershop", "name"], name="unique_service_name_per_tenant")]
