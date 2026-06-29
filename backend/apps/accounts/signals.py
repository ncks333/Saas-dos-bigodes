from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
import logging

logger = logging.getLogger("security")


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    logger.warning("Falha de login para usuário=%s ip=%s", credentials.get("username"), request.META.get("REMOTE_ADDR") if request else None)
