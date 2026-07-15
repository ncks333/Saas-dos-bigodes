# M&R Solutions production readiness

## Objetivo

Publicar a landing M&R Solutions dentro do frontend já hospedado na Vercel,
preservando a página principal do M&R BarberHub e eliminando os bloqueios de
produção encontrados na revisão.

## URLs canônicas

- M&R BarberHub: `https://app.mrbarberhub.com.br/`
- M&R Solutions: `https://app.mrbarberhub.com.br/mr-solutions`
- Agendamento demonstrativo: `https://app.mrbarberhub.com.br/agendar/bigodes`

A Vercel deve reescrever acessos diretos a `/mr-solutions` para
`/index.html`, permitindo abrir, atualizar e compartilhar a rota sem erro 404.
A rota técnica `/demo/globe` não fará parte do produto publicado.

## Contato pelo WhatsApp

O CTA da M&R Solutions consumirá somente
`VITE_MR_SOLUTIONS_WHATSAPP_URL`. O número público real será configurado no
painel da Vercel e não será gravado no repositório.

Builds de produção devem falhar quando a variável estiver ausente, usar número
placeholder ou não tiver URL HTTPS no host `wa.me` com telefone em formato
internacional. O fallback de desenvolvimento, quando necessário aos testes,
não pode entrar no bundle de produção.

O número remetente das notificações Meta permanece configuração separada. A
variável Railway `WHATSAPP_PHONE_NUMBER_ID` recebe o ID numérico exibido pela
Meta, não o telefone em formato E.164.

## Visual, CSP e acessibilidade

A textura atual do globo continuará externa para evitar copiar um ativo de
origem/licença não documentada. A CSP permitirá somente o host R2 exato já
usado pelo componente. Nenhum curinga adicional será aberto.

A animação do globo respeitará `prefers-reduced-motion`, sem alterar a aparência
normal. O componente técnico de demonstração será removido; o globo usado pela
landing continuará disponível.

## Limpeza e escopo

- Remover a dependência `motion` se continuar sem importação.
- Não publicar assets de logo sem referência no produto final.
- Não incluir `dist`, `node_modules` nem alteração gerada de
  `tsconfig.tsbuildinfo` no commit.
- Preservar as alterações visuais existentes, os logos realmente usados, as
  páginas do BarberHub e os fluxos de login/agendamento.
- Metadata social estática específica da M&R Solutions fica fora deste rollout;
  a metadata dinâmica existente continua atendendo navegação no navegador.

## Validação

Testes devem provar:

- a rota `/mr-solutions` existe no app e no rewrite da Vercel;
- o build de produção rejeita WhatsApp ausente, placeholder ou host inválido;
- o CTA usa exatamente a variável validada;
- a CSP permite o host da textura e continua restrita;
- não existe rota pública `/demo/globe`;
- reduced motion desliga a animação do globo;
- build, ESLint e suíte Playwright completa passam.

Depois do deploy, um smoke test real deve abrir e recarregar
`https://app.mrbarberhub.com.br/mr-solutions`, confirmar o globo sem violação de
CSP e verificar o CTA apontando para o número público configurado na Vercel.
