SYSTEM_PROMPT = """
Você é o assistente de agendamento do SaaS dos Bigodes.

REGRA OBRIGATÓRIA:
- Cada cliente pode ter no máximo uma reserva ativa por dia.
- Antes de criar, sempre use listar_reservas_usuario para a data solicitada.
- Se houver reserva ativa, informe o horário existente e pergunte se o cliente
  deseja cancelá-la. Nunca presuma que ele quer substituir a reserva.
- Só use cancelar_reserva após confirmação explícita do cliente.
- Sem conflito diário, consulte a disponibilidade antes de criar a reserva.
- Nunca invente reservas ou horários; use os dados retornados pelas ferramentas.
""".strip()


TOOL_SCHEMAS = [
    {
        "name": "consultar_disponibilidade",
        "description": "Lista horários disponíveis para uma data e serviço.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "format": "date"},
                "servico_id": {"type": "integer"},
            },
            "required": ["data", "servico_id"],
        },
    },
    {
        "name": "listar_reservas_usuario",
        "description": "Lista reservas ativas do cliente na data informada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "usuario_id": {"type": "integer"},
                "data": {"type": "string", "format": "date"},
            },
            "required": ["usuario_id", "data"],
        },
    },
    {
        "name": "criar_reserva",
        "description": "Cria uma reserva após verificar conflito diário e disponibilidade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "usuario_id": {"type": "integer"},
                "servico_id": {"type": "integer"},
                "data": {"type": "string", "format": "date"},
                "horario": {"type": "string", "format": "time"},
            },
            "required": ["usuario_id", "servico_id", "data", "horario"],
        },
    },
    {
        "name": "cancelar_reserva",
        "description": "Cancela uma reserva somente com confirmação explícita do cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reserva_id": {"type": "integer"},
                "confirmacao_explicita": {"type": "boolean", "const": True},
            },
            "required": ["reserva_id", "confirmacao_explicita"],
        },
    },
]
