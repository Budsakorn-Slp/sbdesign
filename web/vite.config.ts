/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API_PROXY_TARGET: ใน docker compose = http://api:8000, รันในเครื่อง = http://localhost:8000
const target = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      "/ws": { target: target.replace(/^http/, "ws"), ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
