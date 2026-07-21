import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

import {validateProductionEnv} from "../scripts/validate-production-env.mjs";

const valid = {
  VITE_API_URL: "https://api.mrbarberhub.com.br/api/v1",
  VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
};

const root = new URL("../", import.meta.url);
const vercel = JSON.parse(readFileSync(new URL("vercel.json", root), "utf8"));
const appSource = readFileSync(new URL("src/App.tsx", root), "utf8");
const repositoryRoot = new URL("../../", import.meta.url);
const dockerfile = readFileSync(new URL("frontend/Dockerfile", repositoryRoot), "utf8");
const compose = readFileSync(new URL("docker-compose.yml", repositoryRoot), "utf8");
const readme = readFileSync(new URL("README.md", repositoryRoot), "utf8");
const deployGuide = readFileSync(new URL("docs/DEPLOY.md", repositoryRoot), "utf8");
const securityGuide = readFileSync(new URL("docs/SECURITY.md", repositoryRoot), "utf8");
const billingRunbook = readFileSync(
  new URL("docs/runbooks/billing-regularization-reconciliation.md", repositoryRoot),
  "utf8",
);
const backendProductionEnv = readFileSync(
  new URL("backend/.env.production.example", repositoryRoot),
  "utf8",
);
const productionEnvValidator = readFileSync(
  new URL("scripts/validate-production-env.mjs", root),
  "utf8",
);
const viteConfig = readFileSync(new URL("vite.config.ts", root), "utf8");
const readmeCommands = [...readme.matchAll(/```(?:bash|powershell)\r?\n([\s\S]*?)```/g)]
  .flatMap(match => match[1].split(/\r?\n/))
  .map(command => command.trim())
  .filter(Boolean);
const localViteEnv = "VITE_API_URL=http://localhost:8000/api/v1 VITE_MR_SOLUTIONS_WHATSAPP_URL=https://wa.me/5511999999999?text=Teste";

test("accepts canonical public production URLs", () => {
  assert.doesNotThrow(() => validateProductionEnv(valid));
});

test("rejects missing WhatsApp URL", () => {
  assert.throws(
    () => validateProductionEnv({...valid, VITE_MR_SOLUTIONS_WHATSAPP_URL: ""}),
    /VITE_MR_SOLUTIONS_WHATSAPP_URL/,
  );
});

test("rejects placeholder and non-wa.me contact URLs", () => {
  for (const value of [
    "https://wa.me/5500000000000?text=Teste",
    "https://example.com/5511999999999",
    "http://wa.me/5511999999999",
  ]) {
    assert.throws(
      () => validateProductionEnv({...valid, VITE_MR_SOLUTIONS_WHATSAPP_URL: value}),
      /WhatsApp pública válida/,
    );
  }
});

test("Vercel serves the M&R Solutions SPA route", () => {
  assert.ok(vercel.rewrites.some(item =>
    item.source === "/mr-solutions" && item.destination === "/index.html"
  ));
});

test("CSP allows only the exact globe texture origin", () => {
  const csp = vercel.headers
    .flatMap(item => item.headers)
    .find(item => item.key === "Content-Security-Policy").value;
  assert.match(csp, /img-src[^;]*https:\/\/pub-940ccf6255b54fa799a9b01050e6c227\.r2\.dev/);
});

test("development globe route is not published", () => {
  assert.doesNotMatch(appSource, /demo\/globe|DemoOne/);
});

test("Docker frontend build receives the validated WhatsApp URL", () => {
  assert.match(dockerfile, /^ARG VITE_MR_SOLUTIONS_WHATSAPP_URL$/m);
  assert.match(dockerfile, /VITE_MR_SOLUTIONS_WHATSAPP_URL=\$VITE_MR_SOLUTIONS_WHATSAPP_URL/);
});

test("Compose provides only a fictitious development WhatsApp fixture", () => {
  assert.match(
    compose,
    /VITE_MR_SOLUTIONS_WHATSAPP_URL: \$\{VITE_MR_SOLUTIONS_WHATSAPP_URL:-https:\/\/wa\.me\/5511999999999\?text=Teste\}/,
  );
});

test("versioned deployment docs require Vercel UI for the real WhatsApp URL", () => {
  for (const document of [readme, deployGuide]) {
    assert.match(document, /VITE_MR_SOLUTIONS_WHATSAPP_URL/);
    assert.match(document, /somente no painel da Vercel/i);
  }
  assert.doesNotMatch(deployGuide, /VITE_MR_SOLUTIONS_WHATSAPP_URL=https:\/\/wa\.me\/55\d/);
});

