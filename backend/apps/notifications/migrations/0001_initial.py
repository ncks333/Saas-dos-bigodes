import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("appointments", "0001_initial"), ("barbershops", "0001_initial")]
    operations = [migrations.CreateModel(name="NotificationLog", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("kind", models.CharField(max_length=30)), ("recipient", models.CharField(max_length=20)),
        ("status", models.CharField(default="PENDING", max_length=20)), ("provider_response", models.JSONField(blank=True, default=dict)),
        ("sent_at", models.DateTimeField(blank=True, null=True)),
        ("appointment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="appointments.appointment")),
        ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="barbershops.barbershop")),
    ], options={"indexes": [models.Index(fields=["barbershop", "status", "created_at"], name="notif_tenant_status_time_idx")], "constraints": [models.UniqueConstraint(fields=("appointment", "kind"), name="unique_notification_kind_per_appointment")]})]
