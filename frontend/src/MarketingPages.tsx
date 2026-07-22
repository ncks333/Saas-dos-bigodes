import {useQuery} from "@tanstack/react-query";
import {type CSSProperties, useEffect, useState} from "react";
import {
  ArrowRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  MessageCircle,
  MonitorSmartphone,
  Scissors,
  Settings,
  UserRound,
  Workflow,
} from "lucide-react";
import Globe from "@/components/ui/globe";
import type {Plan} from "./BillingPages";
import api from "./api";
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

const solutionsServices = [
  {icon: MonitorSmartphone, title: "Sites e produtos digitais", text: "Landing pages, sites institucionais e interfaces web com foco em clareza, confiança e conversão."},
  {icon: Workflow, title: "Automações", text: "Fluxos para atendimento, agenda, avisos e tarefas repetitivas que hoje dependem de controle manual."},
  {icon: ClipboardCheck, title: "Consultoria digital", text: "Diagnóstico de ferramentas, processos e prioridades para transformar operação confusa em rotina organizada."},
];

const solutionsSignals = ["Sites", "Sistemas", "Automações", "Consultoria digital"];

const solutionsProblems = [
  "Processos importantes dependem de planilhas, mensagens soltas e memória da equipe.",
  "Clientes chegam pelo WhatsApp, Instagram ou indicação, mas não existe fluxo claro para atender e vender.",
  "Ideias de produto ficam paradas porque falta transformar necessidade real em sistema simples de usar.",
];

const processSteps = [
  {title: "Entender operação", text: "Mapeamos objetivo, gargalos, público e urgência antes de sugerir tecnologia."},
  {title: "Desenhar solução", text: "Definimos escopo enxuto, telas principais, integrações e caminho de lançamento."},
  {title: "Construir e ajustar", text: "Entregamos versão funcional, medimos uso real e evoluímos com prioridade."},
];

const shootingStars = [
  {left: "66%", delay: "-1.4s", duration: "5.8s", top: "8%"},
  {left: "82%", delay: "-5.1s", duration: "6.4s", top: "16%"},
  {left: "72%", delay: "-3.9s", duration: "6.7s", top: "28%"},
  {left: "92%", delay: "-8.2s", duration: "7.1s", top: "42%"},
  {left: "78%", delay: "-2.7s", duration: "6.2s", top: "58%"},
  {left: "88%", delay: "-5.4s", duration: "7.2s", top: "72%"},
];

const mrWhatsappUrl = import.meta.env.VITE_MR_SOLUTIONS_WHATSAPP_URL;
const money = (amount: string, currency: string) => Number(amount).toLocaleString("pt-BR", {style: "currency", currency});
const useLandingPlan = () => useQuery({queryKey: ["current-plan"], queryFn: () => api.get<Plan>("/billing/plans/current/").then(response => response.data)});

function Brand() {
  return <a className="marketing-brand" href="/" aria-label="M&R BarberHub — início"><BrandMark/><strong><span>M&amp;R</span> Barber<span>Hub</span></strong></a>;
}

function BrandMark() {
  return <span className="brand-symbol" aria-hidden="true"><img src="/barberhub-icon-v2.png" alt=""/></span>;
}

function SolutionsBrand() {
  return <a className="solutions-brand" href="/mr-solutions" aria-label="M&R Solutions — início">
    <img src="/mr-solutions-logo-compact-cutout.png" alt="M&R Solutions"/>
  </a>;
}

function useSolutionsReveal() {
  useEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>(".solutions-reveal"));
    if (!items.length) return;

    const reveal = (element: HTMLElement) => element.classList.add("is-visible");
    if (!("IntersectionObserver" in window)) {
      items.forEach(reveal);
      return;
    }

    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        reveal(entry.target as HTMLElement);
        observer.unobserve(entry.target);
      });
    }, {rootMargin: "0px 0px -12% 0px", threshold: 0.18});

    items.forEach(item => observer.observe(item));
    return () => observer.disconnect();
  }, []);
}

function useSolutionsHeaderScroll(offset = 10) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > offset);
    onScroll();
    window.addEventListener("scroll", onScroll, {passive: true});
    return () => window.removeEventListener("scroll", onScroll);
  }, [offset]);
  return scrolled;
}

