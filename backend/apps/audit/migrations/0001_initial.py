import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("barbershops", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="AuditEvent", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("action", models.CharField(max_length=60)), ("target_type", models.CharField(blank=True, max_length=100)),
        ("target_id", models.CharField(blank=True, max_length=64)), ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
        ("metadata", models.JSONField(blank=True, default=dict)),
        ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
        ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="barbershops.barbershop")),
    ], options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["barbershop", "action", "created_at"], name="audit_tenant_action_time_idx")]})]
