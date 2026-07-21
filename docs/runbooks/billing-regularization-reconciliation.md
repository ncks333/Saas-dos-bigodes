# Reconciliação de checkout de regularização

Use quando assinatura bloqueada ficar em `CREATING` ou `RECONCILIATION_REQUIRED`.
Nunca execute novo checkout antes de consultar Asaas pelo `externalReference` da assinatura e confirmar checkout ativo.

1. Localize assinatura e `external_reference` no Django admin ou shell.
2. Consulte Asaas; confirme manualmente checkout ativo pertencente àquele `externalReference`.
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
