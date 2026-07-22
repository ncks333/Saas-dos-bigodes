from unittest.mock import Mock

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings

from core.email_backends import ResendEmailBackend


@override_settings(
    RESEND_API_KEY="resend-secret",
    DEFAULT_FROM_EMAIL="M&R BarberHub <nao-responda@mail.mrbarberhub.com.br>",
)
def test_resend_backend_sends_django_email(monkeypatch):
    response = Mock()
    monkeypatch.setattr("core.email_backends.requests.post", Mock(return_value=response))
    message = EmailMultiAlternatives(
        "Recuperação de senha",
        "Use o link seguro.",
        None,
        ["cliente@example.com"],
        cc=["copia@example.com"],
        bcc=["auditoria@example.com"],
        reply_to=["suporte@mrbarberhub.com.br"],
    )
    message.attach_alternative("<p>Use o link seguro.</p>", "text/html")

    sent = ResendEmailBackend().send_messages([message])

    assert sent == 1
    response.raise_for_status.assert_called_once_with()
    requests_post = __import__("core.email_backends", fromlist=["requests"]).requests.post
    requests_post.assert_called_once_with(
        "https://api.resend.com/emails",
        json={
            "from": "M&R BarberHub <nao-responda@mail.mrbarberhub.com.br>",
            "to": ["cliente@example.com"],
            "cc": ["copia@example.com"],
            "bcc": ["auditoria@example.com"],
            "reply_to": ["suporte@mrbarberhub.com.br"],
            "subject": "Recuperação de senha",
            "text": "Use o link seguro.",
            "html": "<p>Use o link seguro.</p>",
        },
        headers={"Authorization": "Bearer resend-secret"},
        timeout=10,
    )


@override_settings(RESEND_API_KEY="resend-secret")
def test_resend_backend_propagates_valid_billing_idempotency_key(monkeypatch):
    response = Mock()
    monkeypatch.setattr("core.email_backends.requests.post", Mock(return_value=response))
    message = EmailMultiAlternatives(
        "Cobrança",
        "Pagamento pendente.",
        None,
        ["admin@example.com"],
        headers={"Idempotency-Key": "billing-notification-123"},
    )

    assert ResendEmailBackend().send_messages([message]) == 1
    __import__(
        "core.email_backends", fromlist=["requests"]
    ).requests.post.assert_called_once_with(
        "https://api.resend.com/emails",
        json={
            "from": "nao-responda@bigodes.local",
            "to": ["admin@example.com"],
            "subject": "Cobrança",
            "text": "Pagamento pendente.",
        },
        headers={
            "Authorization": "Bearer resend-secret",
            "Idempotency-Key": "billing-notification-123",
        },
        timeout=10,
    )


@override_settings(RESEND_API_KEY="resend-secret")
def test_resend_backend_propagates_valid_regularization_idempotency_key(monkeypatch):
    response = Mock()
    monkeypatch.setattr("core.email_backends.requests.post", Mock(return_value=response))
    message = EmailMultiAlternatives(
        "Regularização",
        "Use o link seguro.",
        None,
        ["admin@example.com"],
        headers={"Idempotency-Key": "regularization-request-456"},
    )

    assert ResendEmailBackend().send_messages([message]) == 1
    __import__(
        "core.email_backends", fromlist=["requests"]
    ).requests.post.assert_called_once_with(
        "https://api.resend.com/emails",
        json={
            "from": "nao-responda@bigodes.local",
            "to": ["admin@example.com"],
            "subject": "Regularização",
            "text": "Use o link seguro.",
        },
        headers={
            "Authorization": "Bearer resend-secret",
            "Idempotency-Key": "regularization-request-456",
        },
        timeout=10,
    )

@override_settings(RESEND_API_KEY="resend-secret")
def test_resend_backend_ignores_invalid_or_non_billing_idempotency_key(monkeypatch):
    response = Mock()
    monkeypatch.setattr("core.email_backends.requests.post", Mock(return_value=response))
    message = EmailMultiAlternatives(
        "Assunto",
        "Texto",
        None,
        ["cliente@example.com"],
        headers={"Idempotency-Key": "billing-notification-1\r\nX-Injected: true"},
    )

    assert ResendEmailBackend().send_messages([message]) == 1
    __import__("core.email_backends", fromlist=["requests"]).requests.post.assert_called_once_with(
        "https://api.resend.com/emails",
        json={
            "from": "nao-responda@bigodes.local",
            "to": ["cliente@example.com"],
            "subject": "Assunto",
            "text": "Texto",
        },
        headers={"Authorization": "Bearer resend-secret"},
        timeout=10,
    )
@override_settings(RESEND_API_KEY="")
def test_resend_backend_requires_api_key():
    message = EmailMultiAlternatives("Assunto", "Texto", None, ["cliente@example.com"])

    with pytest.raises(ImproperlyConfigured, match="RESEND_API_KEY"):
        ResendEmailBackend().send_messages([message])


@override_settings(RESEND_API_KEY="resend-secret")
def test_resend_backend_respects_fail_silently(monkeypatch):
    monkeypatch.setattr(
        "core.email_backends.requests.post",
        Mock(side_effect=requests.Timeout("timeout")),
    )
    message = EmailMultiAlternatives("Assunto", "Texto", None, ["cliente@example.com"])

    assert ResendEmailBackend(fail_silently=True).send_messages([message]) == 0
    with pytest.raises(requests.Timeout):
        ResendEmailBackend(fail_silently=False).send_messages([message])
