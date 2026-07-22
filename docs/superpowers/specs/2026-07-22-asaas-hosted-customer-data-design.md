# Asaas Checkout: dados do pagador hospedados

## Problema

O cadastro coleta apenas nome, e-mail e WhatsApp. Ao enviar esses dados parciais em `customerData`, o Asaas Sandbox recusa a criação do checkout porque CPF/CNPJ e endereço também são obrigatórios quando esse objeto é enviado.

## Decisão

Não enviar `customerData` ao criar checkout recorrente ou checkout de regularização. O Checkout hospedado do Asaas será responsável por coletar e validar dados do pagador.

## Fluxo

1. Cliente cadastra conta e barbearia com dados mínimos atuais.
2. Backend cria checkout sem `customerData`.
3. Asaas abre checkout seguro e solicita dados obrigatórios do pagador.
4. Webhook confirmado mantém fluxo atual de ativação da assinatura.

## Limites

- Não adicionar CPF, endereço ou CEP ao cadastro BarberHub.
- Não alterar plano, trial, valor, callbacks, webhooks ou regras de acesso.
- Não armazenar dados de cartão no BarberHub.

## Teste

Teste do provider deve afirmar que payload enviado a `/checkouts` não possui `customerData` e mantém demais campos de assinatura e callback.
