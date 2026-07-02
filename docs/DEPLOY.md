# Deploy do M&R BarberHub

Arquitetura preparada:

```text
Namecheap → Cloudflare DNS
                 ├── app.seudominio.com → Vercel (React)
                 └── api.seudominio.com → Railway (Django)
                                               ├── Supabase PostgreSQL
                                               └── Upstash Redis → Celery Worker/Beat
```

Nunca copie arquivos `.env` para o Git. Cadastre cada segredo diretamente no painel correspondente.

## 1. Contas e domínios

1. Registre o domínio na Namecheap.
2. Adicione o domínio à Cloudflare e troque, na Namecheap, os nameservers pelos fornecidos pela Cloudflare.
3. Reserve `app.seudominio.com` para a Vercel e `api.seudominio.com` para a Railway.
4. Na Cloudflare Turnstile, crie um widget para `app.seudominio.com` e guarde a Site Key e a Secret Key.

Use inicialmente os registros DNS indicados por Vercel e Railway como **DNS only**. Ative o proxy da Cloudflare somente depois que SSL e health checks estiverem aprovados.

## 2. Supabase PostgreSQL

1. Crie um projeto na mesma região escolhida para a Railway.
2. Em **Integrations → Data API**, desative **Enable Data API**. O frontend usa apenas a API Django; as tabelas internas não devem ganhar endpoints REST/GraphQL do Supabase.
3. Em **Connect**, copie a URL do **Session Pooler**, porta `5432`.
4. Garanta que a URL termina com `?sslmode=require` (ou acrescente `&sslmode=require` se já houver parâmetros).
5. Salve essa URL como `DATABASE_URL` nos três serviços Railway.

O Session Pooler é adequado aos processos persistentes do Django e Celery. Não coloque essa URL no frontend.

## 3. Upstash Redis

1. Crie um banco Redis na região mais próxima da Railway.
2. Para o Celery, prefira o plano Fixed para evitar cobrança imprevisível por comando.
3. Copie a URL TLS no formato `rediss://default:senha@endpoint:6379`.
4. Salve-a como `REDIS_URL` nos três serviços Railway.

## 4. Railway: API, worker e beat

Crie três serviços a partir do mesmo repositório GitHub. Em todos, configure **Root Directory** como `/backend`.

| Serviço | Config file absoluto | Domínio público |
|---|---|---|
| `barberhub-api` | `/backend/railway.toml` | `api.seudominio.com` |
| `barberhub-worker` | `/backend/railway.worker.toml` | nenhum |
| `barberhub-beat` | `/backend/railway.beat.toml` | nenhum |

Importe em todos os serviços as variáveis de [`.env.production.example`](../backend/.env.production.example). Use variáveis compartilhadas da Railway para evitar divergências.

Gere duas chaves diferentes:

```bash
openssl rand -base64 64
openssl rand -base64 64
```

Use uma em `DJANGO_SECRET_KEY` e outra em `JWT_SIGNING_KEY`. Configure ainda:

```text
ALLOWED_HOSTS=api.seudominio.com,healthcheck.railway.app
CORS_ALLOWED_ORIGINS=https://app.seudominio.com
CSRF_TRUSTED_ORIGINS=https://app.seudominio.com,https://api.seudominio.com
DJANGO_SETTINGS_MODULE=core.settings.production
```

O serviço API executa migrations antes do deploy e só recebe tráfego quando `/api/v1/health/` confirmar PostgreSQL e Redis. Mantenha **uma única réplica** do Beat.

## 5. WhatsApp e e-mail

Configure uma instância Evolution API v2 e, para uso comercial, vincule-a ao WhatsApp Business oficial. Cadastre na Railway:

```text
WHATSAPP_BASE_URL=https://sua-evolution.example.com
WHATSAPP_API_KEY=...
WHATSAPP_INSTANCE_NAME=barberhub
```

Configure também SMTP transacional. O backend se recusa a iniciar em produção usando o backend de e-mail do console, pois tokens de recuperação de senha não podem aparecer em logs.
Defina `FRONTEND_URL=https://app.seudominio.com` para os links de recuperação e mantenha `PASSWORD_RESET_TIMEOUT=3600` para expiração em uma hora.

## 6. Vercel

1. Importe o mesmo repositório GitHub.
2. Defina **Root Directory** como `frontend`.
3. O arquivo `vercel.json` já configura Vite, fallback de `/agendar/*`, cache e cabeçalhos de segurança.
4. Cadastre em Production e Preview:

```text
VITE_API_URL=https://api.seudominio.com/api/v1
VITE_TURNSTILE_SITE_KEY=...
VITE_POSTHOG_KEY=...              # opcional
VITE_POSTHOG_HOST=https://us.i.posthog.com
```

5. Vincule `app.seudominio.com`. Depois, atualize o widget Turnstile para aceitar somente esse hostname.

O PostHog está configurado sem autocapture, gravação de sessão ou persistência em cookies/localStorage. Não envie nomes, telefones ou conteúdo de formulários como eventos.

## 7. Primeiro administrador

Cadastre temporariamente `INITIAL_ADMIN_PASSWORD` no serviço API com uma senha forte. No shell do serviço execute:

```bash
python manage.py create_tenant_admin \
  --shop-name "Nome da Barbearia" \
  --slug "nome-da-barbearia" \
  --username "admin" \
  --email "admin@seudominio.com"
```

Após o sucesso, remova imediatamente `INITIAL_ADMIN_PASSWORD` das variáveis Railway e faça novo deploy. Não use `seed_demo` em produção.

## 8. Checklist de liberação

- `https://api.seudominio.com/api/v1/health/` retorna `{"status":"ok"}`.
- Login administrativo funciona e a senha inicial foi trocada.
- `https://app.seudominio.com/agendar/<slug>` lista serviços e horários.
- Um agendamento de teste aparece no painel e não permite sobreposição.
- Turnstile bloqueia token inválido.
- Confirmação, lembretes e recuperação de senha chegam de verdade.
- Worker está consumindo filas e existe somente um Beat.
- Supabase possui backup habilitado e alertas de uso configurados.
- Upstash, Railway, Vercel e PostHog possuem limites de gasto/alertas.
- Cloudflare está em SSL/TLS **Full (strict)** e HTTPS obrigatório.

## 9. Rollback

Vercel e Railway mantêm deployments anteriores. Em falha:

1. Faça rollback do frontend na Vercel.
2. Faça rollback da API e worker para o mesmo commit na Railway.
3. Não reverta migrations destrutivamente. Restaure backup do Supabase somente após confirmar perda/corrupção de dados.
