import {
  ArrowRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Scissors,
  Settings,
  UserRound,
} from "lucide-react";
import {usePageMetadata} from "./metadata";
import "./marketing.css";

const benefits = [
  {icon: CalendarDays, title: "Agenda organizada", text: "Horários, bloqueios e duração de serviços no mesmo fluxo."},
  {icon: UserRound, title: "Clientes em ordem", text: "Histórico da base para acompanhar quem já passou pela barbearia."},
  {icon: Scissors, title: "Serviços e preços", text: "Cadastro dos atendimentos com duração, valor e status ativo."},
  {icon: BarChart3, title: "Resumo do dia", text: "Faturamento, atendimentos e horários mais procurados à vista."},
];

const productFeatures = [
  {icon: BarChart3, title: "Visão geral"},
  {icon: CalendarDays, title: "Agenda"},
  {icon: UserRound, title: "Clientes e histórico"},
  {icon: Scissors, title: "Serviços"},
  {icon: Settings, title: "Configurações"},
  {icon: CalendarDays, title: "Agendamento público"},
];

function Brand() {
  return <a className="marketing-brand" href="/" aria-label="M&R BarberHub — início"><BrandMark/><strong><span>M&amp;R</span> Barber<span>Hub</span></strong></a>;
}

function BrandMark() {
  return <span className="brand-symbol" aria-hidden="true">
    <svg viewBox="0 0 48 48" role="img">
      <path className="chair-fill" d="M8 24c0-1.3 1-2.3 2.3-2.3h5.1c1.3 0 2.3 1 2.3 2.3v12.8c0 1.3-1 2.3-2.3 2.3h-5.1A2.3 2.3 0 0 1 8 36.8V24Z"/>
      <path className="chair-fill" d="M30.3 24c0-1.3 1-2.3 2.3-2.3h5.1c1.3 0 2.3 1 2.3 2.3v12.8c0 1.3-1 2.3-2.3 2.3h-5.1c-1.3 0-2.3-1-2.3-2.3V24Z"/>
      <path className="chair-fill" d="M16 30c0-1.6 1.3-2.9 2.9-2.9h10.2c1.6 0 2.9 1.3 2.9 2.9v3H16v-3Z"/>
      <rect className="chair-fill" x="18.2" y="34.8" width="11.6" height="4.5" rx="1.5"/>
      <path className="chair-fill" d="M20 41h8v3h-8z"/>
      <path className="chair-fill" d="M14 38h20v3H14z"/>
      <path className="scissor-stroke" d="m15 10 18 18"/>
      <path className="scissor-stroke" d="m33 10-18 18"/>
      <circle className="scissor-stroke" cx="15" cy="28" r="3.3"/>
      <circle className="scissor-stroke" cx="33" cy="28" r="3.3"/>
    </svg>
  </span>;
}

