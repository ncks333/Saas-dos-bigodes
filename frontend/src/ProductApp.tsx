import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import axios from "axios";
import {format} from "date-fns";
import {
  CalendarDays, CalendarX, ChevronLeft, ChevronRight, Clock3, LayoutDashboard, LogOut, Menu, Plus, Save,
  Scissors, Search, Settings, Trash2, UserCog, Users, X,
} from "lucide-react";
import {FormEvent, ReactNode, useEffect, useRef, useState} from "react";
import api from "./api";
import {usePageMetadata} from "./metadata";

type Role = "ADMIN" | "FUNCIONARIO";
type SessionUser = {id: number; name: string; role: Role};
type PageName = "dashboard" | "appointments" | "customers" | "services" | "users" | "blocks" | "settings";
type ApiPage<T> = {results: T[]; count: number};
type Customer = {id: number; name: string; whatsapp: string; notes: string; active: boolean};
type Service = {id: number; name: string; description: string; price: string; duration_minutes: number; active: boolean};
type Employee = {id: number; username: string; email: string; first_name: string; last_name: string; role: Role; is_active: boolean};
type Appointment = {id: number; customer: number; customer_name: string; service: number; service_name: string; employee: number | null; starts_at: string; ends_at: string; notes: string; status: string; source: string};
type Block = {id: number; starts_at: string; ends_at: string; reason: string};
type OperatingHour = {id: number; weekday: number; opens_at: string; closes_at: string; active: boolean};
type Shop = {id: number; name: string; slug: string; whatsapp: string; timezone: string; active: boolean; operating_hours: OperatingHour[]};

const statuses = [
  ["PENDENTE", "Pendente"], ["AGUARDANDO_CONFIRMACAO", "Aguardando"], ["CONFIRMADO", "Confirmado"],
  ["CONCLUIDO", "Concluído"], ["CANCELADO", "Cancelado"], ["NAO_COMPARECEU", "Não compareceu"],
] as const;
const weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const listOf = <T,>(data?: ApiPage<T> | T[]): T[] => Array.isArray(data) ? data : data?.results ?? [];
async function fetchAll<T>(path: string, params?: Record<string, unknown>): Promise<T[]> {
  let next: string | null = path;
  let first = true;
  const items: T[] = [];
  while (next) {
    const response: {data: ApiPage<T> | T[]} = await api.get<ApiPage<T> | T[]>(next, first ? {params} : undefined);
    if (Array.isArray(response.data)) return [...items, ...response.data];
    items.push(...response.data.results);
    next = (response.data as ApiPage<T> & {next?: string | null}).next ?? null;
    first = false;
  }
  return items;
}
const dateTimeLocal = (value: string) => value ? format(new Date(value), "yyyy-MM-dd'T'HH:mm") : "";
const toIso = (value: string) => new Date(value).toISOString();
const money = (value: string | number) => Number(value).toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
const findErrorMessage = (value: unknown): string | null => {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = findErrorMessage(item);
      if (message) return message;
    }
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["details", "detail", "message", "msg", "error"]) {
      const message = findErrorMessage(record[key]);
      if (message) return message;
    }
    for (const item of Object.values(record)) {
      const message = findErrorMessage(item);
      if (message) return message;
    }
  }
  return null;
};
const errorText = (error: unknown) => {
  if (!axios.isAxiosError(error)) return "Não foi possível concluir a operação.";
  if (!error.response) return "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.";
  if (error.response.status >= 500) return "Serviço temporariamente indisponível. Tente novamente em instantes.";
  return findErrorMessage(error.response?.data) ?? "Revise os dados e tente novamente.";
};
const loginErrorText = (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    return "Usuário ou senha inválidos.";
  }
  return errorText(error);
};

