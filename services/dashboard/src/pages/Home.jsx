import React from "react";
import { Link } from "react-router-dom";
import { color, maxWidth, buttonPrimary, buttonGhost } from "../theme.js";
import LocalFirstBadge from "../components/LocalFirstBadge.jsx";

// R1 ships the shell + a light hero so the route isn't blank. The full Home
// narrative (problem / pipeline / features / proof / examples) lands in R2–R6.
export default function Home() {
  return (
    <div>
      <section
        style={{
          padding: "72px 24px 56px",
          background: "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(56,189,248,0.14), transparent)",
        }}
      >
        <div style={{ maxWidth, margin: "0 auto", textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
            <LocalFirstBadge />
          </div>
          <h1 style={{ fontSize: 44, lineHeight: 1.1, margin: "0 0 14px", letterSpacing: -1 }}>
            Catch forged loan documents.<br />
            <span style={{ color: color.accent }}>Explain every verdict.</span>
          </h1>
          <p style={{ fontSize: 17, color: color.textDim, maxWidth: 640, margin: "0 auto 28px", lineHeight: 1.6 }}>
            TrustShield is a 100% local-first underwriting copilot. It inspects every document in a
            loan packet for tampering and forgery, then returns an explainable trust score (0–100)
            with a full evidence chain and a recommended action — no data ever leaves the device.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <Link to="/investigator" style={{ textDecoration: "none" }}>
              <button style={buttonPrimary}>Watch it catch a forgery →</button>
            </Link>
            <Link to="/examples" style={{ textDecoration: "none" }}>
              <button style={buttonGhost}>See annotated examples</button>
            </Link>
          </div>
        </div>
      </section>

      <section style={{ maxWidth, margin: "0 auto", padding: "0 24px 64px" }}>
        <div
          style={{
            border: `1px dashed ${color.border}`,
            borderRadius: 16,
            padding: "32px 24px",
            textAlign: "center",
            color: color.textFaint,
            fontSize: 13,
          }}
        >
          The problem · the 5-layer pipeline · key features · honest proof &amp; results sections are
          coming together here next (plan: <code>DASHBOARD_PLAN.md</code> R2–R5).
        </div>
      </section>
    </div>
  );
}
