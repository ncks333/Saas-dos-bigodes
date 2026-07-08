import {
  ArrowRight,
  Armchair,
  BarChart3,
  Boxes,
  CalendarDays,
  Check,
  CheckCircle2,
  Crown,
  DollarSign,
  Package,
  Scissors,
  ShieldCheck,
  Star,
  UserRound,
  Users,
} from "lucide-react";
import {usePageMetadata} from "./metadata";
import "./marketing.css";

const trustLogos = ["BLACK", "STUDIO7", "THE BROTHERS", "ALFA", "DIMENZZO"];

const benefits = [
  {icon: CalendarDays, title: "Mais tempo para o que importa", text: "Automação que elimina tarefas manuais."},
  {icon: Users, title: "Organização completa", text: "Agenda, clientes, serviços e equipe integrados."},
  {icon: BarChart3, title: "Mais controle, mais lucro", text: "Relatórios e financeiro para decisões inteligentes."},
  {icon: Crown, title: "Clientes mais satisfeitos", text: "Experiência rápida e profissional do agendamento ao pós."},
];

const productFeatures = [
  {icon: CalendarDays, title: "Agenda inteligente"},
  {icon: UserRound, title: "Clientes e histórico"},
  {icon: ShieldCheck, title: "Serviços e preços"},
  {icon: Users, title: "Equipe e comissões"},
  {icon: DollarSign, title: "Financeiro completo"},
  {icon: BarChart3, title: "Relatórios avançados"},
  {icon: Package, title: "Estoque e produtos"},
  {icon: Boxes, title: "Permissões"},
];

const results = [
  {value: "+35%", label: "Aumento médio no faturamento"},
  {value: "-80%", label: "Menos faltas com lembretes automáticos"},
  {value: "2x", label: "Mais agilidade na gestão do dia a dia"},
  {value: "+50 mil", label: "Agendamentos realizados por mês"},
];

const testimonials = [
  {name: "Rafael Lima", shop: "The Brothers Barber Shop", text: "BarberHub mudou completamente nossa barbearia. Hoje temos controle total e mais organização."},
  {name: "Lucas Martins", shop: "Studio7 Barber Club", text: "A agenda inteligente acabou com as falhas e aumentou nosso faturamento em poucos meses."},
  {name: "Thiago Alves", shop: "Dimenzzo Barbearia", text: "Sistema completo, fácil de usar e feito para barbeiro. Recomendo demais."},
];

const plans = [
  {name: "Básico", price: "79", description: "Ideal para barbearias pequenas.", featured: false, items: ["Agenda online", "Clientes ilimitados", "Relatórios básicos", "Suporte via chat"]},
  {name: "Profissional", price: "129", description: "Para barbearias que querem crescer.", featured: true, items: ["Tudo do Básico", "Financeiro completo", "Comissões e equipe", "Relatórios avançados"]},
  {name: "Premium", price: "199", description: "Para redes e barbearias com alto volume.", featured: false, items: ["Tudo do Profissional", "Multiunidades", "Permissões avançadas", "Suporte prioritário"]},
];

function Brand() {
  return <a className="marketing-brand" href="/" aria-label="M&R BarberHub — início"><BrandMark/><strong>M&amp;R BarberHub</strong></a>;
}

function BrandMark() {
  return <span className="brand-symbol" aria-hidden="true"><Armchair/><Scissors/></span>;
}

