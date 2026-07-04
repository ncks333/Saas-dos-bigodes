# Login Error Portuguese Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar `Usuário ou senha inválidos.` quando o login responder HTTP 401.

**Architecture:** Adicionar um formatador específico do login no frontend. Ele intercepta somente HTTP 401 e delega todos os outros casos ao formatador genérico existente.

**Tech Stack:** React 19, TypeScript, Axios, TanStack Query, Playwright

## Global Constraints

- Não revelar se o usuário ou a senha está incorreto.
- Não mostrar a mensagem inglesa retornada pelo Simple JWT.
- Não alterar respostas de erro fora do formulário de login.
- Não alterar autenticação nem armazenamento de tokens.

---

### Task 1: Traduzir erro de credenciais no login

**Files:**
- Modify: `frontend/src/ProductApp.tsx:67-106`
- Test: `frontend/tests/mobile.spec.ts`

**Interfaces:**
- Consumes: erro Axios produzido por `POST /auth/login/`.
- Produces: `loginErrorText(error: unknown): string`.

- [ ] **Step 1: Escrever teste Playwright vermelho**

Adicionar em `frontend/tests/mobile.spec.ts`:

```typescript
test("login traduz erro de credenciais inválidas", async ({page}) => {
  await page.route("**/api/v1/auth/login/", route => route.fulfill({
    status: 401,
    json: {detail: "No active account found with the given credentials"},
  }));
  await page.goto("/login");
  await page.getByLabel("Usuário").fill("admin");
  await page.getByLabel("Senha").fill("SenhaAntiga123");
  await page.getByRole("button", {name: "Entrar"}).click();

  await expect(page.getByText("Usuário ou senha inválidos.")).toBeVisible();
  await expect(page.getByText("No active account found with the given credentials")).toHaveCount(0);
});
```

- [ ] **Step 2: Confirmar falha esperada**

Run:

```bash
cd frontend && npx playwright test tests/mobile.spec.ts --grep "login traduz erro"
```

Expected: FAIL porque a interface ainda mostra `No active account found with the given credentials`.

- [ ] **Step 3: Implementar formatador específico**

Adicionar após `errorText` em `frontend/src/ProductApp.tsx`:

```typescript
const loginErrorText = (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    return "Usuário ou senha inválidos.";
  }
  return errorText(error);
};
```

No `LoginPage`, substituir:

```tsx
<ErrorMessage error={login.error}/>
```

por:

```tsx
{login.error && <p className="form-error">{loginErrorText(login.error)}</p>}
```

- [ ] **Step 4: Confirmar teste verde e qualidade**

Run:

```bash
cd frontend
npx playwright test tests/mobile.spec.ts --grep "login traduz erro"
npm run lint
npm run build
```

Expected: teste passa; ESLint e build saem com código zero.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ProductApp.tsx frontend/tests/mobile.spec.ts
git commit -m "fix: traduz erro de credenciais no login"
```
