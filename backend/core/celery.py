import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

app = Celery("saas_dos_bigodes")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
