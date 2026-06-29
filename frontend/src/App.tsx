import {zodResolver} from "@hookform/resolvers/zod";
import {useMutation, useQuery} from "@tanstack/react-query";
import {format} from "date-fns";
import {CalendarDays, LogOut, Scissors, Users} from "lucide-react";
import {useEffect, useRef, useState} from "react";
import {useForm} from "react-hook-form";
import {z} from "zod";
import api from "./api";

const loginSchema = z.object({username: z.string().min(1), password: z.string().min(8)});
type Login = z.infer<typeof loginSchema>;
const bookingSchema = z.object({name: z.string().min(2, "Informe seu nome"), whatsapp: z.string().min(10, "Informe seu WhatsApp")});
type Booking = z.infer<typeof bookingSchema>;

declare global { interface Window { turnstile?: {render: (element: HTMLElement, options: {sitekey: string; callback: (token: string) => void}) => string}; } }

function LoginPage({onLogin}: {onLogin: () => void}) {
  const {register, handleSubmit, formState: {errors}} = useForm<Login>({resolver: zodResolver(loginSchema)});
  const login = useMutation({mutationFn: (values: Login) => api.post("/auth/login/", values), onSuccess: ({data}) => {localStorage.setItem("access", data.access); localStorage.setItem("refresh", data.refresh); onLogin();}});
  return <main className="grid min-h-screen place-items-center p-5"><section className="card w-full max-w-md p-8"><div className="mb-8 flex items-center gap-3"><div className="rounded-xl bg-gold p-3 text-ink"><Scissors /></div><div><h1 className="text-2xl font-bold">SaaS dos Bigodes</h1><p className="text-sm text-zinc-400">Gestão simples. Agenda cheia.</p></div></div><form className="space-y-4" onSubmit={handleSubmit(v => login.mutate(v))}><label className="block text-sm">Usuário<input className="mt-2" {...register("username")} /></label><label className="block text-sm">Senha<input className="mt-2" type="password" {...register("password")} /></label>{(errors.password || login.error) && <p className="text-sm text-red-400">Confira seus dados e tente novamente.</p>}<button className="w-full bg-gold text-ink" disabled={login.isPending}>Entrar</button></form></section></main>;
}

function Dashboard({onLogout}: {onLogout: () => void}) {
  const {data} = useQuery({queryKey: ["dashboard"], queryFn: () => api.get("/dashboard/").then(r => r.data)});
  const cards = [{label: "Faturamento hoje", value: `R$ ${data?.daily_revenue ?? 0}`}, {label: "Faturamento mensal", value: `R$ ${data?.monthly_revenue ?? 0}`}, {label: "Atendimentos", value: data?.appointments ?? 0}, {label: "Cancelamentos", value: `${data?.cancellation_rate ?? 0}%`}];
  return <main className="mx-auto max-w-6xl p-5 md:p-10"><header className="mb-10 flex items-center justify-between"><div><p className="text-sm font-semibold uppercase tracking-[.25em] text-gold">Painel administrativo</p><h1 className="mt-2 text-3xl font-bold">Visão do negócio</h1></div><button className="flex gap-2 border border-zinc-700" onClick={onLogout}><LogOut size={18}/> Sair</button></header><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{cards.map(card => <article className="card" key={card.label}><p className="text-sm text-zinc-400">{card.label}</p><p className="mt-2 text-2xl font-bold text-gold">{card.value}</p></article>)}</section><section className="mt-8 grid gap-4 md:grid-cols-2"><article className="card"><CalendarDays className="mb-4 text-gold"/><h2 className="text-xl font-semibold">Agenda</h2><p className="mt-2 text-zinc-400">Controle horários, bloqueios e confirmações.</p></article><article className="card"><Users className="mb-4 text-gold"/><h2 className="text-xl font-semibold">Clientes</h2><p className="mt-2 text-zinc-400">Histórico e recorrência em um só lugar.</p></article></section></main>;
}

