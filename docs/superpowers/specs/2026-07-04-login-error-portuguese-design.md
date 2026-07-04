# Mensagem de erro de login em português

## Objetivo

Exibir uma mensagem clara em português quando usuário ou senha forem inválidos, sem revelar qual credencial falhou.

## Comportamento

- Quando `POST /auth/login/` responder HTTP 401, o formulário exibirá `Usuário ou senha inválidos.`
- A mensagem original do backend não será mostrada nesse caso.
- Erros de conexão, servidor e validação fora do login continuarão usando o tratamento existente.
- O fluxo de autenticação e armazenamento dos tokens não mudará.

## Implementação

O componente de login tratará o erro HTTP 401 antes de chamar o formatador genérico `errorText`. A regra ficará limitada ao formulário de login para não alterar respostas 401 de outras áreas.

## Testes

Um teste Playwright simulará resposta 401 com a mensagem inglesa do backend e verificará que:

- `Usuário ou senha inválidos.` aparece;
- `No active account found with the given credentials` não aparece.

Lint e build do frontend também deverão passar.