test("README operacional usa somente WhatsApp Cloud API oficial da Meta", () => {
  assert.match(readme, /WhatsApp Cloud API oficial da Meta/i);
  assert.doesNotMatch(readme, /\bEvolution(?:\s+API)?\b|\bBaileys\b/i);
});

test("README fornece comando Vite sem Docker com ambiente local completo", () => {
  assert.ok(readmeCommands.includes(`${localViteEnv} npm run dev`));
});

test("README fornece comando de build com ambiente local completo", () => {
  assert.ok(readmeCommands.includes(`${localViteEnv} npm run build`));
});

test("README usa exclusivamente a fixture fictícia nos comandos executáveis", () => {
  const whatsappUrls = readme.match(/https:\/\/wa\.me\/[^\s`]+/g) ?? [];
  assert.deepEqual([...new Set(whatsappUrls)], ["https://wa.me/5511999999999?text=Teste"]);
});

test("Vite alias decodes file URLs instead of using encoded pathname", () => {
  assert.match(viteConfig, /import\s+\{fileURLToPath\}\s+from\s+["']node:url["']/);
  assert.match(viteConfig, /"@":\s*fileURLToPath\(new URL\(["']\.\/src["'], import\.meta\.url\)\)/);
  assert.doesNotMatch(viteConfig, /new URL\(["']\.\/src["'], import\.meta\.url\)\.pathname/);
});

test("backend production example declares only placeholder billing and Resend secrets", () => {
  for (const entry of [
    "ASAAS_API_URL=https://api.asaas.com/v3",
    "ASAAS_CHECKOUT_BASE_URL=https://www.asaas.com/checkoutSession/show",
    "ASAAS_API_KEY=cole-o-token-da-api-asaas",
    "ASAAS_WEBHOOK_TOKEN=gere-um-token-webhook-forte-e-independente",
    "ASAAS_CHECKOUT_EXPIRES_MINUTES=60",
    "FRONTEND_URL=https://app.seudominio.com",
    "EMAIL_BACKEND=core.email_backends.ResendEmailBackend",
    "RESEND_API_KEY=cole-a-chave-restrita-de-envio-do-resend",
  ]) {
    assert.match(backendProductionEnv, new RegExp(`^${entry}$`, "m"));
  }
});

test("subscription deployment docs match supported Asaas lifecycle", () => {
  for (const document of [deployGuide, readme]) {
    assert.match(document, /Asaas Sandbox/i);
    assert.match(document, /Asaas.*produção/i);
    assert.match(document, /\/api\/v1\/billing\/webhooks\/asaas\//);
    assert.match(document, /Railway.*somente.*segredos/i);
    assert.match(document, /callback.*redirect.*não.*confirma.*pagamento/i);
    assert.match(document, /30 dias/i);
    assert.match(document, /60 dias/i);
    assert.match(document, /7 dias/i);
    assert.match(document, /e-mail.*primeiro/i);
  }
  for (const eventName of [
    "CHECKOUT_PAID",
    "PAYMENT_CONFIRMED",
    "PAYMENT_RECEIVED",
    "PAYMENT_OVERDUE",
    "PAYMENT_REPROVED_BY_RISK_ANALYSIS",
    "PAYMENT_CHARGEBACK_REQUESTED",
    "PAYMENT_CHARGEBACK_DISPUTE",
    "SUBSCRIPTION_INACTIVATED",
    "SUBSCRIPTION_DELETED",
  ]) {
    assert.match(deployGuide, new RegExp(`\\b${eventName}\\b`));
  }
  assert.match(deployGuide, /não.*recuperação.*automática/i);
  assert.match(deployGuide, /reconciliação manual/i);
  assert.match(deployGuide, /checkout de teste/i);
  assert.match(securityGuide, /dados de cartão.*payload.*provedor/i);
  assert.match(billingRunbook, /nunca execute novo checkout/i);
});

test("frontend production validator accepts only VITE public values", () => {
  assert.throws(
    () => validateProductionEnv({
      ASAAS_API_KEY: "backend-secret",
      ASAAS_WEBHOOK_TOKEN: "webhook-secret",
      RESEND_API_KEY: "resend-secret",
    }),
    /VITE_API_URL/,
  );
  assert.doesNotMatch(productionEnvValidator, /ASAAS_|RESEND_API_KEY/);
});
