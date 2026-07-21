# Task 5 Report: Authenticated, idempotent Asaas webhook transitions

Date: 2026-07-20

## Status

Complete. Task 5 is implemented with authenticated ingestion, sanitized event
storage, provider-event deduplication, transactional financial transitions,
Celery retry support, and no email work.

## Scope delivered

- Added `POST /api/v1/billing/webhooks/asaas/`.
- Authenticates `asaas-access-token` with `hmac.compare_digest` and rejects an
  absent or invalid token with HTTP 401.
- Requires non-empty string `id` and `event` values within model limits.
- Stores only an allowlisted projection of checkout, subscription, and payment
  reconciliation fields. Card data, CVV, payment tokens, API headers, and
  arbitrary payload fields are discarded.
- Deduplicates with the existing unique provider/provider-event key and
  acknowledges valid duplicates with HTTP 202 without queuing them again.
- Added `process_billing_webhook(event_id)` with bounded Celery autoretry.
- Locks both the webhook event and affected subscription with
  `select_for_update` inside transaction boundaries.
- Marks `processed_at` only in the same successful commit as the financial
  transition and audit event.
- On processor failure, rolls back the transition, stores only the safe
  exception class name in `processing_error`, and re-raises for retry.
- Handles `CHECKOUT_PAID`, both payment-success events, both payment-failure
  events, both immediate chargeback events, both cancellation events, and
  unknown events.
- `CHECKOUT_PAID` activates inactive tenant users and does not write
  `Barbershop.active`.
- Added no billing email behavior; that remains Task 6.

## Files changed

- `backend/apps/billing/services.py`
- `backend/apps/billing/views.py`
- `backend/apps/billing/tasks.py`
- `backend/core/urls.py`
- `backend/tests/test_billing_webhooks.py`
- `.superpowers/sdd/task-5-report.md`

## TDD evidence

### RED

Tests were added before production code.

Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
```

Observed result:

```text
27 failed in 2.28s
```

Expected failures were observed: endpoint requests returned HTTP 404 instead
of the required 401/400/202 responses, and the processor test failed with
`ModuleNotFoundError: No module named 'apps.billing.tasks'`.

### GREEN: webhook tests

Same focused command after implementation:

```text
27 passed in 1.80s
```

Coverage includes:

- missing and invalid webhook tokens;
- missing, empty, and wrongly typed provider event ID/type;
- malformed JSON;
- duplicate provider event acknowledgment and one persisted event;
- one-time checkout activation, inactive-user activation, and preservation of
  `Barbershop.active=False`;
- `PAYMENT_CONFIRMED` and `PAYMENT_RECEIVED` activation;
- reactivation from `GRACE` and `SUSPENDED` with stale restrictions cleared;
- exact seven-day grace for overdue and risk-analysis rejection;
- repeated overdue events preserving the first grace deadline;
- immediate suspension for both chargeback event types;
- both subscription cancellation event types with tenant data preserved;
- safe completion of unknown events;
- strict payload projection with card/CVV/token/arbitrary fields discarded;
- malformed known-event handling;
- transaction rollback, safe error metadata, re-raise, and successful retry.

### GREEN: focused regressions

Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_subscription_access.py tests/test_notifications.py -q --no-cov
```

Result:

```text
70 passed in 2.28s
```

The plan's exact focused command without `--no-cov` also executed all 70 tests
successfully, but pytest exited 1 because running only that subset measured
65.51% global project coverage, below the repository-wide 80% threshold. This
is a coverage-scope artifact, not a test failure.

### GREEN: full backend suite

Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest -q
```

Result:

```text
134 passed, 3 warnings in 5.25s
Required test coverage of 80% reached. Total coverage: 90.81%
```

Warnings are existing PyJWT insecure test-key-length warnings in auth tests.

### Static checks

Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m ruff check .
```

Result:

```text
All checks passed!
```

`git diff --check` also passed with no whitespace errors.

## Manual self-review

- Security: token comparison is constant-time; failed auth persists nothing;
  only scalar allowlisted fields reach `BillingWebhookEvent.payload`.
- Idempotency/concurrency: database uniqueness handles concurrent ingestion;
  only newly created rows enqueue; event lock prevents duplicate processing;
  subscription locks serialize different financial events for one tenant.
- Transactions/retries: subscription changes, user activation, audit creation,
  and `processed_at` commit atomically. Failure metadata is saved separately
  after rollback and contains no exception message.
- Domain behavior: success clears grace/suspension, repeated overdue preserves
  the first deadline, chargeback suspends immediately, cancellation preserves
  tenant data, and checkout activation never changes the shop preference.
- Scope: no migrations, raw-payload storage, browser callback activation, or
  email behavior were added.

No concrete issue was found, so no post-GREEN behavior change was made.

## Concerns

- The focused command's repository-wide coverage gate cannot pass in isolation;
  the full suite passes the gate at 90.81%.
- Transaction-lock concurrency is implemented for PostgreSQL; SQLite test mode
  does not provide PostgreSQL-equivalent row-lock behavior, so tests validate
  idempotent outcomes and transaction rollback rather than lock contention.

## WIP pause: independent-review blocker wave

Paused by user deadline before any production implementation. This section
records exact recoverable state; failing RED tests are intentionally
uncommitted.

### Tests added or changed

`backend/tests/test_billing_webhooks.py` now contains RED coverage for:

- broker publication failure returning HTTP 503 without storing broker error
  details;
- duplicate redelivery redispatching the same unprocessed row and transitioning
  once;
- processed duplicates not publishing again;
- bounded recovery-task selection of unprocessed events only and one-minute
  Celery Beat configuration;
- valid outer `dateCreated` inclusion in the sanitized projection;
- cancellation remaining terminal when delayed overdue arrives;
- chargeback suspension resisting delayed overdue and same-payment success;
- stale provider timestamp rejection;
- newer different-payment success reactivating chargeback suspension;
- `CHECKOUT_PAID` activating only `PENDING_CHECKOUT`;
- same-payment overdue not opening a second grace after success;
- a later different payment cycle opening a fresh exact seven-day grace;
- non-ASCII webhook token rejection without server error;
- whitespace-only, surrounding-whitespace, and control-character `id`/`event`
  rejection.

### RED evidence

Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
```

Observed result:

```text
18 failed, 27 passed in 2.65s
```

Expected failures proved all new blocker clusters are currently absent:
publication exceptions escape instead of returning 503; recovery task and Beat
entry do not exist; unsafe state transitions still occur; provider-cycle fields
and outer timestamp projection do not exist; non-ASCII token comparison raises
`TypeError`; malformed identifiers are accepted.

### Remaining implementation

1. Change webhook publication handling to return a safe 503 on `.delay()`
   failure, redispatch every duplicate with `processed_at IS NULL`, and never
   persist broker exception text.
2. Add bounded `redispatch_unprocessed_billing_webhooks` task and one-minute
   Celery Beat schedule.
3. Add `Subscription` provider-cycle fields (`last_payment_id`,
   `grace_payment_id`, `last_provider_event_at`, `suspension_reason`) with a
   migration.
4. Validate and sanitize outer `dateCreated`, then apply timestamp/state/payment
   guards while holding the subscription row lock: canceled terminal,
   checkout-only-pending, stale-event rejection, chargeback priority, and safe
   newer-cycle reactivation.
5. Enforce grace once per payment ID while allowing a later payment ID to start
   a fresh grace cycle.
6. Encode tokens before `compare_digest` and reject whitespace/control provider
   identifiers.
7. Run webhook/access focused suites, full backend suite, Ruff,
   `makemigrations --check`, and `git diff --check`; append final GREEN evidence
   and commit only after all pass.

### Repository state at pause

```text
## feat/saas-onboarding-billing
 M backend/tests/test_billing_webhooks.py
```

This report becomes modified by this WIP entry as well. No production file was
changed during the blocker wave. No launched pytest or nested-review process
remains running.

Last safe commit: `8970aac feat: synchronize Asaas billing webhooks`.

## Blocker wave: GREEN completion

The intentional 18-test RED wave is now GREEN. Production changes add durable
broker handoff recovery, provider-cycle state, normalized provider timestamps,
and row-locked ordering guards without weakening the review tests.

### Implementation

- Ingestion returns HTTP 503 when broker publication fails, retains the
  unprocessed deduplicated row without broker details, republishes unprocessed
  duplicates, and does not republish processed duplicates.
- A bounded recovery task republishes the oldest 100 unprocessed rows every
  minute through Celery Beat.
- `Subscription` now persists `last_payment_id`, `grace_payment_id`,
  `last_provider_event_at`, and `suspension_reason`; migration `0002` adds all
  four fields.
- Outer `dateCreated` is parsed, required to be timezone-aware, normalized to
  UTC, and included in the allowlisted payload projection only when valid.
- Subscription locks now guard terminal cancellation, checkout activation,
  stale timestamps, chargeback priority, and payment-cycle grace use.
- Tokens are compared as UTF-8 bytes. Provider identifiers containing
  whitespace or control characters are rejected before persistence.

### GREEN evidence

Focused webhook suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
45 passed in 2.02s
```

Webhook, access, and notification regressions:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_subscription_access.py tests/test_notifications.py -q --no-cov
88 passed in 2.91s
```

Full backend suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest -q
152 passed, 3 warnings in 6.23s
Required test coverage of 80% reached. Total coverage: 90.93%
```

The three warnings remain the existing PyJWT insecure test-key-length warnings.

Static and migration checks:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m ruff check .
All checks passed!

DJANGO_SETTINGS_MODULE=core.settings.test /home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python manage.py makemigrations --check --dry-run
No changes detected

git diff --check
passed
```

### Final self-review

- Durability/idempotency: database uniqueness remains the ingestion authority;
  both request redelivery and periodic recovery can safely enqueue the same row
  because processor and subscription locks serialize work and `processed_at`
  short-circuits completed events.
- Ordering: ignored stale, terminal, and lower-priority transitions still mark
  their webhook row processed atomically, but create no subscription mutation or
  audit event. Ignored events do not advance `last_provider_event_at`.
- Payment cycles: a payment ID consumes grace once; success retains that cycle
  marker; a different payment can receive a fresh exact seven-day deadline.
- Security: no raw payload, token, broker exception text, or exception message is
  persisted. Sanitization remains allowlist-only.
- Scope: no email behavior, tenant deletion, fixture changes, or
  `Barbershop.active` writes were added. Tasks 1-4 remain untouched.

Remaining concern: row-lock contention semantics require PostgreSQL; SQLite
tests prove state outcomes and atomic rollback but cannot emulate PostgreSQL
locking behavior.
