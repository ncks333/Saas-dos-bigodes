# Endurecimento da entrega WhatsApp

## Escopo

Corrigir somente backend, integração oficial Meta WhatsApp Cloud API v25.0 e documentação operacional. Permanecem dois templates e três eventos: recebimento imediato, lembrete de 24 horas e lembrete de 1 hora. Não haverá frontend, webhook, Evolution API nem migration.

## Números brasileiros

Um helper compartilhado recebe somente texto composto por dígitos e pontuação telefônica comum. Números locais de 10 ou 11 dígitos recebem o prefixo `55`; números de 12 ou 13 dígitos precisam começar com `55`. A saída contém somente dígitos. `CustomerSerializer` e `PublicBookingInput` usam o helper antes da persistência; o provider repete a normalização para proteger registros legados.

Compatibilidade sem data migration exige pesquisar tanto valor canônico `55...` quanto variante local legada dentro do tenant. Serializer considera qualquer variante duplicada. Fluxo público executa busca e canonicalização em transação, bloqueia registro legado encontrado e trata conflito concorrente pela constraint existente antes de criar cliente novo.

## Claim e estados

Cada evento mantém um único `NotificationLog` pela constraint existente. Antes do POST, a task executa `UPDATE ... WHERE status = 'PENDING'` para trocar o estado por `SENDING`. Só a execução que atualizar uma linha pode enviar.

- Resposta aceita e persistida: `SENT`.
- Timeout ou falha de conexão: `UNKNOWN`, sem retry automático.
- HTTP 429, 5xx ou outro HTTP retryable: volta a `PENDING` e agenda retry Celery controlado. Scheduler também pode reenfileirar esse estado, mas cada execução precisa obter novo claim atômico antes do POST.
- Erro terminal: `FAILED`, guardando somente classe, status HTTP e código Meta seguro.
- Falha ao persistir depois da aceitação: mantém `SENDING`; nenhuma execução posterior consegue novo claim.

Metadados nunca guardam mensagem crua de exceção, token, headers, recipient ou payload.

Falhas `DatabaseError` anteriores ao POST — leitura do agendamento, criação/leitura do log ou claim — usam retry Celery limitado com backoff e exceção genérica sanitizada. Depois do início do POST não existe retry por falha de persistência; estado permanece `SENDING` quando resultado aceito não puder ser salvo.

## Lembretes

Scheduler aceita somente 1 e 24 horas. Primeira fase consulta eventos vencidos entre `WHATSAPP_REMINDER_LOOKBACK_MINUTES` e agora, com default de 60 minutos, exigindo que o agendamento ainda esteja no futuro, e materializa o `NotificationLog` idempotente. Segunda fase consulta diretamente todos os logs `REMINDER_*` em `PENDING` cujo evento já venceu, com appointment ainda futuro e ativo, sem depender novamente da janela fresca. Assim, falha do broker depois de `get_or_create` é recuperada em beats posteriores. Não reenfileira `SENT`, `SENDING`, `UNKNOWN` nem `FAILED`. Cada job recebe snapshot UTC serializado de `starts_at`; jobs duplicados continuam produzindo no máximo um POST porque somente um worker obtém o claim.

Task recarrega agendamento com cliente, serviço e barbearia. Antes do claim, exige status `PENDING` ou `CONFIRMED` e snapshot ainda igual. Agendamento cancelado ou reagendado não envia. Formatação do template usa `ZoneInfo(appointment.barbershop.timezone)`.

## Testes e operação

Testes cobrem normalização local/E.164/inválida, colisão com cliente legado, canonicalização pública, claim condicional real, retry DB pré-POST, worker duplicado, falhas incerta/terminal/pós-aceitação, timezone do tenant, cancelamento, reagendamento, hours inválido, catch-up durável após falha do broker, código Meta estritamente inteiro e bloqueio dos demais estados. Deploy usa somente placeholders e documenta token permanente sem expiração de system user, permissões mínimas, rotação, revogação e lookback.
