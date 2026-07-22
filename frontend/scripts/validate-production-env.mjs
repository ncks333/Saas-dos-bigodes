export function validateProductionEnv(env) {
  if (!env.VITE_API_URL) {
    throw new Error("VITE_API_URL deve ser configurada para o build de produção.");
  }

  if (typeof env.VITE_TURNSTILE_SITE_KEY !== "string" || !env.VITE_TURNSTILE_SITE_KEY.trim()) {
    throw new Error("VITE_TURNSTILE_SITE_KEY deve ser configurada para o build de produção.");
  }

  const checkoutOrigins = typeof env.VITE_ASAAS_CHECKOUT_ORIGINS === "string"
    ? env.VITE_ASAAS_CHECKOUT_ORIGINS.split(",").map(value => value.trim()).filter(Boolean)
    : [];
  const productionCheckoutOrigins = new Set(["https://asaas.com", "https://www.asaas.com"]);
  if (
    checkoutOrigins.length === 0
    || checkoutOrigins.some(value => {
      try {
        const url = new URL(value);
        return url.protocol !== "https:"
          || url.origin !== value
          || !productionCheckoutOrigins.has(value);
      } catch {
        return true;
      }
    })
  ) {
    throw new Error("VITE_ASAAS_CHECKOUT_ORIGINS deve conter somente origens HTTPS oficiais do Asaas em produção.");
  }

  const raw = env.VITE_MR_SOLUTIONS_WHATSAPP_URL;
  if (!raw) {
    throw new Error("VITE_MR_SOLUTIONS_WHATSAPP_URL deve ser configurada para o build de produção.");
  }

  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("Configure uma URL de WhatsApp pública válida em VITE_MR_SOLUTIONS_WHATSAPP_URL.");
  }

  const digits = url.pathname.slice(1);
  const isPlaceholder = /^550+$/.test(digits);
  if (
    url.protocol !== "https:"
    || url.hostname !== "wa.me"
    || !/^55\d{10,11}$/.test(digits)
    || isPlaceholder
  ) {
    throw new Error("Configure uma URL de WhatsApp pública válida em VITE_MR_SOLUTIONS_WHATSAPP_URL.");
  }
}
