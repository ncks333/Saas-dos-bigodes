# M&R Solutions Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `https://app.mrbarberhub.com.br/mr-solutions` with a validated WhatsApp CTA, working Vercel routing, compatible CSP, and reduced-motion behavior.

**Architecture:** Keep the existing pathname router and Vite/Vercel deployment. A small importable Node module validates public production environment values before Vite builds; config tests inspect Vercel routing/CSP, while Playwright verifies runtime behavior and accessibility.

**Tech Stack:** React 19, TypeScript 5.8, Vite 6, Vercel JSON configuration, Node test runner, Playwright, ESLint.

## Global Constraints

- Keep `https://app.mrbarberhub.com.br/` as the M&R BarberHub homepage.
- Publish M&R Solutions only at `https://app.mrbarberhub.com.br/mr-solutions`.
- Never commit either real WhatsApp number; configure the M&R Solutions URL only in Vercel.
- `WHATSAPP_PHONE_NUMBER_ID` remains a Meta numeric asset ID, never a phone string.
- Preserve the existing landing design and all BarberHub login/booking flows.
- Remove the public `/demo/globe` development route.
- Allow only the exact existing R2 texture host in CSP; add no new wildcard.
- Do not stage `dist`, `node_modules`, unused logo variants, or `frontend/tsconfig.tsbuildinfo`.

---

## File Structure

- `frontend/scripts/validate-production-env.mjs`: pure production environment validator imported by Vite and Node tests.
- `frontend/config-tests/production-config.test.mjs`: Node tests for env validation, Vercel rewrites, CSP, and removal of development routes.
- `frontend/vite.config.ts`: invokes the validator for build commands and keeps the existing `@` alias.
- `frontend/vercel.json`: rewrites `/mr-solutions` and permits the exact R2 image origin.
- `frontend/src/App.tsx`: retains the product routes and removes `/demo/globe`.
- `frontend/src/MarketingPages.tsx`: consumes the required validated WhatsApp URL without a production fallback.
- `frontend/src/components/ui/globe.tsx`: preserves the globe and disables animation for reduced-motion users.
- `frontend/tests/mobile.spec.ts`: runtime CTA, route, responsive, and reduced-motion regression checks.
- `frontend/playwright.config.ts`: supplies an obviously fictitious development-only CTA to the Vite test server.
- `frontend/package.json` / `frontend/package-lock.json`: adds config testing and removes unused `motion`.

---

### Task 1: Validate the public WhatsApp CTA before build

**Files:**
- Create: `frontend/scripts/validate-production-env.mjs`
- Create: `frontend/config-tests/production-config.test.mjs`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/MarketingPages.tsx:64-65`
- Modify: `frontend/src/vite-env.d.ts:3-8`
- Modify: `frontend/playwright.config.ts:13-18`
- Modify: `frontend/.env.production.example:1-4`
- Modify: `frontend/package.json:6-12`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/marketing.css`
- Create: `frontend/src/components/ui/globe.tsx`
- Create: `frontend/src/components/ui/demo.tsx`
- Add used asset: `frontend/public/mr-solutions-logo-compact-cutout.png`
- Add used asset: `frontend/public/mr-solutions-logo-full-cutout.png`
- Add used asset: `frontend/public/mr-solutions-mark-only.png`
- Add temporary referenced asset: `frontend/public/mr-solutions-logo-icon.png`

**Interfaces:**
- Produces: `validateProductionEnv(env: Record<string, string | undefined>): void`.
- Consumes: `VITE_API_URL` and `VITE_MR_SOLUTIONS_WHATSAPP_URL` from Vite/Vercel.
- Runtime test URL: `https://wa.me/5511999999999?text=Teste` (fictitious and test-only).

- [ ] **Step 1: Write failing Node tests for production environment validation**

Create `frontend/config-tests/production-config.test.mjs` with:

```js
import assert from "node:assert/strict";
import test from "node:test";

import {validateProductionEnv} from "../scripts/validate-production-env.mjs";

const valid = {
  VITE_API_URL: "https://api.mrbarberhub.com.br/api/v1",
  VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
};

test("accepts canonical public production URLs", () => {
  assert.doesNotThrow(() => validateProductionEnv(valid));
});

test("rejects missing WhatsApp URL", () => {
  assert.throws(
    () => validateProductionEnv({...valid, VITE_MR_SOLUTIONS_WHATSAPP_URL: ""}),
    /VITE_MR_SOLUTIONS_WHATSAPP_URL/,
  );
});

test("rejects placeholder and non-wa.me contact URLs", () => {
  for (const value of [
    "https://wa.me/5500000000000?text=Teste",
    "https://example.com/5511999999999",
    "http://wa.me/5511999999999",
  ]) {
    assert.throws(
      () => validateProductionEnv({...valid, VITE_MR_SOLUTIONS_WHATSAPP_URL: value}),
      /WhatsApp pública válida/,
    );
  }
});
```

