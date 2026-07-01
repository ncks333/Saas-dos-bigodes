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

## Antes de produção

Execute análise SAST/dependências, pentest do fluxo público, rotação de segredos em um secret manager e configure alertas para falhas de login, erros 5xx e anomalias entre tenants. O isolamento por aplicação deve ser reforçado com PostgreSQL Row Level Security quando a operação exigir defesa em profundidade. Nunca exponha Redis ou PostgreSQL à internet.

Ao usar Supabase somente como PostgreSQL, desative a Data API. Não exponha o schema `public`, a chave `service_role` ou a string `DATABASE_URL` ao frontend.
