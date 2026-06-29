from django.db import models
from core.utils.models import TimestampedModel


class Barbershop(TimestampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=50, default="America/Sao_Paulo")
    active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class OperatingHour(TimestampedModel):
    barbershop = models.ForeignKey(Barbershop, on_delete=models.CASCADE, related_name="operating_hours")
    weekday = models.PositiveSmallIntegerField()
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["barbershop", "weekday"], name="unique_operating_day")]
