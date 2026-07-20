from .base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ASAAS_API_URL = "https://api-sandbox.asaas.com/v3"
ASAAS_CHECKOUT_BASE_URL = "https://sandbox.asaas.com/checkoutSession/show"
ASAAS_API_KEY = "asaas-test-token"
ASAAS_CHECKOUT_EXPIRES_MINUTES = 60
