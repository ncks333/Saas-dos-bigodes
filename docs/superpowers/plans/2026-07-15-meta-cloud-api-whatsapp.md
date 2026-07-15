# Meta Cloud API WhatsApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the remaining Evolution adapter with the official Meta WhatsApp Cloud API and deliver three real notifications: booking received, 24-hour reminder, and 1-hour reminder.

**Architecture:** Keep the existing `NotificationLog` and Celery task flow. A focused `WhatsAppProvider.send_template()` adapter posts approved `UTILITY` templates to Meta Graph API v25.0; one confirmation template and one reusable reminder template produce the three sends. Railway keeps the existing API and adds/reactivates one combined Celery worker+beat service only after Meta secrets and templates are ready.

**Tech Stack:** Django 5.2, requests, Celery 5.5, django-celery-beat, Redis, pytest, Railway, Meta Graph API v25.0

## Global Constraints

- Use only official WhatsApp Cloud API; never deploy Evolution API, Baileys, or another unofficial provider.
- Produce exactly three notification events: immediate booking receipt, 24-hour reminder, and 1-hour reminder.
- Use exactly two Meta `UTILITY` templates: `barberhub_agendamento_recebido` and reusable `barberhub_lembrete_agendamento`, both `pt_BR`.
- Keep `NotificationLog` idempotency, Celery retries, tenant isolation, and current appointment statuses.
- Do not add a webhook, inbox, chatbot, campaigns, marketing messages, or a database migration.
- Never commit or print `WHATSAPP_ACCESS_TOKEN`; store it only as a Railway secret.
- Do not modify or stage the user's existing uncommitted frontend work.
- Reactivate Celery jobs only after the Meta templates are approved and all Railway secrets exist.

## File Structure

- `backend/apps/notifications/providers.py`: only HTTP transport and Meta template payload construction.
- `backend/apps/notifications/tasks.py`: appointment-to-template parameter mapping, idempotency, scheduling, and Celery retries.
- `backend/core/settings/base.py`: environment-backed Meta configuration with development defaults.
- `backend/core/settings/production.py`: fail-fast production validation for required Meta settings.
- `backend/tests/test_notifications.py`: provider contract, three event paths, scheduling, and idempotency.
- `backend/.env.production.example`: safe variable names and non-secret examples.
- `backend/railway.jobs.toml`: combined worker+beat process; no Redis purge on normal startup.
- `docs/DEPLOY.md`: official Meta setup, template, Railway, smoke-test, and rollback runbook.

---

### Task 1: Meta Cloud API provider and settings

**Files:**
- Modify: `backend/tests/test_notifications.py:1-44`
- Modify: `backend/apps/notifications/providers.py:1-18`
- Modify: `backend/core/settings/base.py:147-150`
- Modify: `backend/core/settings/production.py:20-21`

**Interfaces:**
- Consumes: Django settings `WHATSAPP_GRAPH_API_VERSION`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_TEMPLATE_LANGUAGE`.
- Produces: `WhatsAppProvider.send_template(recipient: str, template_name: str, parameters: list[str]) -> dict`.

- [ ] **Step 1: Replace provider tests with failing Meta contract tests**

Replace `backend/tests/test_notifications.py` with:

```python
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
```

- [ ] **Step 2: Run provider tests and verify they fail**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
```

Expected: FAIL because `WhatsAppProvider` has no `send_template` method.

- [ ] **Step 3: Replace Evolution settings with Meta settings**

Replace the three WhatsApp settings at the end of `backend/core/settings/base.py` with:

```python
WHATSAPP_GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v25.0")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR")
WHATSAPP_CONFIRMATION_TEMPLATE = os.getenv("WHATSAPP_CONFIRMATION_TEMPLATE", "barberhub_agendamento_recebido")
WHATSAPP_REMINDER_TEMPLATE = os.getenv("WHATSAPP_REMINDER_TEMPLATE", "barberhub_lembrete_agendamento")
```

Replace the WhatsApp production validation in `backend/core/settings/production.py` with:

```python
if not all((
    WHATSAPP_GRAPH_API_VERSION, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_TEMPLATE_LANGUAGE, WHATSAPP_CONFIRMATION_TEMPLATE, WHATSAPP_REMINDER_TEMPLATE,
)):  # noqa: F405
    raise RuntimeError("Configure token, número e templates do WhatsApp Cloud API")
```

- [ ] **Step 4: Implement the minimal Meta provider**

Replace `backend/apps/notifications/providers.py` with:

```python
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
```

