import React from "react";
import { ui } from "../theme.js";

// TODO: replace with real team details (names, roles, links).
const TEAM = [
  { name: "Team Member 1", role: "Backend / ML" },
  { name: "Team Member 2", role: "Frontend / Data" },
];

export default function About() {
  return (
    <div style={ui.page}>
      <h1 style={{ fontSize: 28 }}>About TrustShield</h1>
      <section style={{ ...ui.card, marginBottom: 20 }}>
        <p style={{ fontSize: 14, color: "#cbd5e1", lineHeight: 1.7, margin: 0 }}>
          TrustShield was built for the SuRaksha (Canara Bank) hackathon to answer a hard question:
          how can a bank automatically detect tampering, changes, or forgery across land records, legal
          documents, and financial statements in real time? It runs entirely on-premise — no customer
          data ever leaves the machine — and pairs deterministic forensic + semantic checks with an
          explainable learned model and a cross-application graph that catches fraud rings and
          double-financed collateral.
        </p>
      </section>

      <h2 style={ui.sectionTitle}>Team</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        {TEAM.map((m, i) => (
          <div key={i} style={ui.card}>
            <div style={{ width: 48, height: 48, borderRadius: "50%", background: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, marginBottom: 10 }}>
              {m.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
            </div>
            <div style={{ fontWeight: 700, color: "#e2e8f0" }}>{m.name}</div>
            <div style={{ fontSize: 13, color: "#94a3b8" }}>{m.role}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
