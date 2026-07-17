# Desempenho do painel M&R BarberHub

Data: 2026-07-17  
Status: aprovado para especificação

## Objetivo

Reduzir o tempo percebido e real das operações mais usadas antes da apresentação
comercial. Alterações de status devem aparecer imediatamente, telas devem evitar
requisições redundantes e a API deve executar consultas proporcionais ao volume
visível, sem mudar regras de agenda, isolamento multi-tenant ou notificações.

## Diagnóstico

Medições externas feitas durante o diagnóstico encontraram aproximadamente 0,7 a
1,8 segundo no health check da API e 0,9 a 2,5 segundos nos endpoints públicos.
Esses números incluem rede e não substituem métricas da Railway, mas mostram que
cada round-trip adicional é perceptível.

O frontend hoje espera o `PATCH`, invalida o cache e baixa novamente coleções
inteiras. `fetchAll` percorre páginas sequencialmente. Uma alteração de status de
agendamento ainda invalida agenda, dashboard e resumo diário. A busca de clientes
consulta a API a cada tecla. A agenda baixa todos os agendamentos e filtra o dia no
navegador.

No backend, a disponibilidade pública executa duas consultas de conflito para cada
slot candidato. Relatórios agregam dados corretos, mas devem ser atualizados fora do
caminho visual crítico da alteração de status.

## Abordagens consideradas

### 1. Somente frontend

Atualizar cache local e reduzir invalidações. Entrega maior ganho visual com menor
risco, mas mantém consultas desnecessárias na agenda e disponibilidade pública.

### 2. Otimização balanceada — escolhida

Combinar atualização otimista no frontend, filtros de API e redução de consultas no
backend. Ataca percepção e custo real sem trocar hospedagem, banco ou arquitetura.

### 3. Escala de infraestrutura primeiro

Aumentar recursos da Railway ou planos antes de alterar código. Pode reduzir cold
start e contenção, mas adiciona custo e não elimina refetchs, paginação sequencial ou
consultas repetidas. Só será considerada depois das mudanças mensuráveis no código.

## Desenho

### Cache e mutações

Alterações de status de agendamento atualizam imediatamente todas as entradas de
cache afetadas. O valor anterior fica guardado para rollback. Se a API falhar, o
cache volta ao estado anterior e a mensagem de erro existente aparece. A resposta
confirmada pelo servidor substitui o valor otimista.

Criação, edição e desativação de clientes, serviços, usuários e bloqueios passam a
usar a resposta da mutação para atualizar ou remover somente o registro afetado.
Refetch completo fica reservado para situações em que a resposta não permita
reconciliar o cache com segurança.

Dashboard e resumo diário saem do caminho crítico. Após mudança de agenda, a linha
fica atualizada primeiro; agregados são invalidados em segundo plano, sem bloquear a
interação.

### Consultas do painel

A agenda envia a data selecionada para a API. O backend converte o dia em limites de
tempo no fuso da barbearia e filtra por intervalo, preservando o índice existente em
`barbershop`, `starts_at` e `status`. O frontend não baixa histórico completo para
mostrar um único dia.

A busca de clientes usa debounce de 300 ms. Consultas anteriores são descartadas
pelo comportamento do React Query/axios quando deixam de ser relevantes para a
chave atual; resultados antigos não substituem o termo corrente.

Coleções administrativas mantêm paginação da API. Onde a interface realmente exige
todas as opções ativas, será usado endpoint leve ou limite explícito documentado,
sem retornar campos não usados.

### Disponibilidade pública

`available_slots` carrega expediente, agendamentos ativos e bloqueios do dia uma vez.
Os slots são calculados em memória sobre esses intervalos. A quantidade de queries
permanece constante para um dia, independentemente do número de horários candidatos.

As regras existentes permanecem: duração do serviço, expediente, bloqueios,
sobreposição e proibição de horários passados.

### Infraestrutura

Vercel continua servindo frontend estático. Railway continua executando Django e
Celery; Supabase continua como PostgreSQL. Nenhuma troca de provedor faz parte deste
ciclo.

Após otimização do código, serão comparados tempos frios e quentes. A operação deve
confirmar que Railway e Supabase estão na mesma região, que o serviço web não está
entrando em suspensão durante a demonstração e que CPU, memória e conexões não
apresentam saturação. Aumento de plano ou workers depende dessas métricas.

## Segurança e consistência

- Atualização otimista nunca grava diretamente no banco nem ignora resposta da API.
- Falha HTTP restaura cache anterior.
- Filtros de data continuam aplicados dentro do tenant autenticado.
- Regras transacionais de agendamento e bloqueios permanecem no backend.
- WhatsApp, Celery, autenticação e tokens ficam fora deste ciclo.
- Nenhum dado real de cliente entra em teste automatizado ou medição.

## Testes

O trabalho seguirá TDD:

- teste E2E prova que status muda visualmente antes da resposta atrasada da API;
- teste E2E prova rollback e mensagem de erro em falha;
- teste E2E conta requisições e impede refetch completo após mudança confirmada;
- teste backend prova filtro da agenda pelo dia no fuso do tenant;
- teste backend usa contagem de queries para disponibilidade constante;
- suíte backend, lint, build e testes E2E existentes devem continuar verdes.

## Critérios de aceite

- Status aparece atualizado em até um frame após interação local.
- Erro da API restaura o status anterior.
- Mudança de status não baixa novamente a lista completa de agendamentos.
- Agenda carrega somente o dia selecionado.
- Busca de clientes dispara no máximo uma consulta após 300 ms sem digitação.
- Disponibilidade do dia usa quantidade constante de queries.
- Nenhuma regra de negócio, tenant ou notificação sofre regressão.
- Após deploy, endpoints autenticados usados na demonstração terão tempos frios e
  quentes registrados para decidir se ajuste de plano ainda é necessário.

## Fora de escopo

- Migração de Vercel, Railway, Supabase ou Upstash.
- WebSocket ou sincronização em tempo real entre navegadores.
- Mudança visual ampla do painel.
- Alteração das regras de agenda ou mensagens WhatsApp.
- Compra automática de plano ou mudança de configuração externa sem métricas.
