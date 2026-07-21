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

Importe em todos os serviços as variáveis de [`.env.production.example`](../backend/.env.production.example). Na Railway, produção usa somente segredos/variáveis protegidas: não cole valores reais em Git, `.env`, logs, shell compartilhado ou documentação. Use variáveis compartilhadas da Railway para evitar divergências entre API e jobs.

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

Antes do primeiro envio, verifique no Resend o domínio/subdomínio de envio e o endereço em `DEFAULT_FROM_EMAIL`; aguarde estado verificado. A chave deve ser restrita ao envio necessário. E-mails de cobrança são informativos e idempotentes: nunca inclua número de cartão, dados de pagamento, corpo de webhook, IDs do provedor, tokens ou chaves.

## 5.1. Assinaturas Asaas e checkout hospedado

### Configuração de ambiente

Configure Asaas Sandbox primeiro. Cadastre uma API key de Sandbox restrita e estes valores como segredos Railway, nunca no frontend:

```text
ASAAS_API_URL=https://api-sandbox.asaas.com/v3
ASAAS_CHECKOUT_BASE_URL=https://sandbox.asaas.com/checkoutSession/show
ASAAS_API_KEY=defina-no-painel-railway
ASAAS_WEBHOOK_TOKEN=gere-token-forte-independente
ASAAS_CHECKOUT_EXPIRES_MINUTES=60
FRONTEND_URL=https://app.seudominio.com
```

Para Asaas produção, troque somente URLs e API key pelos valores de produção; mantenha o mesmo contrato e HTTPS:

```text
ASAAS_API_URL=https://api.asaas.com/v3
ASAAS_CHECKOUT_BASE_URL=https://www.asaas.com/checkoutSession/show
ASAAS_API_KEY=defina-no-painel-railway
ASAAS_WEBHOOK_TOKEN=gere-outro-token-forte-independente
ASAAS_CHECKOUT_EXPIRES_MINUTES=60
FRONTEND_URL=https://app.seudominio.com
```

Gere `ASAAS_WEBHOOK_TOKEN` de forma independente de `ASAAS_API_KEY`, por exemplo `openssl rand -hex 32`. Cadastre-o no webhook Asaas e no secret Railway; não reutilize token de API, JWT ou chave Django. O endpoint é exatamente `POST https://api.mrbarberhub.com.br/api/v1/billing/webhooks/asaas/`; o Asaas envia token no cabeçalho `asaas-access-token`.

O cadastro chama `POST /api/v1/billing/signup/` e retorna `checkout_url` e `external_reference`. Browser usa somente `checkout_url` para redirect ao checkout hospedado; não use nem exponha `external_reference` no fluxo de navegação. Checkout tem recorrência mensal, cartão tratado pelo Asaas e expira após `ASAAS_CHECKOUT_EXPIRES_MINUTES` (default `60`). Nem `checkout_url` nem `external_reference` prova pagamento. O navegador pode voltar para `/checkout/concluido`, `/checkout/cancelado` ou `/checkout/expirado`, mas callback ou redirect não confirma pagamento e nunca libera acesso. Somente webhook autenticado confirma transição.

### Eventos habilitados e ciclo de acesso

Cadastre apenas estes eventos, pois são os únicos tratados pelo código:

- `CHECKOUT_PAID`: checkout inicial pago ativa `TRIAL`; checkout de regularização pago reativa assinatura restrita.
- `PAYMENT_CONFIRMED` e `PAYMENT_RECEIVED`: confirmam pagamento e mantêm/reativam `ACTIVE`.
- `PAYMENT_OVERDUE` e `PAYMENT_REPROVED_BY_RISK_ANALYSIS`: iniciam `GRACE` de 7 dias. Eventos duplicados para mesmo pagamento não estendem prazo.
- `PAYMENT_CHARGEBACK_REQUESTED` e `PAYMENT_CHARGEBACK_DISPUTE`: suspendem imediatamente por chargeback.
- `SUBSCRIPTION_INACTIVATED` e `SUBSCRIPTION_DELETED`: cancelam assinatura.

No signup, aplicação copia `plan.trial_days` para `subscription.trial_days` e calcula/persiste `subscription.trial_ends_at` antes de criar checkout. Ao criar checkout, envia `subscription.next_billing_at` como `nextDueDate` ao Asaas na criação do checkout. `CHECKOUT_PAID` apenas ativa `TRIAL` usando datas armazenadas na assinatura; não relê `plan.trial_days`. Alterar qualquer `subscription` após signup é proibido e insuficiente para mudar prazo já enviado ao Asaas.

Trial padrão é 30 dias. Para único piloto de 60 dias antes de abrir aquisição pública, defina no servidor `SubscriptionPlan.trial_days=60` ANTES de piloto submeter signup/provision_signup. Conclua signup do piloto para que snapshot local e `nextDueDate` do Asaas usem 60 dias; restaure plano público para 30 imediatamente após checkout ser criado. Este procedimento temporário só é aceitável antes de signup público concorrente. Com aquisição aberta, implemente ou use plano/oferta piloto de servidor antes do provisioning.

Se checkout de 30 dias já existe, não edite somente banco: cancele e reemita via suporte ou fluxo operacional implementado, ou reinicie signup de teste limpo após cancelar checkout antigo. Eventos de webhook e e-mails de ciclo são idempotentes; pedidos públicos de e-mail de regularização podem repetir. O sweep horário envia ciclo e-mail-primeiro: avisos de trial em 7, 3 e 1 dia, cobrança não confirmada, suspensão, reativação e cancelamento. Ao vencer `GRACE`, assinatura fica `SUSPENDED`; usuário não recebe JWT, mas pode pedir link de regularização por e-mail e concluir checkout hospedado.

