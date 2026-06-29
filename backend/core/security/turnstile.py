import requests
from django.conf import settings


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    if settings.DEBUG and not settings.TURNSTILE_SECRET_KEY:
        return True
    if not token or not settings.TURNSTILE_SECRET_KEY:
        return False
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": remote_ip},
            timeout=5,
        )
        return bool(response.ok and response.json().get("success"))
    except (requests.RequestException, ValueError):
        return False
