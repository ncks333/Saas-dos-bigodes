# Final fix — M&R Solutions production config

Data: 2026-07-15
Branch: `feat/mr-solutions-production-ready`

## Correções

- `VITE_MR_SOLUTIONS_WHATSAPP_URL` chega ao build do Docker via `ARG` e `ENV`.
- Compose encaminha somente fixture fictícia para desenvolvimento local.
- README e guia de deploy exigem que valor público real seja cadastrado somente no painel da Vercel, em Production e Preview.
- Alias `@` do Vite usa `fileURLToPath(new URL(...))`, decodificando caminhos com espaços e caracteres codificados.
- README operacional aponta somente para WhatsApp Cloud API oficial da Meta; não instrui Evolution API ou Baileys.
- Comandos executáveis do README para Vite sem Docker e build passam API localhost e exclusivamente a fixture fictícia de WhatsApp.

## TDD

- RED: `node --test config-tests/production-config.test.mjs` teve 6 testes existentes verdes e 4 novos falhos: Docker, Compose, documentação e alias.
- GREEN: `npm run test:config` passou com 10 testes.
- Follow-up RED: nova asserção do README falhou pela instrução legada de Evolution API. GREEN: `npm run test:config` passou com 11 testes.
- Segundo follow-up RED: 11 testes existentes passaram e 3 novos falharam porque os comandos de dev/build estavam incompletos e não continham fixture. GREEN: `npm run test:config` passou com 14 testes; asserção anterior foi restringida ao guia de deploy, pois README agora contém intencionalmente somente a fixture fictícia.

## Verificação

- Build Vite com API e URL de WhatsApp fictícias: passou.
- `npm run lint`: passou.
- Segundo follow-up: build com API localhost e fixture fictícia passou com 2.049 módulos; lint passou sem erros.
- `CHOKIDAR_USEPOLLING=true npm run test:e2e`: 9 passed.
- `docker compose config`: passou; arg do frontend contém fixture fictícia.
- Cópia do frontend em diretório temporário com espaço: build passou.
- `git diff --check`: passou.

## Limitação

`docker compose build frontend` não executou porque usuário atual não tem acesso ao socket Docker (`/var/run/docker.sock`). Compose está instalado e sua configuração foi validada.

## Segurança

Nenhum telefone ou token real foi lido, gravado ou incluído. Valor real continua fora do repositório, somente na interface da Vercel.

---

# SaaS onboarding/billing final review fixes

Date: 2026-07-21

Branch: `feat/saas-onboarding-billing`

Reviewed base before fixes: `d756326`

Implementation range before this report: `d756326..b2bb54e`

## Outcome

All 2 Critical, 10 Important, and 3 Minor findings in `final-review-findings.md` are fixed. Provider/card data remains hosted by Asaas; no browser field is authoritative for plan, price, trial, provider status, or payment. Ambiguous provider results fail closed and no live provider call or real secret was used.

## TDD evidence by requested finding

