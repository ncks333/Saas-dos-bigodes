import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    endpoint = "https://api.resend.com/emails"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        api_key = settings.RESEND_API_KEY
        if not api_key:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured("RESEND_API_KEY deve ser configurada")

        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": message.to,
                "subject": message.subject,
                "text": message.body,
            }
            for field in ("cc", "bcc", "reply_to"):
                value = getattr(message, field, None)
                if value:
                    payload[field] = value
            for content, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    payload["html"] = content
                    break
            try:
                response = requests.post(
                    self.endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                response.raise_for_status()
            except requests.RequestException:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