function Button({children, variant = "primary", ...props}: React.ButtonHTMLAttributes<HTMLButtonElement> & {variant?: "primary" | "secondary" | "danger" | "ghost"}) {
  return <button {...props} className={`btn btn-${variant} ${props.className ?? ""}`}>{children}</button>;
}
function Empty({children}: {children: ReactNode}) { return <div className="empty"><CalendarX/><p>{children}</p></div>; }
function Loading() { return <div className="loading"><span/><span/><span/></div>; }
function Badge({status}: {status: string}) {
  const label = statuses.find(([key]) => key === status)?.[1] ?? status;
  return <span className={`badge badge-${status.toLowerCase()}`}>{label}</span>;
}
function Modal({title, children, onClose}: {title: string; children: ReactNode; onClose: () => void}) {
  useEffect(() => { const close = (e: KeyboardEvent) => e.key === "Escape" && onClose(); addEventListener("keydown", close); return () => removeEventListener("keydown", close); }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><section className="modal"><header><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X/></button></header>{children}</section></div>;
}
function DatePicker({value,onChange}:{value:string;onChange:(value:string)=>void}) {
  const selected=new Date(`${value}T12:00:00`); const [open,setOpen]=useState(false); const [month,setMonth]=useState(()=>new Date(selected.getFullYear(),selected.getMonth(),1));
  const today=new Date(); today.setHours(0,0,0,0);
  const first=new Date(month.getFullYear(),month.getMonth(),1); const gridStart=new Date(first); gridStart.setDate(first.getDate()-first.getDay());
  const days=Array.from({length:42},(_,index)=>{const date=new Date(gridStart);date.setDate(gridStart.getDate()+index);return date});
  const choose=(date:Date)=>{onChange(format(date,"yyyy-MM-dd"));setOpen(false)};
  return <div className="public-date-picker"><button className="public-date-trigger" type="button" onClick={()=>setOpen(true)} aria-label="Escolher data"><CalendarDays/><span>{selected.toLocaleDateString("pt-BR",{weekday:"long",day:"2-digit",month:"long"})}</span></button>{open&&<Modal title="Escolha a data" onClose={()=>setOpen(false)}><div className="calendar-picker"><div className="calendar-month"><button type="button" className="icon-btn" aria-label="Mês anterior" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()-1,1))}><ChevronLeft/></button><strong>{month.toLocaleDateString("pt-BR",{month:"long",year:"numeric"})}</strong><button type="button" className="icon-btn" aria-label="Próximo mês" onClick={()=>setMonth(new Date(month.getFullYear(),month.getMonth()+1,1))}><ChevronRight/></button></div><div className="calendar-weekdays">{["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"].map(day=><span key={day}>{day}</span>)}</div><div className="calendar-days">{days.map(date=>{const key=format(date,"yyyy-MM-dd");const disabled=date<today;const outside=date.getMonth()!==month.getMonth();const active=key===value;return <button type="button" key={key} disabled={disabled} className={`${outside?"outside ":""}${active?"active":""}`} aria-label={date.toLocaleDateString("pt-BR",{day:"numeric",month:"long",year:"numeric"})} onClick={()=>choose(date)}>{date.getDate()}</button>})}</div></div></Modal>}</div>;
}
function PageHeader({title, description, action}: {title: string; description: string; action?: ReactNode}) {
  return <header className="page-header"><div><h1>{title}</h1><p>{description}</p></div>{action}</header>;
}
function ErrorMessage({error}: {error: unknown}) { return error ? <p className="form-error">{errorText(error)}</p> : null; }
function AppBrandMark() { return <div className="brand-mark"><img src="/barberhub-icon-v2.png" alt=""/></div>; }

function LoginPage({onLogin}: {onLogin: (user: SessionUser) => void}) {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const login = useMutation({mutationFn: () => api.post("/auth/login/", {username, password}), onSuccess: ({data}) => {
    localStorage.setItem("access", data.access); localStorage.setItem("refresh", data.refresh);
    localStorage.setItem("user", JSON.stringify(data.user)); onLogin(data.user);
  }});
  return <main className="login-shell"><section className="login-copy"><AppBrandMark/><p className="eyebrow">M&amp;R BarberHub</p><h1>Sua barbearia organizada.<br/><span>Seu tempo de volta.</span></h1><p>Agenda, clientes, equipe e serviços em um painel simples de usar.</p><p className="company-credit">Um produto <strong>M&amp;R Solutions</strong></p></section><section className="login-card"><a className="back-link" href="/">Voltar ao site</a><h2>Bem-vindo</h2><p>Entre para administrar sua barbearia.</p><form onSubmit={e => {e.preventDefault(); login.mutate();}}><label>Usuário<input autoComplete="username" autoFocus value={username} onChange={e => setUsername(e.target.value)}/></label><label>Senha<input autoComplete="current-password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Sua senha"/></label><a className="forgot-link" href="/recuperar-senha">Esqueci minha senha</a>{login.error && <p className="form-error">{loginErrorText(login.error)}</p>}<Button disabled={!username || password.length < 8 || login.isPending}>{login.isPending ? "Entrando..." : "Entrar"}</Button></form><p className="company-credit login-credit">Tecnologia por <strong>M&amp;R Solutions</strong></p></section></main>;
}

const navItems: {page: PageName; label: string; icon: typeof CalendarDays; admin?: boolean}[] = [
  {page: "dashboard", label: "Visão geral", icon: LayoutDashboard}, {page: "appointments", label: "Agenda", icon: CalendarDays},
  {page: "customers", label: "Clientes", icon: Users}, {page: "services", label: "Serviços", icon: Scissors},
  {page: "users", label: "Equipe", icon: UserCog, admin: true}, {page: "blocks", label: "Bloqueios", icon: CalendarX},
  {page: "settings", label: "Configurações", icon: Settings, admin: true},
];
function Shell({user, page, setPage, onLogout, children}: {user: SessionUser; page: PageName; setPage: (p: PageName) => void; onLogout: () => void; children: ReactNode}) {
  const [open, setOpen] = useState(false);
  return <div className="app-shell"><aside className={open ? "sidebar open" : "sidebar"}><div className="sidebar-brand"><AppBrandMark/><div><strong><span>M&amp;R</span> Barber<span>Hub</span></strong><small>Gestão de barbearias</small></div><button className="icon-btn mobile-only" onClick={() => setOpen(false)}><X/></button></div><nav>{navItems.filter(i => !i.admin || user.role === "ADMIN").map(item => <button key={item.page} className={page === item.page ? "active" : ""} onClick={() => {setPage(item.page); setOpen(false);}}><item.icon/>{item.label}</button>)}</nav><div className="sidebar-user"><div className="avatar">{(user.name || "A").charAt(0)}</div><div><strong>{user.name || "Administrador"}</strong><small>{user.role === "ADMIN" ? "Administrador" : "Funcionário"}</small></div><button title="Sair" className="icon-btn" onClick={onLogout}><LogOut/></button></div></aside><main className="content"><button className="mobile-menu icon-btn" onClick={() => setOpen(true)}><Menu/></button>{children}</main></div>;
}

