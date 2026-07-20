# Onboarding comercial e assinatura do M&R BarberHub

## Objetivo

Trocar o acesso direto ao painel por um fluxo comercial completo: o cliente da M&R cria sua conta, cadastra a barbearia, escolhe o plano, informa o meio de pagamento no checkout hospedado do Asaas e recebe acesso ao BarberHub durante o período de teste. A assinatura deve cobrar automaticamente depois do trial, tolerar inadimplência por sete dias e bloquear o login após esse prazo.

## Decisões

- Trial público padrão: 30 dias.
- Trial especial do primeiro barbeiro piloto: 60 dias, aplicado individualmente, sem alterar a oferta pública.
- Gateway inicial: Asaas.
- Checkout: página hospedada do Asaas, aceitando cartão de crédito; o sistema nunca recebe nem armazena número, CVV ou validade do cartão.
- Primeira cobrança: agendada pelo Asaas para o dia seguinte ao fim do trial.
- Tolerância de inadimplência: 7 dias.
- Após tolerância: login bloqueado e página pública de regularização; dados não são excluídos.
- Preço: configurável no plano do banco. Nenhum valor ficará fixo no frontend; M&R poderá definir o preço público e o preço fundador depois da decisão dos sócios.
- Plano inicial: um plano ativo; múltiplos planos ficam fora desta entrega.
- WhatsApp permanece dedicado a confirmação e lembrete de agendamento. Cobrança, trial e suspensão usam e-mail nesta entrega.

## Fluxo comercial

### Cadastro

1. Landing page apresenta produto, trial e plano vigente.
2. Cliente abre `/cadastro` e informa nome, e-mail, usuário, senha, nome da barbearia, slug e WhatsApp.
3. Backend valida senha, e-mail, usuário, slug, consentimento e proteção antiabuso.
4. Backend cria barbearia e usuário em estado `PENDING_CHECKOUT`, vinculados a uma assinatura local pendente.
5. Backend cria checkout recorrente do Asaas com `externalReference` apontando para a assinatura local.
6. Frontend redireciona para o checkout hospedado.
7. Cliente informa o cartão no Asaas. O cartão é validado pelo gateway; nenhum dado bruto do cartão passa pelo backend.
8. Webhook autenticado do Asaas confirma a criação da assinatura e muda a assinatura local para `TRIAL`.
9. Backend ativa o usuário; frontend redireciona para login/painel. A preferência pública `Barbershop.active` continua independente da cobrança.

O callback do navegador serve apenas para experiência de navegação. A ativação financeira depende de webhook; redirecionamento nunca libera acesso sozinho.

### Estados da assinatura

```text
PENDING_CHECKOUT
        ↓ checkout confirmado
TRIAL ──→ ACTIVE ──→ GRACE ──→ SUSPENDED
  │          │           │           │
  └──────────┴───────────┴───────────┴──→ CANCELED
```

- `PENDING_CHECKOUT`: cadastro criado, pagamento ainda não confirmado; painel bloqueado.
- `TRIAL`: acesso completo até `trial_ends_at`; primeira cobrança já agendada.
- `ACTIVE`: pagamento recorrente confirmado; acesso completo.
- `GRACE`: pagamento falhou ou ficou vencido; acesso continua por sete dias e e-mails são enviados.
- `SUSPENDED`: prazo de tolerância acabou; login, painel e agendamento público ficam bloqueados pela assinatura.
- `CANCELED`: assinatura cancelada; acesso bloqueado, dados preservados.

Pagamento confirmado durante `GRACE` retorna para `ACTIVE`. Cancelamento explícito não deve ser confundido com falha temporária de cobrança.

### Login bloqueado

O endpoint de login não emite JWT para assinaturas `PENDING_CHECKOUT`, `SUSPENDED` ou `CANCELED`. A resposta informa apenas que a assinatura precisa ser regularizada, sem revelar dados sensíveis.

O cliente recebe por e-mail um link assinado para gerar novo checkout. A rota pública de regularização não exige login, aplica rate limit e só cria checkout após validar o token temporário. O usuário não precisa acessar o painel para pagar.

## Modelagem

Criar app `apps.billing` com:

### `SubscriptionPlan`

- `code`: identificador estável, único.
- `name`: nome exibido.
- `amount`: valor decimal positivo.
- `currency`: padrão `BRL`.
- `trial_days`: padrão 30.
- `active`: permite retirar plano novo sem apagar histórico.
- timestamps do projeto.

### `Subscription`

- relação um-para-um com `Barbershop`.
- `plan`.
- `status` com estados acima.
- `provider`: `ASAAS`.
- `provider_customer_id`.
- `provider_subscription_id`.
- `provider_checkout_id`.
- `external_reference` único e não previsível.
- `trial_ends_at`, `current_period_ends_at`, `grace_ends_at`, `next_billing_at`.
- `last_payment_status` e `last_payment_at`.
- `suspended_at`, `canceled_at`.
- timestamps do projeto.

Na migração, cada `Barbershop` existente recebe uma assinatura `ACTIVE` vinculada ao plano inicial, preservando o acesso atual. Apenas barbearias criadas pelo novo onboarding começam em `PENDING_CHECKOUT`. Fixtures e comandos de desenvolvimento devem criar a assinatura ativa explicitamente.

### `BillingWebhookEvent`

- `provider`.
- `provider_event_id` único por provider.
- `event_type`.
- `payload` sanitizado, sem cartão, CVV, token secreto ou credencial.
- `processed_at`.
- `processing_error` limitado a diagnóstico seguro.

