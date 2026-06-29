import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("barbershops", "0001_initial")]
    operations = [migrations.CreateModel(name="Customer", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("name", models.CharField(max_length=150)), ("whatsapp", models.CharField(max_length=20)),
        ("notes", models.TextField(blank=True)), ("active", models.BooleanField(default=True)),
        ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="barbershops.barbershop")),
    ], options={"ordering": ["name"], "constraints": [models.UniqueConstraint(fields=("barbershop", "whatsapp"), name="unique_customer_whatsapp_per_tenant")]})]
