# Evolution API WhatsApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Evolution API v2 on Railway, connect the dedicated BarberHub WhatsApp Business number through Baileys, and verify appointment confirmations and reminders end to end.

**Architecture:** A dedicated Railway service runs Evolution API v2 and persists its state in PostgreSQL with Redis cache. The existing Django `WhatsAppProvider` calls the Evolution `sendText` endpoint; Celery sends confirmations and retries failures, while Celery Beat enqueues the 24-hour and 1-hour reminders.

**Tech Stack:** Django, requests, pytest, Celery, Evolution API v2, WhatsApp Baileys, Railway, PostgreSQL, Redis

## Global Constraints

- Use the dedicated new WhatsApp Business number only; do not connect the personal M&R Solutions number.
- Name the Evolution instance exactly `barberhub`.
- Use integration type exactly `WHATSAPP-BAILEYS`.
- Keep all API keys, database URLs, Redis URLs, and QR data out of Git and public logs.
- Send only transactional appointment messages authorized by the customer; no bulk campaigns.
- Preserve one notification per appointment and kind through `NotificationLog` idempotency.
- Keep the Meta business portfolio available but do not register this number in Meta Cloud API.

---

## File Map

- Modify `backend/tests/test_notifications.py`: specify the Evolution API v2 request body and provider failure behavior.
- Modify `backend/apps/notifications/providers.py`: send the v2 `sendText` payload and preserve timeout/error propagation.
- Modify `docs/DEPLOY.md`: document Railway Evolution service, instance creation, QR connection, backend secrets, smoke test, and reconnection.
- Modify `backend/.env.production.example`: clarify Baileys mode and keep secret placeholders non-operational.

### Task 1: Align the provider with Evolution API v2

**Files:**
- Modify: `backend/tests/test_notifications.py`
- Modify: `backend/apps/notifications/providers.py`

**Interfaces:**
- Consumes: Django settings `WHATSAPP_BASE_URL: str`, `WHATSAPP_API_KEY: str`, and `WHATSAPP_INSTANCE_NAME: str`.
- Produces: `WhatsAppProvider.send(recipient: str, message: str) -> dict`, posting `{"number": recipient, "text": message}` to `/message/sendText/{instance}`.

- [ ] **Step 1: Change the request contract test so it fails against the old nested payload**

Replace the expected `json` value in `test_whatsapp_provider_uses_evolution_instance_route` and add a test for HTTP failure propagation:

```python
import pytest
import requests
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
    requests_post = Mock(return_value=response)
    monkeypatch.setattr("apps.notifications.providers.requests.post", requests_post)

    result = WhatsAppProvider().send("5511999999999", "Confirmação")

    assert result == {"key": {"id": "message-id"}}
    response.raise_for_status.assert_called_once()
    requests_post.assert_called_once_with(
        "https://whatsapp.example.com/message/sendText/barberhub",
        json={"number": "5511999999999", "text": "Confirmação"},
        headers={"apikey": "secret"},
        timeout=10,
    )


@override_settings(
    WHATSAPP_BASE_URL="https://whatsapp.example.com",
    WHATSAPP_API_KEY="secret",
    WHATSAPP_INSTANCE_NAME="barberhub",
)
def test_whatsapp_provider_propagates_http_error(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 Server Error")
    monkeypatch.setattr("apps.notifications.providers.requests.post", Mock(return_value=response))

    with pytest.raises(requests.HTTPError, match="503 Server Error"):
        WhatsAppProvider().send("5511999999999", "Confirmação")
```

- [ ] **Step 2: Run the focused tests and verify the payload test fails**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
```

Expected: `test_whatsapp_provider_uses_evolution_instance_route` fails because actual JSON contains `textMessage` instead of `text`; HTTP failure test passes.

- [ ] **Step 3: Implement the minimal Evolution API v2 payload**

Change `WhatsAppProvider.send` in `backend/apps/notifications/providers.py` to:

```python
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
```

- [ ] **Step 4: Run notification and backend tests**

Run:

```bash
cd backend
pytest tests/test_notifications.py -q
pytest -q
```

Expected: both commands exit `0`; focused file reports two passing provider tests plus existing notification tests.

- [ ] **Step 5: Commit the provider contract**

```bash
git add backend/apps/notifications/providers.py backend/tests/test_notifications.py
git commit -m "fix: align WhatsApp provider with Evolution v2"
```

### Task 2: Document the isolated Railway deployment

**Files:**
- Modify: `docs/DEPLOY.md`
- Modify: `backend/.env.production.example`

**Interfaces:**
- Consumes: Evolution global key `AUTHENTICATION_API_KEY`, public `SERVER_URL`, PostgreSQL connection, and Redis connection.
- Produces: public Evolution HTTPS base URL and credentials consumed by the Django settings from Task 1.

- [ ] **Step 1: Add a documentation regression test**

Create a temporary shell assertion without modifying application files:

```bash
python3 - <<'PY'
from pathlib import Path

