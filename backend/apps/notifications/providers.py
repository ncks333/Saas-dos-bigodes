import requests
from django.conf import settings


class WhatsAppProvider:
    def send_template(self, recipient: str, template_name: str, parameters: list[str]) -> dict:
        if not all((settings.WHATSAPP_PHONE_NUMBER_ID, settings.WHATSAPP_ACCESS_TOKEN)):
            if settings.DEBUG:
                return {"simulated": True}
            raise RuntimeError("Provedor de WhatsApp não configurado.")

        response = requests.post(
            (
                f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_API_VERSION}/"
                f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
            ),
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
                    "components": [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": parameter}
                            for parameter in parameters
                        ],
                    }],
                },
            },
            headers={
                "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
