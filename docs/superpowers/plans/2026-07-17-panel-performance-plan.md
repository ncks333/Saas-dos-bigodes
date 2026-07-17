# M&R BarberHub Panel Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make common panel changes feel immediate and reduce unnecessary Railway/Supabase work without changing BarberHub business rules.

**Architecture:** Keep React Query as the cache boundary. Mutations reconcile returned server records into existing query data and roll back optimistic status changes on failure. Add a tenant-safe appointment-day filter and replace per-slot availability queries with one query per interval source.

**Tech Stack:** React 19, TypeScript, React Query 5, Axios, Playwright, Django REST Framework, Django ORM, PostgreSQL, pytest-django.

## Global Constraints

- Preserve tenant isolation, JWT behavior, appointment transactions, WhatsApp delivery, and existing Portuguese UI copy.
- Do not add a frontend dependency.
- Do not change Vercel, Railway, Supabase, Redis, or production secrets in this code cycle.
- Optimistic UI must roll back when the API rejects the mutation.
- No real customer data or production tokens in tests, logs, or fixtures.
- Run TDD: each behavior gets a failing test before production code.

---

## File Map

- Modify `frontend/src/ProductApp.tsx`: debounce customer search, reconcile mutations, query appointments by selected day, and refresh reports in the background.
- Create `frontend/src/useDebouncedValue.ts`: reusable 300 ms debounce hook.
- Modify `frontend/tests/mobile.spec.ts`: E2E tests for optimistic status, rollback, request count, and debounced search.
- Modify `backend/apps/appointments/views.py`: tenant-safe `day` filter using barbershop timezone.
- Modify `backend/apps/appointments/services.py`: load appointment/block intervals once and calculate slots in memory.
- Modify `backend/tests/test_api_flows.py`: API test proving selected-day filtering.
- Modify `backend/tests/test_appointments.py`: query-count test for constant-query availability.
- Modify `docs/DEPLOY.md`: post-change cold/warm latency checklist and Railway/Supabase region checks.

## Task 1: Add failing frontend performance tests

**Files:**
- Modify: `frontend/tests/mobile.spec.ts`
- Create: `frontend/src/useDebouncedValue.ts` only in Step 3

**Interfaces:**
- Consumes: existing `/api/v1/**` Playwright routing and `Appointment` panel UI.
- Produces: executable browser assertions for the cache behavior used by Tasks 2 and 3.

- [ ] **Step 1: Write the failing optimistic-status test**

Add a test that seeds local auth, returns one appointment, delays the PATCH response,
and verifies the row shows `Confirmado` before the delayed response resolves. Count
GET requests to `/appointments/` after the PATCH and require zero additional list GETs.

```ts
test("status da agenda atualiza antes da resposta e não recarrega a lista", async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem("access", "teste");
    localStorage.setItem("refresh", "teste");
    localStorage.setItem("user", JSON.stringify({id: 1, name: "Admin", role: "ADMIN"}));
  });
  let listGets = 0;
  let releasePatch!: () => void;
  const patchReleased = new Promise<void>(resolve => { releasePatch = resolve; });
  await page.route("**/api/v1/**", async route => {
    const url = route.request().url();
    if (url.includes("/appointments/") && route.request().method() === "GET") {
      listGets += 1;
      await route.fulfill({json: [{id: 7, customer: 2, customer_name: "Cliente", service: 3, service_name: "Corte", employee: null, starts_at: "2030-01-10T13:00:00Z", ends_at: "2030-01-10T13:30:00Z", notes: "", status: "PENDENTE", source: "MANUAL"}]});
      return;
    }
    if (url.includes("/appointments/7/") && route.request().method() === "PATCH") {
      await patchReleased;
      await route.fulfill({json: {id: 7, customer: 2, customer_name: "Cliente", service: 3, service_name: "Corte", employee: null, starts_at: "2030-01-10T13:00:00Z", ends_at: "2030-01-10T13:30:00Z", notes: "", status: "CONFIRMADO", source: "MANUAL"}});
      return;
    }
    if (url.includes("daily_summary")) {
      await route.fulfill({json: {total: 1, confirmed: 0, pending: 1, awaiting: 0, cancelled: 0, completed: 0, no_show: 0, revenue: 0}});
      return;
    }
    if (url.includes("/dashboard/")) {
      await route.fulfill({json: {daily_revenue: 0, monthly_revenue: 0, cancellation_rate: 0, popular_hours: []}});
      return;
    }
    await route.fulfill({json: []});
  });
  await page.goto("/login");
  await page.getByRole("button", {name: "Agenda", exact: true}).click();
  await page.getByLabel("Status").selectOption("CONFIRMADO");
  await expect(page.getByText("Confirmado", {exact: true})).toBeVisible();
  expect(listGets).toBe(1);
  releasePatch();
});
```

- [ ] **Step 2: Run the focused test and verify it fails for the intended reason**

Run: `cd frontend && npm run test:e2e -- mobile.spec.ts -g "status da agenda"`

