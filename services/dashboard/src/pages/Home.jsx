import React, { useState } from "react";
import { Link } from "react-router-dom";
import { color as C, layer as L, maxWidth, hexA, radius, shadow, motion } from "../theme.js";
import { Card, Badge, Stat, SectionHeader, Button } from "../components/ui/primitives.jsx";
import PipelineDiagram from "../components/ui/PipelineDiagram.jsx";
import Reveal from "../components/ui/Reveal.jsx";
import HoverLoupe from "../components/ui/HoverLoupe.jsx";
import LocalFirstBadge from "../components/LocalFirstBadge.jsx";
import { HOME_REVEAL } from "../data/homeReveal.js";

const wrap = { maxWidth, margin: "0 auto", padding: "0 24px" };

// ── small inline glyphs for the features grid (no icon-font / CDN — local-only) ──
const g = (d) => (p) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...p}>{d}</svg>
);
const ICON = {
  scan: g(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M8 4v16" /></>),
  id: g(<><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="8.5" cy="11" r="2" /><path d="M13 9h5M13 13h5M5 16c0-1.7 1.3-3 3.5-3s3.5 1.3 3.5 3" /></>),
  brain: g(<><path d="M9 4a3 3 0 00-3 3 3 3 0 00-1 5 3 3 0 003 4 2.5 2.5 0 005 0V5a2 2 0 00-2-1z" /><path d="M15 4a3 3 0 013 3 3 3 0 011 5 3 3 0 01-3 4" /></>),
  gauge: g(<><path d="M4 18a8 8 0 1116 0" /><path d="M12 18l4-5" /><circle cx="12" cy="18" r="1.3" /></>),
  graph: g(<><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="8" r="2.2" /><circle cx="9" cy="18" r="2.2" /><path d="M7.8 7.4l6.6 1.4M7.4 7.8l1 8.2M10.8 17l5.6-7" /></>),
  wallet: g(<><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M16 14h2" /></>),
  lock: g(<><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></>),
  list: g(<><path d="M8 6h12M8 12h12M8 18h12" /><circle cx="4" cy="6" r="1.2" /><circle cx="4" cy="12" r="1.2" /><circle cx="4" cy="18" r="1.2" /></>),
};

const FEATURES = [
  { icon: "scan", hue: L.forensic.hue, title: "Pixel forensics", body: "ELA, sensor-noise loss, copy-move, JPEG-ghost & screen-recapture — finds painted numbers and splices in scans and phone photos." },
  { icon: "id", hue: L.semantic.hue, title: "Semantic ID + QR", body: "Validates PAN / Aadhaar structure and cross-checks the card's signed QR against the printed text — catches valid-looking but wrong edits." },
  { icon: "brain", hue: L.model.hue, title: "Learned forgery model", body: "Our own U-Net localizes seamless edits the hand-tuned heuristics miss. Opt-in, with honestly-measured limits." },
  { icon: "gauge", hue: L.trust.hue, title: "Trust score + evidence", body: "A weighted, documented blend → a 0–100 trust score, an ordered evidence chain, and a recommended action you can defend." },
  { icon: "graph", hue: L.graph.hue, title: "Cross-application graph", body: "Links fraud rings and double-financed collateral across separate loan applications — patterns no single file reveals." },
  { icon: "wallet", hue: C.accent, title: "KYC + underwriting", body: "Establishes identity & address, reconciles declared vs proven income, and computes FOIR / affordability." },
  { icon: "list", hue: C.success, title: "Always explainable", body: "Never a score without an evidence chain. Every verdict cites the exact finding, severity, and the region it came from." },
  { icon: "lock", hue: "#a7f3d0", title: "100% on-device", body: "No document, number, or byte leaves the machine. External verifications are local mock adapters — provably no network." },
];

export default function Home() {
  const [revealed, setRevealed] = useState(false);

  return (
    <div>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section style={{ padding: "76px 24px 40px", background: "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(56,189,248,0.16), transparent)" }}>
        <div style={{ maxWidth, margin: "0 auto", textAlign: "center" }}>
          <Reveal style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
            <LocalFirstBadge />
          </Reveal>
          <Reveal delay={60} as="h1" style={{ fontSize: 46, lineHeight: 1.08, margin: "0 0 16px", letterSpacing: -1.2, fontWeight: 800 }}>
            Catch forged loan documents.<br />
            <span style={{ color: C.accent }}>Explain every verdict.</span>
          </Reveal>
          <Reveal delay={120} as="p" style={{ fontSize: 17.5, color: C.textDim, maxWidth: 660, margin: "0 auto 28px", lineHeight: 1.62 }}>
            TrustShield is a 100% local-first underwriting copilot. It inspects every document in a loan
            packet for tampering and forgery, then returns an explainable <strong style={{ color: C.text }}>trust
            score (0–100)</strong> with a full evidence chain and a recommended action — and no data ever
            leaves the device.
          </Reveal>
          <Reveal delay={180} style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <Link to="/investigator" style={{ textDecoration: "none" }}>
              <Button variant="primary">Watch it catch a forgery →</Button>
            </Link>
            <Link to="/examples" style={{ textDecoration: "none" }}>
              <Button variant="ghost">See annotated examples</Button>
            </Link>
          </Reveal>
          <Reveal delay={260} style={{ display: "flex", gap: 28, justifyContent: "center", flexWrap: "wrap", marginTop: 40 }}>
            {[
              { v: "1.0", l: "precision on clean docs", s: "zero false positives" },
              { v: "5", l: "detection layers", s: "one explainable score" },
              { v: "0", l: "bytes leave the device", s: "100% on-device" },
            ].map((s) => <Stat key={s.l} value={s.v} label={s.l} sub={s.s} align="center" />)}
          </Reveal>
        </div>
      </section>

      {/* ── R2 · The problem: spot the edit ──────────────────────────────── */}
      <section style={{ ...wrap, padding: "44px 24px" }}>
        <Reveal>
          <SectionHeader eyebrow="The problem" accent={C.danger}
            title="A seamless edit slips past the human eye"
            subtitle="Fraudsters inflate income on a Form 16, a bank statement, a payslip — or swap a digit on a PAN/Aadhaar — with no hard edges and matched fonts. One of the two pages below has a repainted salary figure. Hover to magnify the same spot on both — can you tell which?" />
        </Reveal>
        <Reveal delay={80} style={{ marginTop: 22 }}>
          <Card pad={20} style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
            <HoverLoupe data={HOME_REVEAL} revealed={revealed} />
            <div style={{ flex: "1 1 220px", minWidth: 220 }}>
              <p style={{ margin: "0 0 14px", color: C.textDim, fontSize: 13.5, lineHeight: 1.6 }}>
                The repaint erased the page's microscopic sensor-noise floor inside the edited box — invisible
                to you, a fingerprint to us. <strong style={{ color: C.text }}>Hover either page</strong> to
                compare the same area side-by-side; reveal the answer to see exactly where our model localized it.
              </p>
              <Button variant={revealed ? "ghost" : "primary"} c={C.danger} onClick={() => setRevealed((r) => !r)}>
                {revealed ? "Hide the answer" : "Reveal the edit"}
              </Button>
            </div>
          </Card>
        </Reveal>
      </section>

      {/* ── R3 · How it works: the 5-layer pipeline ──────────────────────── */}
      <section style={{ ...wrap, padding: "44px 24px" }}>
        <Reveal>
          <SectionHeader eyebrow="How it works"
            title="Five layers, one explainable score"
            subtitle="Each document flows through five independent detectors. They corroborate each other and roll up into a single trust score with an evidence chain — so every decision is auditable." />
        </Reveal>
        <Reveal delay={80} style={{ marginTop: 22 }}>
          <PipelineDiagram mode="cards" />
        </Reveal>
      </section>

      {/* ── R4 · Key features ────────────────────────────────────────────── */}
      <section style={{ ...wrap, padding: "44px 24px" }}>
        <Reveal>
          <SectionHeader eyebrow="Capabilities" title="Everything in the box" />
        </Reveal>
        <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(248px, 1fr))", marginTop: 22 }}>
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 4) * 70}>
              <Card pad={18} style={{ height: "100%" }}>
                <span style={{ display: "inline-flex", width: 40, height: 40, borderRadius: 11, alignItems: "center", justifyContent: "center", color: f.hue, background: hexA(f.hue, 0.12), border: `1px solid ${hexA(f.hue, 0.36)}`, marginBottom: 12 }}>
                  {ICON[f.icon]()}
                </span>
                <div style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: -0.2, marginBottom: 6 }}>{f.title}</div>
                <p style={{ margin: 0, fontSize: 12.8, color: C.textDim, lineHeight: 1.55 }}>{f.body}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── R5 · Proof / results (honest) ────────────────────────────────── */}
      <section style={{ ...wrap, padding: "44px 24px 8px" }}>
        <Reveal>
          <SectionHeader eyebrow="Proof" accent={C.success}
            title="Measured, and reported honestly"
            subtitle="Numbers from our own evaluation harness on a realistic synthetic corpus (95 clean + 874 tampered documents, train/val/test split). We report what doesn't work, too." />
        </Reveal>
        <Reveal delay={70} style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", marginTop: 22 }}>
          {[
            { v: "0 / 95", l: "false positives on clean docs", s: "heuristics precision 1.0", c: C.success },
            { v: "5 layers", l: "corroborating detectors", s: "one auditable verdict", c: C.accent },
            { v: "0.00 → 0.29", l: "seamless 'pro' edits caught", s: "heuristics miss → learned model", c: L.model.hue },
            { v: "no network", l: "calls at runtime", s: "verify_local_only enforces it", c: "#a7f3d0" },
          ].map((s) => (
            <Card key={s.l} pad={18} tint={s.c}>
              <Stat value={s.v} label={s.l} sub={s.s} accent={s.c} />
            </Card>
          ))}
        </Reveal>
        <Reveal delay={140} style={{ marginTop: 16 }}>
          <Card pad={18} tint={C.warning} style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
            <Badge c={C.warning} solid>HONEST LIMIT</Badge>
            <p style={{ margin: 0, flex: "1 1 320px", fontSize: 13, color: C.textDim, lineHeight: 1.6 }}>
              The learned model is strong on synthetic documents but does <strong style={{ color: C.text }}>not yet
              transfer to real phone-photos of ID cards</strong> (the synthetic→real gap). So the
              guaranteed-local detection layer is heuristics + semantic + QR (which hold zero false positives
              on real docs), and the model stays opt-in. We'd rather show the gap than hide it.
            </p>
          </Card>
        </Reveal>
      </section>

      {/* ── Closing CTA ──────────────────────────────────────────────────── */}
      <section style={{ ...wrap, padding: "32px 24px 72px" }}>
        <Reveal>
          <Card pad={28} tint={C.accent} glow style={{ textAlign: "center" }}>
            <h2 style={{ margin: "0 0 8px", fontSize: 24, fontWeight: 800, letterSpacing: -0.5 }}>See it run on a real loan packet</h2>
            <p style={{ margin: "0 auto 20px", maxWidth: 560, color: C.textDim, fontSize: 14.5, lineHeight: 1.6 }}>
              Open the Investigator, pick a curated case — a forged Form 16, a tampered encumbrance, a
              double-financing ring — and watch the five layers light up into one explainable verdict.
            </p>
            <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
              <Link to="/investigator" style={{ textDecoration: "none" }}><Button variant="primary">Open the Investigator →</Button></Link>
              <Link to="/examples" style={{ textDecoration: "none" }}><Button variant="ghost">Browse examples</Button></Link>
            </div>
          </Card>
        </Reveal>
      </section>
    </div>
  );
}
