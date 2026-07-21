# Reconciliação de checkout de regularização

Use quando assinatura bloqueada ficar em `CREATING` ou `RECONCILIATION_REQUIRED`.
Nunca execute novo checkout antes de consultar Asaas e confirmar a situação do checkout.

`CREATING` só pode ser reconciliado após 5 minutos desde `claim_started_at`, janela acima do timeout de 10 segundos do provedor. Não existe `--force`: claim recente pode ainda concluir checkout e o comando a rejeita.

## Legado anterior à migração 0008

Para um legado `CREATED` com ID e URL persistidos, a migração 0008 preenche `regularization_checkout_reference` com `subscription.external_reference`. O webhook continua exigindo também o ID exato do checkout.

Para `CREATING` ou `RECONCILIATION_REQUIRED` legado com `regularization_checkout_reference` nula, o checkout original usou `subscription.external_reference` no Asaas. Consulte o Asaas por essa referência estática. Só anexe depois de verificar manualmente o ID exato e o status atual daquele checkout no Asaas. Informe a mesma referência estática real da assinatura em `--attempt-reference`:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --verified-checkout-id chk_legacy_123 \
  --verified-checkout-url https://checkout.asaas.com/chk_legacy_123 \
  --attempt-reference 11111111-1111-1111-1111-111111111111
```

`11111111-1111-1111-1111-111111111111` acima representa o valor real de `subscription.external_reference`, não uma UUID nova e não uma tentativa inferida.

## Tentativas novas

Para tentativas criadas após a migração 0008, use somente o valor persistido em `regularization_checkout_reference`. Ele é uma UUID única por tentativa. Nunca o substitua por `subscription.external_reference`:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --verified-checkout-id chk_attempt_456 \
  --verified-checkout-url https://checkout.asaas.com/chk_attempt_456 \
  --attempt-reference 22222222-2222-2222-2222-222222222222
```

`22222222-2222-2222-2222-222222222222` acima representa o valor já armazenado em `regularization_checkout_reference` para essa tentativa.

## Checkout não verificável

Se o checkout legado ou novo não puder ser verificado, não anexe referência, ID ou URL. Somente depois de o Asaas confirmar que não existe checkout ativo, libere nova criação. Isso também limpa com segurança uma referência legada desconhecida:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --reset-confirmed-no-active-checkout
```

Comando aceita somente estados `CREATING` e `RECONCILIATION_REQUIRED`, grava evento de auditoria e não chama Asaas.
