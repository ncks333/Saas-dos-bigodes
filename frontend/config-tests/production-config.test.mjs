import assert from "node:assert/strict";
import test from "node:test";

import {validateProductionEnv} from "../scripts/validate-production-env.mjs";

const valid = {
  VITE_API_URL: "https://api.mrbarberhub.com.br/api/v1",
  VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
};

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