- [ ] **Step 5: Run provider tests and verify they pass**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
ruff check apps/notifications/providers.py core/settings/base.py core/settings/production.py tests/test_notifications.py
```

Expected: three tests PASS; Ruff exits `0`.

- [ ] **Step 6: Commit provider and settings**

```bash
git add backend/apps/notifications/providers.py backend/core/settings/base.py backend/core/settings/production.py backend/tests/test_notifications.py
git commit -m "feat: send WhatsApp templates through Meta Cloud API"
```

---

### Task 2: Three notification events and idempotency

**Files:**
- Modify: `backend/tests/test_notifications.py`
- Modify: `backend/apps/notifications/tasks.py:1-49`

**Interfaces:**
- Consumes: `WhatsAppProvider.send_template(recipient, template_name, parameters)` from Task 1 and settings `WHATSAPP_CONFIRMATION_TEMPLATE` / `WHATSAPP_REMINDER_TEMPLATE`.
- Produces: `_template_parameters(appointment: Appointment) -> list[str]`; unchanged Celery task names `send_appointment_confirmation`, `enqueue_due_reminders`, and `send_appointment_reminder`.

- [ ] **Step 1: Add failing task tests**

Extend the import block at the top of `backend/tests/test_notifications.py` to include:

```python
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests
from django.test import override_settings
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.customers.models import Customer
from apps.notifications.models import NotificationLog
from apps.notifications.providers import WhatsAppProvider
from apps.notifications.tasks import (
    enqueue_due_reminders,
    send_appointment_confirmation,
    send_appointment_reminder,
)
from apps.services.models import Service
```

Then append these helpers and tests after the provider tests:

```python
def make_appointment(
    barbershop,
    starts_at,
    status=Appointment.Status.PENDING,
    sequence=1,
):
    customer_name = "Nick" if sequence == 1 else f"Nick {sequence}"
    whatsapp = "5511999999999" if sequence == 1 else f"55118888888{sequence:02d}"
    service_name = "Corte" if sequence == 1 else f"Corte {sequence}"

    customer = Customer.objects.create(
        barbershop=barbershop,
        name=customer_name,
        whatsapp=whatsapp,
    )
    service = Service.objects.create(
        barbershop=barbershop,
        name=service_name,
        price="50.00",
        duration_minutes=30,
    )
    return Appointment.objects.create(
        barbershop=barbershop,
        customer=customer,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        duration_minutes=30,
        status=status,
    )


