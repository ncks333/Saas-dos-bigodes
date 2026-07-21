import {defineConfig, devices} from "@playwright/test";

const turnstileSiteKey = process.env.VITE_TURNSTILE_SITE_KEY;
const turnstilePrefix = turnstileSiteKey ? `VITE_TURNSTILE_SITE_KEY=${JSON.stringify(turnstileSiteKey)} ` : "";

export default defineConfig({
  testDir: "./tests",
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [
    {name: "mobile-chrome", use: {...devices["Pixel 5"]}},
  ],
  webServer: {
    command: `${turnstilePrefix}npm run dev -- --port 4173`,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    env: {
      VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
      ...(turnstileSiteKey ? {VITE_TURNSTILE_SITE_KEY: turnstileSiteKey} : {}),
    },
  },
});
