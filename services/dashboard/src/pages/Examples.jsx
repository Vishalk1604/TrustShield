import React from "react";
import { color, maxWidth, sectionTitle } from "../theme.js";

// Stub for R1 — the routing shell ships first; the curated before/after gallery
// (overlay + caption per case) lands in R6 per DASHBOARD_PLAN.md.
export default function Examples() {
  return (
    <div style={{ maxWidth, margin: "0 auto", padding: "40px 24px 64px" }}>
      <h1 style={{ margin: "0 0 8px", fontSize: 28, letterSpacing: -0.5 }}>Annotated examples</h1>
      <p style={{ color: color.textDim, margin: "0 0 24px", maxWidth: 640, lineHeight: 1.6 }}>
        A gallery of before/after tampered documents with detection overlays and plain-English
        captions — Form 16 gross-salary edits, bank statement salary-credit edits, PAN swaps — is
        coming together here next.
      </p>
      <div style={{ border: `1px dashed ${color.border}`, borderRadius: 16, padding: "40px 24px", textAlign: "center", color: color.textFaint, fontSize: 13 }}>
        <h2 style={{ ...sectionTitle, marginBottom: 8 }}>Coming soon</h2>
        In the meantime, try the live detector with real examples in the Investigator console.
      </div>
    </div>
  );
}
