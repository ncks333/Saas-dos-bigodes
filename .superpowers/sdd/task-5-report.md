# Task 5 Report: Authenticated, idempotent Asaas webhook transitions

Date: 2026-07-20

## Status

Complete. Task 5 is implemented with authenticated ingestion, sanitized event
storage, provider-event deduplication, transactional financial transitions,
bounded durable retry/dead-letter support, and no email work.

## Scope delivered

- Added `POST /api/v1/billing/webhooks/asaas/`.
- Authenticates `asaas-access-token` with `hmac.compare_digest` and rejects an
  absent or invalid token with HTTP 401.
- Requires non-empty string `id` and `event` values within model limits.
- Stores only an allowlisted projection of checkout, subscription, and payment
  reconciliation fields. Card data, CVV, payment tokens, API headers, and
  arbitrary payload fields are discarded.
- Deduplicates with the existing unique provider/provider-event key, republishes
  eligible unprocessed duplicates, and never republishes processed or
  dead-lettered duplicates.
- Added `process_billing_webhook(event_id)` with bounded persistent backoff and
  dead-letter handling through periodic recovery.
- Locks both the webhook event and affected subscription with
  `select_for_update` inside transaction boundaries.
- Marks `processed_at` only in the same successful commit as the financial
  transition and audit event.
- On processor failure, rolls back the transition, stores only the safe
  exception class name in `processing_error`, schedules bounded backoff, and
  re-raises until the dead-letter limit is reached.
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
  new and eligible unprocessed duplicate rows may enqueue; processed and
  dead-lettered rows do not. Event locks prevent duplicate processing, and
  subscription locks serialize financial events for one tenant.
- Transactions/retries: subscription changes, user activation, audit creation,
  and `processed_at` commit atomically. Failure metadata is saved separately
  after rollback and contains no exception message.
- Domain behavior: success clears grace/suspension, repeated overdue preserves
  the first deadline, chargeback suspends immediately, cancellation preserves
  tenant data, and checkout activation never changes the shop preference.
- Scope: migrations `0002` and `0003` add ordering, payment-cycle, and recovery
  metadata. No raw-payload storage, browser callback activation, or email
  behavior was added.

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

### Remaining implementation at pause (completed by later waves)

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
  unprocessed deduplicated row without broker details, republishes only
  currently eligible unprocessed duplicates, and does not republish processed
  duplicates.
- A bounded recovery task republishes the oldest 100 eligible unprocessed rows
  every minute through Celery Beat.
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
  eligible request redelivery and periodic recovery can safely enqueue the same
  row because processor and subscription locks serialize work and
  `processed_at` short-circuits completed events.
- Ordering: ignored stale, terminal, and lower-priority transitions still mark
  their webhook row processed atomically, but create no subscription mutation or
  audit event. Ignored events do not advance `last_provider_event_at`.
- Payment cycles: unique durable `SubscriptionPaymentCycle` rows retain every
  payment's first grace and success timestamps; historical payments cannot
  reopen grace after later cycles.
- Security: no raw payload, token, broker exception text, or exception message is
  persisted. Sanitization remains allowlist-only.
- Scope: no email behavior, tenant deletion, fixture changes, or
  `Barbershop.active` writes were added. Tasks 1-4 remain untouched.

Remaining concern: row-lock contention semantics require PostgreSQL; SQLite
tests prove state outcomes and atomic rollback but cannot emulate PostgreSQL
locking behavior.

## Final re-review wave: strict chargeback ordering and fair recovery

Date: 2026-07-21

### RED evidence

All tests were added before production changes. Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
10 failed, 45 passed in 3.29s
```

Failures matched the reviewed gaps: undated/equal-timestamp success reactivated
chargeback suspension; historical payment-cycle storage did not exist; recovery
had no eligibility metadata, lease, dead-letter exclusion, bounded failure
count, or supporting index.

### Implementation

- Chargeback reactivation now requires a different payment ID plus a present
  provider timestamp strictly greater than `last_provider_event_at`. Chargeback
  wins equal timestamp ties; undated success cannot reactivate it.
- Added unique `SubscriptionPaymentCycle(subscription, provider_payment_id)`
  rows with `grace_started_at` and `succeeded_at`. Grace eligibility reads this
  durable history rather than the single latest subscription marker.
- Added webhook dispatch/processing attempt counts, last dispatch/processing
  timestamps, next-dispatch eligibility, dead-letter timestamp, and composite
  recovery index in migration `0003`.
- Dispatch preparation, lease release, failure backoff, dead-lettering, and
  success completion all lock the webhook row inside transactions.
- Recovery selects only the oldest 100 currently eligible non-dead-letter rows.
  A five-minute dispatch lease prevents minute-by-minute requeueing; processing
  failures receive exponential backoff and dead-letter on attempt five.
- Broker publication failures still return HTTP 503, leave the row eligible for
  redelivery, and persist no exception message.

### GREEN evidence

Focused webhook suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
55 passed in 2.74s
```