export function MRSolutionsPage() {
  usePageMetadata("M&R Solutions | Sistemas, sites e automações", "Sistemas, sites e automações para empresas que querem operar melhor.", "/mr-solutions");
  useSolutionsReveal();
  const navScrolled = useSolutionsHeaderScroll();
  return <main className="solutions-shell">
    <div className="solutions-sky" aria-hidden="true">
      {shootingStars.map((star, index) => <span
        className="shooting-star"
        key={index}
        style={{
          "--star-left": star.left,
          "--star-delay": star.delay,
          "--star-duration": star.duration,
          "--star-top": star.top,
        } as CSSProperties}
      />)}
    </div>
    <header className={navScrolled ? "solutions-nav is-scrolled" : "solutions-nav"}>
      <SolutionsBrand/>
      <nav aria-label="Navegação M&R Solutions"><a href="#servicos">Serviços</a><a href="#case">BarberHub</a><a href="#processo">Processo</a></nav>
      <a className="solutions-whatsapp" href={mrWhatsappUrl} target="_blank" rel="noreferrer"><MessageCircle/> Contato</a>
    </header>

    <section className="solutions-hero solutions-reveal">
      <div className="solutions-hero-copy solutions-reveal">
        <p className="solutions-kicker">M&amp;R Solutions</p>
        <h1>Sistemas, sites e automações para empresas que querem operar melhor.</h1>
        <p>A M&amp;R Solutions cria soluções digitais sob medida para organizar processos, melhorar atendimento e transformar ideias em produto.</p>
        <div className="solutions-actions">
          <a className="solutions-primary" href={mrWhatsappUrl} target="_blank" rel="noreferrer"><MessageCircle/> Conversar sobre meu projeto</a>
          <a className="solutions-secondary" href="#servicos">Ver serviços</a>
        </div>
        <div className="solutions-trust" aria-label="Áreas de atuação">{solutionsSignals.map((item, index) => <span style={{"--delay": `${index * 80}ms`} as CSSProperties} key={item}>{item}</span>)}</div>
      </div>
      <aside className="solutions-hero-mark solutions-reveal" aria-label="Identidade M&R Solutions">
        <div className="solutions-orbit" aria-label="Globo digital M&R Solutions">
          <Globe fullScreen={false} size={300}/>
          <span className="hero-symbol" aria-hidden="true"/>
        </div>
        <img className="hero-logo" src="/mr-solutions-logo-full-cutout.png" alt="M&R Solutions"/>
        <div className="hero-note">
          <span>Empresa em construção pública</span>
          <strong>Projetos selecionados em preparação</strong>
        </div>
      </aside>
    </section>

    <section className="solutions-problems solutions-reveal" aria-label="Problemas que resolvemos">
      <div><p className="solutions-kicker">O que resolvemos</p><h2>Quando a operação cresce no improviso, tecnologia vira necessidade.</h2></div>
      <ul>{solutionsProblems.map((item, index) => <li style={{"--delay": `${index * 90}ms`} as CSSProperties} key={item}><CheckCircle2/>{item}</li>)}</ul>
    </section>

    <section className="solutions-services solutions-reveal" id="servicos" aria-label="Serviços M&R Solutions">
      <div className="solutions-section-heading"><p className="solutions-kicker">Serviços</p><h2>Três frentes para tirar a ideia do papel e colocar a operação em ordem.</h2></div>
      <div className="solutions-service-grid">{solutionsServices.map(({icon: Icon, title, text}, index) => <article style={{"--delay": `${index * 100}ms`} as CSSProperties} key={title}>
        <Icon/>
        <h3>{title}</h3>
        <p>{text}</p>
      </article>)}</div>
    </section>

    <section className="solutions-case solutions-reveal" id="case">
      <div className="case-copy">
        <p className="solutions-kicker">Prova real</p>
        <h2>BarberHub nasceu como produto próprio da M&amp;R.</h2>
        <p>Um SaaS para barbearias com agendamento online, painel administrativo, clientes, serviços, notificações e operação multiempresa.</p>
        <a href="/" className="solutions-text-link">Conhecer BarberHub <ArrowRight/></a>
      </div>
      <div className="case-panel" aria-label="Resumo do BarberHub">
        <span>Produto próprio</span>
        <strong>Agendamento, gestão e atendimento no mesmo fluxo.</strong>
        <div><b>Agenda online</b><b>Painel SaaS</b><b>Multiempresa</b></div>
      </div>
    </section>

    <section className="solutions-process solutions-reveal" id="processo">
      <div className="solutions-section-heading"><p className="solutions-kicker">Processo</p><h2>Como começamos</h2></div>
      <div>{processSteps.map((step, index) => <article style={{"--delay": `${index * 100}ms`} as CSSProperties} key={step.title}>
        <span>{String(index + 1).padStart(2, "0")}</span>
        <h3>{step.title}</h3>
        <p>{step.text}</p>
      </article>)}</div>
    </section>

    <section className="solutions-final solutions-reveal">
      <p className="solutions-kicker">Próximo passo</p>
      <h2>Conte o que sua empresa precisa organizar, vender ou automatizar.</h2>
      <a className="solutions-primary" href={mrWhatsappUrl} target="_blank" rel="noreferrer"><MessageCircle/> Conversar sobre meu projeto</a>
    </section>

    <footer className="solutions-footer">
      <SolutionsBrand/>
      <span>Projetos selecionados em preparação</span>
      <a href={mrWhatsappUrl} target="_blank" rel="noreferrer">WhatsApp</a>
    </footer>
  </main>;
}