function DashboardPage({go}: {go: (p: PageName) => void}) {
  const dashboard = useQuery({queryKey: ["dashboard"], queryFn: () => api.get("/dashboard/").then(r => r.data), refetchInterval: 30_000});
  const summary = useQuery({queryKey: ["daily-summary"], queryFn: () => api.get("/appointments/daily_summary/").then(r => r.data), refetchInterval: 30_000});
  if (dashboard.isLoading) return <Loading/>;
  const d = dashboard.data ?? {}; const s = summary.data ?? {};
  const remainingToday = (s.confirmed ?? 0) + (s.pending ?? 0) + (s.awaiting ?? 0);
  return <><PageHeader title="Visão geral" description={`Resumo de ${format(new Date(), "dd/MM/yyyy")}`} action={<div className="header-actions"><Button variant="secondary" onClick={() => {dashboard.refetch(); summary.refetch();}} disabled={dashboard.isFetching || summary.isFetching}>Atualizar</Button><Button onClick={() => go("appointments")}><Plus/> Novo agendamento</Button></div>}/><section className="stats"><article><span>Faturamento hoje</span><strong>{money(d.daily_revenue ?? 0)}</strong><small>{s.completed ?? 0} concluídos</small></article><article><span>Faturamento no mês</span><strong>{money(d.monthly_revenue ?? 0)}</strong><small>Receita confirmada</small></article><article><span>Atendimentos restantes</span><strong>{remainingToday}</strong><small>de {s.total ?? 0} registros hoje</small></article><article><span>Taxa de cancelamento</span><strong>{d.cancellation_rate ?? 0}%</strong><small>{s.cancelled ?? 0} hoje</small></article></section><section className="dashboard-grid"><article className="panel"><h2>Resumo de hoje</h2><div className="summary-list"><div><span>Aguardando</span><strong>{s.awaiting ?? 0}</strong></div><div><span>Confirmados</span><strong>{s.confirmed ?? 0}</strong></div><div><span>Pendentes</span><strong>{s.pending ?? 0}</strong></div><div><span>Concluídos</span><strong>{s.completed ?? 0}</strong></div><div><span>Cancelados</span><strong>{s.cancelled ?? 0}</strong></div><div><span>Não compareceu</span><strong>{s.no_show ?? 0}</strong></div></div></article><article className="panel"><h2>Horários mais procurados</h2>{d.popular_hours?.length ? <div className="ranking">{d.popular_hours.map((x: {hour: number; total: number}, i: number) => <div key={x.hour}><span>{String(x.hour).padStart(2, "0")}:00</span><div style={{width: `${Math.max(12, 100 - i * 16)}%`}}/><strong>{x.total}</strong></div>)}</div> : <Empty>Ainda não há dados suficientes.</Empty>}</article></section></>;
}

function CustomersPage() {
  const qc = useQueryClient(); const [search, setSearch] = useState(""); const [editing, setEditing] = useState<Partial<Customer> | null>(null);
  const query = useQuery({queryKey: ["customers", search], queryFn: () => fetchAll<Customer>("/customers/", {search})});
  const save = useMutation({mutationFn: (d: Partial<Customer>) => d.id ? api.patch(`/customers/${d.id}/`, d) : api.post("/customers/", d), onSuccess: () => {qc.invalidateQueries({queryKey: ["customers"]}); setEditing(null);}});
  const remove = useMutation({mutationFn: (id: number) => api.delete(`/customers/${id}/`), onSuccess: () => qc.invalidateQueries({queryKey: ["customers"]})});
  return <><PageHeader title="Clientes" description="Cadastro e histórico da sua base de clientes." action={<Button onClick={() => setEditing({name: "", whatsapp: "", notes: "", active: true})}><Plus/> Novo cliente</Button>}/><SearchBox value={search} setValue={setSearch} placeholder="Buscar por nome ou WhatsApp"/>{query.isLoading ? <Loading/> : listOf(query.data).length ? <div className="table-wrap"><table><thead><tr><th>Cliente</th><th>WhatsApp</th><th>Status</th><th/></tr></thead><tbody>{listOf(query.data).map(c => <tr key={c.id}><td><strong>{c.name}</strong><small>{c.notes || "Sem observações"}</small></td><td>{c.whatsapp}</td><td><span className={c.active ? "active-dot" : "inactive-dot"}>{c.active ? "Ativo" : "Inativo"}</span></td><td className="actions"><button onClick={() => setEditing(c)}>Editar</button><button className="danger-link" onClick={() => confirm(`Desativar ${c.name}?`) && remove.mutate(c.id)}>Desativar</button></td></tr>)}</tbody></table></div> : <Empty>Nenhum cliente encontrado.</Empty>}{editing && <CustomerForm value={editing} save={save} close={() => setEditing(null)}/>}</>;
}
function CustomerForm({value, save, close}: {value: Partial<Customer>; save: ReturnType<typeof useMutation<unknown, Error, Partial<Customer>>>; close: () => void}) {
  const [d, setD] = useState(value); return <Modal title={d.id ? "Editar cliente" : "Novo cliente"} onClose={close}><form className="form-grid" onSubmit={e => {e.preventDefault(); save.mutate(d);}}><label className="full">Nome<input required value={d.name ?? ""} onChange={e => setD({...d, name: e.target.value})}/></label><label className="full">WhatsApp<input required value={d.whatsapp ?? ""} onChange={e => setD({...d, whatsapp: e.target.value})} placeholder="11999999999"/></label><label className="full">Observações<textarea rows={3} value={d.notes ?? ""} onChange={e => setD({...d, notes: e.target.value})}/></label><Toggle checked={d.active ?? true} setChecked={active => setD({...d, active})}>Cliente ativo</Toggle><ErrorMessage error={save.error}/><div className="form-actions full"><Button type="button" variant="secondary" onClick={close}>Cancelar</Button><Button disabled={save.isPending}><Save/> Salvar</Button></div></form></Modal>;
}

