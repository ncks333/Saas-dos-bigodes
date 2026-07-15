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