export function LandingPage() {
  usePageMetadata("M&R BarberHub | Gestão para barbearias", "Agenda, clientes, equipe e serviços em um painel feito para a rotina da barbearia.", "/");
  const plan = useLandingPlan();
  const currentPlan = plan.data;
  const trialLabel = currentPlan ? `${currentPlan.trial_days} dias grátis` : "teste grátis";
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
        <div className="hero-actions"><a className="marketing-primary" href="/cadastro">Começar {trialLabel} <ArrowRight/></a><a className="marketing-secondary" href="/login">Já sou cliente</a></div>
        <ul className="hero-checks"><li><CheckCircle2/> Sem conflito de horários</li><li><CheckCircle2/> Funciona no celular</li><li><CheckCircle2/> Dados separados por barbearia</li></ul>
      </div>

      <div className="product-preview" aria-label="Prévia do painel BarberHub">
        <div className="preview-top"><span className="preview-logo"><BrandMark/></span><div><strong>Visão geral</strong><small>Resumo do dia</small></div><span className="preview-avatar">MR</span></div>
        <div className="preview-stats"><article><small>Atendimentos</small><strong>23</strong><span>Hoje</span></article><article><small>Faturamento</small><strong>R$ 2.840</strong><span>Hoje</span></article></div>
        <div className="preview-agenda"><div className="preview-title"><strong>Próximos horários</strong><span>Hoje</span></div><div className="preview-row"><time>10:30</time><span><strong>Corte + Barba</strong><small>Cliente confirmado</small></span><i>Confirmado</i></div><div className="preview-row"><time>11:30</time><span><strong>Corte</strong><small>Agendamento online</small></span><i className="awaiting">Aguardando</i></div><div className="preview-row"><time>14:00</time><span><strong>Barba</strong><small>Cliente recorrente</small></span><i>Confirmado</i></div></div>
        <div className="preview-accent"/>
      </div>
    </section>

    <section className="landing-pricing" aria-labelledby="pricing-title">
      <div><p className="marketing-kicker">Plano direto para sua rotina</p><h2 id="pricing-title">Agenda, clientes e equipe no mesmo lugar.</h2><p>Comece sem cobrança hoje. Valor e período grátis vêm do plano publicado pelo servidor.</p></div>
      <div className="landing-price-card">{plan.isLoading ? <p role="status">Carregando plano...</p> : plan.isError || !currentPlan ? <p role="alert">Plano indisponível. Atualize a página e tente novamente.</p> : <><span>{currentPlan.name}</span><strong>{money(currentPlan.amount, currentPlan.currency)}</strong><small>por mês, depois de {currentPlan.trial_days} dias grátis</small><a className="marketing-primary" href="/cadastro">Começar {currentPlan.trial_days} dias grátis <ArrowRight/></a></>}</div>
    </section>

    <section className="marketing-section" id="recursos">
      <div className="section-heading centered"><p className="marketing-kicker">Tudo que sua barbearia precisa em um só lugar</p></div>
      <div className="benefit-grid">{benefits.map(({icon:Icon,title,text})=><article key={title}><Icon/><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className="system-section" id="sistema">
      <div className="system-copy"><p className="marketing-kicker">Sistema em uso</p><h2>Interface simples para agenda, clientes e serviços.</h2><p>O painel reúne a rotina da barbearia em telas diretas: visão geral, atendimentos, cadastro de clientes, serviços e horários de funcionamento.</p><a className="marketing-primary" href="/cadastro">Começar {trialLabel} <ArrowRight/></a></div>
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
      <a className="marketing-primary" href="/cadastro">Começar {trialLabel} <ArrowRight/></a>
    </section>

    <section className="marketing-cta"><div><h2>Abra o BarberHub e acompanhe a rotina.</h2><p>Use o painel para gerenciar agenda, clientes, serviços e configurações da barbearia.</p></div><a className="marketing-primary" href="/cadastro">Começar {trialLabel} <ArrowRight/></a></section>

    <footer className="marketing-footer"><Brand/><p>Produto da <a href="/mr-solutions">M&amp;R Solutions</a>.</p><div><a href="/privacidade">Privacidade</a><a href="/login">Painel</a></div></footer>
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