export function LandingPage() {
  usePageMetadata("M&R BarberHub | Gestão para barbearias", "Agenda, clientes, equipe e serviços em um painel feito para a rotina da barbearia.", "/");
  return <main className="marketing-shell">
    <header className="marketing-nav">
      <Brand/>
      <nav aria-label="Navegação principal"><a href="#recursos">Recursos</a><a href="#sistema">Sistema</a><a href="#agendamento">Agendamento</a></nav>
      <a className="marketing-login" href="/login">Acessar painel <ArrowRight/></a>
    </header>

    <section className="marketing-hero">
      <div className="hero-copy">
        <p className="marketing-kicker"><span/> Feito para a rotina da barbearia</p>
        <h1>Menos conversa perdida.<br/><em>Mais cadeira ocupada.</em></h1>
        <p className="hero-lead">Centralize agenda, clientes, equipe e serviços. Seu cliente marca pelo celular; você acompanha tudo em um painel direto.</p>
        <div className="hero-actions"><a className="marketing-primary" href="/agendar/bigodes">Ver agendamento <ArrowRight/></a><a className="marketing-secondary" href="/login">Acessar painel</a></div>
        <ul className="hero-checks"><li><CheckCircle2/> Sem conflito de horários</li><li><CheckCircle2/> Funciona no celular</li><li><CheckCircle2/> Dados separados por barbearia</li></ul>
      </div>

      <div className="product-preview" aria-label="Prévia do painel BarberHub">
        <div className="preview-top"><span className="preview-logo"><BrandMark/></span><div><strong>Visão geral</strong><small>Resumo do dia</small></div><span className="preview-avatar">MR</span></div>
        <div className="preview-stats"><article><small>Atendimentos</small><strong>23</strong><span>Hoje</span></article><article><small>Faturamento</small><strong>R$ 2.840</strong><span>Hoje</span></article></div>
        <div className="preview-agenda"><div className="preview-title"><strong>Próximos horários</strong><span>Hoje</span></div><div className="preview-row"><time>10:30</time><span><strong>Corte + Barba</strong><small>Cliente confirmado</small></span><i>Confirmado</i></div><div className="preview-row"><time>11:30</time><span><strong>Corte</strong><small>Agendamento online</small></span><i className="awaiting">Aguardando</i></div><div className="preview-row"><time>14:00</time><span><strong>Barba</strong><small>Cliente recorrente</small></span><i>Confirmado</i></div></div>
        <div className="preview-accent"/>
      </div>
    </section>

    <section className="marketing-section" id="recursos">
      <div className="section-heading centered"><p className="marketing-kicker">Tudo que sua barbearia precisa em um só lugar</p></div>
      <div className="benefit-grid">{benefits.map(({icon:Icon,title,text})=><article key={title}><Icon/><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className="system-section" id="sistema">
      <div className="system-copy"><p className="marketing-kicker">Sistema em uso</p><h2>Interface simples para agenda, clientes e serviços.</h2><p>O painel reúne a rotina da barbearia em telas diretas: visão geral, atendimentos, cadastro de clientes, serviços e horários de funcionamento.</p><a className="marketing-primary" href="/login">Acessar painel <ArrowRight/></a></div>
      <div className="device-showcase" aria-label="Dashboard em notebook e celular">
        <div className="laptop-frame">
          <div className="dashboard-screen">
            <aside>{["Visão geral", "Agenda", "Clientes", "Serviços", "Configurações"].map(item => <span key={item}>{item}</span>)}</aside>
            <section>
              <div className="screen-header"><strong>Dashboard</strong><i/></div>
              <div className="chart-bars">{Array.from({length: 14}).map((_, index) => <span key={index} style={{height: `${34 + (index % 5) * 11}px`}}/>)}</div>
              <div className="screen-cards"><b/><b/><b/><b/></div>
            </section>
          </div>
        </div>
        <div className="phone-frame">
          <div className="phone-screen"><span>Hoje</span><strong>23 horários</strong><i/><i/><i/></div>
        </div>
      </div>
    </section>

    <section className="feature-band" aria-label="Recursos do sistema">
      <p className="marketing-kicker">Recursos disponíveis no sistema</p>
      <div>{productFeatures.map(({icon:Icon,title}) => <article key={title}><Icon/><span>{title}</span></article>)}</div>
    </section>

    <section className="booking-section" id="agendamento">
      <div><p className="marketing-kicker">Agendamento público</p><h2>Cliente escolhe serviço, data e horário pelo celular.</h2><p>O fluxo público já existe em <strong>/agendar/bigodes</strong> e envia a reserva para a agenda do painel.</p></div>
      <a className="marketing-primary" href="/agendar/bigodes">Ver agendamento <ArrowRight/></a>
    </section>

    <section className="marketing-cta"><div><h2>Abra o BarberHub e acompanhe a rotina.</h2><p>Use o painel para gerenciar agenda, clientes, serviços e configurações da barbearia.</p></div><a className="marketing-primary" href="/login">Acessar painel <ArrowRight/></a></section>

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
