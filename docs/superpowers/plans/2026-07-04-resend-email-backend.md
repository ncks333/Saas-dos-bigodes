# Resend Email Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send Django transactional email through the Resend HTTPS API so password recovery works on Railway plans that block SMTP.

**Architecture:** Add one reusable Django email backend that translates `EmailMessage` objects into Resend `/emails` requests. Existing `send_mail()` callers remain unchanged, tests keep the in-memory backend, and production explicitly requires a Resend API key when the new backend is selected.

**Tech Stack:** Python 3.13, Django, `requests`, pytest, pytest-django, Ruff, Resend Email API

## Global Constraints

- Use `https://api.resend.com/emails` with a ten-second timeout.
- Read authentication only from `RESEND_API_KEY`; never log or commit it.
- Use `DEFAULT_FROM_EMAIL` for the sender.
- Preserve Django's `fail_silently` behavior.
- Keep SMTP and in-memory backends available outside production.
- Do not add a new Python dependency; `requests>=2.32,<3` already exists.

---

### Task 1: Resend Django email backend

**Files:**
- Create: `backend/core/email_backends.py`
- Create: `backend/tests/test_email_backend.py`

**Interfaces:**
- Consumes: Django `EmailMessage` / `EmailMultiAlternatives`, `settings.RESEND_API_KEY`, and `settings.DEFAULT_FROM_EMAIL`.
- Produces: `core.email_backends.ResendEmailBackend.send_messages(email_messages: list[EmailMessage]) -> int`.

- [ ] **Step 1: Write failing provider tests**

Create `backend/tests/test_email_backend.py`:

```python
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
```

- [ ] **Step 2: Run tests and confirm expected failure**

Run:

```bash
docker compose run --rm backend pytest tests/test_email_backend.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'core.email_backends'`.

- [ ] **Step 3: Implement minimal reusable backend**

Create `backend/core/email_backends.py`:

```python
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
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
docker compose run --rm backend pytest tests/test_email_backend.py tests/test_api_flows.py::test_password_user_and_session_flows -q
```

Expected: all tests pass; the API flow still uses Django's in-memory test backend.

- [ ] **Step 5: Commit backend and tests**

```bash
git add backend/core/email_backends.py backend/tests/test_email_backend.py
git commit -m "feat: adiciona backend de email via Resend"
```

---

### Task 2: Production configuration and deployment documentation

**Files:**
- Modify: `backend/core/settings/base.py:137-145`
- Modify: `backend/core/settings/production.py:14-15`
- Modify: `backend/.env.production.example:21-29`
- Modify: `docs/DEPLOY.md:71-83`

**Interfaces:**
- Consumes: `core.email_backends.ResendEmailBackend` from Task 1.
- Produces: `settings.RESEND_API_KEY: str` and an explicit production startup check.

- [ ] **Step 1: Expose Resend configuration in base settings**

Add immediately after `DEFAULT_FROM_EMAIL` in `backend/core/settings/base.py`:

```python
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
```

- [ ] **Step 2: Require the key when production selects Resend**

Replace the email validation block in `backend/core/settings/production.py` with:

```python
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":  # noqa: F405
    raise RuntimeError("Configure um EMAIL_BACKEND transacional em produção")
if EMAIL_BACKEND == "core.email_backends.ResendEmailBackend" and not RESEND_API_KEY:  # noqa: F405
    raise RuntimeError("RESEND_API_KEY deve ser configurada para o backend Resend")
```

- [ ] **Step 3: Replace SMTP variables in the production template**

Replace lines 21-27 of `backend/.env.production.example` with:

```text
EMAIL_BACKEND=core.email_backends.ResendEmailBackend
RESEND_API_KEY=cole-a-chave-restrita-de-envio-do-resend
DEFAULT_FROM_EMAIL="M&R BarberHub <nao-responda@mail.seudominio.com>"
```

- [ ] **Step 4: Update deployment guidance**

Replace the SMTP paragraph in `docs/DEPLOY.md` with:

````markdown
Para e-mail transacional em Railway Free, Trial ou Hobby, use a API HTTPS do Resend; SMTP de saída é bloqueado nesses planos. Verifique um subdomínio de envio, crie uma chave restrita e cadastre:

```text
EMAIL_BACKEND=core.email_backends.ResendEmailBackend
DEFAULT_FROM_EMAIL=M&R BarberHub <nao-responda@mail.seudominio.com>
```

Cadastre `RESEND_API_KEY` como secret diretamente no painel Railway. Defina `FRONTEND_URL=https://app.seudominio.com` para os links de recuperação e mantenha `PASSWORD_RESET_TIMEOUT=3600` para expiração em uma hora. Nunca coloque a chave Resend no frontend ou no repositório.
````

- [ ] **Step 5: Run configuration checks**

Run:

```bash
docker compose run --rm backend ruff check core tests
docker compose run --rm backend pytest tests/test_email_backend.py tests/test_api_flows.py::test_password_user_and_session_flows -q
```

Expected: Ruff exits zero and all selected tests pass.

- [ ] **Step 6: Commit settings and docs**

```bash
git add backend/core/settings/base.py backend/core/settings/production.py backend/.env.production.example docs/DEPLOY.md
git commit -m "docs: configura Resend para produção"
```

---

### Task 3: Full verification and Railway rollout

**Files:**
- Verify only: repository and Railway variables

**Interfaces:**
- Consumes: commits from Tasks 1 and 2.
- Produces: a deployed API capable of delivering password-reset email through Resend.

- [ ] **Step 1: Run complete backend quality checks**

```bash
docker compose run --rm backend ruff check .
docker compose run --rm backend pytest
```

Expected: Ruff exits zero; pytest meets the configured 80% coverage threshold.

- [ ] **Step 2: Confirm no secret entered version control**

```bash
git diff --check
git grep -n "re_[A-Za-z0-9]" -- ':!docs/superpowers/**'
git status --short
```

Expected: `git diff --check` succeeds, grep prints nothing, and the working tree is clean.

- [ ] **Step 3: Push implementation commits**

```bash
git push origin main
```

Expected: GitHub accepts both commits and Railway begins a deployment from the latest commit.

- [ ] **Step 4: Apply Railway variables after the code push**

Set these values on the API service and deploy the pending variable changes:

```text
EMAIL_BACKEND=core.email_backends.ResendEmailBackend
DEFAULT_FROM_EMAIL=M&R BarberHub <nao-responda@mail.mrbarberhub.com.br>
```

Mantenha sem alteração o valor secreto de `RESEND_API_KEY` que já está salvo na Railway.

Remove `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `EMAIL_USE_TLS` only after the new deployment reports healthy.

- [ ] **Step 5: Validate production behavior**

Open `https://app.mrbarberhub.com.br/recuperar-senha`, request one reset for the administrator email, and verify:

```text
API response: 200
Resend event: Delivered
Reset link host: app.mrbarberhub.com.br
Reset link expiry: 1 hour
```

- [ ] **Step 6: Roll back on failure**

If health checks or delivery fail, restore the previous Railway deployment, retain `RESEND_API_KEY`, and inspect Resend Logs without exposing the Authorization header. Do not restore Gmail SMTP on a Railway Trial/Hobby service because outbound SMTP remains blocked.
