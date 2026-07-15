import {lazy, Suspense} from "react";
import {LandingPage, MRSolutionsPage, PrivacyPage} from "./MarketingPages";

const AdminApp=lazy(()=>import("./ProductApp"));
const PublicBooking=lazy(()=>import("./ProductApp").then(module=>({default:module.PublicBooking})));
const PasswordResetRequestPage=lazy(()=>import("./PasswordResetPages").then(module=>({default:module.PasswordResetRequestPage})));
const PasswordResetConfirmPage=lazy(()=>import("./PasswordResetPages").then(module=>({default:module.PasswordResetConfirmPage})));

function RouteLoading(){return <main className="route-loading" aria-label="Carregando"><span/><span/><span/></main>}

export default function App(){
  const path=location.pathname.replace(/\/+$/,"")||"/";
  const parts=path.split("/").filter(Boolean);
  let page;
  if(path==="/")page=<LandingPage/>;
  else if(path==="/mr-solutions")page=<MRSolutionsPage/>;
  else if(path==="/login")page=<AdminApp/>;
  else if(path==="/privacidade")page=<PrivacyPage/>;
  else if(path==="/recuperar-senha")page=<PasswordResetRequestPage/>;
  else if(path==="/redefinir-senha")page=<PasswordResetConfirmPage/>;
  else if(parts[0]==="agendar"&&parts[1])page=<PublicBooking slug={parts[1]}/>;
  else page=<main className="not-found"><p className="eyebrow">Erro 404</p><h1>Página não encontrada</h1><a className="btn btn-primary" href="/">Voltar ao início</a></main>;
  return <Suspense fallback={<RouteLoading/>}>{page}</Suspense>;
}
