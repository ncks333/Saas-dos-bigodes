# Integração do BarberHub com WhatsApp Cloud API

**Data:** 2026-07-15  
**Status:** Desenho e documento aprovados pelo usuário.

## Contexto

O BarberHub já possui confirmações e lembretes assíncronos via Celery, registro idempotente em `NotificationLog` e API pública em produção na Railway. A Evolution API foi retirada da infraestrutura após banimento durante os testes. O próximo provedor será a WhatsApp Cloud API oficial da Meta, usando WABA e número dedicado configurados somente no ambiente de deploy.

O código atual ainda contém o adapter da Evolution (`WHATSAPP_BASE_URL`, `WHATSAPP_API_KEY`, `WHATSAPP_INSTANCE_NAME` e `/message/sendText/{instance}`). A mudança deve substituir somente esse contrato, preservando o fluxo de agenda e a infraestrutura Railway existente.

## Objetivos

- Enviar confirmação de recebimento de agendamento e lembretes de 24 horas e 1 hora por WhatsApp.
- Usar somente a API oficial Meta Graph/WhatsApp Cloud API.
- Manter Celery, retries, idempotência e isolamento multi-tenant existentes.
- Publicar configuração segura na Railway sem gravar token no repositório ou nos logs.
- Deixar frontend, agendamento público e painel administrativo utilizáveis durante a demo.

## Fora de escopo

- Evolution API, Baileys ou qualquer integração não oficial.
- Webhook de mensagens recebidas, inbox, chatbot ou resposta automática.
- Alteração do fluxo de autenticação, agenda, clientes ou layout do frontend.
- Campanhas, disparos em massa ou mensagens de marketing.
- Persistência de status de entrega via webhook. O primeiro corte registra o retorno de envio da Meta e mantém status operacional em `NotificationLog`.

## Abordagens consideradas

1. **Cloud API outbound-only — escolhida.** Troca pequena no provider, aproveita tarefas Celery existentes e entrega notificações reais com menor risco.
2. **Cloud API com webhook e inbox.** Mais completo, mas adiciona endpoint público, verificação de assinatura, estados de mensagem e escopo de produto não necessário para a primeira demo.
3. **Publicar sem WhatsApp.** Menor esforço, mas não atende ao requisito de cliente utilizar o produto com notificações reais.

## Arquitetura e fluxo

```text
Agendamento público/painel
        │
        ├── cria Appointment + NotificationLog idempotente
        └── enfileira tarefa Celery
                    │
                    ▼
          WhatsAppCloudProvider
                    │ HTTPS + Bearer token
                    ▼
      Graph API /{phone_number_id}/messages
                    │
                    ▼
       WhatsApp Business do cliente
```

