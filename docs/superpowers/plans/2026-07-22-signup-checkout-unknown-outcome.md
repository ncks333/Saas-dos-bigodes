# Signup Checkout Unknown Outcome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve pending signup records when Asaas checkout creation has unknown outcome, preventing duplicate recurring charges.

**Architecture:** Complete local tenant provisioning in one transaction before contacting Asaas. Persist checkout state on `Subscription`; success stores provider checkout ID, known pre-creation refusal deletes local tenant, unknown outcome marks durable reconciliation-required state. A repeat signup with same unique credentials fails validation instead of creating a second checkout.

**Tech Stack:** Django 5, Django ORM transactions, pytest-django, Asaas provider adapter.

## Global Constraints

- No Asaas network call while local transaction is open.
- `AsaasCheckoutOutcomeUnknownError` preserves durable local audit/reconciliation data.
- `AsaasCheckoutNotCreatedError` keeps existing rollback behavior.
- Tests must run red before production code and green after it.

---

### Task 1: Persist unknown signup checkout outcome

**Files:**

- Modify: `backend/apps/billing/models.py`
- Create: `backend/apps/billing/migrations/0010_subscription_signup_checkout_state.py`
- Modify: `backend/apps/billing/services.py:554-616`
- Modify: `backend/tests/test_onboarding.py`

**Interfaces:**

- Consumes: `create_recurring_checkout(subscription, user) -> CheckoutResult` and `AsaasCheckoutOutcomeUnknownError`.
- Produces: `Subscription.signup_checkout_state` with `READY`, `CREATING`, `CREATED`, `RECONCILIATION_REQUIRED` values.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.django_db
def test_signup_unknown_checkout_outcome_persists_reconciliation_record(plan, monkeypatch):
    monkeypatch.setattr(
        "apps.billing.services.create_recurring_checkout",
        lambda *_args: (_ for _ in ()).throw(AsaasCheckoutOutcomeUnknownError("timeout")),
    )

    with pytest.raises(AsaasCheckoutOutcomeUnknownError):
        provision_signup(signup_payload(), plan)

    subscription = Subscription.objects.get(barbershop__slug="barbearia-joao")
    assert subscription.status == Subscription.Status.PENDING_CHECKOUT
    assert subscription.signup_checkout_state == "RECONCILIATION_REQUIRED"
    assert subscription.provider_checkout_id == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm backend pytest tests/test_onboarding.py::test_signup_unknown_checkout_outcome_persists_reconciliation_record -q`

Expected: FAIL because signup rolls back all local records.

- [ ] **Step 3: Write minimal implementation**

```python
with transaction.atomic():
    subscription = Subscription.objects.create(...)
    subscription.signup_checkout_state = Subscription.SignupCheckoutState.CREATING
    subscription.save(update_fields=["signup_checkout_state", "updated_at"])

try:
    checkout = create_recurring_checkout(subscription, user)
except AsaasCheckoutOutcomeUnknownError:
    Subscription.objects.filter(pk=subscription.pk).update(
        signup_checkout_state=Subscription.SignupCheckoutState.RECONCILIATION_REQUIRED
    )
    raise
```

Keep successful checkout persistence outside transaction. Keep compensation only for known local failure after a returned checkout.

- [ ] **Step 4: Run focused test to verify it passes**

Run: `docker compose run --rm backend pytest tests/test_onboarding.py::test_signup_unknown_checkout_outcome_persists_reconciliation_record -q`

Expected: PASS.

- [ ] **Step 5: Run regression tests**

Run: `docker compose run --rm backend pytest tests/test_onboarding.py tests/test_asaas_provider.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/billing/models.py backend/apps/billing/migrations/0010_subscription_signup_checkout_state.py backend/apps/billing/services.py backend/tests/test_onboarding.py
git commit -m "fix: preserve unknown signup checkouts for reconciliation"
```