| # | Severity and behavior | RED captured before production edit | GREEN evidence | Main files / commit |
|---|---|---|---|---|
| 1 | Critical: Vercel direct SPA routes | New direct-route/privacy config assertions failed against missing fallback/headers. | Direct-route, headers, token-order and redirect config tests passed; final config suite `27/27`. | `frontend/vercel.json`, `frontend/config-tests/production-config.test.mjs`; `986278a`, `0e7bd29` |
| 2 | Critical: durable webhook returns exact 200 | 3 new acceptance/recovery tests failed; storage-failure control already passed. | Focused `4/4`; webhook suite `70/70`; persisted event returns 200 despite broker/release failure and recovery dispatches it. | `backend/apps/billing/views.py`, `tasks.py`, `tests/test_billing_webhooks.py`; `800138a` |
| 3 | Important: canonical public plan and safe pilot | Backend tests exposed arbitrary active-plan selection and frontend E2E exposed `plan_code` submission. | Focused backend `40/40`; E2E `1/1`; public endpoints resolve exact active `BILLING_PUBLIC_PLAN_CODE`, while trusted service input can snapshot an internal 60-day pilot offer. | `backend/apps/billing/serializers.py`, `services.py`, `views.py`, `tests/test_onboarding.py`, `frontend/src/BillingPages.tsx`; `79fccbe` |
| 4 | Important: official-shape `CHECKOUT_PAID` correlation | Official-shape fixture/provider/webhook tests failed because event-only fields were trusted and provider reconciliation was absent. | Provider/lifecycle focused `19/19`; provider+webhook `108/108`. Persisted checkout ID is retrieved and ID/status/reference plus exactly one active subscription are verified; mismatch/absence/ambiguity fails closed. | `backend/tests/fixtures/asaas_checkout_paid.json`, `providers/asaas.py`, `services.py`, provider/webhook tests; `95b776e` |
| 5 | Important: Asaas `dateCreated` timezone and ordering | Exact local timestamp and cross-cycle stale/out-of-order tests failed. | Same focused `19/19` and broad `108/108`; local documented format uses `ASAAS_PROVIDER_TIMEZONE`, aware ISO preserves its offset, stale cycle events do not win. | `backend/apps/billing/services.py`, settings, provider/webhook tests; `95b776e` |
| 6 | Important: canceled/expired checkout recovery | Initial/current regularization terminal-event and pending-owner email tests failed; frontend status route still encouraged duplicate signup. | Lifecycle/config/regularization suites passed (`19/19`, `145/145`, final E2E `27/27`); only current IDs/state are cleared and email can safely reissue. | `backend/apps/billing/services.py`, `views.py`, webhook/regularization tests, `frontend/src/BillingPages.tsx`; `95b776e`, `986278a` |
| 7 | Important: auth gate before JWT and password mutation | Tests showed blocked login changed `last_login`/could create token state and blocked access token could change password; logout control stayed available. | Focused auth `5/5` plus activation `3/3`; broader auth/access `122/122`. Block happens before pair creation; no `OutstandingToken` or `last_login` mutation; logout endpoints remain usable. | `backend/apps/accounts/serializers.py`, `views.py`, billing regularization tests; `fcb5a3f` |
| 8 | Important: preserve intentionally inactive employees | New initial and regularization activation tests failed because all tenant users were re-enabled. | Focused activation `3/3`; only intended owner/admin is activated; employees remain unchanged. | `backend/apps/billing/services.py`, webhook tests; `fcb5a3f` |
| 9 | Important: checkout URL origin defense | Backend provider/operator/API and browser E2E accepted non-official or lookalike HTTPS hosts. | Backend focused `40/40`; frontend origin rejection E2E passed; final config `27/27` and E2E `27/27`. Exact configured HTTPS Asaas origins are enforced at every boundary. | provider/service/view tests, `frontend/src/BillingPages.tsx`, production validators/env docs; `79fccbe`, `986278a`, `0e7bd29` |
| 10 | Important: regularization token privacy | Config/E2E assertions failed because capability token remained visible when analytics could initialize and route protections were absent. | Token is synchronously removed before PostHog, preserved only in module memory, analytics is disabled on the route, and Vercel/meta protections pass config/E2E. | `frontend/src/regularizationToken.ts`, `main.tsx`, `metadata.ts`, `index.html`, `vercel.json`; `986278a` |
| 11 | Important: suspension email per immutable cycle | New two-cycle test failed because static `SUSPENDED` dedupe suppressed the later cycle. | Focused lifecycle notifications `1/1`; broader migration/notification slice `24/24`; key uses `grace_payment_id` (legacy deadline fallback). | `backend/apps/billing/tasks.py`, notification tests; `d008cdd` |
| 12 | Minor: migration 0003 success backfill | MigrationExecutor test failed because legacy failed statuses populated successful payment state. | Focused migration test `1/1`; only `CONFIRMED`/`RECEIVED` backfill success; `OVERDUE`/risk rows remain grace-only. | migration `0003`, `tests/test_billing_models.py`; `d008cdd` |
| 13 | Minor: Turnstile retry target >=44px | E2E bounding-box assertion failed at 32px. | Focused E2E `1/1`; final E2E `27/27` with required Turnstile test key. | `frontend/src/billing.css`, `tests/mobile.spec.ts`; `986278a`, `b2bb54e` |
| 14 | Minor: durable non-enumerating regularization outbox | 7 outbox/retry/privacy tests failed; separate Resend idempotency-key allowlist test failed. | Focused outbox `8/8`, Resend `1/1`, broader regularization/email `66/66`; known eligible admin requests persist before broker, unknown emails are not stored, retries are bounded and snapshots expire within 24h. | model/migration `0009`, `views.py`, `tasks.py`, `core/email_backends.py`, regularization/email tests; `ee3fb12` |
| 15 | Recommended release hardening directly needed | Production settings tests failed for unsafe API host, origin, timezone, weak/reused tokens, and expiry; docs config tests later failed `4` new contracts (`23` passed). | Production settings `8/8`; docs/config GREEN `27/27`. Strong exact hosts/tokens/expiry and current env/runbooks are enforced. | `backend/core/settings/production.py`, production tests, env examples and deploy/security/runbook docs; `79fccbe`, `0e7bd29` |

