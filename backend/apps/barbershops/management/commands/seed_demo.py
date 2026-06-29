from datetime import time
from decimal import Decimal
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour
from apps.services.models import Service


class Command(BaseCommand):
    help = "Cria uma barbearia e um administrador de demonstração"

    def handle(self, *args, **options):
        shop, _ = Barbershop.objects.get_or_create(slug="bigodes", defaults={"name": "SaaS dos Bigodes"})
        for weekday in range(6):
            OperatingHour.objects.get_or_create(barbershop=shop, weekday=weekday, defaults={"opens_at": time(8), "closes_at": time(18)})
        for name, price, duration in [("Corte", "50", 30), ("Barba", "35", 30), ("Corte + Barba", "80", 60)]:
            Service.objects.get_or_create(barbershop=shop, name=name, defaults={"price": Decimal(price), "duration_minutes": duration})
        user, created = User.objects.get_or_create(username="admin", defaults={"email": "admin@bigodes.local", "barbershop": shop, "role": User.Role.ADMIN})
        if created:
            user.set_password("Bigodes123")
            user.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS("Demo criada: admin / Bigodes123 (troque a senha no primeiro acesso)."))
