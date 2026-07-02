from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("appointments", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="privacy_notice_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
