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
