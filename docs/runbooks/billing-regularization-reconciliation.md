# Reconciliação de checkout de regularização

Use quando assinatura bloqueada ficar em `CREATING` ou `RECONCILIATION_REQUIRED`.
Nunca execute novo checkout antes de consultar Asaas pelo `externalReference` da assinatura e confirmar checkout ativo.

`CREATING` só pode ser reconciliado após 5 minutos desde `claim_started_at`, janela acima do timeout de 10 segundos do provedor. Não existe `--force`: claim recente pode ainda concluir checkout e o comando a rejeita.

1. Localize assinatura e `regularization_checkout_reference` no Django admin ou shell. Para signup inicial, use `external_reference`.
2. Consulte Asaas; confirme manualmente checkout ativo pertencente àquela referência de tentativa.
3. Se existir, anexe ID e URL verificados:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --verified-checkout-id chk_123 \
  --verified-checkout-url https://checkout.asaas.com/chk_123
```

4. Somente se Asaas confirmar que não existe checkout ativo, libere nova criação:

```bash
python manage.py reconcile_regularization_checkout \
  --subscription-id 42 \
  --reset-confirmed-no-active-checkout
```

Comando aceita somente estados `CREATING` e `RECONCILIATION_REQUIRED`, grava evento de auditoria e não chama Asaas.
