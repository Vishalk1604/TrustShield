import React from "react";
import { Link } from "react-router-dom";
import { color as C, layer as L, maxWidth, hexA, radius, shadow } from "../theme.js";
import { Card, Badge, SectionHeader, Button } from "../components/ui/primitives.jsx";
import Reveal from "../components/ui/Reveal.jsx";

const wrap = { maxWidth, margin: "0 auto", padding: "0 24px" };

// Seamless before/after crops (synthetic, zero PII) — top = genuine, lower = the edit.
const SEAMLESS = [
  {
    img: "examples/ex_form16_salary.png",
    title: "Form 16 — gross salary inflated",
    tags: [["model", "naive → pro"]],
    body: "Top: the genuine figure (Rs 18,20,000). Middle: a naive hard-edge edit — a flat fill with no scan noise, which the pixel heuristics catch. Bottom: our seamless 'pro' edit to Rs 27,30,000 with matched font, ink tone and the page's sensor-noise floor — invisible to the eye and to the naive heuristics. That gap is exactly what the learned model is for.",
  },
  {
    img: "examples/ex_pan_swap.png",
    title: "PAN — one character swapped",
    tags: [["semantic", "semantic + QR"]],
    body: "A single character changed (…1234F → …1235F) and seamlessly re-rendered. Even a perfect pixel edit fails the semantic layer: the card's signed QR (and the PAN checksum/format) disagree with the printed value.",
  },
  {
    img: "examples/ex_bank_credit.png",
    title: "Bank statement — salary credit inflated",
    tags: [["forensic", "pro"], ["trust", "arithmetic"]],
    body: "A salary credit lifted Rs 1,24,000 → Rs 2,00,000. In the arithmetic-consistent variant the running-balance column is recomputed so the maths still ties — only the pixels betray it. In the broken variant the cross-field check catches the inconsistency.",
  },
  {
    img: "examples/ex_salary_netpay.png",
    title: "Payslip — net pay inflated",
    tags: [["forensic", "pro"], ["model", "learned"]],
    body: "Take-home pay repainted, with the bold weight and scan softness matched to the surrounding print. Seamless to the eye; the model is trained to localize exactly this kind of edit.",
  },
];

// Full-document localization overlays (committed demo renders — the detector's boxed regions).
const LOCALIZED = [
  {
    img: "demo/PKT-0010_0.png",
    title: "Forged Form 16 — localized",
    body: "An income figure was white-boxed and redrawn. Pixel forensics + a render→OCR cross-check flag the exact box; the verdict cites it as evidence.",
  },
  {
    img: "demo/PKT-0028_0.png",
    title: "Tampered encumbrance — localized",
    body: "An encumbrance certificate doctored to read 'NIL' while the registry still shows an active charge. The altered row is boxed and raised as a critical semantic hit.",
  },
];

function LayerTag({ id, label }) {
  const ly = L[id] || { hue: C.accent };
  return <Badge c={ly.hue}>{label}</Badge>;
}

function CaseImage({ src, alt }) {
  return (
    <div style={{ borderRadius: radius.md, overflow: "hidden", border: `1px solid ${C.border}`, background: "#f4f6fa", boxShadow: shadow.sm }}>
      <img src={src} alt={alt} style={{ display: "block", width: "100%", height: "auto" }} />
    </div>
  );
}

export default function Examples() {
  return (
    <div style={{ paddingBottom: 64 }}>
      {/* header */}
      <section style={{ ...wrap, padding: "48px 24px 8px" }}>
        <Reveal>
          <SectionHeader eyebrow="Annotated examples"
            title="Seamless edits — and how we catch them"
            subtitle="Every example is synthetic (zero PII). The crops show a genuine figure above the tampered one; in most cases you can't tell which was edited — that's the point. Each is tagged with the layer that catches it." />
        </Reveal>
      </section>

      {/* seamless before/after crops */}
      <section style={{ ...wrap, padding: "20px 24px" }}>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
          {SEAMLESS.map((c, i) => (
            <Reveal key={c.title} delay={(i % 2) * 80}>
              <Card pad={16} style={{ height: "100%" }}>
                <CaseImage src={c.img} alt={c.title} />
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "14px 0 8px" }}>
                  <span style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: -0.2 }}>{c.title}</span>
                  <span style={{ flex: 1 }} />
                  {c.tags.map(([id, label]) => <LayerTag key={id + label} id={id} label={label} />)}
                </div>
                <p style={{ margin: 0, fontSize: 12.8, color: C.textDim, lineHeight: 1.6 }}>{c.body}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* full-document localization */}
      <section style={{ ...wrap, padding: "28px 24px 8px" }}>
        <Reveal>
          <SectionHeader eyebrow="In the document" accent={L.forensic.hue}
            title="Localized, not just flagged"
            subtitle="The detector boxes the exact region it found — so every verdict points at evidence a reviewer can see." />
        </Reveal>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", marginTop: 20 }}>
          {LOCALIZED.map((c, i) => (
            <Reveal key={c.title} delay={(i % 2) * 80}>
              <Card pad={16} style={{ height: "100%" }}>
                <CaseImage src={c.img} alt={c.title} />
                <div style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: -0.2, margin: "14px 0 8px" }}>{c.title}</div>
                <p style={{ margin: 0, fontSize: 12.8, color: C.textDim, lineHeight: 1.6 }}>{c.body}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* honest note + CTA */}
      <section style={{ ...wrap, padding: "28px 24px 0" }}>
        <Reveal>
          <Card pad={18} tint={C.warning} style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
            <Badge c={C.warning} solid>HONEST LIMIT</Badge>
            <p style={{ margin: 0, flex: "1 1 320px", fontSize: 13, color: C.textDim, lineHeight: 1.6 }}>
              These are synthetic documents. On real phone-photos of ID cards the learned model does not yet
              transfer — so the guaranteed layer there is heuristics + semantic + QR (zero false positives),
              and the model stays opt-in. See the honest numbers on the Home page.
            </p>
          </Card>
        </Reveal>
        <Reveal style={{ textAlign: "center", marginTop: 26 }}>
          <Link to="/investigator" style={{ textDecoration: "none" }}>
            <Button variant="primary">Run the detector live →</Button>
          </Link>
        </Reveal>
      </section>
    </div>
  );
}
