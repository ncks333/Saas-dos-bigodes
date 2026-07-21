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
- Checkout e cobrança são confirmados apenas por webhook Asaas autenticado; callback ou redirect de navegador não concede acesso. Depois da persistência durável, falha do broker ainda recebe `200` e é recuperada pelo job periódico.
- URLs de checkout exigem HTTPS e origens exatas configuradas do Asaas na resposta do provedor, anexo operacional, API e frontend; host parecido, credencial embutida, caminho usado como origem ou HTTP é rejeitado.
- `CHECKOUT_PAID` correlaciona somente o ID de checkout persistido e reconcilia ID, estado, referência e assinatura atual com o Asaas. Campo somente do evento, ausência ou divergência nunca concede acesso.
- Segredos Asaas, Resend, banco, Django e JWT ficam somente em secrets/variáveis protegidas Railway. Frontend recebe somente `VITE_*` públicos.
- Somente eventos de webhook e e-mails de ciclo de cobrança são idempotentes por evento. E-mails de ciclo nunca contêm dados de cartão, pagamento, payload, token, chave ou referência do provedor.
- E-mail de regularização contém intencionalmente link com token assinado, válido por uma hora, para o administrador bloqueado. O pedido de regularização conhecido é persistido antes do broker, revalidado e recuperado com tentativas limitadas; a resposta genérica não enumera contas. E-mail desconhecido não é persistido, e o snapshot de destinatário conhecido é expurgado em até 24 horas.
- Na rota de regularização, o token sai da URL antes do PostHog; analytics não inicializa e Vercel aplica `private, no-store`, `no-referrer` e `noindex, nofollow`.
- Login bloqueado valida a senha, mas não cria JWT, `OutstandingToken` nem atualiza `last_login`. Alteração de senha também exige acesso de tenant; logout da sessão e de todos os dispositivos permanece disponível.
- Ativação do checkout inicial habilita somente o administrador proprietário pretendido; funcionário intencionalmente inativo nunca é reativado por pagamento ou regularização.
- Regularização com resultado ambíguo falha fechada em `RECONCILIATION_REQUIRED`; recuperação exige reconciliação manual documentada, nunca nova cobrança automática.

## Antes de produção

Execute análise SAST/dependências, pentest do fluxo público, rotação de segredos em um secret manager e configure alertas para falhas de login, erros 5xx e anomalias entre tenants. O isolamento por aplicação deve ser reforçado com PostgreSQL Row Level Security quando a operação exigir defesa em profundidade. Nunca exponha Redis ou PostgreSQL à internet.

Ao usar Supabase somente como PostgreSQL, desative a Data API. Não exponha o schema `public`, a chave `service_role` ou a string `DATABASE_URL` ao frontend.
