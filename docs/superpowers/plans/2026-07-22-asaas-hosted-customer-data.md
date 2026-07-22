# Asaas Hosted Customer Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar checkout recorrente Asaas sem dados parciais de pagador, deixando coleta para checkout hospedado.

**Architecture:** `apps.billing.providers.asaas._create_checkout` mantém plano, callbacks e assinatura. Remove somente `customerData`; Asaas coleta e valida CPF, telefone e endereço na página hospedada.

**Tech Stack:** Django, pytest, requests, Asaas Checkout API.

## Global Constraints

- Não adicionar CPF, endereço ou CEP ao cadastro BarberHub.
- Não armazenar dados de cartão no BarberHub.
- Não alterar plano, trial, callbacks, webhooks ou regras de acesso.

---

### Task 1: Remover dados parciais do payload Asaas

**Files:**

- Modify: `backend/tests/test_asaas_provider.py:35-87`
- Modify: `backend/apps/billing/providers/asaas.py:65-92`

**Interfaces:**

- Consumes: `create_recurring_checkout(subscription, user) -> CheckoutResult`
- Produces: POST para `/checkouts` sem chave `customerData`.

- [x] **Step 1: Write failing test**

No dicionário esperado em `test_checkout_uses_server_plan_and_credit_card`, remover bloco `customerData` com nome, email e telefone.

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm backend pytest tests/test_asaas_provider.py::test_checkout_uses_server_plan_and_credit_card -q`

Expected: FAIL porque payload atual ainda inclui `customerData`.

- [x] **Step 3: Write minimal implementation**

Remover bloco `customerData` de `backend/apps/billing/providers/asaas.py`. Manter todos outros campos de payload intactos.

- [x] **Step 4: Run focused and full provider tests**

Run: `docker compose run --rm backend pytest tests/test_asaas_provider.py -q`

Run: `docker compose run --rm backend ruff check .`

Expected: tests and Ruff pass.

- [x] **Step 5: Commit**

Run: `git add backend/apps/billing/providers/asaas.py backend/tests/test_asaas_provider.py`

Run: `git commit -m "fix: let Asaas checkout collect payer data"`

### Task 2: Verificar Sandbox pelo fluxo real

**Files:** No code changes.

**Interfaces:**

- Consumes: formulário em `http://localhost:5174/cadastro` e Asaas Sandbox.
- Produces: URL hospedada Sandbox em vez de “Checkout indisponível”.

- [x] **Step 1: Recriar backend local**

Run: `docker compose up -d --force-recreate backend worker beat`

- [ ] **Step 2: Criar cadastro em janela privada**

Usar dados novos, concluir Turnstile de teste e clicar `Começar 30 dias grátis`.

Expected: redirecionamento para `https://sandbox.asaas.com/...`.

- [ ] **Step 3: Commit no code changes**

Nenhum commit: validação manual não altera código.