Expected: FAIL because the current UI waits for PATCH and invalidates the full
appointment query before the row changes.

- [ ] **Step 3: Write failing debounce and rollback tests**

Add one test that types three characters into the customer search and asserts only
one `/customers/?search=...` request after 300 ms. Add one test that rejects the
customer PATCH and asserts the old row value returns with the existing form error.

- [ ] **Step 4: Run both tests and verify they fail**

Run: `cd frontend && npm run test:e2e -- mobile.spec.ts -g "busca de clientes|rollback"`

Expected: FAIL because search currently requests every keystroke and mutations only
invalidate after the server response.

## Task 2: Implement React Query reconciliation and debounce

**Files:**
- Create: `frontend/src/useDebouncedValue.ts`
- Modify: `frontend/src/ProductApp.tsx`

**Interfaces:**
- Consumes: `useDebouncedValue<T>(value: T, delayMs: number): T`.
- Produces: mutations that update cache directly, rollback context for status, and
  query keys using the debounced customer term.

- [ ] **Step 1: Implement only the debounce hook**

```ts
import {useEffect, useState} from "react";

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
```

- [ ] **Step 2: Run debounce test and verify it passes**

Run: `cd frontend && npm run test:e2e -- mobile.spec.ts -g "busca de clientes"`

Expected: PASS after wiring the hook into `CustomersPage` with
`const debouncedSearch = useDebouncedValue(search, 300)` and query key
`["customers", debouncedSearch]`.

- [ ] **Step 3: Implement optimistic appointment status**

Change the status mutation to return `response.data`, update `appointments` cache
in `onMutate`, keep the previous array in the mutation context, restore it in
`onError`, and replace the row with the server response in `onSuccess`. Do not
invalidate `appointments` on success. Keep dashboard and daily-summary invalidation
as background calls using `void qc.invalidateQueries(...)`.

```ts
const status = useMutation({
  mutationFn: ({id, status}: {id: number; status: string}) =>
    api.patch<Appointment>(`/appointments/${id}/`, {status}).then(response => response.data),
  onMutate: async ({id, status}) => {
    await qc.cancelQueries({queryKey: ["appointments"]});
    const previous = qc.getQueryData<Appointment[]>(["appointments"]);
    qc.setQueryData<Appointment[]>(["appointments"], current =>
      current?.map(item => item.id === id ? {...item, status} : item),
    );
    return {previous};
  },
  onError: (_error, _variables, context) => {
    if (context?.previous) qc.setQueryData(["appointments"], context.previous);
  },
  onSuccess: serverItem => {
    qc.setQueryData<Appointment[]>(["appointments"], current =>
      current?.map(item => item.id === serverItem.id ? serverItem : item),
    );
  },
  onSettled: () => {
    void qc.invalidateQueries({queryKey: ["dashboard"]});
    void qc.invalidateQueries({queryKey: ["daily-summary"]});
  },
});
```

- [ ] **Step 4: Apply the same direct-cache rule to customer/service edits**

For an existing customer or service, replace the matching item in every active
query whose key starts with `customers` or `services`. Keep invalidation only for
creation, because a newly created record may need to enter multiple filtered lists.
For soft deletion, remove the item from visible customer lists and update the active
options cache. Keep the server response as the source of truth.

- [ ] **Step 5: Run focused frontend tests and build**

Run: `cd frontend && npm run test:e2e -- mobile.spec.ts -g "status da agenda|busca de clientes|rollback"`

Run: `cd frontend && npm run build && npm run lint`

Expected: focused tests, TypeScript build, and lint pass.

## Task 3: Filter agenda requests by selected day

**Files:**
- Modify: `backend/apps/appointments/views.py`
- Modify: `backend/tests/test_api_flows.py`
- Modify: `frontend/src/ProductApp.tsx`

**Interfaces:**
- Consumes: optional authenticated query parameter `day=YYYY-MM-DD`.
- Produces: appointments whose UTC timestamps fall within the selected local day,
  and no behavior change when `day` is absent.

- [ ] **Step 1: Write the failing backend API test**

Create two appointments in the same tenant on different local dates, request
`/api/v1/appointments/?day=<first-date>`, and assert only the first ID is returned.
Also request without `day` and assert both are returned.

```python
filtered = api_client.get(f"/api/v1/appointments/?day={first_day.date().isoformat()}")
assert filtered.status_code == 200
assert [item["id"] for item in filtered.data["results"]] == [first.id]

all_items = api_client.get("/api/v1/appointments/")
assert {item["id"] for item in all_items.data["results"]} == {first.id, second.id}
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd backend && pytest tests/test_api_flows.py -k "appointment_day_filter" -v`

Expected: FAIL because the view currently ignores `day`.

- [ ] **Step 3: Implement tenant-safe local-day filtering**