deploy = Path("docs/DEPLOY.md").read_text()
required = [
    "WHATSAPP-BAILEYS",
    "AUTHENTICATION_API_KEY",
    "DATABASE_CONNECTION_URI",
    "CACHE_REDIS_URI",
    "/instance/create",
    "/instance/connect/barberhub",
    "/instance/connectionState/barberhub",
]
missing = [value for value in required if value not in deploy]
raise SystemExit(f"missing deployment instructions: {missing}" if missing else 0)
PY
```

Expected: non-zero exit with all or some required strings listed.

- [ ] **Step 2: Replace the Evolution paragraph in `docs/DEPLOY.md` with exact deployment instructions**

Document these Railway actions under `## 5. WhatsApp e e-mail`:

```markdown
### Evolution API v2 por Baileys

Crie um serviço Railway separado usando a imagem Docker oficial fixada na versão validada durante o deploy. Não use a tag `latest`. Conecte PostgreSQL e Redis dedicados, ou bancos logicamente isolados, e configure no serviço Evolution:

```text
SERVER_URL=https://<domínio-público-gerado-pela-railway>
AUTHENTICATION_API_KEY=<chave-aleatória-gerada-com-openssl-rand-hex-32>
DATABASE_ENABLED=true
DATABASE_PROVIDER=postgresql
DATABASE_CONNECTION_URI=<url-postgresql-da-evolution>
DATABASE_CONNECTION_CLIENT_NAME=barberhub_evolution
CACHE_REDIS_ENABLED=true
CACHE_REDIS_URI=<url-redis-da-evolution>
CACHE_REDIS_PREFIX_KEY=barberhub_evolution
CACHE_REDIS_SAVE_INSTANCES=false
CACHE_LOCAL_ENABLED=false
```

Gere domínio público HTTPS para a porta `8080`. Com a implantação saudável, crie a instância sem gravar a chave no histórico do shell:

```bash
read -rsp "Evolution API key: " EVOLUTION_API_KEY
curl -fsS -X POST "$EVOLUTION_URL/instance/create" \
  -H "Content-Type: application/json" \
  -H "apikey: $EVOLUTION_API_KEY" \
  -d '{"instanceName":"barberhub","integration":"WHATSAPP-BAILEYS","qrcode":true}'
```

Obtenha o QR Code e conecte somente o número dedicado ao BarberHub:

```bash
curl -fsS "$EVOLUTION_URL/instance/connect/barberhub" \
  -H "apikey: $EVOLUTION_API_KEY"
```

No WhatsApp Business do celular, abra **Dispositivos conectados → Conectar dispositivo** e leia o QR Code. Confirme estado `open`:

```bash
curl -fsS "$EVOLUTION_URL/instance/connectionState/barberhub" \
  -H "apikey: $EVOLUTION_API_KEY"
```

Cadastre a mesma URL, chave e instância nos serviços Railway `barberhub-api`, `barberhub-worker` e `barberhub-beat`:

```text
WHATSAPP_BASE_URL=https://<domínio-público-gerado-pela-railway>
WHATSAPP_API_KEY=<mesma-chave-de-AUTHENTICATION_API_KEY>
WHATSAPP_INSTANCE_NAME=barberhub
```
```

Keep placeholders in documentation only; enter real secrets directly in Railway.

- [ ] **Step 3: Clarify Baileys mode in `backend/.env.production.example`**

Use:

```dotenv
# Evolution API v2 via WHATSAPP-BAILEYS. Nunca grave valores reais neste arquivo.
WHATSAPP_BASE_URL=https://evolution.seudominio.com
WHATSAPP_API_KEY=cole-a-chave-global-da-evolution
WHATSAPP_INSTANCE_NAME=barberhub
```

- [ ] **Step 4: Run documentation and secret checks**

Run the Python assertion from Step 1 again. Expected: exit `0`.

Run:

```bash
git diff --check
git diff -- docs/DEPLOY.md backend/.env.production.example | grep -E 'AUTHENTICATION_API_KEY=[0-9A-Fa-f]{32,}|WHATSAPP_API_KEY=[0-9A-Fa-f]{32,}' && exit 1 || true
```

Expected: both commands exit `0` and no real-looking secret is printed.

- [ ] **Step 5: Commit the runbook**

```bash
git add docs/DEPLOY.md backend/.env.production.example
git commit -m "docs: add Evolution Railway runbook"
```

### Task 3: Deploy, pair, and run end-to-end acceptance

**Files:**
- Verify: `backend/apps/notifications/providers.py`
- Verify: `backend/apps/notifications/tasks.py`
- Verify: Railway services `evolution-api`, `barberhub-api`, `barberhub-worker`, and `barberhub-beat`

**Interfaces:**
- Consumes: committed provider contract, Railway environment values, dedicated WhatsApp Business number, and a test appointment.
- Produces: connected `barberhub` instance and evidence that confirmations and reminders send once.

- [ ] **Step 1: Provision Evolution dependencies and service in Railway**

In the existing BarberHub Railway project:

1. Create isolated PostgreSQL and Redis resources for Evolution.
2. Create `evolution-api` from the official Evolution Docker image, pinned to the version selected from the official release list at execution time.
3. Enter the exact variables documented in Task 2.
4. Generate a Railway public HTTPS domain mapped to port `8080`.
5. Confirm deployment logs finish without Prisma, PostgreSQL, Redis, or bind errors.

Expected: opening `https://<evolution-domain>/` returns an HTTP success response.

- [ ] **Step 2: Create and pair the `barberhub` instance**

Execute the three documented API calls in order: `/instance/create`, `/instance/connect/barberhub`, and `/instance/connectionState/barberhub`.

Expected final response contains the equivalent of:

```json
{"instance":{"instanceName":"barberhub","state":"open"}}
```

- [ ] **Step 3: Send a direct smoke-test message**

Use a test recipient with Brazilian country code and digits only:

```bash
read -rsp "Evolution API key: " EVOLUTION_API_KEY
curl -fsS -X POST "$EVOLUTION_URL/message/sendText/barberhub" \
  -H "Content-Type: application/json" \
  -H "apikey: $EVOLUTION_API_KEY" \
  -d '{"number":"55DDDNUMERODETESTE","text":"Teste de integração do M&R BarberHub."}'
```

Expected: response contains a message ID and the test phone receives exactly one message.

- [ ] **Step 4: Configure and redeploy all backend processes**

Add these shared Railway secrets to API, worker, and beat:

```text
WHATSAPP_BASE_URL=https://<evolution-domain>
WHATSAPP_API_KEY=<Evolution global key>
WHATSAPP_INSTANCE_NAME=barberhub
```

Redeploy all three services. Expected: production settings start without `Configure URL, chave e instância do provedor de WhatsApp` and worker connects to Celery broker.

- [ ] **Step 5: Verify appointment confirmation idempotency**

Create one appointment through the public booking flow using the authorized test phone. Do not repeat submission after success.

Expected:

- one confirmation arrives;
- Django admin or shell shows one `NotificationLog` with kind `CONFIRMATION` and status `SENT`;
- manually replaying `send_appointment_confirmation.delay(appointment_id)` does not produce a second message.

- [ ] **Step 6: Verify both reminders with controlled test data**

In a Railway Django shell, use a dedicated test appointment and set its start time first inside the 24-hour scan window, then inside the 1-hour scan window. Invoke `enqueue_due_reminders.delay()` after each change.

Expected:

- exactly one `REMINDER_24H` message;
- exactly one `REMINDER_1H` message;
- rerunning the enqueue task does not duplicate either sent notification.

- [ ] **Step 7: Verify retry evidence without messaging a customer**

Temporarily use an invalid Evolution hostname only in a controlled non-production worker or test environment, enqueue a test confirmation, and inspect Celery logs.

Expected: task reports retry with backoff and stops after configured `max_retries=5`; no real customer number is used. Restore the valid URL immediately after the check.

- [ ] **Step 8: Record operational result without secrets**

Append a dated checklist result to the deployment record or issue tracker containing only:

```text
Evolution deployment: healthy
Instance barberhub: open
Direct smoke test: passed
Confirmation idempotency: passed
24h reminder: passed
1h reminder: passed
Retry behavior: passed
```

Do not record phone numbers, API keys, QR data, database URLs, Redis URLs, or message bodies.

