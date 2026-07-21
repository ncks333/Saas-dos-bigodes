# Task 9 — Deployment documentation and verification report

## Scope

Documented Asaas Sandbox/production deployment, webhook and checkout lifecycle,
Resend verification, Railway-only backend secrets, release/smoke cleanup, and
fail-closed reconciliation. Added configuration assertions without changing the
frontend validator: it already accepts only public `VITE_*` values and must not
reference Asaas or Resend backend secrets.

## RED

Command: `cd frontend && npm run test:config`

Result: 15 passed, 2 failed.

- `ASAAS_WEBHOOK_TOKEN` was empty in `backend/.env.production.example`.
- Deployment docs lacked required Asaas Sandbox/production lifecycle setup.

The new test also proves backend-only `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, and
`RESEND_API_KEY` cannot replace required public `VITE_API_URL`.

## GREEN

Command: `cd frontend && npm run test:config`

Result: 17 passed, 0 failed.

Coverage added for production placeholders, HTTPS frontend URL, Resend setup,
all code-supported Asaas events, browser callback boundary, lifecycle terms,
manual reconciliation, test-checkout cleanup, and validator secret boundary.

## Full verification

- Backend: `/tmp/saas-task9-uv-venv/bin/python -m pytest` — 224 passed; coverage 90.82% (threshold 80%).
- Backend: `/tmp/saas-task9-uv-venv/bin/python -m ruff check .` — passed.
- Backend: `/tmp/saas-task9-uv-venv/bin/python manage.py makemigrations --check --dry-run` — `No changes detected`.
- Frontend: `npm run test:config` — 17 passed.
- Frontend: `VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run build` — passed.
- Frontend: `npm run lint` — passed.
- Frontend: `CHOKIDAR_USEPOLLING=true npm run test:e2e` — 24 passed.
- Diff: `git diff --check` — passed.

## Changed files

- `backend/.env.production.example`
- `docs/DEPLOY.md`
- `docs/SECURITY.md`
- `README.md`
- `frontend/config-tests/production-config.test.mjs`
- `.superpowers/sdd/task-9-report.md`

## Self-review

- Matched event names against `backend/apps/billing/tasks.py`; no unsupported event is documented.
- Matched webhook and public routes against `backend/core/urls.py`.
- Verified trial pilot wording against `subscription.plan.trial_days`; a dedicated pilot plan is required for a 60-day subscription.
- Kept all example credentials as placeholders. No backend secret is added to Vercel/frontend validation.
- Documents state browser redirects do not confirm payment and ambiguous regularization requires manual fail-closed reconciliation.

## Environment warnings

- Initial backend commands failed because `python`, `pytest`, and `ruff` were absent from PATH. A temporary uv venv at `/tmp/saas-task9-uv-venv` supplied project dependencies for verification.
- Migration dry-run warned that hostname `postgres` could not resolve, but completed with `No changes detected`.
- E2E emitted non-fatal `NO_COLOR`/`FORCE_COLOR` warnings and one Vite proxy `ECONNREFUSED` for local backend; Playwright still completed 24/24.
- Docker daemon socket was unavailable to current user, so Docker was not used for backend gates.
