from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="Barbershop", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=150)), ("slug", models.SlugField(max_length=80, unique=True)),
            ("whatsapp", models.CharField(blank=True, max_length=20)), ("timezone", models.CharField(default="America/Sao_Paulo", max_length=50)),
            ("active", models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name="OperatingHour", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("weekday", models.PositiveSmallIntegerField()), ("opens_at", models.TimeField()), ("closes_at", models.TimeField()),
            ("active", models.BooleanField(default=True)),
            ("barbershop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operating_hours", to="barbershops.barbershop")),
        ], options={"constraints": [models.UniqueConstraint(fields=("barbershop", "weekday"), name="unique_operating_day")]})
    ]
