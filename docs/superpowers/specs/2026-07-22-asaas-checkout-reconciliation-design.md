# Asaas Checkout Reconciliation

## Goal

Activate a local subscription only after a signed `CHECKOUT_PAID` webhook and a provider-side active subscription match its stored external reference.

## Decision

Do not request `GET /checkouts/{id}`: Asaas returns `404` for that route. The webhook already carries the checkout id, `PAID` status, and external reference. Its `asaas-access-token` is validated before processing.

The reconciliation will:

1. Keep validating checkout id, `PAID` status, and external reference from the webhook.
2. Query Asaas subscriptions by that external reference.
3. Require exactly one active provider subscription with matching reference.
4. Activate the local trial only then.

## Failure behavior

Missing, ambiguous, inactive, or mismatched subscriptions keep the local subscription blocked and record a processing error for retry. Browser redirects never grant access.

## Tests

Provider tests will prove no checkout retrieval is attempted, active matching subscriptions reconcile, and invalid subscription results remain rejected.
