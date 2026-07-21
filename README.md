# M&R BarberHub

Plataforma multi-tenant de gestão e agendamento para barbearias, desenvolvida pela **M&R Solutions**, com Django REST Framework, React, PostgreSQL, Redis e Celery.

## O que já está disponível

- JWT com rotação, blacklist, logout por sessão e em todos os dispositivos.
- Recuperação e alteração de senha; perfis `ADMIN` e `FUNCIONARIO`.
- Isolamento por `barbershop_id` em clientes, serviços, agenda, bloqueios, usuários, relatórios, notificações e auditoria.
- Clientes com busca, filtros, paginação, WhatsApp único e exclusão lógica.
- Serviços com preço e duração.
- Agendamento transacional sem sobreposição, datas passadas ou horários fora do expediente.
- Disponibilidade considerando duração, expediente, bloqueios e agenda existente.
- Fluxo público, Turnstile, cancelamento por token com hash e rate limiting.
- Resumo diário e dashboard com faturamento, cancelamentos, recorrência e horários populares.
- Confirmações e lembretes assíncronos de 24h/1h por Celery, com retries.
- Ferramentas para agente de IA com regra transacional de uma reserva ativa por cliente/dia.
- Painel React responsivo e fluxo público mobile-first.
- Testes iniciais de autenticação, agendamento e isolamento multi-tenant.
- Cadastro com checkout recorrente hospedado pelo Asaas; webhook autenticado ativa trial e controla acesso.
- Ciclo de assinatura: 30 dias padrão, piloto de 60 dias por plano exclusivo vinculado à assinatura, 7 dias de tolerância e suspensão/regularização por e-mail.

## Subir localmente

Requer Docker Desktop.

```powershell
Copy-Item .env.example .env
docker compose up --build
docker compose exec backend python manage.py seed_demo
```

Abra `http://localhost:5173`. A seed cria `admin / Bigodes123`; troque essa senha imediatamente. A API fica em `http://localhost:8000/api/v1/` e o agendamento público de demonstração em `http://localhost:5173/agendar/bigodes`.

Sem Docker, instale Python 3.13, PostgreSQL, Redis e Node 22; depois instale `backend/requirements/development.txt`. Para iniciar o frontend com configuração exclusivamente local:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000/api/v1 VITE_TURNSTILE_SITE_KEY=1x00000000000000000000AA VITE_ASAAS_CHECKOUT_ORIGINS=https://sandbox.asaas.com VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run dev
```

## Testes e qualidade

```bash
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
cd frontend
VITE_API_URL=http://localhost:8000/api/v1 VITE_TURNSTILE_SITE_KEY=1x00000000000000000000AA VITE_ASAAS_CHECKOUT_ORIGINS=https://sandbox.asaas.com VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run build
CHOKIDAR_USEPOLLING=true npm run test:e2e
```

O limite de cobertura está configurado em 80%. A suíte incluída estabelece a fundação, mas novos fluxos precisam manter esse patamar.

## Variáveis importantes

Copie `.env.example`; nunca versione `.env`. Produção exige chaves independentes para Django e JWT, credenciais fortes, origens CORS/CSRF exatas, Turnstile, e-mail transacional via Resend HTTPS API e WhatsApp Cloud API oficial da Meta com uma integração configurada.

O build do frontend exige `VITE_TURNSTILE_SITE_KEY`, `VITE_ASAAS_CHECKOUT_ORIGINS` e `VITE_MR_SOLUTIONS_WHATSAPP_URL`. O Compose usa apenas fixtures públicas fictícias para desenvolvimento local. Cadastre valores públicos reais somente no painel da Vercel; nunca em `.env`, Docker, Compose, documentação ou Git.

Frontend aceita somente configuração pública `VITE_*`. Railway usa somente segredos para `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN` e `RESEND_API_KEY`; eles nunca pertencem à Vercel, bundle do navegador ou repositório.

## Estrutura

```text
backend/
  apps/ accounts barbershops customers services appointments notifications reports audit
  core/ settings permissions middlewares exceptions utils security
  requirements/ tests/
frontend/
  src/ React + TypeScript + React Query + React Hook Form + Zod
docs/ SECURITY.md DEPLOY.md
docker-compose.yml
```

Consulte também [Agente de agendamento](docs/AGENT.md) para o prompt, as ferramentas e o fluxo seguro de cancelamento.

## Produção

O Compose é voltado a desenvolvimento/homologação. A produção está preparada para Vercel, Railway, Supabase e Upstash. Siga o [guia completo de deploy](docs/DEPLOY.md) e a [lista de controles de segurança](docs/SECURITY.md). Configure primeiro Asaas Sandbox, depois Asaas produção; ambos usam checkout hospedado e endpoint `/api/v1/billing/webhooks/asaas/`. Callback ou redirect não confirma pagamento: webhook autenticado confirma. Cadastre somente segredos Railway e nunca espere recuperação automática de checkout ambíguo; use a [runbook de reconciliação](docs/runbooks/billing-regularization-reconciliation.md).

Signup público resolve no servidor somente o plano ativo de `BILLING_PUBLIC_PLAN_CODE`; browser não escolhe plano, preço ou trial. A aplicação grava `subscription.trial_days` e `subscription.trial_ends_at` antes do checkout e envia `nextDueDate` ao Asaas; `CHECKOUT_PAID` só ativa datas armazenadas depois de reconciliar o ID persistido com o Asaas. Alterar assinatura após signup é proibido e insuficiente. Para piloto, use oferta piloto de servidor com 60 dias antes de `provision_signup`, sem alterar o plano público. Se checkout de 30 dias existe, não edite somente banco: cancele e reemita via suporte/fluxo operacional ou reinicie signup de teste após cancelar checkout antigo. `PAYMENT_OVERDUE` e `PAYMENT_REPROVED_BY_RISK_ANALYSIS` iniciam 7 dias de tolerância; após isso, acesso suspende até regularização por e-mail e webhook. Ciclo e-mail-primeiro: eventos de webhook e e-mails de ciclo são idempotentes; e-mails de ciclo não contêm cartão, pagamento, payload nem identificador do provedor. Pedido de regularização é durável para administrador conhecido, recupera falha de broker e mantém resposta pública não enumerável; e-mail desconhecido não é armazenado. Limpe usuário e checkout de teste somente após smoke Sandbox; nunca apague dados produtivos para esse fim.

O antigo `main.py` foi preservado como protótipo didático; a aplicação comercial está em `backend/` e `frontend/`.
