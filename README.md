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
VITE_API_URL=http://localhost:8000/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run dev
```

## Testes e qualidade

```bash
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
cd frontend
VITE_API_URL=http://localhost:8000/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste npm run build
npm run test:e2e
```

O limite de cobertura está configurado em 80%. A suíte incluída estabelece a fundação, mas novos fluxos precisam manter esse patamar.

## Variáveis importantes

Copie `.env.example`; nunca versione `.env`. Produção exige chaves independentes para Django e JWT, credenciais fortes, origens CORS/CSRF exatas, Turnstile, SMTP transacional e WhatsApp Cloud API oficial da Meta com uma integração configurada.

O build do frontend também exige `VITE_MR_SOLUTIONS_WHATSAPP_URL`. O Compose usa apenas uma fixture fictícia para desenvolvimento local. Cadastre valor público real somente no painel da Vercel; nunca em `.env`, Docker, Compose, documentação ou Git.

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

O Compose é voltado a desenvolvimento/homologação. A produção está preparada para Vercel, Railway, Supabase e Upstash. Siga o [guia completo de deploy](docs/DEPLOY.md) e a [lista de controles de segurança](docs/SECURITY.md). Credenciais reais, domínio, WhatsApp e SMTP ainda precisam ser cadastrados nos respectivos painéis antes da liberação. O valor real de `VITE_MR_SOLUTIONS_WHATSAPP_URL` fica somente no painel da Vercel.

O antigo `main.py` foi preservado como protótipo didático; a aplicação comercial está em `backend/` e `frontend/`.
