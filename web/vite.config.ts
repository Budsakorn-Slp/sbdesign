/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API_PROXY_TARGET: ใน docker compose = http://api:8000, รันในเครื่อง = http://localhost:8000
const target = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // แยก React + router ออกจากโค้ดเรา — สองอย่างนี้คิดเป็น 77% ของก้อนแรก (gzip 53 จาก 68 kB)
        // แต่แทบไม่เคยเปลี่ยน ถ้าปนอยู่ในไฟล์เดียวกัน ทุกครั้งที่ deploy ผู้ใช้ต้องโหลดใหม่หมด
        // ทั้งที่ของที่แก้จริงมีแค่ 16 kB · แยกแล้วเบราว์เซอร์ใช้ vendor ตัวเดิมจาก cache ต่อได้
        manualChunks: { vendor: ["react", "react-dom", "react-router-dom"] },
      },
    },
  },
  server: {
    proxy: {
      "/api": { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      "/ws": { target: target.replace(/^http/, "ws"), ws: true },
    },
  },
  // vite preview ไม่ได้ใช้ server.proxy ข้างบน ต้องประกาศซ้ำ — ไม่งั้นเวลาทดสอบไฟล์ที่ build แล้ว
  // (ซึ่งเป็นอย่างเดียวที่เห็นผลของ manualChunks) ทุก API จะ 404 จนดูอะไรไม่ได้เลย
  preview: {
    // vite ปฏิเสธ request ที่ Host ไม่ตรงกับที่อนุญาต (กัน DNS rebinding) — ถ้าไม่ใส่โดเมนนี้
    // เปิดผ่าน Cloudflare Tunnel แล้วจะเจอ "Blocked request. This host is not allowed."
    allowedHosts: ["designdev.sbhapps.com"],
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
