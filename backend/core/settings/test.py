from .base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ASAAS_API_URL = "https://api-sandbox.asaas.com/v3"
ASAAS_CHECKOUT_BASE_URL = "https://sandbox.asaas.com/checkoutSession/show"
ASAAS_CHECKOUT_ALLOWED_ORIGINS = ["https://sandbox.asaas.com"]
ASAAS_API_KEY = "asaas-test-token"
ASAAS_WEBHOOK_TOKEN = "asaas-webhook-test-token"
ASAAS_CHECKOUT_EXPIRES_MINUTES = 60
ASAAS_PROVIDER_TIMEZONE = "America/Sao_Paulo"
BILLING_PUBLIC_PLAN_CODE = "barberhub"
