import os
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def production_environment(**overrides):
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "core.settings.production",
        "DJANGO_SECRET_KEY": "s" * 50,
        "JWT_SIGNING_KEY": "j" * 50,
        "ALLOWED_HOSTS": "api.example.com",
        "TURNSTILE_SECRET_KEY": "turnstile-secret",
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "FRONTEND_URL": "https://app.example.com",
        "WHATSAPP_GRAPH_API_VERSION": "v25.0",
        "WHATSAPP_PHONE_NUMBER_ID": "123456789",
        "WHATSAPP_ACCESS_TOKEN": "whatsapp-token",
        "WHATSAPP_TEMPLATE_LANGUAGE": "pt_BR",
        "WHATSAPP_CONFIRMATION_TEMPLATE": "confirmation",
        "WHATSAPP_REMINDER_TEMPLATE": "reminder",
        "ASAAS_API_KEY": "asaas-production-token",
        "ASAAS_API_URL": "https://api.asaas.com/v3",
        "ASAAS_CHECKOUT_BASE_URL": "https://www.asaas.com/checkoutSession/show",
    }
    environment.update(overrides)
    return environment


def import_production_settings(**overrides):
    return subprocess.run(
        [sys.executable, "-c", "import core.settings.production"],
        cwd=BACKEND_DIR,
        env=production_environment(**overrides),
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_require_asaas_api_key():
    result = import_production_settings(ASAAS_API_KEY="")

    assert result.returncode != 0
    assert "ASAAS_API_KEY" in result.stderr


def test_production_settings_require_https_asaas_urls():
    result = import_production_settings(ASAAS_API_URL="http://api.asaas.com/v3")

    assert result.returncode != 0
    assert "ASAAS_API_URL deve usar HTTPS" in result.stderr
