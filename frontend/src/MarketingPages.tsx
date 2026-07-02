import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  LayoutDashboard,
  MessageCircle,
  Scissors,
  ShieldCheck,
  Users,
} from "lucide-react";
import {usePageMetadata} from "./metadata";
import "./marketing.css";

const features = [
  {icon: CalendarDays, title: "Agenda sem conflito", text: "Horários, bloqueios e duração de cada serviço organizados no mesmo fluxo."},
  {icon: MessageCircle, title: "Agendamento online", text: "Cliente escolhe serviço, data e horário pelo celular, sem depender de troca de mensagens."},
  {icon: Users, title: "Clientes e equipe", text: "Histórico da base, acesso por perfil e rotina da equipe em um painel simples."},
  {icon: LayoutDashboard, title: "Visão do negócio", text: "Faturamento, atendimentos, cancelamentos e horários procurados sempre à vista."},
];

function Brand() {
  return <a className="marketing-brand" href="/" aria-label="M&R BarberHub — início"><span><Scissors/></span><strong>M&amp;R BarberHub</strong></a>;
}

export function LandingPage() {
  usePageMetadata("M&R BarberHub | Gestão para barbearias", "Agenda, clientes, equipe e serviços em um painel feito para a rotina da barbearia.", "/");
  return <main className="marketing-shell">
    <header className="marketing-nav">
      <Brand/>
      <nav aria-label="Navegação principal"><a href="#recursos">Recursos</a><a href="#como-funciona">Como funciona</a><a href="#seguranca">Segurança</a></nav>
      <a className="marketing-login" href="/login">Acessar painel <ArrowRight/></a>
    </header>

    <section className="marketing-hero">
      <div className="hero-copy">
        <p className="marketing-kicker"><span/> Feito para a rotina da barbearia</p>
        <h1>Menos conversa perdida.<br/><em>Mais cadeira ocupada.</em></h1>
        <p className="hero-lead">Centralize agenda, clientes, equipe e serviços. Seu cliente marca pelo celular; você acompanha tudo em um painel direto.</p>
        <div className="hero-actions"><a className="marketing-primary" href="/agendar/bigodes">Ver agendamento <ArrowRight/></a><a className="marketing-secondary" href="/login">Entrar no sistema</a></div>
        <ul className="hero-checks"><li><CheckCircle2/> Sem conflito de horários</li><li><CheckCircle2/> Funciona no celular</li><li><CheckCircle2/> Dados separados por barbearia</li></ul>
      </div>

      <div className="product-preview" aria-label="Prévia do painel BarberHub">
        <div className="preview-top"><span className="preview-logo"><Scissors/></span><div><strong>Visão geral</strong><small>Resumo do dia</small></div><span className="preview-avatar">MR</span></div>
        <div className="preview-stats"><article><small>Atendimentos</small><strong>8</strong><span>Hoje</span></article><article><small>Faturamento</small><strong>R$ 315</strong><span>Confirmado</span></article></div>
        <div className="preview-agenda"><div className="preview-title"><strong>Próximos horários</strong><span>Hoje</span></div><div className="preview-row"><time>10:30</time><span><strong>Corte + Barba</strong><small>Cliente confirmado</small></span><i>Confirmado</i></div><div className="preview-row"><time>11:30</time><span><strong>Corte</strong><small>Agendamento online</small></span><i className="awaiting">Aguardando</i></div><div className="preview-row"><time>14:00</time><span><strong>Barba</strong><small>Cliente recorrente</small></span><i>Confirmado</i></div></div>
        <div className="preview-accent"/>
      </div>
    </section>

    <section className="marketing-strip" aria-label="Principais benefícios"><span>Agenda organizada</span><i/><span>Atendimento mais rápido</span><i/><span>Gestão sem planilha</span><i/><span>Experiência profissional</span></section>

    <section className="marketing-section" id="recursos">
      <div className="section-heading"><p className="marketing-kicker">Tudo no lugar certo</p><h2>Operação simples para quem precisa trabalhar.</h2><p>Ferramentas essenciais, sem transformar sua rotina em curso de software.</p></div>
      <div className="feature-grid">{features.map(({icon:Icon,title,text},index)=><article key={title}><span className="feature-number">0{index+1}</span><Icon/><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className="workflow-section" id="como-funciona">
      <div className="workflow-copy"><p className="marketing-kicker">Do clique à cadeira</p><h2>Agendar fica fácil para os dois lados.</h2><p>Cliente encontra um horário livre. Pedido entra na agenda. Equipe acompanha e confirma. Sem copiar dados de conversa para planilha.</p><a href="/agendar/bigodes">Testar fluxo público <ArrowRight/></a></div>
      <ol className="workflow-steps"><li><span>1</span><div><strong>Cliente escolhe serviço</strong><p>Preço e duração aparecem antes da reserva.</p></div></li><li><span>2</span><div><strong>Seleciona horário livre</strong><p>Agenda considera expediente, bloqueios e outros atendimentos.</p></div></li><li><span>3</span><div><strong>Equipe recebe o pedido</strong><p>Reserva fica centralizada e pronta para acompanhamento.</p></div></li></ol>
    </section>

    <section className="security-section" id="seguranca"><div className="security-icon"><ShieldCheck/></div><div><p className="marketing-kicker">Segurança desde a base</p><h2>Cada barbearia vê somente seus dados.</h2><p>Isolamento por estabelecimento, acesso por perfil, autenticação protegida, trilha de auditoria e verificação anti-bot no agendamento público.</p></div><ul><li><CheckCircle2/> Sessões protegidas</li><li><CheckCircle2/> Controle de acesso</li><li><CheckCircle2/> Auditoria de ações</li></ul></section>

    <section className="marketing-cta"><div><p className="marketing-kicker">Sua agenda merece clareza</p><h2>Abra o painel. Veja o dia. Comece a atender.</h2></div><a className="marketing-primary" href="/login">Acessar BarberHub <ArrowRight/></a></section>

    <footer className="marketing-footer"><Brand/><p>Produto da M&amp;R Solutions.</p><div><a href="/privacidade">Privacidade</a><a href="/login">Painel</a></div></footer>
  </main>;
}

export function PrivacyPage() {
  usePageMetadata("Privacidade | M&R BarberHub", "Entenda como os dados são usados no agendamento pelo M&R BarberHub.", "/privacidade");
  return <main className="privacy-page">
    <header><Brand/><a href="/">Voltar ao início</a></header>
    <article>
      <p className="marketing-kicker">Aviso de privacidade</p>
      <h1>Seus dados servem para cuidar do seu agendamento.</h1>
      <p className="privacy-updated">Atualizado em 2 de julho de 2026.</p>
      <section><h2>Dados utilizados</h2><p>Nome, WhatsApp, serviço escolhido, data e horário. Dados técnicos de segurança, como endereço IP, podem ser registrados para prevenir abuso.</p></section>
      <section><h2>Finalidade</h2><p>Criar, confirmar, lembrar e administrar seu atendimento; permitir cancelamento; proteger a agenda contra fraude e manter registros operacionais da barbearia.</p></section>
      <section><h2>Compartilhamento</h2><p>Os dados podem passar por fornecedores necessários à operação, como hospedagem, banco de dados, e-mail, WhatsApp e proteção anti-bot. Eles não são vendidos.</p></section>
      <section><h2>Prazo e proteção</h2><p>Registros são mantidos pelo tempo necessário à operação, segurança e obrigações legais. O sistema usa controle de acesso, separação entre barbearias e comunicação protegida por HTTPS.</p></section>
      <section><h2>Seus direitos</h2><p>Você pode pedir confirmação, acesso, correção ou exclusão aplicável dos dados. Entre em contato diretamente com a barbearia onde realizou o agendamento.</p></section>
      <section><h2>Responsabilidades</h2><p>A barbearia escolhida administra a relação com seus clientes. A M&amp;R Solutions fornece a tecnologia BarberHub para executar essa operação.</p></section>
    </article>
    <footer><a href="/">M&amp;R BarberHub</a><a href="/agendar/bigodes">Ir para agendamento</a></footer>
  </main>;
}
