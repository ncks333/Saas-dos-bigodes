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
