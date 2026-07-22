import {fileURLToPath} from "node:url";
import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";
import {validateProductionEnv} from "./scripts/validate-production-env.mjs";

export default defineConfig(({command, mode}) => {
  const env = loadEnv(mode, process.cwd(), "");
  const turnstileSiteKey = process.env.VITE_TURNSTILE_SITE_KEY ?? env.VITE_TURNSTILE_SITE_KEY ?? "";
  if (command === "build") validateProductionEnv(env);
  return {
    define: {
      "import.meta.env.VITE_TURNSTILE_SITE_KEY": JSON.stringify(turnstileSiteKey),
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
      },
    },
  };
});