function ServicesPage() {
  const qc = useQueryClient(); const [editing, setEditing] = useState<Partial<Service> | null>(null);
  const query = useQuery({queryKey: ["services"], queryFn: () => fetchAll<Service>("/services/")});
  const save = useMutation({mutationFn: (d: Partial<Service>) => d.id ? api.patch(`/services/${d.id}/`, d) : api.post("/services/", d), onSuccess: () => {qc.invalidateQueries({queryKey: ["services"]}); setEditing(null);}});
  const remove = useMutation({mutationFn: (id: number) => api.delete(`/services/${id}/`), onSuccess: () => qc.invalidateQueries({queryKey: ["services"]})});
  return <><PageHeader title="Serviços" description="Defina preços e duração dos atendimentos." action={<Button onClick={() => setEditing({name: "", description: "", price: "", duration_minutes: 30, active: true})}><Plus/> Novo serviço</Button>}/>{query.isLoading ? <Loading/> : <div className="cards-grid">{listOf(query.data).map(s => <article className="resource-card" key={s.id}><div className="resource-icon"><Scissors/></div><div><h3>{s.name}</h3><p>{s.description || "Sem descrição"}</p></div><div className="resource-meta"><strong>{money(s.price)}</strong><span><Clock3/> {s.duration_minutes} min</span></div><div className="card-actions"><button onClick={() => setEditing(s)}>Editar</button><button onClick={() => confirm(`Desativar ${s.name}?`) && remove.mutate(s.id)}>Desativar</button></div></article>)}</div>}{!query.isLoading && !listOf(query.data).length && <Empty>Nenhum serviço cadastrado.</Empty>}{editing && <ServiceForm value={editing} save={save} close={() => setEditing(null)}/>}</>;
}
function ServiceForm({value, save, close}: {value: Partial<Service>; save: ReturnType<typeof useMutation<unknown, Error, Partial<Service>>>; close: () => void}) {
  const [d, setD] = useState(value); return <Modal title={d.id ? "Editar serviço" : "Novo serviço"} onClose={close}><form className="form-grid" onSubmit={e => {e.preventDefault(); save.mutate(d);}}><label className="full">Nome<input required value={d.name ?? ""} onChange={e => setD({...d, name: e.target.value})}/></label><label>Preço (R$)<input required type="number" min="0" step="0.01" value={d.price ?? ""} onChange={e => setD({...d, price: e.target.value})}/></label><label>Duração (minutos)<input required type="number" min="5" step="5" value={d.duration_minutes ?? 30} onChange={e => setD({...d, duration_minutes: Number(e.target.value)})}/></label><label className="full">Descrição<textarea rows={3} value={d.description ?? ""} onChange={e => setD({...d, description: e.target.value})}/></label><Toggle checked={d.active ?? true} setChecked={active => setD({...d, active})}>Disponível para agendamento</Toggle><ErrorMessage error={save.error}/><div className="form-actions full"><Button type="button" variant="secondary" onClick={close}>Cancelar</Button><Button disabled={save.isPending}><Save/> Salvar</Button></div></form></Modal>;
}