Webhook, access, and notification regressions:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_subscription_access.py tests/test_notifications.py -q --no-cov
98 passed in 4.07s
```

Full backend suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest -q
162 passed, 3 warnings in 7.46s
Required test coverage of 80% reached. Total coverage: 90.93%
```

The three warnings remain existing PyJWT insecure test-key-length warnings.

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

- Ordering: both chargeback-first and success-first equal timestamp orders end
  suspended. Missing success timestamps cannot establish strict newer order.
- Cycle durability: A overdue/success, B overdue/success, then delayed A overdue
  remains active; new C receives one exact seven-day grace window.
- Recovery fairness: queued, backed-off, and dead-lettered rows are ineligible,
  so they do not consume the bounded recovery batch; newer eligible rows flow.
- Atomicity: domain transition, payment-cycle writes, attempt metadata, audit,
  and `processed_at` retain row-lock and transaction boundaries. Failed domain
  work rolls back before safe failure metadata commits separately.
- Security/scope: no exception messages, secrets, raw payload fields, emails,
  tenant deletion, fixture changes, or `Barbershop.active` writes were added.

Remaining concern remains test-environment fidelity: SQLite validates outcomes,
constraints, and rollback but not PostgreSQL-equivalent lock contention.

## Final Task 5 re-review closure

Date: 2026-07-21

### RED evidence

Tests were added before production changes. Command:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_billing_models.py -q --no-cov
4 failed, 62 passed in 4.26s
```

Failures proved all remaining findings: duplicate delivery bypassed active
dispatch leases and processing backoff, undated chargeback retained an older
known timestamp and allowed reactivation, and migration `0003` created no cycle
history from `0002` data.

### Implementation

- Webhook ingestion now uses normal `next_dispatch_at` eligibility. The unused
  force-dispatch option was removed, so duplicate delivery cannot bypass a
  lease or processing backoff. Initial rows remain eligible, and broker failure
  still releases the lease for immediate redelivery.
- An undated chargeback explicitly clears `last_provider_event_at`. Webhook
  reactivation therefore fails closed until chargeback chronology is known;
  dated chargeback followed by a strictly newer different payment still
  reactivates.
- Migration `0003` now runs a historical-model-safe, idempotent data backfill
  after cycle-table creation. It resolves unique provider subscription IDs,
  imports processed sanitized payment failure/success events, and fills any
  remaining grace/last-payment markers. Reverse migration uses noop.
- Backfill keeps the earliest known grace and success timestamp per unique
  subscription/payment cycle. Ambiguous provider subscription IDs are skipped
  rather than assigned incorrectly.

### GREEN evidence

Webhook and migration/model tests:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_billing_models.py -q --no-cov
66 passed in 4.80s
```

Focused webhook suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py -q --no-cov
58 passed in 2.77s
```

Webhook, access, and notification regressions:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest tests/test_billing_webhooks.py tests/test_subscription_access.py tests/test_notifications.py -q --no-cov
101 passed in 3.06s
```

Full backend suite:

```text
/home/ncks/Documentos/Meus_projetos/Saas-dos-bigodes/.venv/bin/python -m pytest -q
166 passed, 3 warnings in 8.65s
Required test coverage of 80% reached. Total coverage: 91.01%
```

The three warnings remain existing PyJWT insecure test-key-length warnings.

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

- Duplicate eligibility: active leases/backoff leave dispatch and processing
  attempt counts unchanged; broker-failure release remains immediately
  dispatchable.
- Chronology: prior dated T0, undated chargeback, then different dated T1 stays
  suspended. Dated chargeback plus strictly newer different payment remains
  covered and GREEN.
- Upgrade safety: MigrationExecutor verifies `0002` A/B event history creates
  durable cycles under `0003`; an undated delayed A overdue event cannot reopen
  grace afterward.
- Migration safety: only historical app models are used; malformed, ambiguous,
  or unresolvable data is skipped; reruns update no duplicate cycle rows.
- Scope/security: no raw payload expansion, secrets, exception messages, email
  behavior, fixture changes, or `Barbershop.active` writes were added.

Remaining concern remains SQLite's lack of PostgreSQL-equivalent row-lock
contention; migration state, uniqueness, outcomes, and rollback are covered.
