# Integração do BarberHub com Evolution API

**Data:** 2026-07-09

## Objetivo

Conectar um número novo do WhatsApp Business ao BarberHub para enviar confirmações e lembretes de agendamentos por meio da Evolution API v2 usando `WHATSAPP-BAILEYS`.

## Escopo

- Hospedar a Evolution API em serviço separado na Railway.
- Criar uma instância chamada `barberhub`.
- Vincular o número novo pelo QR Code do WhatsApp Business.
- Configurar o backend com URL, chave e nome da instância.
- Validar confirmação de agendamento e lembretes de 24 horas e 1 hora.
- Documentar operação, teste e reconexão.

Ficam fora deste ciclo: Meta Cloud API, templates oficiais da Meta, campanhas, disparos em massa, caixa de atendimento e uso do número pessoal da M&R Solutions na automação.

## Arquitetura

```text
Agendamento no BarberHub
        |
        v
Django cria tarefa Celery
        |
        v
Worker chama Evolution API v2
        |
        v
Instância barberhub (Baileys)
        |
        v
WhatsApp entrega mensagem ao cliente
```

A Evolution API roda isolada da aplicação Django. Seus segredos ficam nas variáveis da Railway e nunca entram no repositório. O número novo permanece dedicado ao BarberHub; o número pessoal continua reservado ao atendimento provisório da M&R Solutions.

## Configuração

O backend já possui o provedor e usa:

```text
WHATSAPP_BASE_URL=https://<dominio-da-evolution>
WHATSAPP_API_KEY=<segredo>
WHATSAPP_INSTANCE_NAME=barberhub
```

A instância usa o provedor `WHATSAPP-BAILEYS` e é vinculada pelo QR Code exibido pela Evolution. Banco e cache da Evolution devem ser próprios ou logicamente isolados dos dados da aplicação BarberHub.

## Fluxos de mensagem

### Confirmação

Ao concluir um agendamento, o backend agenda uma tarefa Celery. A mensagem informa nome do cliente, serviço, data e horário.

### Lembretes

O Celery Beat procura agendamentos pendentes ou confirmados e agenda lembretes aproximadamente 24 horas e 1 hora antes do atendimento.

### Idempotência

Cada agendamento aceita somente um registro por tipo de notificação. Uma mensagem marcada como enviada não deve ser enviada novamente por repetição da mesma tarefa.

## Falhas e operação

- Chamadas HTTP usam timeout curto e falhas geram novas tentativas com espera progressiva.
- Cada tarefa tenta novamente no máximo cinco vezes.
- Resposta do provedor e status ficam registrados em `NotificationLog`.
- Sessão desconectada exige novo pareamento por QR Code.
- Logs nunca devem expor API key, QR Code ou conteúdo além do necessário para diagnóstico.
- Como Baileys usa conexão não oficial baseada no WhatsApp Web, existe risco de instabilidade, desconexão ou bloqueio. O uso fica limitado a mensagens transacionais autorizadas, sem disparos em massa.

## Testes e aceite

1. Evolution responde em HTTPS e a instância `barberhub` aparece conectada.
2. Um envio manual pela API chega ao número de teste.
3. Um agendamento de teste envia exatamente uma confirmação.
4. Lembretes de 24 horas e 1 hora são exercitados com horários controlados e não duplicam.
5. Falha simulada deixa evidência no log e aciona nova tentativa.
6. Nenhuma credencial aparece no Git, frontend ou saída pública.

## Migração futura

O portfólio empresarial M&R Solutions permanece disponível. Se volume, estabilidade ou conformidade exigirem, o provedor poderá migrar para a Meta Cloud API oficial sem mudar os fluxos de negócio do agendamento.