O evento é salvo antes do processamento e processado de modo idempotente. Reentrega do mesmo ID não repete ativação, e-mail ou mudança de estado.

### `BillingNotificationLog`

- relação com `Subscription`.
- `kind`: tipo estável da notificação.
- `status`: `PENDING`, `SENT` ou `FAILED`.
- `sent_at`.
- unicidade por assinatura e tipo de notificação.

O registro funciona como chave de idempotência dos e-mails. Uma repetição de webhook ou da tarefa periódica não envia novamente a mesma notificação de ciclo.

O estado financeiro fica em `Subscription`. `Barbershop.active` continua sendo a preferência do dono para ligar ou desligar o agendamento público e nunca é sobrescrito por cobrança. Disponibilidade pública exige simultaneamente `Barbershop.active=True` e assinatura em `TRIAL`, `ACTIVE` ou `GRACE`.

## Integração Asaas

Criar um adaptador isolado em `apps.billing.providers.asaas` usando API HTTP existente no projeto. O adaptador expõe operações internas, sem espalhar nomes da Asaas pela aplicação:

- `create_recurring_checkout(...) -> CheckoutResult`.
- `get_checkout(...) -> ProviderCheckout`.
- `parse_webhook(...) -> ProviderEvent`.
- `create_regularization_checkout(...) -> CheckoutResult`.

O checkout usa `chargeTypes: ["RECURRENT"]`, `billingTypes: ["CREDIT_CARD"]`, item com preço vindo do plano e `subscription.nextDueDate` igual ao dia seguinte ao fim do trial. `externalReference` relaciona Asaas à assinatura local.

Segredos ficam somente em variáveis de ambiente: URL, API key e token de webhook. O sistema valida o token do webhook, responde rapidamente e processa eventos de forma idempotente. O fluxo deve ser testado primeiro no Sandbox do Asaas.

Referências de integração: [Checkout recorrente do Asaas](https://docs.asaas.com/docs/checkout-com-assinatura-recorrente), [eventos de Webhook](https://docs.asaas.com/docs/webhooks-events) e [Sandbox](https://docs.asaas.com/docs/sandbox-1).

## E-mails

Usar `send_mail`/backend Resend já existente e tarefas Celery para não atrasar requests. E-mails transacionais:

- trial ativado, com data da primeira cobrança;
- trial próximo do fim;
- pagamento aprovado;
- pagamento falhou, com prazo de tolerância;
- assinatura suspensa, com link de regularização;
- assinatura reativada;
- assinatura cancelada.

Templates de e-mail devem exibir nome da barbearia, data, valor do plano, estado atual e URL HTTPS de regularização. Não incluir dados de cartão.

## Frontend

Adicionar rotas públicas para:

- cadastro;
- checkout pendente;
- checkout concluído aguardando confirmação;
- checkout cancelado/expirado;
- assinatura suspensa/regularização.

O login atual deve tratar respostas de assinatura bloqueada e apontar para regularização. O painel só monta conteúdo após sessão válida e assinatura liberada.

Landing deve exibir trial e preço vindos de endpoint público de planos, sem aceitar valor vindo do navegador para criar checkout. A copy deve deixar explícitos duração do trial, data da primeira cobrança, valor mensal, tolerância, cancelamento e preservação dos dados.

## Segurança e abuso

- Nunca aceitar preço, trial ou plano confiado pelo frontend.
- Usar rate limit e Turnstile no cadastro e na regularização.
- Normalizar e validar slug, e-mail, telefone e senha.
- Limitar uma assinatura de trial por e-mail, usuário e slug; regras adicionais por CPF/CNPJ ficam para etapa posterior de antifraude.
- Não registrar cartão, CVV, token de pagamento ou payload sensível em logs.
- Validar autenticidade dos webhooks e rejeitar eventos inválidos.
- Registrar auditoria para cadastro, checkout criado, trial ativado, pagamento, falha, suspensão, reativação e cancelamento.
- Usar transação e constraints para impedir duas barbearias/assinaturas para o mesmo cadastro.
- Não bloquear clientes existentes por ausência acidental de assinatura durante a migração; a data migration deve criar os vínculos ativos antes de ativar o gate de login.

## Testes e critérios de aceite

- Cadastro válido cria exatamente uma barbearia, um administrador e uma assinatura pendente.
- Cadastro inválido não cria registros parciais.
- Plano e preço são resolvidos no backend.
- Checkout Asaas recebe somente cartão, trial e preço esperados.
- Callback isolado não ativa acesso.
- Webhook válido ativa trial uma única vez.
- Webhook duplicado não duplica e-mail nem transição.
- Pagamento confirmado ativa ou reativa assinatura.
- Falha inicia tolerância de sete dias.
- Pagamento dentro da tolerância restaura acesso.
- Tolerância expirada bloqueia login e agendamento público.
- Cliente suspenso pode gerar checkout de regularização sem login.
- Cancelamento preserva dados e bloqueia acesso.
- E-mails não vazam dados de cartão e falhas do Resend não quebram webhook.
- Frontend mostra trial, primeira cobrança, valor e estado correto.
- Testes de integração usam Asaas Sandbox; produção nunca usa credenciais de teste.

## Fora desta entrega

- Migração em massa do primeiro barbeiro.
- Horários fixos recorrentes.
- Múltiplos planos públicos.
- Cobrança via WhatsApp.
- PIX automático como método principal.
- Marketplace, split ou cobrança dos clientes finais da barbearia.
- Painel financeiro completo da M&R.

Esses itens serão avaliados depois da demonstração do sistema ao primeiro cliente e da decisão final dos sócios sobre preço.