O provider fará `POST` para `https://graph.facebook.com/{graph_api_version}/{phone_number_id}/messages`, com `Authorization: Bearer <token>` e payload de template:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "5511999999999",
  "type": "template",
  "template": {
    "name": "barberhub_agendamento_recebido",
    "language": {"code": "pt_BR"},
    "components": [{
      "type": "body",
      "parameters": [
        {"type": "text", "text": "Nick"},
        {"type": "text", "text": "Corte"},
        {"type": "text", "text": "15/07 às 14:00"}
      ]
    }]
  }
}
```

O provider retorna o JSON da Meta. Erros HTTP continuam subindo para a tarefa Celery, preservando retry com backoff. O token nunca entra no payload persistido, na mensagem de erro ou no log da aplicação.

## Templates Meta

Antes do smoke test, criar e aprovar templates da categoria `UTILITY` no WhatsApp Manager:

- `barberhub_agendamento_recebido`, idioma `pt_BR`: `Olá, {{1}}! Seu {{2}} foi registrado para {{3}}. A barbearia confirmará seu horário pelo WhatsApp.`
- `barberhub_lembrete_agendamento`, idioma `pt_BR`: `Olá, {{1}}! Lembrete: seu {{2}} está marcado para {{3}}.`

O sistema fará três disparos: confirmação imediata, lembrete 24 horas antes e lembrete 1 hora antes. O template de lembrete será reutilizado nos dois horários. Os dois templates usam três parâmetros de corpo, nesta ordem: nome do cliente, nome do serviço e data/hora formatada no fuso da barbearia. Nomes reais podem ser ajustados no WhatsApp Manager, desde que os valores sejam cadastrados nas variáveis correspondentes da Railway.

O fluxo público continuará exibindo “Horário solicitado!” porque o registro nasce com status `AGUARDANDO_CONFIRMACAO`; a mensagem será de recebimento do pedido, não de confirmação definitiva. O lembrete só será enviado para os status já aceitos por `enqueue_due_reminders`.

## Configuração

Substituir as variáveis Evolution por:

```text
WHATSAPP_GRAPH_API_VERSION=<versão Graph validada no deploy>
WHATSAPP_PHONE_NUMBER_ID=<phone number ID do ambiente>
WHATSAPP_ACCESS_TOKEN=<token do usuário do sistema, secreto>
WHATSAPP_WABA_ID=<WABA ID do ambiente, para rastreabilidade operacional>
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
WHATSAPP_CONFIRMATION_TEMPLATE=barberhub_agendamento_recebido
WHATSAPP_REMINDER_TEMPLATE=barberhub_lembrete_agendamento
```

`WHATSAPP_WABA_ID` não será usado para envio, mas permanece cadastrado para facilitar auditoria e manutenção. Produção deve falhar cedo quando `WHATSAPP_GRAPH_API_VERSION`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN` ou os templates estiverem ausentes. O token será cadastrado diretamente nos secrets da Railway, nunca em `.env`, GitHub, frontend ou arquivo de documentação com valor real.

## Alterações previstas

- `backend/apps/notifications/providers.py`: substituir `WhatsAppProvider.send` baseado em texto/Evolution por envio de template na Graph API.
- `backend/apps/notifications/tasks.py`: montar parâmetros dos dois templates, mantendo logs, retries, horários e idempotência.
- `backend/core/settings/base.py` e `backend/core/settings/production.py`: ler e validar variáveis Meta.
- `backend/tests/test_notifications.py`: validar URL, Bearer token, payload de template, retorno e propagação de erro.
- `backend/.env.production.example` e `docs/DEPLOY.md`: documentar Cloud API e remover instruções operacionais da Evolution.
- Não haverá migração de banco nesta etapa.

## Segurança e operação

- Usar somente número dedicado conectado à WABA aprovada para o ambiente.
- Não usar número pessoal da M&R Solutions.
- Aplicação e usuário do sistema recebem apenas ativos necessários; token deve ser revogado e recriado se exposto.
- Enviar somente mensagens transacionais ligadas a agendamento autorizado.
- Manter timeout HTTP curto e retries limitados; não repetir uma notificação já marcada como `SENT`.
- Não registrar token, cabeçalho `Authorization` ou payload contendo dados além do necessário.
- Se a Meta rejeitar template, número, token ou categoria, marcar tarefa como falha após retries e preservar erro operacional sem segredo.

## Validação e liberação

1. Rodar testes focados de notificações.
2. Rodar suíte backend e `ruff`.
3. Rodar build/lint/testes E2E do frontend.
4. Configurar secrets Meta e templates na Railway.
5. Fazer deploy da API e confirmar `/api/v1/health/`.
6. Criar agendamento de teste com número controlado e confirmar registro `SENT` e recebimento da mensagem.
7. Confirmar que lembrete de 24h/1h enfileira uma única mensagem por tipo.
8. Publicar frontend com `VITE_API_URL` apontando para API online e validar fluxo público e painel.

Critério de aceite: cliente consegue abrir o link online, solicitar horário, acompanhar o registro no painel e receber mensagem transacional real no WhatsApp conectado, sem Evolution API.

## Rollback

Se o envio Meta falhar após deploy, manter API e frontend disponíveis, revogar token somente se houver suspeita de exposição e fazer rollback para o deployment anterior da API. Não reativar Evolution. O banco não recebe migrations nesta alteração, então rollback não exige reversão de schema.
