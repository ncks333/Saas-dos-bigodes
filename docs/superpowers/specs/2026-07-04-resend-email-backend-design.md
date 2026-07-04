# Backend de e-mail transacional via Resend

## Objetivo

Enviar e-mails transacionais pelo endpoint HTTPS do Resend, pois os planos
Trial, Free e Hobby da Railway bloqueiam conexões SMTP de saída.

## Arquitetura

- Criar `core.email_backends.ResendEmailBackend`, compatível com a interface de
  backends de e-mail do Django.
- Manter as chamadas existentes a `django.core.mail.send_mail`; views e demais
  consumidores não conhecerão detalhes do provedor.
- Enviar mensagens para `https://api.resend.com/emails` usando `requests`, que
  já é dependência do projeto.
- Autenticar com `RESEND_API_KEY` e usar `DEFAULT_FROM_EMAIL` como remetente.
- Preservar o backend em memória nos testes e permitir backends locais em
  desenvolvimento.

## Dados e erros

- Enviar remetente, destinatários, cópias, assunto e corpo textual. Incluir HTML
  quando a mensagem fornecer alternativa `text/html`.
- Usar timeout explícito de dez segundos e chamar `raise_for_status()`.
- Respeitar `fail_silently`: propagar falhas quando falso e retornar zero quando
  verdadeiro.
- Nunca registrar a chave da API nem o cabeçalho de autorização.
- A produção deve falhar na inicialização quando o backend Resend estiver ativo
  sem `RESEND_API_KEY`.

## Configuração

Produção usará:

```text
EMAIL_BACKEND=core.email_backends.ResendEmailBackend
RESEND_API_KEY=re_...
DEFAULT_FROM_EMAIL=M&R BarberHub <nao-responda@mail.mrbarberhub.com.br>
```

As variáveis SMTP antigas poderão ser removidas depois do primeiro envio
validado.

## Testes e liberação

- Testar payload, autenticação, timeout, resposta bem-sucedida e
  `fail_silently` com HTTP simulado.
- Manter o teste existente do fluxo de recuperação usando backend em memória.
- Rodar testes direcionados e lint do backend.
- Após push, alterar `EMAIL_BACKEND` na Railway, fazer deploy e solicitar uma
  recuperação de senha. Confirmar entrega e link com o domínio público.

## Rollback

Reverter o commit e restaurar um backend de e-mail suportado. A chave Resend
permanece revogável no painel e não será armazenada no repositório.
