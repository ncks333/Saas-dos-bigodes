import os
from datetime import time
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.barbershops.models import Barbershop, OperatingHour
from apps.billing.models import Subscription, SubscriptionPlan


class Command(BaseCommand):
    help = "Cria a primeira barbearia e seu administrador usando uma senha em variável de ambiente"

    def add_arguments(self, parser):
        parser.add_argument("--shop-name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--password-env", default="INITIAL_ADMIN_PASSWORD")

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv(options["password_env"], "")
        if not password:
            raise CommandError(f"Defina a variável temporária {options['password_env']}.")
        validate_password(password)
        if User.objects.filter(username=options["username"]).exists():
            raise CommandError("Este usuário já existe; nenhuma alteração foi feita.")

        shop = Barbershop.objects.create(name=options["shop_name"], slug=options["slug"])
        plan, _ = SubscriptionPlan.objects.get_or_create(
            code="barberhub",
            defaults={"name": "BarberHub", "amount": Decimal("79.90"), "trial_days": 30},
        )
        Subscription.objects.create(barbershop=shop, plan=plan, status=Subscription.Status.ACTIVE)
        for weekday in range(6):
            OperatingHour.objects.create(
                barbershop=shop,
                weekday=weekday,
                opens_at=time(8),
                closes_at=time(18),
            )
        User.objects.create_user(
            username=options["username"],
            email=options["email"],
            password=password,
            barbershop=shop,
            role=User.Role.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS("Barbearia e administrador criados. Remova a variável de senha agora."))