Additional full-gate RED/GREEN: the first required production frontend build found an implicit-`any` origin parser; after explicit typing, production build passed. The first full E2E with a required Turnstile key found a test hardcoded to the no-key development bypass; after making the assertion honor Cloudflare's test-key token, focused E2E passed `1/1` and full E2E passed `27/27`. Commit: `b2bb54e`.

## Commits

- `986278a` — harden billing routes and redirects
- `79fccbe` — enforce server-owned billing offers
- `800138a` — acknowledge durable billing webhooks
- `95b776e` — reconcile Asaas checkout lifecycle
- `fcb5a3f` — gate blocked account credentials
- `d008cdd` — scope suspension notices to payment cycles
- `ee3fb12` — persist regularization email requests
- `0e7bd29` — align billing release contracts and config docs
- `b2bb54e` — satisfy production frontend gates

## Final release gates

- Backend full pytest with coverage: `271 passed`, `15 warnings`, total coverage `90.76%` (required `80%`). Warnings are only the deliberately short test JWT key.
- Ruff: `All checks passed!`
- Migration model diff: `No changes detected` from `makemigrations --check --dry-run` under test settings.
- Migration dry-run: `migrate --plan` resolved the complete graph through `billing.0009_regularization_email_request` without error.
- Frontend config/direct-route tests: `27 passed`, `0 failed`.
- Frontend production build with required API, Turnstile, exact production checkout origins and public WhatsApp env: passed; `2,053 modules transformed`.
- Frontend lint: passed with no findings.
- Full Playwright mobile E2E with required Turnstile and checkout-origin env: `27 passed`, `0 failed`.
- `git diff --check`: passed before each implementation/docs commit and before report commit.

## Residual risks and consciously deferred recommendations

- No live Asaas/Sandbox call was made. The sanitized official-shape fixture and mocked provider tests cover the contract. Checkout retrieval is isolated behind `GET /checkouts/{persisted_id}`; the current Asaas checkout guide advertises retrieval while its reference navigation is inconsistent. Any provider 404/schema drift fails closed, never activates access, and is observable/retryable.
- Conditional uniqueness for non-empty `provider_subscription_id` was not added: a production duplicate audit was unavailable, so enforcing it could make migration unsafe for legacy rows. Existing reconciliation requires exactly one provider result and fails closed.
- A separate dead-letter replay command was not added. Existing bounded dispatch/processing recovery, dead-letter state and database inspection are sufficient for this release; replay remains an operator hardening follow-up.
- Migration tests exercise production-shaped legacy rows and the full graph, but final production rollout still requires normal backup and migration monitoring. No migration should be reversed destructively.
