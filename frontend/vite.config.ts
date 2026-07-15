import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";
import {validateProductionEnv} from "./scripts/validate-production-env.mjs";

export default defineConfig(({command, mode}) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build") validateProductionEnv(env);
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": new URL("./src", import.meta.url).pathname,
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