- [ ] **Step 2: Run the config test and verify RED**

Run:

```bash
cd frontend
node --test config-tests/production-config.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `scripts/validate-production-env.mjs`.

- [ ] **Step 3: Implement the pure production validator**

Create `frontend/scripts/validate-production-env.mjs` with:

```js
export function validateProductionEnv(env) {
  if (!env.VITE_API_URL) {
    throw new Error("VITE_API_URL deve ser configurada para o build de produção.");
  }

  const raw = env.VITE_MR_SOLUTIONS_WHATSAPP_URL;
  if (!raw) {
    throw new Error("VITE_MR_SOLUTIONS_WHATSAPP_URL deve ser configurada para o build de produção.");
  }

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("Configure uma URL de WhatsApp pública válida em VITE_MR_SOLUTIONS_WHATSAPP_URL.");
  }

  const digits = url.pathname.slice(1);
  const isPlaceholder = /^550+$/.test(digits);
  if (
    url.protocol !== "https:"
    || url.hostname !== "wa.me"
    || !/^55\d{10,11}$/.test(digits)
    || isPlaceholder
  ) {
    throw new Error("Configure uma URL de WhatsApp pública válida em VITE_MR_SOLUTIONS_WHATSAPP_URL.");
  }
}
```

- [ ] **Step 4: Connect Vite to the validator and remove the runtime placeholder**

Update `frontend/vite.config.ts` so its imports and validation are:

```ts
import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";
import {validateProductionEnv} from "./scripts/validate-production-env.mjs";

