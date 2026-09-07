import { useEffect, useState } from "react";
import { apiGet } from "./lib/api";

type Health = { status: string; app: string; sap_mode: string; db: string };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Health>("/healthz").then(setHealth).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main style={{ maxWidth: 640, margin: "80px auto", padding: "0 24px" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>SB Design Square</h1>
      <p style={{ color: "#777", marginTop: 0 }}>STEP 0 — placeholder · เว็บเชื่อมกับ API ผ่าน proxy /api</p>
      <pre className="mono" style={{ background: "#16181a", color: "#f2f2f0", padding: 16, borderRadius: 10 }}>
        {error ? `healthz error: ${error}` : health ? JSON.stringify(health, null, 2) : "loading /healthz…"}
      </pre>
    </main>
  );
}