In `AppointmentViewSet.get_queryset`, call `super().get_queryset()` first, parse
`day` with DRF `DateField`, read `request.user.barbershop.timezone`, build an aware
local midnight and the following midnight, then apply `starts_at__gte` and
`starts_at__lt`. Raise DRF validation error for malformed dates.

```python
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from rest_framework import serializers

def get_queryset(self):
    queryset = super().get_queryset()
    raw_day = self.request.query_params.get("day")
    if not raw_day:
        return queryset
    day = serializers.DateField().to_internal_value(raw_day)
    timezone_name = self.request.user.barbershop.timezone
    start = datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone_name))
    return queryset.filter(starts_at__gte=start, starts_at__lt=start + timedelta(days=1))
```

- [ ] **Step 4: Run backend test and verify it passes**

Run: `cd backend && pytest tests/test_api_flows.py -k "appointment_day_filter" -v`

Expected: PASS.

- [ ] **Step 5: Send day in the frontend query key and request**

Use query key `["appointments", day]` and call
`fetchAll<Appointment>("/appointments/", {ordering: "starts_at", day})`. Remove
the client-side date filter over a full historical list. Update cache handlers to
use the active day key.

- [ ] **Step 6: Run frontend build and backend API regression**

Run: `cd frontend && npm run build`

Run: `cd backend && pytest tests/test_api_flows.py -k "staff_appointment_dashboard_and_summary or appointment_day_filter" -v`

Expected: PASS.

## Task 4: Make availability query count constant

**Files:**
- Modify: `backend/apps/appointments/services.py`
- Modify: `backend/tests/test_appointments.py`

**Interfaces:**
- Consumes: existing `available_slots(barbershop, day, service)` signature.
- Produces: same slot list with three interval-source queries: operating hour,
  active appointments, and schedule blocks.

- [ ] **Step 1: Add a failing query-count test**

Use `django_assert_num_queries(3)` around `available_slots` for a day with a normal
service and operating hours. Assert the returned slots still contain the expected
first future slot.

```python
def test_available_slots_use_constant_query_count(barbershop, service, django_assert_num_queries):
    day = (datetime.now(ZoneInfo(barbershop.timezone)) + timedelta(days=7)).date()
    with django_assert_num_queries(3):
        slots = available_slots(barbershop=barbershop, day=day, service=service)
    assert slots
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd backend && pytest tests/test_appointments.py -k "constant_query_count" -v`

Expected: FAIL because the current implementation queries appointments and blocks
once per candidate slot.

- [ ] **Step 3: Replace per-slot ORM calls with interval lists**

Fetch `starts_at`/`ends_at` for active appointments and blocks once. Add a local
overlap predicate using `interval_start < candidate_end and interval_end > candidate_start`.
Keep the existing time-zone conversion, service duration, past-time check, and
30-minute increment unchanged.

```python
appointments = list(Appointment.objects.filter(
    barbershop=barbershop,
    status__in=ACTIVE_STATUSES,
    starts_at__lt=close,
    ends_at__gt=cursor,
).values_list("starts_at", "ends_at"))
blocks = list(ScheduleBlock.objects.filter(
    barbershop=barbershop,
    starts_at__lt=close,
    ends_at__gt=cursor,
).values_list("starts_at", "ends_at"))

def overlaps(intervals, candidate_start, candidate_end):
    return any(start < candidate_end and end > candidate_start for start, end in intervals)
```

- [ ] **Step 4: Run availability tests and full backend suite**

Run: `cd backend && pytest tests/test_appointments.py -k "available_slots" -v`

Run: `cd backend && pytest`

Expected: PASS with no slot-rule regressions.

## Task 5: Document production measurement and final verification

**Files:**
- Modify: `docs/DEPLOY.md`

**Interfaces:**
- Consumes: deployed API URL and Railway/Supabase dashboards.
- Produces: repeatable cold/warm measurement procedure for the client-demo
  environment.

- [ ] **Step 1: Add the operator checklist**

Document measuring five sequential requests to `/api/v1/health/` and one authenticated
panel request, recording cold and warm medians. Include checks that Railway and
Supabase use the same region, the web service is not sleeping during the demo, and
CPU/RAM/database connection limits are below saturation.

- [ ] **Step 2: Run all verification commands**

Run:

```bash
cd backend && pytest && ruff check .
cd ../frontend && npm run build && npm run lint && npm run test:e2e
```

Expected: all commands pass.

- [ ] **Step 3: Commit the implementation as one reviewed performance change**

```bash
git add frontend/src frontend/tests backend/apps/appointments backend/tests docs/DEPLOY.md
git commit -m "perf: speed up BarberHub panel interactions"
```

## Self-review checklist

- Spec coverage: optimistic update, rollback, targeted queries, debounce, availability
  query reduction, infrastructure measurement, security constraints, and regression
  tests each have a task above.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation step remains.
- Type consistency: appointment cache uses `Appointment[]`; backend day filter uses
  `day`; debounce returns the same generic value type.
- Scope: no provider migration, visual redesign, authentication change, or WhatsApp
  change is included.
