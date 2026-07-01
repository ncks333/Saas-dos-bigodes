import {defineConfig, loadEnv} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({command, mode}) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build" && !env.VITE_API_URL) {
    throw new Error("VITE_API_URL deve ser configurada para o build de produção.");
  }
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
      },
    },
  };
});