export function LandingPage() {
  usePageMetadata("M&R BarberHub | Gestão para barbearias", "Agenda, clientes, equipe e serviços em um painel feito para a rotina da barbearia.", "/");
  return <main className="marketing-shell">
    <header className="marketing-nav">
      <Brand/>
      <nav aria-label="Navegação principal"><a href="#recursos">Recursos</a><a href="#sistema">Como funciona</a><a href="#precos">Preços</a><a href="#depoimentos">Depoimentos</a></nav>
      <a className="marketing-login" href="/login">Acessar painel <ArrowRight/></a>
    </header>

    <section className="marketing-hero">
      <div className="hero-copy">
        <p className="marketing-kicker"><span/> Feito para a rotina da barbearia</p>
        <h1>Menos conversa perdida.<br/><em>Mais cadeira ocupada.</em></h1>
        <p className="hero-lead">Centralize agenda, clientes, equipe e serviços. Seu cliente marca pelo celular; você acompanha tudo em um painel direto.</p>
        <div className="hero-actions"><a className="marketing-primary" href="/agendar/bigodes">Ver agendamento <ArrowRight/></a><a className="marketing-secondary" href="/login">Fazer teste grátis</a></div>
        <ul className="hero-checks"><li><CheckCircle2/> Sem conflito de horários</li><li><CheckCircle2/> Funciona no celular</li><li><CheckCircle2/> Dados separados por barbearia</li></ul>
      </div>

      <div className="product-preview" aria-label="Prévia do painel BarberHub">
        <div className="preview-top"><span className="preview-logo"><BrandMark/></span><div><strong>Visão geral</strong><small>Resumo do dia</small></div><span className="preview-avatar">MR</span></div>
        <div className="preview-stats"><article><small>Atendimentos</small><strong>23</strong><span>Hoje</span></article><article><small>Faturamento</small><strong>R$ 2.840</strong><span>Hoje</span></article></div>
        <div className="preview-agenda"><div className="preview-title"><strong>Próximos horários</strong><span>Hoje</span></div><div className="preview-row"><time>10:30</time><span><strong>Corte + Barba</strong><small>Cliente confirmado</small></span><i>Confirmado</i></div><div className="preview-row"><time>11:30</time><span><strong>Corte</strong><small>Agendamento online</small></span><i className="awaiting">Aguardando</i></div><div className="preview-row"><time>14:00</time><span><strong>Barba</strong><small>Cliente recorrente</small></span><i>Confirmado</i></div></div>
        <div className="preview-accent"/>
      </div>
    </section>

    <section className="trusted-strip" aria-label="Barbearias que confiam">
      <p>Barbearias que confiam</p>
      <div>{trustLogos.map(logo => <strong key={logo}>{logo}<small>Barbershop</small></strong>)}</div>
    </section>

    <section className="marketing-section" id="recursos">
      <div className="section-heading centered"><p className="marketing-kicker">Tudo que sua barbearia precisa em um só lugar</p></div>
      <div className="benefit-grid">{benefits.map(({icon:Icon,title,text})=><article key={title}><Icon/><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className="system-section" id="sistema">
      <div className="system-copy"><p className="marketing-kicker">Sistema feito para barbeiros reais</p><h2>Interface simples, poderosa e pensada para a rotina da barbearia.</h2><p>Do agendamento ao financeiro, tudo conectado. Acesse de qualquer lugar, no computador ou celular.</p><a className="marketing-primary" href="/login">Conhecer o sistema <ArrowRight/></a></div>
      <div className="device-showcase" aria-label="Dashboard em notebook e celular">
        <div className="laptop-frame">
          <div className="dashboard-screen">
            <aside>{["Agenda", "Clientes", "Serviços", "Financeiro", "Relatórios"].map(item => <span key={item}>{item}</span>)}</aside>
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
      <p className="marketing-kicker">Recursos que transformam a rotina</p>
      <div>{productFeatures.map(({icon:Icon,title}) => <article key={title}><Icon/><span>{title}</span></article>)}</div>
    </section>

    <section className="results-section" aria-label="Resultados">
      <p className="marketing-kicker">Resultados que você sente no dia a dia</p>
      <div>{results.map(item => <article key={item.value}><strong>{item.value}</strong><span>{item.label}</span></article>)}</div>
    </section>

    <section className="testimonial-section" id="depoimentos">
      <p className="marketing-kicker">Quem usa, recomenda</p>
      <div>{testimonials.map(testimonial => <article key={testimonial.name}><div className="stars">{Array.from({length: 5}).map((_, index) => <Star key={index}/>)}</div><p>"{testimonial.text}"</p><footer><span>{testimonial.name.charAt(0)}</span><div><strong>{testimonial.name}</strong><small>{testimonial.shop}</small></div></footer></article>)}</div>
    </section>

    <section className="pricing-section" id="precos">
      <p className="marketing-kicker">Planos para barbearias de todos os tamanhos</p>
      <div>{plans.map(plan => <article key={plan.name} className={plan.featured ? "featured" : undefined}>{plan.featured && <small className="plan-badge">Mais escolhido</small>}<h3>{plan.name}</h3><p><strong>R$ {plan.price}</strong>/mês</p><span>{plan.description}</span><ul>{plan.items.map(item => <li key={item}><Check/>{item}</li>)}</ul><a href="/login">Começar agora</a></article>)}</div>
    </section>

    <section className="marketing-cta"><div><h2>Pronto para transformar sua barbearia?</h2><p>Teste grátis por 7 dias. Sem cartão de crédito.</p></div><a className="marketing-primary" href="/login">Começar teste grátis <ArrowRight/></a></section>

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