function AppointmentsPage({role}: {role: Role}) {
  const qc = useQueryClient(); const [editing, setEditing] = useState<Partial<Appointment> | null>(null); const [day, setDay] = useState(format(new Date(), "yyyy-MM-dd"));
  const appointments = useQuery({queryKey: ["appointments"], queryFn: () => fetchAll<Appointment>("/appointments/", {ordering: "-starts_at"})});
  const customers = useQuery({queryKey: ["customers-options"], queryFn: () => fetchAll<Customer>("/customers/", {active: true})});
  const services = useQuery({queryKey: ["services-options"], queryFn: () => fetchAll<Service>("/services/", {active: true})});
  const employees = useQuery({queryKey: ["users-options"], enabled: role === "ADMIN", queryFn: () => fetchAll<Employee>("/users/")});
  const refreshReports = () => {qc.invalidateQueries({queryKey: ["dashboard"]}); qc.invalidateQueries({queryKey: ["daily-summary"]});};
  const save = useMutation({mutationFn: (d: Partial<Appointment>) => {const payload = {...d, starts_at: d.starts_at ? toIso(d.starts_at) : undefined}; return d.id ? api.patch(`/appointments/${d.id}/`, payload) : api.post("/appointments/", payload);}, onSuccess: () => {qc.invalidateQueries({queryKey: ["appointments"]}); refreshReports(); setEditing(null);}});
  const status = useMutation({mutationFn: ({id, status}: {id: number; status: string}) => api.patch(`/appointments/${id}/`, {status}), onSuccess: () => {qc.invalidateQueries({queryKey: ["appointments"]}); refreshReports();}});
  const cancel = useMutation({mutationFn: (id: number) => api.post(`/appointments/${id}/cancel/`), onSuccess: () => {qc.invalidateQueries({queryKey: ["appointments"]}); refreshReports();}});
  const all = listOf(appointments.data); const shown = all.filter(a => format(new Date(a.starts_at), "yyyy-MM-dd") === day);
  const canCancel = (a: Appointment) => ["PENDENTE", "CONFIRMADO", "AGUARDANDO_CONFIRMACAO"].includes(a.status);
  return <><PageHeader title="Agenda" description="Acompanhe e gerencie todos os atendimentos." action={<Button onClick={() => setEditing({customer: undefined, service: undefined, employee: null, starts_at: `${day}T09:00`, status: "PENDENTE", notes: ""})}><Plus/> Novo agendamento</Button>}/><div className="toolbar"><label>Data<input type="date" value={day} onChange={e => setDay(e.target.value)}/></label><span>{shown.length} atendimento(s)</span></div><ErrorMessage error={status.error || cancel.error}/>{appointments.isLoading ? <Loading/> : shown.length ? <div className="agenda-list">{shown.sort((a,b) => a.starts_at.localeCompare(b.starts_at)).map(a => <article key={a.id}><time>{format(new Date(a.starts_at), "HH:mm")}<small>{format(new Date(a.ends_at), "HH:mm")}</small></time><div className="agenda-main"><strong>{a.customer_name}</strong><span>{a.service_name} · {a.source === "ONLINE" ? "Online" : "Manual"}</span>{a.notes && <small>{a.notes}</small>}</div><select aria-label="Status" value={a.status} disabled={status.isPending || cancel.isPending} onChange={e => status.mutate({id: a.id, status: e.target.value})}>{statuses.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select><Badge status={a.status}/><div className="agenda-actions"><button title="Editar agendamento" onClick={() => setEditing({...a, starts_at: dateTimeLocal(a.starts_at)})}><Settings/> Editar</button>{canCancel(a) && <button className="cancel-action" title="Cancelar agendamento" onClick={() => confirm(`Cancelar o horário de ${a.customer_name}?`) && cancel.mutate(a.id)}><Trash2/> Cancelar</button>}</div></article>)}</div> : <Empty>Nenhum atendimento nesta data.</Empty>}{editing && <AppointmentForm value={editing} customers={listOf(customers.data)} services={listOf(services.data)} employees={listOf(employees.data)} save={save} close={() => setEditing(null)}/>}</>;
}
function AppointmentForm({value, customers, services, employees, save, close}: {value: Partial<Appointment>; customers: Customer[]; services: Service[]; employees: Employee[]; save: ReturnType<typeof useMutation<unknown, Error, Partial<Appointment>>>; close: () => void}) {
  const [d, setD] = useState(value); return <Modal title={d.id ? "Editar agendamento" : "Novo agendamento"} onClose={close}><form className="form-grid" onSubmit={e => {e.preventDefault(); save.mutate(d);}}><label>Cliente<select required value={d.customer ?? ""} onChange={e => setD({...d, customer: Number(e.target.value)})}><option value="">Selecione</option>{customers.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Serviço<select required value={d.service ?? ""} onChange={e => setD({...d, service: Number(e.target.value)})}><option value="">Selecione</option>{services.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Data e horário<input required type="datetime-local" value={d.starts_at ?? ""} onChange={e => setD({...d, starts_at: e.target.value})}/></label><label>Profissional<select value={d.employee ?? ""} onChange={e => setD({...d, employee: e.target.value ? Number(e.target.value) : null})}><option value="">Sem preferência</option>{employees.filter(x => x.is_active).map(x => <option key={x.id} value={x.id}>{x.first_name || x.username}</option>)}</select></label><label className="full">Status<select value={d.status ?? "PENDENTE"} onChange={e => setD({...d, status: e.target.value})}>{statuses.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label className="full">Observações<textarea rows={3} value={d.notes ?? ""} onChange={e => setD({...d, notes: e.target.value})}/></label><ErrorMessage error={save.error}/><div className="form-actions full"><Button type="button" variant="secondary" onClick={close}>Cancelar</Button><Button disabled={save.isPending}><Save/> Salvar</Button></div></form></Modal>;
}

function UsersPage() {
  const qc = useQueryClient(); const [editing, setEditing] = useState<Partial<Employee> & {password?: string} | null>(null);
  const query = useQuery({queryKey: ["users"], queryFn: () => fetchAll<Employee>("/users/")});
  const save = useMutation({mutationFn: (d: Partial<Employee> & {password?: string}) => d.id ? api.patch(`/users/${d.id}/`, d) : api.post("/users/", d), onSuccess: () => {qc.invalidateQueries({queryKey: ["users"]}); setEditing(null);}});
  return <><PageHeader title="Equipe" description="Gerencie o acesso dos profissionais ao sistema." action={<Button onClick={() => setEditing({username: "", email: "", first_name: "", last_name: "", role: "FUNCIONARIO", is_active: true, password: ""})}><Plus/> Novo usuário</Button>}/>{query.isLoading ? <Loading/> : <div className="cards-grid">{listOf(query.data).map(u => <article className="person-card" key={u.id}><div className="avatar large">{(u.first_name || u.username)[0].toUpperCase()}</div><div><h3>{`${u.first_name} ${u.last_name}`.trim() || u.username}</h3><p>@{u.username} · {u.email}</p><span className={u.is_active ? "active-dot" : "inactive-dot"}>{u.role === "ADMIN" ? "Administrador" : "Funcionário"}</span></div><button onClick={() => setEditing(u)}>Editar</button></article>)}</div>}{editing && <UserForm value={editing} save={save} close={() => setEditing(null)}/>}</>;
}
function UserForm({value, save, close}: {value: Partial<Employee> & {password?: string}; save: ReturnType<typeof useMutation<unknown, Error, Partial<Employee> & {password?: string}>>; close: () => void}) {
  const [d, setD] = useState(value); return <Modal title={d.id ? "Editar usuário" : "Novo usuário"} onClose={close}><form className="form-grid" onSubmit={e => {e.preventDefault(); save.mutate(d);}}><label>Nome<input value={d.first_name ?? ""} onChange={e => setD({...d, first_name: e.target.value})}/></label><label>Sobrenome<input value={d.last_name ?? ""} onChange={e => setD({...d, last_name: e.target.value})}/></label><label>Usuário<input required value={d.username ?? ""} onChange={e => setD({...d, username: e.target.value})}/></label><label>E-mail<input required type="email" value={d.email ?? ""} onChange={e => setD({...d, email: e.target.value})}/></label><label>Perfil<select value={d.role ?? "FUNCIONARIO"} onChange={e => setD({...d, role: e.target.value as Role})}><option value="FUNCIONARIO">Funcionário</option><option value="ADMIN">Administrador</option></select></label><label>{d.id ? "Nova senha (opcional)" : "Senha"}<input required={!d.id} minLength={d.id ? undefined : 8} pattern={d.password ? "(?=.*[a-z])(?=.*[A-Z])(?=.*\\d).{8,}" : undefined} title="Use ao menos 8 caracteres, com letra maiúscula, minúscula e número." type="password" value={d.password ?? ""} onChange={e => setD({...d, password: e.target.value})}/><small>8+ caracteres, com maiúscula, minúscula e número.</small></label><Toggle checked={d.is_active ?? true} setChecked={is_active => setD({...d, is_active})}>Acesso ativo</Toggle><ErrorMessage error={save.error}/><div className="form-actions full"><Button type="button" variant="secondary" onClick={close}>Cancelar</Button><Button disabled={save.isPending}><Save/> Salvar</Button></div></form></Modal>;
}

function BlocksPage() {
  const qc = useQueryClient(); const [editing, setEditing] = useState<Partial<Block> | null>(null);
  const query = useQuery({queryKey: ["blocks"], queryFn: () => fetchAll<Block>("/schedule-blocks/", {ordering: "-starts_at"})});
  const save = useMutation({mutationFn: (d: Partial<Block>) => {const payload = {...d, starts_at: toIso(d.starts_at!), ends_at: toIso(d.ends_at!)}; return d.id ? api.patch(`/schedule-blocks/${d.id}/`, payload) : api.post("/schedule-blocks/", payload);}, onSuccess: () => {qc.invalidateQueries({queryKey: ["blocks"]}); setEditing(null);}});
  const remove = useMutation({mutationFn: (id: number) => api.delete(`/schedule-blocks/${id}/`), onSuccess: () => qc.invalidateQueries({queryKey: ["blocks"]})});
  return <><PageHeader title="Bloqueios de agenda" description="Reserve períodos para folgas, almoço ou compromissos." action={<Button onClick={() => setEditing({starts_at: `${format(new Date(), "yyyy-MM-dd")}T12:00`, ends_at: `${format(new Date(), "yyyy-MM-dd")}T13:00`, reason: ""})}><Plus/> Novo bloqueio</Button>}/>{query.isLoading ? <Loading/> : listOf(query.data).length ? <div className="table-wrap"><table><thead><tr><th>Início</th><th>Término</th><th>Motivo</th><th/></tr></thead><tbody>{listOf(query.data).map(b => <tr key={b.id}><td>{format(new Date(b.starts_at), "dd/MM/yyyy HH:mm")}</td><td>{format(new Date(b.ends_at), "dd/MM/yyyy HH:mm")}</td><td>{b.reason || "Sem motivo informado"}</td><td className="actions"><button onClick={() => setEditing({...b, starts_at: dateTimeLocal(b.starts_at), ends_at: dateTimeLocal(b.ends_at)})}>Editar</button><button className="danger-link" onClick={() => confirm("Remover este bloqueio?") && remove.mutate(b.id)}>Remover</button></td></tr>)}</tbody></table></div> : <Empty>Nenhum período bloqueado.</Empty>}{editing && <BlockForm value={editing} save={save} close={() => setEditing(null)}/>}</>;
}
function BlockForm({value, save, close}: {value: Partial<Block>; save: ReturnType<typeof useMutation<unknown, Error, Partial<Block>>>; close: () => void}) {const [d,setD]=useState(value); return <Modal title="Bloqueio de agenda" onClose={close}><form className="form-grid" onSubmit={e=>{e.preventDefault();save.mutate(d);}}><label>Início<input required type="datetime-local" value={d.starts_at ?? ""} onChange={e=>setD({...d,starts_at:e.target.value})}/></label><label>Término<input required type="datetime-local" value={d.ends_at ?? ""} onChange={e=>setD({...d,ends_at:e.target.value})}/></label><label className="full">Motivo<input value={d.reason ?? ""} onChange={e=>setD({...d,reason:e.target.value})}/></label><ErrorMessage error={save.error}/><div className="form-actions full"><Button type="button" variant="secondary" onClick={close}>Cancelar</Button><Button><Save/> Salvar</Button></div></form></Modal>}

function SettingsPage() {
  const qc = useQueryClient(); const shop = useQuery({queryKey:["shop-settings"],queryFn:()=>api.get<Shop>("/barbershop/").then(r=>r.data)}); const [draft,setDraft]=useState<Shop|null>(null);
  // O formulário precisa de uma cópia editável sempre que os dados remotos forem atualizados.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(()=>{if(shop.data)setDraft(shop.data)},[shop.data]);
  const saveShop=useMutation({mutationFn:(d:Shop)=>api.patch("/barbershop/",{name:d.name,whatsapp:d.whatsapp,timezone:d.timezone,active:d.active}),onSuccess:()=>qc.invalidateQueries({queryKey:["shop-settings"]})});
  const saveHours=useMutation({mutationFn:async(hours:OperatingHour[])=>Promise.all(hours.map(h=>h.id?api.patch(`/operating-hours/${h.id}/`,h):api.post("/operating-hours/",h))),onSuccess:()=>qc.invalidateQueries({queryKey:["shop-settings"]})});
  if(!draft)return <Loading/>; const byDay=weekdays.map((_,weekday)=>draft.operating_hours.find(h=>h.weekday===weekday)??{id:0,weekday,opens_at:"08:00",closes_at:"18:00",active:false});
  const updateHour=(weekday:number,patch:Partial<OperatingHour>)=>setDraft({...draft,operating_hours:byDay.map(h=>h.weekday===weekday?{...h,...patch}:h)});
  return <><PageHeader title="Configurações" description="Dados públicos e funcionamento da barbearia."/><div className="settings-grid"><form className="panel form-grid" onSubmit={e=>{e.preventDefault();saveShop.mutate(draft)}}><h2 className="full">Dados da barbearia</h2><label className="full">Nome<input value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label><label>WhatsApp<input value={draft.whatsapp} onChange={e=>setDraft({...draft,whatsapp:e.target.value})}/></label><label>Endereço público<input readOnly value={`/agendar/${draft.slug}`}/></label><label className="full">Fuso horário<input value={draft.timezone} onChange={e=>setDraft({...draft,timezone:e.target.value})}/></label><Toggle checked={draft.active} setChecked={active=>setDraft({...draft,active})}>Agendamento público ativo</Toggle><ErrorMessage error={saveShop.error}/><div className="form-actions full"><Button disabled={saveShop.isPending}><Save/> Salvar dados</Button></div></form><form className="panel hours" onSubmit={e=>{e.preventDefault();saveHours.mutate(byDay)}}><h2>Horários de funcionamento</h2>{byDay.map(h=><div className="hour-row" key={h.weekday}><Toggle checked={h.active} setChecked={active=>updateHour(h.weekday,{active})}>{weekdays[h.weekday]}</Toggle><input type="time" value={h.opens_at.slice(0,5)} onChange={e=>updateHour(h.weekday,{opens_at:e.target.value})}/><span>até</span><input type="time" value={h.closes_at.slice(0,5)} onChange={e=>updateHour(h.weekday,{closes_at:e.target.value})}/></div>)}<ErrorMessage error={saveHours.error}/><Button disabled={saveHours.isPending}><Save/> Salvar horários</Button></form></div></>;
}

function SearchBox({value,setValue,placeholder}:{value:string;setValue:(v:string)=>void;placeholder:string}) {return <div className="search-box"><Search/><input value={value} onChange={e=>setValue(e.target.value)} placeholder={placeholder}/></div>}
function Toggle({checked,setChecked,children}:{checked:boolean;setChecked:(v:boolean)=>void;children:ReactNode}) {return <label className="toggle"><input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/><span/>{children}</label>}

declare global {interface Window {turnstile?: {render:(element:HTMLElement,options:{sitekey:string;callback:(token:string)=>void})=>string}}}
function PublicBooking({slug}:{slug:string}) {
  usePageMetadata("Agendamento online | M&R BarberHub", "Escolha serviço, data e horário para solicitar seu atendimento.", `/agendar/${slug}`);
  const [service,setService]=useState(""); const [day,setDay]=useState(format(new Date(),"yyyy-MM-dd")); const [slot,setSlot]=useState(""); const [name,setName]=useState(""); const [whatsapp,setWhatsapp]=useState(""); const [privacyAccepted,setPrivacyAccepted]=useState(false); const [captcha,setCaptcha]=useState(import.meta.env.VITE_TURNSTILE_SITE_KEY ? "" : "development"); const captchaRef=useRef<HTMLDivElement>(null);
  const shop=useQuery({queryKey:["public-shop",slug],queryFn:()=>api.get<Shop>(`/public/${slug}/`).then(r=>r.data)}); const services=useQuery({queryKey:["public-services",slug],queryFn:()=>api.get<Service[]>(`/public/${slug}/services/`).then(r=>r.data)}); const slots=useQuery({queryKey:["slots",slug,service,day],enabled:!!service,queryFn:()=>api.get(`/public/${slug}/availability/`,{params:{service_id:service,day}}).then(r=>r.data.slots as string[])});
  const booking=useMutation({mutationFn:()=>api.post(`/public/${slug}/book/`,{name,whatsapp,service_id:Number(service),starts_at:slot,captcha_token:captcha,privacy_notice_accepted:privacyAccepted})});
  const initialLoading=shop.isLoading||services.isLoading;
  const initialError=shop.error||services.error;
  useEffect(()=>{if(initialLoading||initialError)return;const sitekey=import.meta.env.VITE_TURNSTILE_SITE_KEY;if(!sitekey)return;const script=document.createElement("script");script.src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";script.async=true;script.onload=()=>{if(captchaRef.current&&window.turnstile)window.turnstile.render(captchaRef.current,{sitekey,callback:setCaptcha})};document.head.appendChild(script);return()=>script.remove()},[initialLoading,initialError]);
  if(initialLoading)return <main className="public-shell"><section className="success-card public-state"><Loading/><h1>Carregando agenda...</h1><p>Buscando serviços e horários disponíveis.</p></section></main>;
  if(initialError)return <main className="public-shell"><section className="success-card public-state"><div className="success-icon error-icon"><CalendarX/></div><p className="eyebrow">Agenda indisponível</p><h1>Não foi possível carregar</h1><p>{errorText(initialError)}</p><Button onClick={()=>location.reload()}>Tentar novamente</Button></section></main>;
  if(booking.isSuccess)return <main className="public-shell"><section className="success-card"><div className="success-icon"><CalendarDays/></div><p className="eyebrow">Tudo certo</p><h1>Horário solicitado!</h1><p>Seu pedido foi registrado. Você receberá a confirmação pelo WhatsApp.</p><Button onClick={()=>location.reload()}>Fazer outro agendamento</Button><p className="company-credit public-credit">Agendamento por <strong>M&amp;R BarberHub</strong></p></section></main>;
  return <main className="public-shell"><header className="public-header"><div className="public-brand-mark"><img src="/barberhub-icon-v2.png" alt=""/></div><div><p>Agendamento online</p><h1>{shop.data?.name??"Barbearia"}</h1></div></header><form className="booking-card" onSubmit={(e:FormEvent)=>{e.preventDefault();booking.mutate()}}><div className="booking-step"><span>1</span><div><h2>Escolha o serviço</h2><p>Selecione o atendimento desejado.</p></div></div><div className="service-options">{services.data?.map(s=><button type="button" className={service===String(s.id)?"selected":""} key={s.id} onClick={()=>{setService(String(s.id));setSlot("")}}><span>{s.name}<small>{s.duration_minutes} minutos</small></span><strong>{money(s.price)}</strong></button>)}</div><div className="booking-step"><span>2</span><div><h2>Data e horário</h2><p>Veja os horários disponíveis.</p></div></div><DatePicker value={day} onChange={value=>{setDay(value);setSlot("")}}/><div className="slots">{slots.isFetching?<Loading/>:slots.isError?<div className="slot-error"><p className="form-error">{errorText(slots.error)}</p><Button type="button" variant="secondary" onClick={()=>slots.refetch()}>Tentar novamente</Button></div>:slots.data?.length?slots.data.map(s=><button type="button" className={slot===s?"selected":""} onClick={()=>setSlot(s)} key={s}>{format(new Date(s),"HH:mm")}</button>):service&&<p>Nenhum horário disponível nesta data.</p>}</div><div className="booking-step"><span>3</span><div><h2>Seus dados</h2><p>Para identificarmos o agendamento.</p></div></div><div className="form-grid"><label>Nome<input required minLength={2} autoComplete="name" value={name} onChange={e=>setName(e.target.value)}/></label><label>WhatsApp<input required minLength={10} inputMode="tel" autoComplete="tel" value={whatsapp} onChange={e=>setWhatsapp(e.target.value)} placeholder="(11) 99999-9999"/></label></div><label className="privacy-check"><input required type="checkbox" checked={privacyAccepted} onChange={e=>setPrivacyAccepted(e.target.checked)}/><span>Li o <a href="/privacidade" target="_blank" rel="noreferrer">aviso de privacidade</a> e estou ciente do uso dos dados para este agendamento.</span></label><div ref={captchaRef}/><ErrorMessage error={booking.error}/><Button className="booking-submit" disabled={!service||!slot||!captcha||!privacyAccepted||booking.isPending}>{booking.isPending?"Confirmando...":"Confirmar agendamento"}</Button></form><p className="company-credit public-credit">Agendamento por <strong>M&amp;R BarberHub</strong></p></main>;
}
export default function AdminApp() {
  usePageMetadata("Painel | M&R BarberHub", "Painel de gestão da sua barbearia.", "/login");
  const stored=localStorage.getItem("user"); const [user,setUser]=useState<SessionUser|null>(stored?JSON.parse(stored):null); const [page,setPage]=useState<PageName>("dashboard");
  const logout=async()=>{const refresh=localStorage.getItem("refresh");try{if(refresh)await api.post("/auth/logout/",{refresh})}catch{/* remove a sessão local mesmo se o token já expirou */}localStorage.clear();setUser(null)};
  if(!user||!localStorage.getItem("access"))return <LoginPage onLogin={setUser}/>;
  const content={dashboard:<DashboardPage go={setPage}/>,appointments:<AppointmentsPage role={user.role}/>,customers:<CustomersPage/>,services:<ServicesPage/>,users:<UsersPage/>,blocks:<BlocksPage/>,settings:<SettingsPage/>}[page];
  return <Shell user={user} page={page} setPage={setPage} onLogout={logout}>{content}</Shell>;
}
export {PublicBooking};
