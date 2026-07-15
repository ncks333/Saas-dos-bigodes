# WhatsApp Delivery Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Brazilian recipient handling and duplicate-safe Meta WhatsApp notification delivery without schema changes.

**Architecture:** A shared phone helper normalizes all ingress and provider recipients. Notification tasks use the existing text status field as an atomic delivery claim, while reminder jobs carry a UTC appointment snapshot and scheduler catch-up enqueues new or pre-existing `PENDING` logs.

**Tech Stack:** Python 3, Django ORM, Django REST Framework, Pydantic, Celery, requests, pytest, Ruff.

## Global Constraints

- Backend/WhatsApp and related docs only; never edit frontend.
- Meta Cloud API v25.0, exactly two templates and three events.
- No Evolution API, webhook, DB migration, secret, real phone, or sensitive error metadata.
- Strict RED then GREEN; one final commit only.

---

### Task 1: Brazilian WhatsApp normalization

**Files:**
- Create: `backend/core/utils/phones.py`
- Modify: `backend/apps/customers/serializers.py`
- Modify: `backend/apps/appointments/schemas.py`
- Modify: `backend/apps/notifications/providers.py`
- Test: `backend/tests/test_whatsapp_phone_numbers.py`
- Test: `backend/tests/test_notifications.py`

**Interfaces:**
- Produces: `normalize_brazilian_whatsapp(value: str) -> str`, raising `ValueError` for invalid input.
- Consumers: customer serializer, public booking schema, Meta provider.

- [ ] **Step 1: Write failing tests** for 10/11-digit local input, formatted `+55`, invalid country/length, serializer persistence, public booking parsing, and provider legacy normalization.
- [ ] **Step 2: Run RED:** `cd backend && pytest tests/test_whatsapp_phone_numbers.py tests/test_notifications.py -q`.
- [ ] **Step 3: Implement minimal helper and replace duplicate regex validators; normalize provider recipient before POST.**
- [ ] **Step 4: Run GREEN:** same focused pytest command.

### Task 2: Atomic notification delivery

**Files:**
- Modify: `backend/apps/notifications/tasks.py`
- Test: `backend/tests/test_notifications.py`

**Interfaces:**
- Produces: `_claim_notification(log_id: int) -> bool` using conditional `PENDING -> SENDING` update.
- Produces: sanitized terminal/uncertain metadata and manual retry path for retryable HTTP responses.

- [ ] **Step 1: Write failing tests** proving one real conditional claim, no POST from a second worker, `UNKNOWN` for timeout, controlled retry for retryable HTTP, sanitized `FAILED` for terminal HTTP, and no second POST after final persistence failure.
- [ ] **Step 2: Run RED:** `cd backend && pytest tests/test_notifications.py -q`.
- [ ] **Step 3: Implement shared delivery function.** Claim before provider call; map timeout/connection to `UNKNOWN`; map retryable HTTP to `PENDING` plus `self.retry`; map terminal failures to sanitized `FAILED`; conditionally persist `SENT` and swallow final persistence failure so `SENDING` remains.
- [ ] **Step 4: Run GREEN:** focused notification tests.

### Task 3: Tenant timezone and valid reminder execution

**Files:**
- Modify: `backend/apps/notifications/tasks.py`
- Test: `backend/tests/test_notifications.py`

**Interfaces:**
- Reminder signature: `send_appointment_reminder(appointment_id: int, hours: int, starts_at_snapshot: str)`.
- Snapshot: UTC ISO-8601 string generated from persisted `starts_at`.

- [ ] **Step 1: Write failing tests** for another tenant timezone, rejected `hours`, cancelled appointment, and rescheduled appointment.
- [ ] **Step 2: Run RED:** focused notification tests.
- [ ] **Step 3: Add `barbershop` to `select_related`, use `ZoneInfo`, validate hours/status/snapshot before claim.**
- [ ] **Step 4: Run GREEN:** focused notification tests.

### Task 4: Reminder catch-up

**Files:**
- Modify: `backend/core/settings/base.py`
- Modify: `backend/apps/notifications/tasks.py`
- Modify: `backend/.env.production.example`
- Modify: `docs/DEPLOY.md`
- Test: `backend/tests/test_notifications.py`

**Interfaces:**
- Consumes: `WHATSAPP_REMINDER_LOOKBACK_MINUTES`, positive integer, default `60`.
- Scheduler sends task args `(appointment.id, hours, starts_at_snapshot)` for a unique reminder log whose state is `PENDING`; all other states are skipped.

- [ ] **Step 1: Write failing tests** for an event missed 30 minutes ago, future-only filtering, snapshot argument, recovery of a pre-existing `PENDING` log, blocked terminal/in-flight states, and duplicate jobs producing one POST.
- [ ] **Step 2: Run RED:** focused notification tests.
- [ ] **Step 3: Query `[now + hours - lookback, now + hours]`, require `starts_at > now`, create or recover the existing unique notification log, and enqueue whenever status remains `PENDING`.**
- [ ] **Step 4: Document optional lookback plus permanent system-user token, least permissions, rotation, and revocation.**
- [ ] **Step 5: Run GREEN:** focused tests.

### Task 5: Full verification and one commit

**Files:** all files above; no migrations or frontend files.

- [ ] **Step 1: Run:** `cd backend && pytest`.
- [ ] **Step 2: Run:** `cd backend && ruff check .`.
- [ ] **Step 3: Run:** `cd backend && DJANGO_SETTINGS_MODULE=core.settings.development python manage.py check`.
- [ ] **Step 4: Run:** `cd backend && python manage.py makemigrations --check --dry-run`.
- [ ] **Step 5: Review status/diff for scope and sensitive values.**
- [ ] **Step 6: Commit once:** `git commit -m "fix: harden WhatsApp notification delivery"`.
