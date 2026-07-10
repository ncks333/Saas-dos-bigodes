import requests
from django.conf import settings


class WhatsAppProvider:
    def send(self, recipient: str, message: str) -> dict:
        if not all((settings.WHATSAPP_BASE_URL, settings.WHATSAPP_API_KEY, settings.WHATSAPP_INSTANCE_NAME)):
            if settings.DEBUG:
                return {"simulated": True}
            raise RuntimeError("Provedor de WhatsApp não configurado.")
        response = requests.post(
            f"{settings.WHATSAPP_BASE_URL.rstrip('/')}/message/sendText/{settings.WHATSAPP_INSTANCE_NAME}",
            json={"number": recipient, "text": message},
            headers={"apikey": settings.WHATSAPP_API_KEY},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
