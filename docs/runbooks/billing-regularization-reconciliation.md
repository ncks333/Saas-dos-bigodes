# Reconciliação de checkout de regularização

Use quando assinatura bloqueada ficar em `CREATING` ou `RECONCILIATION_REQUIRED`.
Nunca execute novo checkout antes de consultar Asaas e confirmar a situação do checkout.

`CREATING` só pode ser reconciliado após 5 minutos desde `claim_started_at`, janela acima do timeout de 10 segundos do provedor. Não existe `--force`: claim recente pode ainda concluir checkout e o comando a rejeita.

No fluxo normal, `CHECKOUT_PAID` não confia em uma referência recebida somente no evento. O worker parte do ID de checkout já persistido, consulta esse checkout no Asaas e exige ID, estado `PAID`, referência externa e exatamente uma assinatura ativa compatíveis. Falta, divergência ou resultado múltiplo falha fechado e fica disponível para retry; não anexe valor inferido do payload.

`CHECKOUT_CANCELED` e `CHECKOUT_EXPIRED` limpam somente o checkout atual. Depois de processados, o administrador bloqueado ou `PENDING_CHECKOUT` pode pedir novo link em `/regularizar`. Evento de tentativa anterior não libera nem limpa tentativa nova.

## Legado anterior à migração 0008

Para um legado `CREATED` com ID e URL persistidos, a migração 0008 preenche `regularization_checkout_reference` com `subscription.external_reference`. O webhook continua exigindo também o ID exato do checkout.

Para `CREATING` ou `RECONCILIATION_REQUIRED` legado com `regularization_checkout_reference` nula, o checkout original usou `subscription.external_reference` no Asaas. Consulte o Asaas por essa referência estática. Só anexe depois de verificar manualmente o ID exato e o status atual daquele checkout no Asaas. Informe a mesma referência estática real da assinatura em `--attempt-reference`:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --verified-checkout-id chk_legacy_123 \
  --verified-checkout-url https://sandbox.asaas.com/checkoutSession/show/chk_legacy_123 \
  --attempt-reference 11111111-1111-1111-1111-111111111111
```

`11111111-1111-1111-1111-111111111111` acima representa o valor real de `subscription.external_reference`, não uma UUID nova e não uma tentativa inferida.

## Tentativas novas

Para tentativas criadas após a migração 0008, use somente o valor persistido em `regularization_checkout_reference`. Ele é uma UUID única por tentativa. Nunca o substitua por `subscription.external_reference`:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --verified-checkout-id chk_attempt_456 \
  --verified-checkout-url https://sandbox.asaas.com/checkoutSession/show/chk_attempt_456 \
  --attempt-reference 22222222-2222-2222-2222-222222222222
```

`22222222-2222-2222-2222-222222222222` acima representa o valor já armazenado em `regularization_checkout_reference` para essa tentativa.

O comando valida a URL antes do anexo. Use somente HTTPS sob uma origem Asaas exata presente em `ASAAS_CHECKOUT_ALLOWED_ORIGINS` do ambiente (`sandbox.asaas.com` em Sandbox; `asaas.com`/`www.asaas.com` em produção). URL HTTP, host semelhante, credencial embutida ou origem não configurada deve ser investigada e rejeitada.

## Checkout não verificável

Se o checkout legado ou novo não puder ser verificado, não anexe referência, ID ou URL. Somente depois de o Asaas confirmar que não existe checkout ativo, libere nova criação. Isso também limpa com segurança uma referência legada desconhecida:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --reset-confirmed-no-active-checkout
```

Comando aceita somente estados `CREATING` e `RECONCILIATION_REQUIRED`, grava evento de auditoria e não chama Asaas.

## Recuperação do e-mail de regularização

O endpoint público devolve a mesma resposta para endereço conhecido e desconhecido. Somente administrador elegível conhecido gera `RegularizationEmailRequest`; endereço desconhecido não fica armazenado. Se o broker falhar depois da persistência, `apps.billing.tasks.recover_regularization_email_requests` redispatcha a cada minuto, em lote limitado.

Cada solicitação usa no máximo cinco tentativas, chave de idempotência estável e revalida identidade/estado antes do envio. O snapshot de destinatário é apagado em até 24 horas. Ao investigar atraso, confirme que há exatamente um Beat, worker consumindo fila e linhas `PENDING` ainda não expiradas; não copie e-mail, token ou snapshot para ticket/log e não recrie manualmente pedido desconhecido.
