import requests
from django.conf import settings


class WhatsAppProvider:
    def send(self, recipient: str, message: str) -> dict:
        if not settings.WHATSAPP_BASE_URL or not settings.WHATSAPP_API_KEY:
            if settings.DEBUG:
                return {"simulated": True}
            raise RuntimeError("Provedor de WhatsApp não configurado.")
        response = requests.post(
            f"{settings.WHATSAPP_BASE_URL.rstrip('/')}/message/sendText",
            json={"number": recipient, "text": message},
            headers={"apikey": settings.WHATSAPP_API_KEY},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
