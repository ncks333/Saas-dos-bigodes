import {useMutation} from "@tanstack/react-query";
import axios from "axios";
import {CheckCircle2, KeyRound, Scissors} from "lucide-react";
import {FormEvent, useEffect, useState} from "react";
import api from "./api";
import {usePageMetadata} from "./metadata";
import "./auth.css";

function messageFrom(error: unknown) {
  if (!axios.isAxiosError(error)) return "Não foi possível concluir a operação.";
  if (!error.response) return "Não foi possível conectar ao servidor.";
  const data = error.response.data;
  const text = JSON.stringify(data);
  if (text.includes("Token inválido") || text.includes("Código inválido")) return "Link inválido ou expirado. Solicite uma nova recuperação.";
  if (error.response.status === 429) return "Muitas tentativas. Aguarde antes de tentar novamente.";
  if (error.response.status >= 500) return "Serviço temporariamente indisponível.";
  return "Revise os dados e tente novamente.";
}

function AuthBrand() {
  return <a className="auth-brand" href="/"><span><Scissors/></span><strong>M&amp;R BarberHub</strong></a>;
}

export function PasswordResetRequestPage() {
  usePageMetadata("Recuperar senha | M&R BarberHub", "Solicite um link seguro para redefinir sua senha.", "/recuperar-senha");
  const [email,setEmail]=useState("");
  const request=useMutation({mutationFn:()=>api.post("/auth/password-reset/",{email})});
  return <main className="auth-page"><AuthBrand/><section className="auth-card">
    {request.isSuccess?<><div className="auth-icon success"><CheckCircle2/></div><p className="eyebrow">Verifique seu e-mail</p><h1>Link enviado</h1><p>Se o e-mail estiver cadastrado, você receberá um link válido por uma hora.</p><a className="btn btn-primary" href="/login">Voltar ao login</a></>:<><div className="auth-icon"><KeyRound/></div><p className="eyebrow">Recuperação de acesso</p><h1>Esqueceu sua senha?</h1><p>Informe o e-mail cadastrado. Enviaremos um link seguro para criar outra senha.</p><form onSubmit={(event:FormEvent)=>{event.preventDefault();request.mutate()}}><label>E-mail<input required type="email" autoComplete="email" value={email} onChange={event=>setEmail(event.target.value)} placeholder="voce@exemplo.com"/></label>{request.error&&<p className="form-error">{messageFrom(request.error)}</p>}<button className="btn btn-primary" disabled={request.isPending}>{request.isPending?"Enviando...":"Enviar link"}</button></form><a className="auth-back" href="/login">Voltar ao login</a></>}
  </section></main>;
}

export function PasswordResetConfirmPage() {
  usePageMetadata("Redefinir senha | M&R BarberHub", "Crie uma nova senha para acessar o M&R BarberHub.", "/redefinir-senha");
  const params=new URLSearchParams(location.search);
  const [uid]=useState(params.get("uid")??"");
  const [token]=useState(params.get("token")??"");
  const [password,setPassword]=useState("");
  const [confirmation,setConfirmation]=useState("");
  useEffect(()=>{if(location.search)history.replaceState({},"","/redefinir-senha")},[]);
  const reset=useMutation({mutationFn:()=>api.post("/auth/password-reset/confirm/",{uid,token,password})});
  const validPassword=/(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}/.test(password);
  const validLink=Boolean(uid&&token);
  return <main className="auth-page"><AuthBrand/><section className="auth-card">
    {reset.isSuccess?<><div className="auth-icon success"><CheckCircle2/></div><p className="eyebrow">Acesso recuperado</p><h1>Senha atualizada</h1><p>Sua nova senha já pode ser usada para entrar no painel.</p><a className="btn btn-primary" href="/login">Acessar painel</a></>:<><div className="auth-icon"><KeyRound/></div><p className="eyebrow">Nova senha</p><h1>Crie uma senha segura</h1><p>Use ao menos oito caracteres, com letra maiúscula, minúscula e número.</p>{!validLink?<div className="form-error auth-link-error">Link ausente ou inválido. Solicite uma nova recuperação.</div>:<form onSubmit={(event:FormEvent)=>{event.preventDefault();reset.mutate()}}><label>Nova senha<input required type="password" autoComplete="new-password" minLength={8} value={password} onChange={event=>setPassword(event.target.value)}/></label><label>Confirmar senha<input required type="password" autoComplete="new-password" value={confirmation} onChange={event=>setConfirmation(event.target.value)}/></label>{confirmation&&password!==confirmation&&<p className="form-error">As senhas não coincidem.</p>}{reset.error&&<p className="form-error">{messageFrom(reset.error)}</p>}<button className="btn btn-primary" disabled={!validPassword||password!==confirmation||reset.isPending}>{reset.isPending?"Salvando...":"Salvar nova senha"}</button></form>}<a className="auth-back" href="/recuperar-senha">Solicitar outro link</a></>}
  </section></main>;
}
