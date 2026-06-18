import React from "react";
import { Link } from "react-router-dom";
import { ui } from "../theme.js";

const LAYERS = [
  { t: "Forensic tamper detection", d: "PDF metadata, white-box edits, font/object anomalies, incremental revisions, and a re-OCR-vs-text-layer cross-check that catches edits even on flattened scans." },
  { t: "Cross-document semantics", d: "Income vs bank credits vs salary slip, name/PAN consistency, owner-vs-applicant, LTV, valuation-vs-registry, EC-vs-CERSAI charge checks." },
  { t: "KYC validation", d: "PAN structure, Aadhaar Verhoeff checksum, and IFSC checks on uploaded identity documents." },
  { t: "Learned, explainable model", d: "Gradient-boosted trees + isolation forest with per-feature attributions — never a black-box number." },
  { t: "Cross-application graph", d: "Surfaces fraud rings and double-financed collateral across applications — what single-document tools miss." },
];

export default function Home() {
  return (
    <div style={ui.page}>
      <section style={{ textAlign: "center", padding: "40px 0 28px" }}>
        <h1 style={{ fontSize: 40, margin: 0, letterSpacing: -1 }}>
          🛡️ TrustShield
        </h1>
        <p style={{ fontSize: 18, color: "#94a3b8", maxWidth: 720, margin: "14px auto 0", lineHeight: 1.6 }}>
          A 100% local-first underwriting copilot that detects document tampering and forgery across a
          loan packet — returning an explainable trust score, an evidence chain, and a recommended action.
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 24 }}>
          <Link to="/signup"><button style={ui.btn}>Get started</button></Link>
          <Link to="/signin"><button style={ui.btnGhost}>Sign in</button></Link>
        </div>
      </section>

      <div style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.4)", borderRadius: 10, padding: "10px 14px", margin: "10px 0 28px", fontSize: 13, color: "#bbf7d0", textAlign: "center" }}>
        🔒 <strong>All processing on-premise.</strong> No customer data leaves the machine — every analysis is local.
      </div>

      <h2 style={{ ...ui.sectionTitle, textAlign: "center" }}>How it works — five analysis layers</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        {LAYERS.map((l, i) => (
          <div key={i} style={ui.card}>
            <div style={{ fontWeight: 700, color: "#38bdf8", marginBottom: 6 }}>{i + 1}. {l.t}</div>
            <div style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>{l.d}</div>
          </div>
        ))}
      </div>

      <section style={{ ...ui.card, marginTop: 24 }}>
        <h2 style={ui.sectionTitle}>Two ways in</h2>
        <p style={{ fontSize: 14, color: "#cbd5e1", lineHeight: 1.6, margin: 0 }}>
          <strong>Applicants</strong> upload their documents (KYC, loan, …) and get an instant trust
          assessment. <strong>Underwriters / admins</strong> review every submission with the full
          forensic evidence chain, KYC validation, tamper localization, and the trust score.
        </p>
      </section>
    </div>
  );
}
