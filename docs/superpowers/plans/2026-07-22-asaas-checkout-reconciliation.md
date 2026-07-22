# Asaas Checkout Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate subscriptions from valid `CHECKOUT_PAID` webhooks without calling unsupported Asaas checkout retrieval.

**Architecture:** Authenticated webhook payload supplies checkout id, paid status, and optional reference. Provider reconciliation queries only Asaas subscriptions by stored reference and requires one active match before local transition to `TRIAL`.

**Tech Stack:** Django, pytest, requests, Asaas v3 API.

## Global Constraints

- Never grant access from browser callback or redirect.
- Keep Asaas webhook token validation unchanged.
- Require exactly one active provider subscription whose `externalReference` matches.
- Do not call `GET /checkouts/{id}`.

---

### Task 1: Reconcile paid checkout through subscription lookup

**Files:**

- Modify: `backend/tests/test_asaas_provider.py:364-524`
- Modify: `backend/apps/billing/providers/asaas.py:177-236`

**Interfaces:**

- Consumes: `reconcile_paid_checkout(checkout_id: str, expected_external_reference: str)`.
- Produces: `PaidCheckoutReconciliation(checkout_id, external_reference, provider_subscription_id)`.

- [ ] Step 1: Replace provider test fixture with one subscriptions response. Assert exact request URL `https://api-sandbox.asaas.com/v3/subscriptions`, params `{"externalReference": external_reference, "limit": 2}`, and no checkout request.
- [ ] Step 2: Run `docker compose exec -T backend sh -c 'export PATH=$PATH:/home/appuser/.local/bin; pytest backend/tests/test_asaas_provider.py -q --no-cov'`. Expected: fail because implementation calls `/checkouts/chk_paid`.
- [ ] Step 3: Remove checkout `_get_provider_json` request and payload comparison in `reconcile_paid_checkout`. Keep input validation; retain existing exact-one active matching subscription validation.
- [ ] Step 4: Run same provider suite. Expected: pass.
- [ ] Step 5: Commit provider and test change as `fix: reconcile Asaas checkout via subscription`.

### Task 2: Verify webhook activation regression path

**Files:**

- Test: `backend/tests/test_billing_webhooks.py`

**Interfaces:**

- Consumes: `activate_checkout_from_webhook(event)` and reconciler result.
- Produces: local subscription `TRIAL` only after reconciliation result.

- [ ] Step 1: Run `docker compose exec -T backend sh -c 'export PATH=$PATH:/home/appuser/.local/bin; pytest backend/tests/test_billing_webhooks.py -q --no-cov'`. Expected: pass.
- [ ] Step 2: Run `docker compose exec -T backend sh -c 'export PATH=$PATH:/home/appuser/.local/bin; ruff check .'`. Expected: `All checks passed!`.
- [ ] Step 3: Resend latest `CHECKOUT_PAID` in Asaas Webhook Logs. Confirm stored event gets `processed_at`, no `processing_error`, matching subscription becomes `TRIAL`.
