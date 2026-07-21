import {useMutation, useQuery} from "@tanstack/react-query";
import axios from "axios";
import {CalendarCheck2, CheckCircle2, CircleAlert, Clock3, CreditCard, Mail, Scissors} from "lucide-react";
import {FormEvent, useEffect, useRef, useState} from "react";
import api from "./api";
import {usePageMetadata} from "./metadata";
import "./billing.css";

export type Plan = {code: string; name: string; amount: string; currency: string; trial_days: number};

declare global {
  interface Window {
    turnstile?: {render: (element: HTMLElement, options: {sitekey: string; callback: (token: string) => void}) => string};
  }
}

const money = (amount: string, currency = "BRL") => Number(amount).toLocaleString("pt-BR", {style: "currency", currency});
const slugify = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
const errorMessage = (error: unknown) => {
  if (error instanceof Error) return error.message;
  if (!axios.isAxiosError(error)) return "Não foi possível concluir esta etapa. Tente novamente.";
  const detail = error.response?.data?.detail ?? error.response?.data?.message;
  if (typeof detail === "string") return detail;
  return error.response?.status === 503 ? "Checkout indisponível. Tente novamente." : "Revise os dados e tente novamente.";
};

function useCurrentPlan() {
  return useQuery({queryKey: ["current-plan"], queryFn: () => api.get<Plan>("/billing/plans/current/").then(response => response.data)});
}

function safeCheckoutTarget(checkoutUrl: string) {
  try {
    if (typeof checkoutUrl !== "string") throw new Error("unsafe target");
    const target = new URL(checkoutUrl, window.location.origin);
    if (target.protocol !== "http:" && target.protocol !== "https:") throw new Error("unsafe protocol");
    return target.href;
  } catch {
    throw new Error("Link de pagamento inválido. Tente novamente.");
  }
}

function redirectToCheckout(checkoutUrl: string) {
  window.location.href = safeCheckoutTarget(checkoutUrl);
}

function BillingBrand() {
  return <a className="billing-brand" href="/" aria-label="M&R BarberHub — início"><img src="/barberhub-icon-v2.png" alt=""/><strong><span>M&amp;R</span> Barber<span>Hub</span></strong></a>;
}

function PlanReceipt({plan}: {plan: Plan}) {
  return <aside className="plan-receipt" aria-label="Resumo da assinatura">
    <div className="plan-receipt-heading"><span>Seu plano</span><strong>{plan.name}</strong></div>
    <div className="plan-price"><small>Depois do período grátis</small><strong>{money(plan.amount, plan.currency)}</strong><span>/mês</span></div>
    <ol className="billing-agenda-rail" aria-label="Linha do tempo da assinatura">
      <li><CalendarCheck2/><div><strong>Hoje</strong><span>Crie sua agenda e vá ao checkout.</span></div></li>
      <li><Clock3/><div><strong>{plan.trial_days} dias grátis</strong><span>Use o painel sem cobrança neste período.</span></div></li>
      <li><CreditCard/><div><strong>Primeira mensalidade</strong><span>{money(plan.amount, plan.currency)} após confirmação do provedor.</span></div></li>
    </ol>
  </aside>;
}

function BillingShell({children}: {children: React.ReactNode}) {
  return <main className="billing-shell"><header className="billing-header"><BillingBrand/><a href="/login">Já sou cliente</a></header>{children}</main>;
}

function StatusMessage({children}: {children: React.ReactNode}) {
  return <p className="billing-message" role="alert"><CircleAlert/>{children}</p>;
}

