# Endurecimento da entrega WhatsApp

## Escopo

Corrigir somente backend, integração oficial Meta WhatsApp Cloud API v25.0 e documentação operacional. Permanecem dois templates e três eventos: recebimento imediato, lembrete de 24 horas e lembrete de 1 hora. Não haverá frontend, webhook, Evolution API nem migration.

## Números brasileiros

Um helper compartilhado recebe somente texto composto por dígitos e pontuação telefônica comum. Números locais de 10 ou 11 dígitos recebem o prefixo `55`; números de 12 ou 13 dígitos precisam começar com `55`. A saída contém somente dígitos. `CustomerSerializer` e `PublicBookingInput` usam o helper antes da persistência; o provider repete a normalização para proteger registros legados.

## Claim e estados

Cada evento mantém um único `NotificationLog` pela constraint existente. Antes do POST, a task executa `UPDATE ... WHERE status = 'PENDING'` para trocar o estado por `SENDING`. Só a execução que atualizar uma linha pode enviar.

- Resposta aceita e persistida: `SENT`.
- Timeout ou falha de conexão: `UNKNOWN`, sem retry automático.
- HTTP 429, 5xx ou outro HTTP retryable: volta a `PENDING` e agenda retry Celery controlado. Scheduler também pode reenfileirar esse estado, mas cada execução precisa obter novo claim atômico antes do POST.
- Erro terminal: `FAILED`, guardando somente classe, status HTTP e código Meta seguro.
- Falha ao persistir depois da aceitação: mantém `SENDING`; nenhuma execução posterior consegue novo claim.

Metadados nunca guardam mensagem crua de exceção, token, headers, recipient ou payload.

## Lembretes

Scheduler aceita somente 1 e 24 horas. Para cada janela, consulta eventos vencidos entre `WHATSAPP_REMINDER_LOOKBACK_MINUTES` e agora, com default de 60 minutos, exigindo que o agendamento ainda esteja no futuro. Scheduler cria ou recupera o `NotificationLog` idempotente e enfileira quando seu estado é `PENDING`, inclusive para recuperar falha do broker depois de `get_or_create`. Não reenfileira `SENT`, `SENDING`, `UNKNOWN` nem `FAILED`. Cada job recebe snapshot UTC serializado de `starts_at`; jobs duplicados continuam produzindo no máximo um POST porque somente um worker obtém o claim.

Task recarrega agendamento com cliente, serviço e barbearia. Antes do claim, exige status `PENDING` ou `CONFIRMED` e snapshot ainda igual. Agendamento cancelado ou reagendado não envia. Formatação do template usa `ZoneInfo(appointment.barbershop.timezone)`.

## Testes e operação

Testes cobrem normalização local/E.164/inválida, defesa do provider, claim condicional real, worker duplicado, falhas incerta/terminal/pós-aceitação, timezone do tenant, cancelamento, reagendamento, hours inválido, catch-up de 30 minutos, recuperação de log `PENDING` e bloqueio dos demais estados. Deploy documenta token permanente sem expiração de system user, permissões mínimas, rotação, revogação e lookback.
