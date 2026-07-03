# Migração para os domínios M&R BarberHub

## Objetivo

Usar `app.mrbarberhub.com.br` como URL pública canônica do frontend e
`api.mrbarberhub.com.br` como endpoint da API, sem remover imediatamente o
endpoint Railway anterior usado para rollback.

## Alterações

- Incluir `https://api.mrbarberhub.com.br` em `connect-src` da política CSP.
- Manter `https://saas-dos-bigodes-production.up.railway.app` em `connect-src`
  durante a transição.
- Trocar URLs públicas antigas da Vercel pelo domínio
  `https://app.mrbarberhub.com.br` no HTML, metadata dinâmica, `robots.txt` e
  sitemap.
- Preservar as rotas públicas atuais, inclusive `/agendar/bigodes` e
  `/privacidade`.

## Verificação

- Executar build de produção com `VITE_API_URL` e chave Turnstile de teste não
  secreta.
- Confirmar que arquivos gerados contêm os domínios novos e que nenhuma URL
  pública antiga permaneceu nos arquivos do frontend.
- Após push, executar redeploy na Vercel e validar página inicial, login,
  agendamento público e comunicação com a API.

## Rollback

O domínio antigo da Vercel e o endpoint Railway permanecem disponíveis. Em
falha, reverter o commit e fazer redeploy do deployment anterior na Vercel.
