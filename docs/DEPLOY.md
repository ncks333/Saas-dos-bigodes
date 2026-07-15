# Deploy do M&R BarberHub

Arquitetura preparada:

```text
Namecheap → Cloudflare DNS
                 ├── app.seudominio.com → Vercel (React)
                 └── api.mrbarberhub.com.br → Railway (Django)
                                               ├── Supabase PostgreSQL
                                               └── Upstash Redis → Celery Worker/Beat
```

Nunca copie arquivos `.env` para o Git. Cadastre cada segredo diretamente no painel correspondente.

## 1. Contas e domínios

1. Registre o domínio na Namecheap.
2. Adicione o domínio à Cloudflare e troque, na Namecheap, os nameservers pelos fornecidos pela Cloudflare.
3. Reserve `app.seudominio.com` para a Vercel e `api.mrbarberhub.com.br` para a Railway.
4. Na Cloudflare Turnstile, crie um widget para `app.seudominio.com` e guarde a Site Key e a Secret Key.

Use inicialmente os registros DNS indicados por Vercel e Railway como **DNS only**. Ative o proxy da Cloudflare somente depois que SSL e health checks estiverem aprovados.

## 2. Supabase PostgreSQL

1. Crie um projeto na mesma região escolhida para a Railway.
2. Em **Integrations → Data API**, desative **Enable Data API**. O frontend usa apenas a API Django; as tabelas internas não devem ganhar endpoints REST/GraphQL do Supabase.
3. Em **Connect**, copie a URL do **Session Pooler**, porta `5432`.
4. Garanta que a URL termina com `?sslmode=require` (ou acrescente `&sslmode=require` se já houver parâmetros).
5. Salve essa URL como `DATABASE_URL` nos dois serviços Railway.

O Session Pooler é adequado aos processos persistentes do Django e Celery. Não coloque essa URL no frontend.

## 3. Upstash Redis

1. Crie um banco Redis na região mais próxima da Railway.
2. Para o Celery, prefira o plano Fixed para evitar cobrança imprevisível por comando.
3. Copie a URL TLS no formato `rediss://default:senha@endpoint:6379`.
4. Salve-a como `REDIS_URL` nos dois serviços Railway.

## 4. Railway: API e jobs

Crie dois serviços a partir do mesmo repositório GitHub. Em todos, configure **Root Directory** como `/backend`.

| Serviço | Config file absoluto | Domínio público |
|---|---|---|
| `barberhub-api` | `/backend/railway.toml` | `api.mrbarberhub.com.br` |
| `barberhub-jobs` | `/backend/railway.jobs.toml` | nenhum |

Importe em todos os serviços as variáveis de [`.env.production.example`](../backend/.env.production.example). Use variáveis compartilhadas da Railway para evitar divergências.

Gere duas chaves diferentes:

```bash
openssl rand -base64 64
openssl rand -base64 64
```

Use uma em `DJANGO_SECRET_KEY` e outra em `JWT_SIGNING_KEY`. Configure ainda:

```text
ALLOWED_HOSTS=api.mrbarberhub.com.br,healthcheck.railway.app
CORS_ALLOWED_ORIGINS=https://app.seudominio.com
CSRF_TRUSTED_ORIGINS=https://app.seudominio.com,https://api.mrbarberhub.com.br
DJANGO_SETTINGS_MODULE=core.settings.production
```

O serviço API executa migrations antes do deploy e só recebe tráfego quando `/api/v1/health/` confirmar PostgreSQL e Redis. Mantenha **uma única réplica** do serviço jobs.

## 5. WhatsApp Cloud API e e-mail

### Meta WhatsApp Cloud API

Use somente a API oficial da Meta. WABA, número dedicado e app devem pertencer
ao portfólio empresarial aprovado para o ambiente, sem registrar IDs reais
neste documento.

No Meta Business Settings, crie um usuário do sistema dedicado, atribua somente
o app e a conta WhatsApp usados pelo BarberHub e gere um token permanente com
expiração `Never`/sem expiração. Selecione exatamente as permissões mínimas
`whatsapp_business_management` e `whatsapp_business_messaging`, sem adicionar
escopos de anúncios, páginas ou perfil. Cadastre o token somente como secret da
Railway. Token sem expiração não elimina necessidade de rotação operacional.

