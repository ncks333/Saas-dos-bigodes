import os

# ruff: noqa: F405

from .base import *  # noqa: F403

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://mr-barberhub.vercel.app")

if SECRET_KEY == INSECURE_DEFAULT_SECRET or SECRET_KEY.startswith("troque-") or len(SECRET_KEY) < 50:  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY deve ser configurada em produção")
if not JWT_SIGNING_KEY or JWT_SIGNING_KEY == SECRET_KEY or len(JWT_SIGNING_KEY) < 50:  # noqa: F405
    raise RuntimeError("JWT_SIGNING_KEY deve ser longa e diferente de DJANGO_SECRET_KEY")
if not ALLOWED_HOSTS or any(host in {"*", "localhost", "127.0.0.1"} for host in ALLOWED_HOSTS):  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS deve conter apenas os domínios públicos da API")
if not TURNSTILE_SECRET_KEY:  # noqa: F405
    raise RuntimeError("TURNSTILE_SECRET_KEY deve ser configurada em produção")
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":  # noqa: F405
    raise RuntimeError("Configure um EMAIL_BACKEND transacional em produção")
if EMAIL_BACKEND == "core.email_backends.ResendEmailBackend" and not RESEND_API_KEY:  # noqa: F405
    raise RuntimeError("RESEND_API_KEY deve ser configurada para o backend Resend")
if not FRONTEND_URL.startswith("https://"):  # noqa: F405
    raise RuntimeError("FRONTEND_URL deve usar HTTPS em produção")
if not all((
    WHATSAPP_GRAPH_API_VERSION, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_TEMPLATE_LANGUAGE, WHATSAPP_CONFIRMATION_TEMPLATE, WHATSAPP_REMINDER_TEMPLATE,
)):  # noqa: F405
    raise RuntimeError("Configure token, número e templates do WhatsApp Cloud API")

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
