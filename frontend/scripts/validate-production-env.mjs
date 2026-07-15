export function validateProductionEnv(env) {
  if (!env.VITE_API_URL) {
    throw new Error("VITE_API_URL deve ser configurada para o build de produção.");
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
