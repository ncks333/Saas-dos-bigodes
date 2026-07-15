import {defineConfig, devices} from "@playwright/test";

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
    command: "npm run dev -- --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
    env: {
      VITE_MR_SOLUTIONS_WHATSAPP_URL: "https://wa.me/5511999999999?text=Teste",
    },
  },
});