export default defineConfig(({command, mode}) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build") validateProductionEnv(env);
```

Keep the existing `plugins`, `resolve.alias`, `server`, and proxy configuration unchanged.

Replace the WhatsApp constant in `frontend/src/MarketingPages.tsx` with:

```ts
const mrWhatsappUrl = import.meta.env.VITE_MR_SOLUTIONS_WHATSAPP_URL;
```

Make `VITE_MR_SOLUTIONS_WHATSAPP_URL` required in `frontend/src/vite-env.d.ts`:

```ts
readonly VITE_MR_SOLUTIONS_WHATSAPP_URL: string;
```

Keep a placeholder, never a real number, in `frontend/.env.production.example`:

```text
VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/55DDDNUMERO?text=Ol%C3%A1%2C%20quero%20conversar%20com%20a%20M%26R%20Solutions.
```

- [ ] **Step 5: Give Playwright an explicit test-only contact and add the config script**

Add `env` to `webServer` in `frontend/playwright.config.ts`:

```ts
webServer: {
  command: "npm run dev -- --port 4173",
  url: "http://127.0.0.1:4173",
  reuseExistingServer: true,
  env: {
    VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
  },
},
```

Add this script to `frontend/package.json`:

```json
"test:config": "node --test config-tests/*.test.mjs"
```

Retain the existing `@` aliases in `frontend/vite.config.ts` and
`frontend/tsconfig.json`; they are required by the globe imports.

- [ ] **Step 6: Run GREEN tests and prove the placeholder cannot build**

Run:

```bash
cd frontend
npm run test:config
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5500000000000 npm run build
```

Expected: Node tests PASS; build exits non-zero with `Configure uma URL de WhatsApp pública válida`.

- [ ] **Step 7: Commit Task 1**

```bash
git add frontend/scripts/validate-production-env.mjs frontend/config-tests/production-config.test.mjs frontend/vite.config.ts frontend/src/MarketingPages.tsx frontend/src/vite-env.d.ts frontend/playwright.config.ts frontend/.env.production.example frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/src/App.tsx frontend/src/marketing.css frontend/src/components/ui/globe.tsx frontend/src/components/ui/demo.tsx frontend/public/mr-solutions-logo-compact-cutout.png frontend/public/mr-solutions-logo-full-cutout.png frontend/public/mr-solutions-mark-only.png frontend/public/mr-solutions-logo-icon.png
git commit -m "feat: validate M&R Solutions production contact"
```

---

### Task 2: Make the M&R Solutions route and globe production-safe

**Files:**
- Modify: `frontend/config-tests/production-config.test.mjs`
- Modify: `frontend/vercel.json`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/components/ui/demo.tsx`
- Modify: `frontend/tests/mobile.spec.ts:42-71`

**Interfaces:**
- Produces: Vercel rewrite `/mr-solutions -> /index.html`.
- Produces: CSP `img-src` allowlist entry for `https://pub-940ccf6255b54fa799a9b01050e6c227.r2.dev`.
- Removes: application route `/demo/globe`.

- [ ] **Step 1: Add failing config assertions**

Extend `frontend/config-tests/production-config.test.mjs` imports:

```js
import {readFileSync} from "node:fs";
```

Append:

```js
const root = new URL("../", import.meta.url);
const vercel = JSON.parse(readFileSync(new URL("vercel.json", root), "utf8"));
const appSource = readFileSync(new URL("src/App.tsx", root), "utf8");

test("Vercel serves the M&R Solutions SPA route", () => {
  assert.ok(vercel.rewrites.some(item =>
    item.source === "/mr-solutions" && item.destination === "/index.html"
  ));
});

test("CSP allows only the exact globe texture origin", () => {
  const csp = vercel.headers
    .flatMap(item => item.headers)
    .find(item => item.key === "Content-Security-Policy").value;
  assert.match(csp, /img-src[^;]*https:\/\/pub-940ccf6255b54fa799a9b01050e6c227\.r2\.dev/);
});

test("development globe route is not published", () => {
  assert.doesNotMatch(appSource, /demo\/globe|DemoOne/);
});
```

- [ ] **Step 2: Run config tests and verify RED**

Run: `cd frontend && npm run test:config`

Expected: three new tests FAIL because rewrite/CSP are absent and `DemoOne` remains.

- [ ] **Step 3: Update Vercel routing and CSP**

Add this rewrite to `frontend/vercel.json`:

```json
{"source": "/mr-solutions", "destination": "/index.html"}
```

In the existing CSP string, change `img-src` to:

```text
img-src 'self' data: blob: https://*.posthog.com https://pub-940ccf6255b54fa799a9b01050e6c227.r2.dev;
```

Do not change the remaining directives.

- [ ] **Step 4: Remove the technical route and strengthen the runtime CTA check**

Remove the `DemoOne` import and `/demo/globe` branch from `frontend/src/App.tsx`.
Delete `frontend/src/components/ui/demo.tsx`.

Delete the Playwright test named `demo do globo renderiza componente shadcn`.
Replace the M&R CTA assertion with:

```ts
await expect(page.getByRole("link", {name: /Conversar sobre meu projeto/}).first())
  .toHaveAttribute("href", /^https:\/\/wa\.me\/5511999999999\?text=Teste$/);
```

- [ ] **Step 5: Run Task 2 GREEN tests**

Run:

```bash
cd frontend
npm run test:config
CHOKIDAR_USEPOLLING=true npm run test:e2e
```

Expected: config tests PASS; Playwright suite passes with one fewer technical demo test.

- [ ] **Step 6: Commit Task 2**

```bash
git add frontend/config-tests/production-config.test.mjs frontend/vercel.json frontend/src/App.tsx frontend/tests/mobile.spec.ts
git add -u frontend/src/components/ui/demo.tsx
git commit -m "fix: make M&R Solutions route production-safe"
```

---

### Task 3: Respect reduced motion and remove unused production inputs

**Files:**
- Modify: `frontend/src/components/ui/globe.tsx`
- Modify: `frontend/src/MarketingPages.tsx:75-78`
- Modify: `frontend/tests/mobile.spec.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Delete: `frontend/public/mr-solutions-logo-icon.png`
- Preserve unstaged: unused logo variants and `frontend/tsconfig.tsbuildinfo`

**Interfaces:**
- Produces: `.mr-solutions-globe` and `.mr-solutions-globe-star` CSS hooks.
- Produces: reduced-motion computed `animation-name: none`.
- Removes: unused npm dependency `motion`.

- [ ] **Step 1: Add a failing reduced-motion Playwright test**

Append after the M&R Solutions landing test in `frontend/tests/mobile.spec.ts`:

```ts
test("globo respeita preferência por movimento reduzido", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/mr-solutions");
  const globe = page.locator(".mr-solutions-globe");
  await expect(globe).toBeVisible();
  await expect(globe).toHaveCSS("animation-name", "none");
  await expect(page.locator(".mr-solutions-globe-star").first()).toHaveCSS("animation-name", "none");
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend
CHOKIDAR_USEPOLLING=true npx playwright test -g "globo respeita"
```

Expected: FAIL because `.mr-solutions-globe` does not exist.

- [ ] **Step 3: Add stable classes and reduced-motion CSS**

In `frontend/src/components/ui/globe.tsx`, add `mr-solutions-globe` to the globe
container class and `mr-solutions-globe-star` to every star class. Append to the
component style block:

```css
@media (prefers-reduced-motion: reduce) {
  .mr-solutions-globe,
  .mr-solutions-globe-star {
    animation: none !important;
  }
}
```

Keep the texture URL, dimensions, shadows, and normal animations unchanged.

- [ ] **Step 4: Simplify the unused compact brand branch**

Replace `SolutionsBrand` in `frontend/src/MarketingPages.tsx` with:

```tsx
function SolutionsBrand() {
  return <a className="solutions-brand" href="/mr-solutions" aria-label="M&R Solutions — início">
    <img src="/mr-solutions-logo-compact-cutout.png" alt="M&R Solutions"/>
  </a>;
}
```

The unreferenced icon logo must not remain in the final tree.

Remove the now-unreferenced tracked icon asset:

```bash
git rm frontend/public/mr-solutions-logo-icon.png
```

- [ ] **Step 5: Remove the unused package mechanically**

Run:

```bash
cd frontend
npm uninstall motion
```

Expected: `motion` disappears from `package.json` and its lockfile entries.

- [ ] **Step 6: Run Task 3 GREEN tests**

Run:

```bash
cd frontend
CHOKIDAR_USEPOLLING=true npm run test:e2e
npm run lint
```

Expected: Playwright and ESLint both exit `0`.

- [ ] **Step 7: Commit Task 3 without unused/generated assets**

```bash
git add frontend/src/components/ui/globe.tsx frontend/src/MarketingPages.tsx frontend/tests/mobile.spec.ts frontend/package.json frontend/package-lock.json
git commit -m "fix: polish M&R Solutions production experience"
```

Before committing, verify these paths are not staged:

```bash
git diff --cached --name-only | rg "tsconfig\.tsbuildinfo|mr-solutions-logo-(compact|full)\.png" && exit 1 || true
```

---

### Task 4: Full verification and deploy handoff

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: Tasks 1-3 and external Vercel variables.
- Produces: a reviewed commit set ready for Vercel deployment.

- [ ] **Step 1: Run all frontend checks with safe local public values**

```bash
cd frontend
npm ci
npm run test:config
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run build
npm run lint
CHOKIDAR_USEPOLLING=true npm run test:e2e
```

Expected: install, config tests, build, lint, and Playwright all exit `0`.

- [ ] **Step 2: Scan the production bundle and staged changes**

```bash
rg -n "5500000000000|55DDDNUMERO" dist --glob '!node_modules/**'
git restore --worktree frontend/tsconfig.tsbuildinfo
git diff --check
git status --short
```

Expected: no real number or zero placeholder in `dist`; only intentionally
preserved unstaged logo variants and `frontend/tsconfig.tsbuildinfo` may remain.

- [ ] **Step 3: Request independent code review**

Review all frontend commits from `4c128b8` through `HEAD` against
`docs/superpowers/specs/2026-07-15-mr-solutions-production-readiness-design.md`.
Fix every Critical or Important finding and rerun Step 1.

- [ ] **Step 4: Configure Vercel without committing the real value**

In Vercel Production and Preview, set the API URL exactly as below:

```text
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1
```

Set `VITE_MR_SOLUTIONS_WHATSAPP_URL` in the Vercel UI to the user-approved public
contact converted to E.164 and the approved encoded greeting. Never paste that
real value into Git, a commit message, or a shared log.

- [ ] **Step 5: Push only after backend Railway prerequisites also exist**

Confirm Meta templates are `APPROVED`, Railway has all `WHATSAPP_*` values, and
the API/jobs services are ready. Then push `main` so Railway and Vercel deploy
the same reviewed revision.

- [ ] **Step 6: Smoke test deployed URLs**

Verify:

```text
https://app.mrbarberhub.com.br/                     -> BarberHub homepage
https://app.mrbarberhub.com.br/mr-solutions        -> HTTP 200 after direct load and reload
https://app.mrbarberhub.com.br/agendar/bigodes     -> services and available dates
https://api.mrbarberhub.com.br/api/v1/health/      -> {"status":"ok"}
```

Inspect the M&R Solutions CTA in the browser and confirm it resolves to the
Vercel-configured public number. Confirm the console has no CSP violation for
the globe texture.
