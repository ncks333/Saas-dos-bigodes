# SaaS dos Bigodes

Plataforma multi-tenant de agendamento para barbearias, com Django REST Framework, React, PostgreSQL, Redis e Celery.

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

Sem Docker, instale Python 3.13, PostgreSQL, Redis e Node 22; depois instale `backend/requirements/development.txt` e execute Vite no diretório `frontend`.

## Testes e qualidade

```powershell
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
docker compose run --rm frontend npm run build
```

O limite de cobertura está configurado em 80%. A suíte incluída estabelece a fundação, mas novos fluxos precisam manter esse patamar.

## Variáveis importantes

Copie `.env.example`; nunca versione `.env`. Produção exige chaves independentes para Django e JWT, credenciais fortes, origens CORS/CSRF exatas, Turnstile e provedor de WhatsApp. O adaptador atual usa um endpoint compatível com Evolution API e deve ser ajustado à versão contratada.

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

## Produção

O Compose é voltado a desenvolvimento/homologação. As migrations iniciais estão versionadas; valide mudanças com `python manage.py makemigrations --check --dry-run`. Consulte [segurança](docs/SECURITY.md) e [deploy](docs/DEPLOY.md). Integração real de WhatsApp, e-mail transacional, observabilidade e testes E2E são gates obrigatórios antes de receber clientes pagantes.

O antigo `main.py` foi preservado como protótipo didático; a aplicação comercial está em `backend/` e `frontend/`.
