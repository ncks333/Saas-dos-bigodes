from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        EMPLOYEE = "FUNCIONARIO", "Funcionário"

    barbershop = models.ForeignKey(
        "barbershops.Barbershop", on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = ["email"]
