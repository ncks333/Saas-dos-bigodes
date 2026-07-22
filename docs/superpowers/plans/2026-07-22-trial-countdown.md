# Trial Countdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or execute inline task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show trial users remaining calendar days at top of dashboard.

**Architecture:** Extend existing authenticated `/api/v1/dashboard/` response with current tenant subscription status and `trial_ends_at`. `DashboardPage` renders a small notice only when status is `TRIAL`, using a pure frontend day calculation.

**Tech Stack:** Django REST Framework, React, TypeScript, TanStack Query, pytest.

## Global Constraints

- Do not change checkout, trial dates, access control, or payment collection.
- Notice copy exactly: `Teste grátis: faltam X dias`.
- Remaining days never below zero.

---

### Task 1: Expose current subscription in dashboard API

**Files:**
- Modify: `backend/apps/reports/views.py`
- Create: `backend/tests/test_dashboard_subscription.py`

**Consumes:** authenticated tenant user and `Barbershop.subscription` one-to-one relation.

**Produces:** dashboard JSON keys `subscription_status` and `trial_ends_at`.

- [ ] **Step 1: Write failing API test**

```python
@pytest.mark.django_db
def test_dashboard_returns_current_tenant_trial_end(client, admin_user, subscription):
    subscription.status = Subscription.Status.TRIAL
    subscription.trial_ends_at = timezone.now() + timedelta(days=29)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])
    client.force_login(admin_user)

    response = client.get("/api/v1/dashboard/")

    assert response.status_code == 200
    assert response.data["subscription_status"] == "TRIAL"
    assert response.data["trial_ends_at"] == subscription.trial_ends_at.isoformat().replace("+00:00", "Z")
```

- [ ] **Step 2: Verify RED**

Run:

```bash
docker compose exec -T -e DJANGO_SETTINGS_MODULE=core.settings.test backend pytest tests/test_dashboard_subscription.py -q --no-cov
```

Expected: FAIL because dashboard response lacks subscription keys.

- [ ] **Step 3: Add current tenant subscription data**

```python
from apps.billing.models import Subscription

subscription = Subscription.objects.filter(
    barbershop_id=request.user.barbershop_id
).only("status", "trial_ends_at").first()

return Response({
    # existing dashboard fields
    "subscription_status": subscription.status if subscription else None,
    "trial_ends_at": subscription.trial_ends_at if subscription else None,
})
```

- [ ] **Step 4: Verify GREEN**

Run same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/reports/views.py backend/tests/test_dashboard_subscription.py
git commit -m "feat: expose trial status in dashboard"
```

### Task 2: Render dashboard trial notice

**Files:**
- Modify: `frontend/src/ProductApp.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/tests/mobile.spec.ts`

**Consumes:** dashboard API `subscription_status: string | null` and `trial_ends_at: string | null`.

**Produces:** visible trial notice for trial users only.

- [ ] **Step 1: Write failing browser test**

```ts
test("trial dashboard shows remaining days", async ({ page }) => {
  await page.route("**/api/v1/dashboard/", route => route.fulfill({json: {
    daily_revenue: 0, monthly_revenue: 0, appointments: 0,
    cancellation_rate: 0, popular_hours: [], recurring_customers: [],
    subscription_status: "TRIAL", trial_ends_at: "2026-08-21T18:39:24Z",
  }}));

  await page.goto("/");

  await expect(page.getByText(/Teste grátis: faltam \d+ dias/)).toBeVisible();
});
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd frontend && npx playwright test tests/mobile.spec.ts
```

Expected: FAIL because notice does not exist.

- [ ] **Step 3: Add minimal renderer and styling**

```tsx
const trialDaysRemaining = (value?: string | null) => {
  if (!value) return 0;
  return Math.max(0, Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000));
};

{d.subscription_status === "TRIAL" && (
  <p className="trial-notice" role="status">
    Teste grátis: faltam {trialDaysRemaining(d.trial_ends_at)} dias
  </p>
)}
```

```css
.trial-notice {
  margin: 0 0 1rem;
  padding: .75rem 1rem;
  border: 1px solid var(--gold);
  border-radius: .75rem;
  color: var(--gold);
}
```

- [ ] **Step 4: Verify GREEN**

Run same Playwright command. Expected: PASS.

- [ ] **Step 5: Run regression checks**

```bash
cd frontend && npm run build
docker compose exec -T -e DJANGO_SETTINGS_MODULE=core.settings.test backend pytest tests/test_dashboard_subscription.py -q --no-cov
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ProductApp.tsx frontend/src/index.css frontend/tests/mobile.spec.ts
git commit -m "feat: show trial days in dashboard"
```