export function SignupPage() {
  usePageMetadata("Começar teste grátis | M&R BarberHub", "Crie a agenda da sua barbearia e comece 30 dias grátis.", "/cadastro");
  const planQuery = useCurrentPlan();
  const [firstName, setFirstName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [barbershopName, setBarbershopName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [whatsapp, setWhatsapp] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY;
  const [captchaToken, setCaptchaToken] = useState(siteKey ? "" : import.meta.env.DEV ? "development" : "");
  const captchaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!siteKey) return;
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () => {
      if (captchaRef.current && window.turnstile) window.turnstile.render(captchaRef.current, {sitekey: siteKey, callback: setCaptchaToken});
    };
    document.head.appendChild(script);
    return () => script.remove();
  }, [siteKey]);

  const signup = useMutation({
    mutationFn: async () => {
      if (!planQuery.data) throw new Error("Plano indisponível. Atualize a página e tente novamente.");
      const {data} = await api.post<{checkout_url: string}>("/billing/signup/", {
        first_name: firstName,
        email,
        username,
        password,
        barbershop_name: barbershopName,
        slug,
        whatsapp,
        plan_code: planQuery.data.code,
        captcha_token: captchaToken,
        terms_accepted: termsAccepted,
      });
      redirectToCheckout(data.checkout_url);
    },
  });
  const updateBarbershopName = (value: string) => {
    setBarbershopName(value);
    if (!slugEdited) setSlug(slugify(value));
  };
  const submit = (event: FormEvent) => { event.preventDefault(); signup.mutate(); };
  const plan = planQuery.data;

  return <BillingShell><section className="billing-intro"><p>Agenda pronta para trabalhar</p><h1>Comece sua agenda. <em>O primeiro corte é grátis.</em></h1><span>Sem cobrar hoje. Confirme o checkout com o provedor antes de liberar o painel.</span></section><div className="signup-layout"><form className="billing-card signup-form" onSubmit={submit}>
    <div className="billing-card-heading"><span>Cadastro da barbearia</span><h2>Leva poucos minutos.</h2><p>Campos com * são obrigatórios.</p></div>
    {planQuery.isLoading && <p className="billing-loading" role="status">Carregando condições do plano...</p>}
    {planQuery.isError && <StatusMessage>Não foi possível carregar plano. Atualize a página e tente novamente.</StatusMessage>}
    <div className="billing-form-grid">
      <label>Nome *<input required autoComplete="given-name" value={firstName} onChange={event => setFirstName(event.target.value)}/></label>
      <label>E-mail *<input required type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)}/></label>
      <label>Usuário *<input required minLength={3} autoComplete="username" value={username} onChange={event => setUsername(event.target.value)}/></label>
      <label>Senha *<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)}/></label>
      <label className="billing-full">Nome da barbearia *<input required autoComplete="organization" value={barbershopName} onChange={event => updateBarbershopName(event.target.value)}/></label>
      <label className="billing-full">Endereço público *<span className="slug-input"><b>/agendar/</b><input required pattern="[a-z0-9-]+" value={slug} onChange={event => {setSlugEdited(true); setSlug(slugify(event.target.value));}} aria-describedby="slug-help"/></span><small id="slug-help">Você pode editar este endereço antes de continuar.</small></label>
      <label className="billing-full">WhatsApp *<input required minLength={10} inputMode="tel" autoComplete="tel" value={whatsapp} onChange={event => setWhatsapp(event.target.value)} placeholder="11999999999"/></label>
    </div>
    <label className="billing-check"><input required type="checkbox" checked={termsAccepted} onChange={event => setTermsAccepted(event.target.checked)}/><span>Li e aceito os <a href="/privacidade" target="_blank" rel="noreferrer">termos e aviso de privacidade</a>.</span></label>
    <div ref={captchaRef}/>
    {signup.error && <StatusMessage>{errorMessage(signup.error)}</StatusMessage>}
    <button className="billing-primary" type="submit" disabled={!plan || !captchaToken || !termsAccepted || signup.isPending} aria-label="Começar 30 dias grátis — continuar para pagamento">{signup.isPending ? "Preparando checkout..." : `Começar ${plan?.trial_days ?? ""} dias grátis`}</button>
    <p className="billing-provider-note">Você será levado ao checkout seguro. Acesso só libera após confirmação do provedor.</p>
  </form>{plan && <PlanReceipt plan={plan}/>}</div></BillingShell>;
}

const checkoutCopy = {
  "/checkout/concluido": {eyebrow: "Checkout recebido", title: "Pagamento em confirmação.", text: "Seu acesso espera a confirmação do provedor de pagamento. Assim que ela chegar, sua agenda estará pronta.", icon: CheckCircle2},
  "/checkout/cancelado": {eyebrow: "Checkout cancelado", title: "Nenhuma cobrança foi concluída.", text: "Seu acesso espera a confirmação do provedor de pagamento. Volte ao checkout quando quiser continuar.", icon: CircleAlert},
  "/checkout/expirado": {eyebrow: "Checkout expirado", title: "Esse link não está mais ativo.", text: "Seu acesso espera a confirmação do provedor de pagamento. Gere um novo checkout para continuar.", icon: Clock3},
} as const;

export function CheckoutStatusPage({path}: {path: keyof typeof checkoutCopy}) {
  const copy = checkoutCopy[path];
  usePageMetadata(`${copy.title} | M&R BarberHub`, copy.text, path);
  const Icon = copy.icon;
  return <BillingShell><section className="billing-state"><div className="billing-state-icon"><Icon/></div><p>{copy.eyebrow}</p><h1>{copy.title}</h1><span>{copy.text}</span><a className="billing-primary" href={path === "/checkout/concluido" ? "/login" : "/cadastro"}>{path === "/checkout/concluido" ? "Ir para login" : "Começar 30 dias grátis"}</a><a className="billing-secondary-link" href="/">Voltar ao início</a></section></BillingShell>;
}

export function RegularizationPage() {
  usePageMetadata("Regularizar assinatura | M&R BarberHub", "Solicite instruções ou regularize sua assinatura com segurança.", "/regularizar");
  const token = new URLSearchParams(window.location.search).get("token");
  const [email, setEmail] = useState("");
  const request = useMutation({mutationFn: () => api.post<{message: string}>("/billing/regularization/request/", {email}).then(response => response.data)});
  const checkout = useMutation({mutationFn: async () => {
    if (!token) throw new Error("Token inválido ou expirado.");
    const {data} = await api.post<{checkout_url: string}>("/billing/regularization/checkout/", {token});
    redirectToCheckout(data.checkout_url);
  }});

  return <BillingShell><section className="billing-state billing-regularization"><div className="billing-state-icon"><Scissors/></div><p>Assinatura bloqueada</p><h1>{token ? "Regularize para voltar à agenda." : "Vamos encontrar sua assinatura."}</h1><span>{token ? "Abra checkout seguro. Seu acesso só volta depois da confirmação do provedor." : "Informe e-mail administrativo. Se houver pendência, enviaremos instruções para regularizar."}</span>
    {token ? <><button className="billing-primary" type="button" onClick={() => checkout.mutate()} disabled={checkout.isPending}>{checkout.isPending ? "Preparando checkout..." : "Regularizar assinatura"}</button>{checkout.error && <StatusMessage>{errorMessage(checkout.error)}</StatusMessage>}</> : <form className="billing-email-form" onSubmit={event => {event.preventDefault(); request.mutate();}}><label>E-mail<input required type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)}/></label><button className="billing-primary" disabled={request.isPending}>{request.isPending ? "Enviando..." : "Enviar instruções"}</button>{request.isSuccess && <p className="billing-success" role="status"><Mail/> {request.data.message}</p>}{request.error && <StatusMessage>{errorMessage(request.error)}</StatusMessage>}</form>}
  </section></BillingShell>;
}
