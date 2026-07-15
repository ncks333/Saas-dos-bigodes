# Final fix — M&R Solutions production config

Data: 2026-07-15
Branch: `feat/mr-solutions-production-ready`

## Correções

- `VITE_MR_SOLUTIONS_WHATSAPP_URL` chega ao build do Docker via `ARG` e `ENV`.
- Compose encaminha somente fixture fictícia para desenvolvimento local.
- README e guia de deploy exigem que valor público real seja cadastrado somente no painel da Vercel, em Production e Preview.
- Alias `@` do Vite usa `fileURLToPath(new URL(...))`, decodificando caminhos com espaços e caracteres codificados.
- README operacional aponta somente para WhatsApp Cloud API oficial da Meta; não instrui Evolution API ou Baileys.
- Comandos executáveis do README para Vite sem Docker e build passam API localhost e exclusivamente a fixture fictícia de WhatsApp.

## TDD

- RED: `node --test config-tests/production-config.test.mjs` teve 6 testes existentes verdes e 4 novos falhos: Docker, Compose, documentação e alias.
- GREEN: `npm run test:config` passou com 10 testes.
- Follow-up RED: nova asserção do README falhou pela instrução legada de Evolution API. GREEN: `npm run test:config` passou com 11 testes.
- Segundo follow-up RED: 11 testes existentes passaram e 3 novos falharam porque os comandos de dev/build estavam incompletos e não continham fixture. GREEN: `npm run test:config` passou com 14 testes; asserção anterior foi restringida ao guia de deploy, pois README agora contém intencionalmente somente a fixture fictícia.

## Verificação

- Build Vite com API e URL de WhatsApp fictícias: passou.
- `npm run lint`: passou.
- Segundo follow-up: build com API localhost e fixture fictícia passou com 2.049 módulos; lint passou sem erros.
- `CHOKIDAR_USEPOLLING=true npm run test:e2e`: 9 passed.
- `docker compose config`: passou; arg do frontend contém fixture fictícia.
- Cópia do frontend em diretório temporário com espaço: build passou.
- `git diff --check`: passou.

## Limitação

`docker compose build frontend` não executou porque usuário atual não tem acesso ao socket Docker (`/var/run/docker.sock`). Compose está instalado e sua configuração foi validada.

## Segurança

Nenhum telefone ou token real foi lido, gravado ou incluído. Valor real continua fora do repositório, somente na interface da Vercel.