function PublicBooking({slug}: {slug: string}) {
  const [service, setService] = useState(""); const [day, setDay] = useState(format(new Date(), "yyyy-MM-dd")); const [slot, setSlot] = useState("");
  const [captcha, setCaptcha] = useState(""); const captchaRef = useRef<HTMLDivElement>(null);
  const {register, handleSubmit, formState: {errors}} = useForm<Booking>({resolver: zodResolver(bookingSchema)});
  const shop = useQuery({queryKey: ["shop", slug], queryFn: () => api.get(`/public/${slug}/`).then(r => r.data)});
  const services = useQuery({queryKey: ["public-services", slug], queryFn: () => api.get(`/public/${slug}/services/`).then(r => r.data)});
  const slots = useQuery({queryKey: ["slots", slug, service, day], enabled: !!service, queryFn: () => api.get(`/public/${slug}/availability/`, {params: {service_id: service, day}}).then(r => r.data.slots)});
  const booking = useMutation({mutationFn: (values: Booking) => api.post(`/public/${slug}/book/`, {name: values.name, whatsapp: values.whatsapp, service_id: Number(service), starts_at: slot, captcha_token: captcha})});
  useEffect(() => {const sitekey = import.meta.env.VITE_TURNSTILE_SITE_KEY; if (!sitekey) {setCaptcha("development"); return;} const script = document.createElement("script"); script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"; script.async = true; script.onload = () => {if (captchaRef.current && window.turnstile) window.turnstile.render(captchaRef.current, {sitekey, callback: setCaptcha});}; document.head.appendChild(script); return () => script.remove();}, []);
  if (booking.isSuccess) return <main className="grid min-h-screen place-items-center p-5"><section className="card max-w-md text-center"><div className="mx-auto mb-5 w-fit rounded-full bg-gold p-4 text-ink"><CalendarDays /></div><h1 className="text-2xl font-bold">Horário solicitado!</h1><p className="mt-3 text-zinc-400">Você receberá a confirmação pelo WhatsApp.</p></section></main>;
  return <main className="mx-auto min-h-screen max-w-xl p-5 pt-12"><p className="text-sm uppercase tracking-[.25em] text-gold">Agendamento online</p><h1 className="mt-3 text-3xl font-bold">{shop.data?.name ?? "Barbearia"}</h1><form className="card mt-8 space-y-5" onSubmit={handleSubmit(v => booking.mutate(v))}><label>Serviço<select className="mt-2" value={service} onChange={e => {setService(e.target.value); setSlot("");}}><option value="">Escolha</option>{services.data?.map((s: {id:number; name:string; price:string}) => <option key={s.id} value={s.id}>{s.name} — R$ {s.price}</option>)}</select></label><label>Data<input className="mt-2" type="date" min={format(new Date(), "yyyy-MM-dd")} value={day} onChange={e => {setDay(e.target.value); setSlot("");}} /></label><div><p className="mb-2">Horário</p><div className="grid grid-cols-3 gap-2">{slots.data?.map((s: string) => <button type="button" className={slot === s ? "bg-gold text-ink" : "border border-zinc-700"} onClick={() => setSlot(s)} key={s}>{format(new Date(s), "HH:mm")}</button>)}</div></div><label>Nome<input className="mt-2" {...register("name")} /></label><label>WhatsApp<input className="mt-2" inputMode="tel" {...register("whatsapp")} /></label>{(errors.name || errors.whatsapp || booking.error) && <p className="text-sm text-red-400">Revise os dados e tente novamente.</p>}<div ref={captchaRef}/><button className="w-full bg-gold text-ink" disabled={!service || !slot || !captcha || booking.isPending}>Confirmar agendamento</button></form></main>;
}

export default function App() {
  const parts = location.pathname.split("/").filter(Boolean);
  const [authenticated, setAuthenticated] = useState(!!localStorage.getItem("access"));
  if (parts[0] === "agendar" && parts[1]) return <PublicBooking slug={parts[1]} />;
  if (!authenticated) return <LoginPage onLogin={() => setAuthenticated(true)} />;
  return <Dashboard onLogout={() => {localStorage.clear(); setAuthenticated(false);}} />;
}
