from unittest.mock import Mock

import pytest
import requests
from django.test import override_settings

from apps.notifications.providers import WhatsAppProvider


META_SETTINGS = {
    "WHATSAPP_GRAPH_API_VERSION": "v25.0",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789012345",
    "WHATSAPP_ACCESS_TOKEN": "secret-token",
    "WHATSAPP_TEMPLATE_LANGUAGE": "pt_BR",
}


@override_settings(**META_SETTINGS)
def test_whatsapp_provider_sends_meta_template(monkeypatch):
    response = Mock()
    response.json.return_value = {"messages": [{"id": "wamid.message-id"}]}
    requests_post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", requests_post)

    result = WhatsAppProvider().send_template(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "15/07 às 14:00"],
    )

    assert result == {"messages": [{"id": "wamid.message-id"}]}
    response.raise_for_status.assert_called_once_with()
    requests_post.assert_called_once_with(
        "https://graph.facebook.com/v25.0/123456789012345/messages",
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "5511999999999",
            "type": "template",
            "template": {
                "name": "barberhub_agendamento_recebido",
                "language": {"code": "pt_BR"},
                "components": [{
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Nick"},
                        {"type": "text", "text": "Corte"},
                        {"type": "text", "text": "15/07 às 14:00"},
                    ],
                }],
            },
        },
        headers={
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
        },
        timeout=10,
    )


@override_settings(**META_SETTINGS)
def test_whatsapp_provider_propagates_meta_http_error(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
    monkeypatch.setattr("apps.notifications.providers.requests.post", Mock(return_value=response))

    with pytest.raises(requests.HTTPError, match="503 Server Error"):
        WhatsAppProvider().send_template(
            "5511999999999",
            "barberhub_agendamento_recebido",
            ["Nick", "Corte", "15/07 às 14:00"],
        )


@override_settings(
    DEBUG=True,
    WHATSAPP_GRAPH_API_VERSION="v25.0",
    WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_ACCESS_TOKEN="",
    WHATSAPP_TEMPLATE_LANGUAGE="pt_BR",
)
def test_whatsapp_provider_simulates_when_development_is_unconfigured():
    result = WhatsAppProvider().send_template(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "15/07 às 14:00"],
    )

    assert result == {"simulated": True}
