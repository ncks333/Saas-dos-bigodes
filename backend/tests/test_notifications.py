from unittest.mock import Mock

from django.test import override_settings

from apps.notifications.providers import WhatsAppProvider


@override_settings(
    WHATSAPP_BASE_URL="https://whatsapp.example.com",
    WHATSAPP_API_KEY="secret",
    WHATSAPP_INSTANCE_NAME="barberhub",
)
def test_whatsapp_provider_uses_evolution_instance_route(monkeypatch):
    response = Mock()
    response.json.return_value = {"key": {"id": "message-id"}}
    monkeypatch.setattr("apps.notifications.providers.requests.post", Mock(return_value=response))

    result = WhatsAppProvider().send("5511999999999", "Confirmação")

    assert result == {"key": {"id": "message-id"}}
    response.raise_for_status.assert_called_once()
    requests_post = __import__("apps.notifications.providers", fromlist=["requests"]).requests.post
    requests_post.assert_called_once_with(
        "https://whatsapp.example.com/message/sendText/barberhub",
        json={"number": "5511999999999", "textMessage": {"text": "Confirmação"}},
        headers={"apikey": "secret"},
        timeout=10,
    )
