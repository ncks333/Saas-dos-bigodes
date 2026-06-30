# Agente de agendamento

O prompt de sistema e os schemas das ferramentas ficam em
`backend/apps/appointments/agent_prompt.py`. A regra crítica também é validada
na camada transacional do backend: um cliente pode possuir no máximo uma
reserva ativa por data.

## Ferramentas autenticadas

Todas exigem JWT e são automaticamente isoladas pela barbearia do usuário:

- `POST /api/v1/agent-tools/listar-reservas-usuario/`
- `POST /api/v1/agent-tools/consultar-disponibilidade/`
- `POST /api/v1/agent-tools/criar-reserva/`
- `POST /api/v1/agent-tools/cancelar-reserva/`

O cancelamento exige `confirmacao_explicita: true`. Mesmo que um agente tente
criar diretamente uma segunda reserva ativa na mesma data, o backend rejeita a
operação.

## Fluxo obrigatório

1. Listar as reservas do cliente na data desejada.
2. Se existir uma reserva, informar o horário e solicitar confirmação para
   cancelá-la. Sem confirmação, não alterar nada.
3. Sem conflito, consultar a disponibilidade do serviço.
4. Criar a reserva somente se o slot estiver disponível.

O `servico_id` foi incluído nos schemas porque duração e disponibilidade variam
por serviço no domínio da barbearia.
