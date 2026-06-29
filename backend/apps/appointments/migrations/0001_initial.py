import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("barbershops", "0001_initial"), ("customers", "0001_initial"), ("services", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="ScheduleBlock", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("starts_at", models.DateTimeField()), ("ends_at", models.DateTimeField()), ("reason", models.CharField(blank=True, max_length=200)),
            ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="barbershops.barbershop")),
        ], options={"ordering": ["starts_at"], "constraints": [models.CheckConstraint(condition=models.Q(("ends_at__gt", models.F("starts_at"))), name="block_end_after_start")]}),
        migrations.CreateModel(name="Appointment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("starts_at", models.DateTimeField()), ("ends_at", models.DateTimeField()), ("duration_minutes", models.PositiveIntegerField()),
            ("notes", models.TextField(blank=True)),
            ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("CONFIRMADO", "Confirmado"), ("CONCLUIDO", "Concluído"), ("CANCELADO", "Cancelado"), ("NAO_COMPARECEU", "Não compareceu"), ("AGUARDANDO_CONFIRMACAO", "Aguardando confirmação")], default="PENDENTE", max_length=30)),
            ("source", models.CharField(choices=[("MANUAL", "Manual"), ("ONLINE", "Online")], default="MANUAL", max_length=10)),
            ("cancellation_token_hash", models.CharField(blank=True, db_index=True, max_length=64)),
            ("cancellation_token_expires_at", models.DateTimeField(blank=True, null=True)),
            ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="barbershops.barbershop")),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to="customers.customer")),
            ("employee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to=settings.AUTH_USER_MODEL)),
            ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to="services.service")),
        ], options={"ordering": ["starts_at"], "indexes": [models.Index(fields=["barbershop", "starts_at", "status"], name="appt_tenant_start_status_idx")], "constraints": [models.UniqueConstraint(fields=("barbershop", "starts_at", "employee"), name="unique_employee_start_per_tenant")]})
    ]