No WhatsApp Manager, crie e aguarde aprovação destes templates `UTILITY` em
`pt_BR`:

- `barberhub_agendamento_recebido`: `Olá, {{1}}! Seu {{2}} foi registrado para {{3}}. A barbearia confirmará seu horário pelo WhatsApp.`
- `barberhub_lembrete_agendamento`: `Olá, {{1}}! Lembrete: seu {{2}} está marcado para {{3}}.`

Cadastre como variáveis compartilhadas nos serviços `barberhub-api` e
`barberhub-jobs`:

```text
WHATSAPP_GRAPH_API_VERSION=v25.0
WHATSAPP_PHONE_NUMBER_ID=cole-o-phone-number-id
WHATSAPP_ACCESS_TOKEN=defina-no-painel
WHATSAPP_WABA_ID=cole-o-waba-id
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
WHATSAPP_CONFIRMATION_TEMPLATE=barberhub_agendamento_recebido
WHATSAPP_REMINDER_TEMPLATE=barberhub_lembrete_agendamento
WHATSAPP_REMINDER_LOOKBACK_MINUTES=60
```

Substitua os placeholders pelos IDs exibidos em WhatsApp → API Setup e cadastre
os valores reais somente como secrets/variáveis protegidas da Railway. Nunca
registre vínculo entre IDs reais e contas, nem use texto de exemplo como token
em produção.

O sistema envia três notificações: recebimento imediato, lembrete 24 horas antes
e lembrete 1 hora antes. Os dois lembretes reutilizam o mesmo template.
`WHATSAPP_REMINDER_LOOKBACK_MINUTES` é opcional, usa default `60` e aceita de 1
a 1440 minutos. A janela recupera execuções atrasadas, mas nunca seleciona
agendamentos cujo horário já passou.

Para rotacionar o token, gere outro token permanente para o mesmo usuário do
sistema e as mesmas duas permissões, atualize o secret nos dois serviços,
reinicie-os e valide um envio antes de revogar o token anterior. Faça rotação em
cadência definida pela operação e imediatamente após suspeita de exposição,
troca de responsável ou mudança de acesso. Para revogar, remova o token no
usuário do sistema ou retire dele o app/ativo WhatsApp no Business Settings;
depois remova o secret antigo da Railway. Nunca copie qualquer token para shell,
issue, log ou documentação durante rotação e resposta a incidente.

Somente depois de os templates estarem `APPROVED` e as variáveis existirem,
implante `barberhub-api` e ative `barberhub-jobs`. O serviço jobs deve mostrar um
worker conectado ao Redis e o beat executando
`apps.notifications.tasks.enqueue_due_reminders` a cada 600 segundos.

Nunca registre token, cabeçalho `Authorization`, telefone de cliente ou conteúdo
de mensagem em issue, Git ou log manual.

Para e-mail transacional em Railway Free, Trial ou Hobby, use a API HTTPS do Resend; SMTP de saída é bloqueado nesses planos. Verifique um subdomínio de envio, crie uma chave restrita e cadastre:

```text
EMAIL_BACKEND=core.email_backends.ResendEmailBackend
DEFAULT_FROM_EMAIL=M&R BarberHub <nao-responda@mail.seudominio.com>
```

Cadastre `RESEND_API_KEY` como secret diretamente no painel Railway. Defina `FRONTEND_URL=https://app.seudominio.com` para os links de recuperação e mantenha `PASSWORD_RESET_TIMEOUT=3600` para expiração em uma hora. Nunca coloque a chave Resend no frontend ou no repositório.

## 6. Vercel

1. Importe o mesmo repositório GitHub.
2. Defina **Root Directory** como `frontend`.
3. O arquivo `vercel.json` já configura Vite, fallback de `/agendar/*`, cache e cabeçalhos de segurança.
4. Cadastre em Production e Preview:

```text
VITE_API_URL=https://api.mrbarberhub.com.br/api/v1
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

- `https://api.mrbarberhub.com.br/api/v1/health/` retorna `{"status":"ok"}`.
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
2. Faça rollback da API e jobs para o mesmo commit na Railway.
3. Não reverta migrations destrutivamente. Restaure backup do Supabase somente após confirmar perda/corrupção de dados.