Falhas ambíguas de criação de checkout de regularização entram em `CREATING` ou `RECONCILIATION_REQUIRED`; não há recuperação automática. Siga a [runbook de reconciliação](runbooks/billing-regularization-reconciliation.md): confirme checkout no Asaas e execute reconciliação manual fail-closed antes de criar outro checkout.

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

Cadastre também `VITE_MR_SOLUTIONS_WHATSAPP_URL` com a URL HTTPS pública `wa.me` aprovada. Esse valor real fica somente no painel da Vercel, em Production e Preview; não o copie para Docker, Compose, `.env`, documentação ou Git. O Compose local usa exclusivamente fixture fictícia de desenvolvimento.

5. Vincule `app.seudominio.com`. Depois, atualize o widget Turnstile para aceitar somente esse hostname.

O PostHog está configurado sem autocapture, gravação de sessão ou persistência em cookies/localStorage. Não envie nomes, telefones ou conteúdo de formulários como eventos.

Vercel recebe somente valores públicos `VITE_*`, incluindo `VITE_TURNSTILE_SITE_KEY`. Nunca cadastre `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `RESEND_API_KEY`, `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` ou `DATABASE_URL` no ambiente frontend; esses segredos existem somente na Railway.

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
- Asaas Sandbox: `GET /api/v1/billing/plans/current/` retorna plano; cadastro por `POST /api/v1/billing/signup/` abre somente checkout hospedado; callback do navegador não altera acesso.
- Webhook Sandbox autenticado chega em `/api/v1/billing/webhooks/asaas/`; `CHECKOUT_PAID` ativa trial de 30 dias e duplicata não duplica transição/e-mail.
- Piloto de 60 dias, antes de abrir signup público: defina `SubscriptionPlan.trial_days=60` antes de `signup/provision_signup`, confirme snapshot/`nextDueDate` 60 no checkout criado e restaure plano público para 30. Se checkout de 30 dias existe, cancele/reemita; não edite banco somente.
- Simule `PAYMENT_OVERDUE`, confirme `GRACE` de 7 dias estável, depois regularize apenas por e-mail e webhook; simule chargeback, inativação e deleção em Sandbox.
- Verifique domínio/remetente Resend e receba e-mail de ciclo sem cartão, payload ou referência do provedor.
- Após smoke Sandbox, cancele/expire checkout de teste no painel Asaas, confirme que não há assinatura/pagamento ativo e remova usuário/tenant de teste apenas em ambiente não produtivo. Não apague dados de produção para limpeza.
- Antes de liberar produção, execute gates: `cd backend && pytest`; `cd backend && ruff check .`; `cd backend && python manage.py makemigrations --check --dry-run`; `cd frontend && npm run test:config`; `cd frontend && VITE_API_URL=<API HTTPS> VITE_TURNSTILE_SITE_KEY=<site-key-publica> VITE_MR_SOLUTIONS_WHATSAPP_URL=<URL HTTPS wa.me aprovada> npm run build`; `cd frontend && npm run lint`; `cd frontend && CHOKIDAR_USEPOLLING=true npm run test:e2e`.

## 8.1. Smoke test de desempenho antes da demonstração

Depois de cada deploy, meça cinco chamadas sequenciais ao health check e registre
mediana fria e mediana quente. A primeira chamada após período sem tráfego representa
o caminho frio; as quatro seguintes representam o serviço aquecido:

```bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null -w "request=$i status=%{http_code} total=%{time_total}s\n" \
    https://api.mrbarberhub.com.br/api/v1/health/
done
```

No navegador, abra DevTools → Network, filtre `api/v1`, faça login e meça:

- carregamento do dashboard;
- abertura da agenda do dia;
- alteração de status;
- cadastro/edição de cliente.

Uma alteração de status deve produzir um único `PATCH` e não deve baixar novamente a
coleção completa de agendamentos. Se a API continuar lenta mesmo sem refetch, confira
no Railway CPU, memória, reinícios e suspensão do serviço web. Confirme também que
Railway e Supabase usam a mesma região e que o pool de conexões não atingiu o limite.
Só aumente workers ou plano depois de observar saturação nesses indicadores.

Para comparar a operação autenticada, use a mesma conta de teste e o endpoint
`GET /api/v1/appointments/?day=YYYY-MM-DD`. Faça cinco medições frias, aguardando o
período normal de suspensão entre cada primeira chamada, e cinco medições quentes em
sequência. Registre os cinco tempos, calcule a mediana de cada grupo e anote a data,
região e commit implantado. O critério de comparação é:

```text
fria:  t1, t2, t3, t4, t5  → mediana fria
quente: t1, t2, t3, t4, t5 → mediana quente
```

Não cole token JWT, cookies ou dados reais no relatório. Use DevTools para preservar
autenticação local sem expor credenciais.

## 9. Rollback

Vercel e Railway mantêm deployments anteriores. Em falha:

1. Faça rollback do frontend na Vercel.
2. Faça rollback da API e jobs para o mesmo commit na Railway.
3. Não reverta migrations destrutivamente. Restaure backup do Supabase somente após confirmar perda/corrupção de dados.
