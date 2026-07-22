# Cadastro: resultado desconhecido do checkout Asaas

## Objetivo

Impedir cobrança recorrente órfã quando Asaas pode ter criado checkout, mas a resposta não chegou ao BarberHub.

## Decisão

Cadastro persiste barbearia, administrador e assinatura antes da chamada externa. Assinatura nasce em `PENDING_CHECKOUT` e recebe referência externa estável. Em resultado desconhecido, registro local permanece e bloqueia nova criação automática.

## Fluxo

1. Criar dados locais e confirmar transação.
2. Solicitar checkout Asaas usando `external_reference` da assinatura.
3. Sucesso: persistir ID do checkout e retornar URL validada.
4. Resultado desconhecido: manter assinatura pendente, marcar reconciliação necessária e retornar erro seguro.
5. Nova tentativa deve reconciliar ou cancelar checkout remoto antes de criar outro. Operação não pode criar segunda cobrança às cegas.

## Segurança e testes

- Nenhuma chamada externa ocorre dentro de transação local aberta.
- Erro ambíguo preserva referência para auditoria/reconciliação.
- Teste comprova persistência local e bloqueio de nova tentativa após timeout.
