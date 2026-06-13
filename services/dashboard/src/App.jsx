import React, { useEffect, useState } from "react";
import { SERVICES } from "./config.js";

const PHASES = [
  { n: 0, name: "Foundation & synthetic data", done: true },
  { n: 1, name: "Forensic tamper detection", done: false },
  { n: 2, name: "Cross-document semantics", done: false },
  { n: 3, name: "Behavioral anomaly scoring", done: false },
  { n: 4, name: "Trust score & evidence chain", done: false },
  { n: 5, name: "Cross-application graph", done: false },
  { n: 6, name: "Investigator dashboard", done: false },
  { n: 7, name: "Privacy & trust layer", done: false },
  { n: 8, name: "Demo script & narrative", done: false },
];

function useHealth(base) {
  // "loading" | "ok" | "down". Pings the LOCAL service /health endpoint.
  const [state, setState] = useState({ status: "loading", detail: "" });
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const res = await fetch(`${base}/health`, { cache: "no-store" });
        const body = await res.json();
        if (alive) setState({ status: body.status === "ok" ? "ok" : "down", detail: body.version || "" });
      } catch {
        if (alive) setState({ status: "down", detail: "" });
      }
    };
    ping();
    const id = setInterval(ping, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [base]);
  return state;
}

function StatusDot({ status }) {
  const color = status === "ok" ? "#22c55e" : status === "down" ? "#ef4444" : "#eab308";
  return (
    <span
      style={{
        display: "inline-block", width: 11, height: 11, borderRadius: "50%",
        background: color, boxShadow: `0 0 8px ${color}`, marginRight: 8,
      }}
    />
  );
}

function ServiceCard({ label, base }) {
  const { status, detail } = useHealth(base);
  const text = status === "ok" ? `healthy ${detail && `· v${detail}`}` : status === "down" ? "unreachable" : "checking…";
  return (
    <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 12, padding: "16px 18px", minWidth: 240 }}>
      <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 6 }}>{base}</div>
      <div style={{ fontWeight: 600, fontSize: 16 }}>{label}</div>
      <div style={{ marginTop: 10, fontSize: 14, color: "#cbd5e1" }}>
        <StatusDot status={status} />{text}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div style={{ maxWidth: 920, margin: "0 auto", padding: "48px 24px" }}>
      <header style={{ marginBottom: 8 }}>
        <h1 style={{ margin: 0, fontSize: 30, letterSpacing: -0.5 }}>
          🛡️ TrustShield <span style={{ color: "#38bdf8" }}>Investigator Console</span>
        </h1>
        <p style={{ color: "#94a3b8", marginTop: 6 }}>
          Local-first underwriting copilot — forensic, semantic, and behavioral fraud detection with a
          full evidence chain.
        </p>
      </header>

      <div
        style={{
          background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.4)",
          borderRadius: 12, padding: "12px 16px", margin: "20px 0", fontSize: 14, color: "#bbf7d0",
        }}
      >
        🔒 <strong>All processing on-premise.</strong> No customer data is transmitted externally —
        every analysis runs locally on this machine.
      </div>

      <section>
        <h2 style={{ fontSize: 15, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8" }}>
          Service health
        </h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {SERVICES.map((s) => (
            <ServiceCard key={s.key} label={s.label} base={s.base} />
          ))}
        </div>
      </section>

      <section style={{ marginTop: 36 }}>
        <h2 style={{ fontSize: 15, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8" }}>
          Build progress
        </h2>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
          {PHASES.map((p) => (
            <li key={p.n} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14 }}>
              <span style={{ color: p.done ? "#22c55e" : "#475569" }}>{p.done ? "✓" : "○"}</span>
              <span style={{ color: "#64748b", width: 64 }}>Phase {p.n}</span>
              <span style={{ color: p.done ? "#e2e8f0" : "#94a3b8" }}>{p.name}</span>
            </li>
          ))}
        </ul>
      </section>

      <footer style={{ marginTop: 40, fontSize: 12, color: "#475569" }}>
        Phase 0 placeholder — upload, scoring, and the evidence-chain view arrive in Phase 6.
      </footer>
    </div>
  );
}