@pytest.mark.django_db
@override_settings(
    WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido",
    WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento",
)
def test_confirmation_uses_booking_received_template(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at, Appointment.Status.AWAITING)
    send_template = Mock(return_value={"messages": [{"id": "wamid.confirmation"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)

    send_template.assert_called_once_with(
        "5511999999999",
        "barberhub_agendamento_recebido",
        ["Nick", "Corte", "16/07 às 14:00"],
    )
    log = NotificationLog.objects.get(appointment=appointment, kind="CONFIRMATION")
    assert log.status == "SENT"
    assert log.provider_response == {"messages": [{"id": "wamid.confirmation"}]}


@pytest.mark.django_db
@pytest.mark.parametrize(("hours", "kind"), [(24, "REMINDER_24H"), (1, "REMINDER_1H")])
@override_settings(WHATSAPP_REMINDER_TEMPLATE="barberhub_lembrete_agendamento")
def test_reminders_reuse_one_meta_template(monkeypatch, barbershop, hours, kind):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": f"wamid.{hours}h"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_reminder.run(appointment.id, hours)

    send_template.assert_called_once_with(
        "5511999999999",
        "barberhub_lembrete_agendamento",
        ["Nick", "Corte", "16/07 às 14:00"],
    )
    assert NotificationLog.objects.get(appointment=appointment, kind=kind).status == "SENT"


@pytest.mark.django_db
@override_settings(WHATSAPP_CONFIRMATION_TEMPLATE="barberhub_agendamento_recebido")
def test_sent_confirmation_is_idempotent(monkeypatch, barbershop):
    starts_at = datetime(2026, 7, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    appointment = make_appointment(barbershop, starts_at)
    send_template = Mock(return_value={"messages": [{"id": "wamid.once"}]})
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppProvider.send_template", send_template)

    send_appointment_confirmation.run(appointment.id)
    send_appointment_confirmation.run(appointment.id)

    send_template.assert_called_once()
    assert NotificationLog.objects.filter(appointment=appointment, kind="CONFIRMATION").count() == 1


@pytest.mark.django_db
def test_scheduler_enqueues_24h_and_1h_reminders(monkeypatch, barbershop):
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    reminder_24h = make_appointment(barbershop, now + timedelta(hours=24))
    reminder_1h = make_appointment(barbershop, now + timedelta(hours=1), sequence=2)
    delay = Mock()
    monkeypatch.setattr(timezone, "now", lambda: now)
    monkeypatch.setattr("apps.notifications.tasks.send_appointment_reminder.delay", delay)

    enqueue_due_reminders.run()

    assert delay.call_count == 2
    delay.assert_any_call(reminder_24h.id, 24)
    delay.assert_any_call(reminder_1h.id, 1)
```

- [ ] **Step 2: Run task tests and verify they fail**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
```

Expected: provider tests PASS; new task tests FAIL because tasks still call `WhatsAppProvider.send`.

- [ ] **Step 3: Implement template parameters and the three event paths**

Replace `backend/apps/notifications/tasks.py` with:

```python
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.appointments.models import Appointment
from .models import NotificationLog
from .providers import WhatsAppProvider


def _template_parameters(appointment: Appointment) -> list[str]:
    local_start = timezone.localtime(appointment.starts_at)
    return [
        appointment.customer.name,
        appointment.service.name,
        local_start.strftime("%d/%m às %H:%M"),
    ]


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_appointment_confirmation(self, appointment_id: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind="CONFIRMATION",
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    log.provider_response = WhatsAppProvider().send_template(
        log.recipient,
        settings.WHATSAPP_CONFIRMATION_TEMPLATE,
        _template_parameters(appointment),
    )
    log.status = "SENT"
    log.sent_at = timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])


@shared_task
def enqueue_due_reminders():
    now = timezone.now()
    for hours in (24, 1):
        start = now + timedelta(hours=hours, minutes=-5)
        end = now + timedelta(hours=hours, minutes=5)
        ids = Appointment.objects.filter(
            status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
            starts_at__range=(start, end),
        ).values_list("id", flat=True)
        for appointment_id in ids:
            send_appointment_reminder.delay(appointment_id, hours)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_appointment_reminder(self, appointment_id: int, hours: int):
    appointment = Appointment.objects.select_related("customer", "service").get(pk=appointment_id)
    kind = f"REMINDER_{hours}H"
    log, created = NotificationLog.objects.get_or_create(
        barbershop=appointment.barbershop,
        appointment=appointment,
        kind=kind,
        defaults={"recipient": appointment.customer.whatsapp},
    )
    if not created and log.status == "SENT":
        return
    log.provider_response = WhatsAppProvider().send_template(
        log.recipient,
        settings.WHATSAPP_REMINDER_TEMPLATE,
        _template_parameters(appointment),
    )
    log.status = "SENT"
    log.sent_at = timezone.now()
    log.save(update_fields=["provider_response", "status", "sent_at", "updated_at"])
```

- [ ] **Step 4: Run notification tests and verify they pass**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
ruff check apps/notifications/tasks.py tests/test_notifications.py
```

Expected: eight tests PASS (three provider tests, confirmation, two parameterized reminders, idempotency, scheduler); Ruff exits `0`.

- [ ] **Step 5: Commit notification tasks**

```bash
git add backend/apps/notifications/tasks.py backend/tests/test_notifications.py
git commit -m "feat: send three appointment notifications"
```

---

### Task 3: Railway jobs activation and deployment documentation

**Files:**
- Modify: `backend/.env.production.example`
- Modify: `backend/railway.jobs.toml`
- Modify: `docs/DEPLOY.md:41-158`

**Interfaces:**
- Consumes: Meta setting names from Task 1 and Celery task names from Task 2.
- Produces: one deployable `barberhub-jobs` service running worker+beat and an exact operator runbook.

- [ ] **Step 1: Replace Evolution variables in the production example**

Replace the WhatsApp block in `backend/.env.production.example` with:

```text
# Meta WhatsApp Cloud API. Nunca grave valores reais neste arquivo.
WHATSAPP_GRAPH_API_VERSION=v25.0
WHATSAPP_PHONE_NUMBER_ID=cole-o-phone-number-id
WHATSAPP_ACCESS_TOKEN=cole-o-token-do-usuario-do-sistema
WHATSAPP_WABA_ID=cole-o-id-da-conta-mr-barberhub
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
WHATSAPP_CONFIRMATION_TEMPLATE=barberhub_agendamento_recebido
WHATSAPP_REMINDER_TEMPLATE=barberhub_lembrete_agendamento
```

- [ ] **Step 2: Reactivate the combined Celery service without destructive startup**

Replace `backend/railway.jobs.toml` with:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "sh -c 'celery -A core worker -B -l INFO --concurrency=${CELERY_WORKER_CONCURRENCY:-1}'"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 5
```

This removes `flushdb()` from normal startup. Never purge shared Redis during deploy.

- [ ] **Step 3: Replace the Railway service matrix and WhatsApp section in the runbook**

Update `docs/DEPLOY.md` so Railway uses two application services:

```markdown
| Serviço | Config file absoluto | Domínio público |
|---|---|---|
| `barberhub-api` | `/backend/railway.toml` | `api.mrbarberhub.com.br` |
| `barberhub-jobs` | `/backend/railway.jobs.toml` | nenhum |
```

Replace `## 5. WhatsApp e e-mail` through the line before the Resend instructions with:

```markdown
## 5. WhatsApp Cloud API e e-mail

### Meta WhatsApp Cloud API

Use somente a API oficial da Meta. WABA, número dedicado e app devem pertencer
ao portfólio empresarial aprovado para o ambiente, sem registrar IDs reais
neste documento.

No Meta Business Settings, crie um usuário do sistema com acesso total ao app e
à conta WhatsApp. Gere token com validade controlada pela operação e permissões
`whatsapp_business_management` e `whatsapp_business_messaging`. Cadastre o token
somente como secret da Railway.

No WhatsApp Manager, crie e aguarde aprovação destes templates `UTILITY` em
`pt_BR`:

- `barberhub_agendamento_recebido`: `Olá, {{1}}! Seu {{2}} foi registrado para {{3}}. A barbearia confirmará seu horário pelo WhatsApp.`
- `barberhub_lembrete_agendamento`: `Olá, {{1}}! Lembrete: seu {{2}} está marcado para {{3}}.`

Cadastre como variáveis compartilhadas nos serviços `barberhub-api` e
`barberhub-jobs`:

```text
WHATSAPP_GRAPH_API_VERSION=v25.0
WHATSAPP_PHONE_NUMBER_ID=cole-o-phone-number-id
WHATSAPP_ACCESS_TOKEN=defina-no-painel
WHATSAPP_WABA_ID=cole-o-waba-id
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
WHATSAPP_CONFIRMATION_TEMPLATE=barberhub_agendamento_recebido
WHATSAPP_REMINDER_TEMPLATE=barberhub_lembrete_agendamento
```

Substitua os placeholders pelos IDs exibidos em WhatsApp → API Setup e cadastre
os valores reais somente como secrets/variáveis protegidas da Railway. Nunca
registre vínculo entre IDs reais e contas, nem use texto de exemplo como token
em produção.

O sistema envia três notificações: recebimento imediato, lembrete 24 horas antes
e lembrete 1 hora antes. Os dois lembretes reutilizam o mesmo template.

Somente depois de os templates estarem `APPROVED` e as variáveis existirem,
implante `barberhub-api` e ative `barberhub-jobs`. O serviço jobs deve mostrar um
worker conectado ao Redis e o beat executando
`apps.notifications.tasks.enqueue_due_reminders` a cada 600 segundos.

Nunca registre token, cabeçalho `Authorization`, telefone de cliente ou conteúdo
de mensagem em issue, Git ou log manual.
```

Keep the existing Resend subsection after this new WhatsApp subsection.

- [ ] **Step 4: Verify active code and runbook contain no Evolution contract**

Run:

```bash
rg -n "EVOLUTION|WHATSAPP_BASE_URL|WHATSAPP_API_KEY|WHATSAPP_INSTANCE_NAME|message/sendText|flushdb" backend docs/DEPLOY.md
```

Expected: no matches; `rg` exits `1`.

- [ ] **Step 5: Commit deployment configuration and docs**

```bash
git add backend/.env.production.example backend/railway.jobs.toml docs/DEPLOY.md
git commit -m "docs: prepare Meta WhatsApp production rollout"
```

---

### Task 4: Full local verification

**Files:**
- Verify only; no planned file changes.

**Interfaces:**
- Consumes: completed code and documentation from Tasks 1-3.
- Produces: test evidence safe to merge and deploy.

- [ ] **Step 1: Run all backend tests**

```bash
cd backend
pytest
```

Expected: all tests PASS and coverage remains at least 80%.

- [ ] **Step 2: Run backend lint and Django checks**

```bash
cd backend
ruff check .
DJANGO_SETTINGS_MODULE=core.settings.development python manage.py check
```

Expected: both commands exit `0`; Django reports no issues.

- [ ] **Step 3: Run frontend build, lint, and E2E regression checks**

```bash
cd frontend
npm ci
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 npm run build
npm run lint
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 npm run test:e2e
```

Expected: dependency install, TypeScript/Vite build, ESLint, and Playwright all exit `0`.

- [ ] **Step 4: Confirm no secret-like value entered Git**

```bash
git diff main...HEAD -- . ':!docs/superpowers/plans/2026-07-15-meta-cloud-api-whatsapp.md' | rg -n "EA[A-Za-z0-9]{80,}|Bearer [A-Za-z0-9_-]{40,}|WHATSAPP_ACCESS_TOKEN=[A-Za-z0-9_-]{40,}"
```

Expected: no matches; `rg` exits `1`.

- [ ] **Step 5: Review commit scope**

```bash
git status --short
git log --oneline main..HEAD
git diff --stat main...HEAD
```

Expected: clean worktree; three implementation commits; only backend notification/settings/deploy files and `docs/DEPLOY.md` changed.

---

### Task 5: Safe Railway rollout and real-message smoke test

**Files:**
- External configuration only: Meta WhatsApp Manager and Railway project `eloquent-victory`.
- Verify: `https://api.mrbarberhub.com.br/api/v1/health/` and deployed BarberHub frontend.

**Interfaces:**
- Consumes: approved Meta templates, private permanent system-user token, WABA ID, phone number ID, and tested commits.
- Produces: healthy API, running Celery jobs, and three real notification paths.

- [ ] **Step 1: Confirm Meta assets without exposing the token**

In Meta WhatsApp Manager, confirm:

```text
Phone status: Connected
Template barberhub_agendamento_recebido: APPROVED / pt_BR / UTILITY
Template barberhub_lembrete_agendamento: APPROVED / pt_BR / UTILITY
System-user token permissions: whatsapp_business_management, whatsapp_business_messaging
```

Record the WABA ID and phone number ID in the Railway variables; never paste the access token into chat or a shell command history.

- [ ] **Step 2: Configure both Railway services before deploying code**

In Railway project `eloquent-victory`, add the seven `WHATSAPP_*` variables from Task 3 to `barberhub-api` and `barberhub-jobs`. If `barberhub-jobs` does not exist, create it from the same GitHub repository with root directory `/backend` and config file `/backend/railway.jobs.toml`.

Expected: both services show all variable names; Railway UI masks `WHATSAPP_ACCESS_TOKEN`.

- [ ] **Step 3: Merge implementation and recheck the user's frontend work**

Merge the implementation branch into `main`, preserving the existing uncommitted frontend files. Before staging or pushing those frontend files, run:

```bash
cd frontend
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 npm run build
npm run lint
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 npm run test:e2e
```

Expected: all three commands exit `0`; no frontend file is staged by the backend merge.

- [ ] **Step 4: Push and deploy API first**

Push `main` only after Railway variables from Step 2 exist.

Expected: `barberhub-api` deploy becomes healthy and `https://api.mrbarberhub.com.br/api/v1/health/` returns `{"status":"ok"}`.

- [ ] **Step 5: Deploy the combined jobs service**

Deploy `barberhub-jobs` from the same commit as the API.

Expected logs include one Celery worker ready message and periodic beat dispatches for `apps.notifications.tasks.enqueue_due_reminders`; logs contain no token and no `flushdb` call.

- [ ] **Step 6: Smoke-test immediate confirmation**

Use the public BarberHub booking link with a controlled recipient number, select a real available slot, accept privacy notice, and submit.

Expected:

```text
HTTP/UI: Horário solicitado
Panel: appointment visible with AGUARDANDO_CONFIRMACAO
NotificationLog: CONFIRMATION / SENT
WhatsApp: barberhub_agendamento_recebido received once
```

- [ ] **Step 7: Smoke-test 24-hour and 1-hour reminders without waiting**

Create two controlled `PENDENTE` appointments from the admin panel: one 24 hours ahead and one 1 hour ahead, each within the scheduler's ±5 minute window. In Railway shell for `barberhub-jobs`, run:

```bash
python manage.py shell -c "from apps.notifications.tasks import enqueue_due_reminders; enqueue_due_reminders.delay(); print('reminders enqueued')"
```

Expected:

```text
NotificationLog: REMINDER_24H / SENT
NotificationLog: REMINDER_1H / SENT
WhatsApp: barberhub_lembrete_agendamento received once for each appointment
```

- [ ] **Step 8: Verify idempotency and finish rollout**

Run the same enqueue command once more.

Expected: no duplicate WhatsApp messages for logs already marked `SENT`; API and jobs stay healthy. Keep the previous Railway API deployment available for rollback, but do not reactivate Evolution.
