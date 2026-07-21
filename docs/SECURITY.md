# Segurança

## Controles implementados

- JWT de 15 minutos, refresh de 7 dias, rotação e blacklist.
- Argon2 como hasher primário e política de senha forte.
- Querysets e criação sempre vinculados ao `barbershop_id` autenticado.
- Validação cruzada de cliente, serviço e funcionário no tenant.
- Rate limiting no login e nos fluxos públicos.
- Turnstile obrigatório fora do modo de desenvolvimento.
- Tokens de cancelamento aleatórios, armazenados como SHA-256 e invalidados após uso.
- HTTPS, HSTS, cookies seguros, CORS restritivo e proteção de frame em produção.
- Auditoria de ações sensíveis sem registrar senhas ou tokens.
- Health check de produção valida PostgreSQL e Redis sem expor detalhes internos.
- PostHog sem autocapture, gravação de sessão ou persistência de identificadores.
- Produção falha ao iniciar se chaves, Turnstile, e-mail ou WhatsApp estiverem ausentes.
- Asaas autentica webhook por `ASAAS_WEBHOOK_TOKEN` independente, comparado em tempo constante no endpoint `/api/v1/billing/webhooks/asaas/`.
- Checkout e cobrança são confirmados apenas por webhook Asaas autenticado; callback ou redirect de navegador não concede acesso.
- Segredos Asaas, Resend, banco, Django e JWT ficam somente em secrets/variáveis protegidas Railway. Frontend recebe somente `VITE_*` públicos.
- Eventos de cobrança e e-mails são idempotentes. E-mail nunca contém dados de cartão, payload do provedor, token, chave ou referência do provedor.
- Regularização com resultado ambíguo falha fechada em `RECONCILIATION_REQUIRED`; recuperação exige reconciliação manual documentada, nunca nova cobrança automática.

## Antes de produção

Execute análise SAST/dependências, pentest do fluxo público, rotação de segredos em um secret manager e configure alertas para falhas de login, erros 5xx e anomalias entre tenants. O isolamento por aplicação deve ser reforçado com PostgreSQL Row Level Security quando a operação exigir defesa em profundidade. Nunca exponha Redis ou PostgreSQL à internet.

Ao usar Supabase somente como PostgreSQL, desative a Data API. Não exponha o schema `public`, a chave `service_role` ou a string `DATABASE_URL` ao frontend.
