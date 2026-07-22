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
        "ASAAS_API_KEY": "a" * 40,
        "ASAAS_API_URL": "https://api.asaas.com/v3",
        "ASAAS_CHECKOUT_BASE_URL": "https://www.asaas.com/checkoutSession/show",
        "ASAAS_CHECKOUT_ALLOWED_ORIGINS": "https://asaas.com,https://www.asaas.com",
        "ASAAS_WEBHOOK_TOKEN": "w" * 64,
        "ASAAS_CHECKOUT_EXPIRES_MINUTES": "60",
        "ASAAS_PROVIDER_TIMEZONE": "America/Sao_Paulo",
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


def test_production_settings_require_strong_asaas_api_key():
    result = import_production_settings(ASAAS_API_KEY="short")

    assert result.returncode != 0
    assert "ASAAS_API_KEY" in result.stderr


def test_production_settings_require_asaas_webhook_token():
    result = import_production_settings(ASAAS_WEBHOOK_TOKEN="")

    assert result.returncode != 0
    assert "ASAAS_WEBHOOK_TOKEN" in result.stderr


def test_production_settings_require_https_asaas_urls():
    result = import_production_settings(ASAAS_API_URL="http://api.asaas.com/v3")

    assert result.returncode != 0
    assert "ASAAS_API_URL deve usar HTTPS" in result.stderr


def test_production_settings_require_exact_asaas_hosts():
    for overrides, expected in [
        ({"ASAAS_API_URL": "https://evil.example/v3"}, "ASAAS_API_URL"),
        (
            {"ASAAS_CHECKOUT_BASE_URL": "https://evil.example/checkout"},
            "ASAAS_CHECKOUT_BASE_URL",
        ),
    ]:
        result = import_production_settings(**overrides)
        assert result.returncode != 0
        assert expected in result.stderr


def test_production_settings_require_strong_independent_webhook_token():
    for token in ["short", "a" * 40]:
        result = import_production_settings(ASAAS_WEBHOOK_TOKEN=token)
        assert result.returncode != 0
        assert "ASAAS_WEBHOOK_TOKEN" in result.stderr


def test_production_settings_require_documented_checkout_expiry_range():
    for minutes in ["9", "1441"]:
        result = import_production_settings(ASAAS_CHECKOUT_EXPIRES_MINUTES=minutes)
        assert result.returncode != 0
        assert "ASAAS_CHECKOUT_EXPIRES_MINUTES" in result.stderr


def test_production_settings_require_valid_provider_timezone():
    result = import_production_settings(ASAAS_PROVIDER_TIMEZONE="Mars/Olympus")

    assert result.returncode != 0
    assert "ASAAS_PROVIDER_TIMEZONE" in result.stderr
