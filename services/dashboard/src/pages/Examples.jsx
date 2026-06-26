import React, { useState } from "react";
import { Link } from "react-router-dom";
import { color as C, layer as L, maxWidth, hexA, radius, shadow } from "../theme.js";
import { Card, Badge, SectionHeader, Button } from "../components/ui/primitives.jsx";
import BoxedImage from "../components/ui/BoxedImage.jsx";
import DocModal from "../components/ui/DocModal.jsx";
import Reveal from "../components/ui/Reveal.jsx";
import { DEMO_EXAMPLES } from "../data/demoExamples.js";
import { METHOD, DETECTOR_LABEL } from "../data/methods.js";

const wrap = { maxWidth, margin: "0 auto", padding: "0 24px" };
const VERDICT_C = { EDITED: C.danger, SUSPICIOUS: C.warning, CLEAN: C.success };
const byKey = Object.fromEntries(DEMO_EXAMPLES.map((e) => [e.key, e]));

const CAUGHT = DEMO_EXAMPLES.filter((e) => (e.method === "model" || e.method === "pixel") && e.boxes.length && e.key !== "form16_pro");
const EVADED = DEMO_EXAMPLES.filter((e) => e.method === "none");

// One detection case — the edited doc with the real detected box, the method, and an "open" action.
function ExampleCard({ ex, onOpen }) {
  const m = METHOD[ex.method] || METHOD.none;
  const vc = VERDICT_C[ex.verdict] || C.info;
  const caught = ex.boxes.length > 0 && ex.method !== "clean" && ex.method !== "none";
  return (
    <Card pad={14} style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <BoxedImage src={ex.edited_img} alt={ex.title} boxes={caught ? ex.boxes : []} imgW={ex.w} imgH={ex.h}
        hue={m.hue} label={caught ? "detected" : null} onClick={() => onOpen(ex)} style={{ maxHeight: 220 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", margin: "12px 0 8px" }}>
        <Badge c={vc} solid>{ex.verdict}</Badge>
        <Badge c={m.hue}>{m.label}{ex.detector ? ` · ${DETECTOR_LABEL[ex.detector] || ex.detector}` : ""}</Badge>
      </div>
      <div style={{ fontSize: 14.5, fontWeight: 700, color: C.text, letterSpacing: -0.2 }}>{ex.title}</div>
      <p style={{ margin: "6px 0 12px", fontSize: 12.6, color: C.textDim, lineHeight: 1.55, flex: 1 }}>{ex.blurb}</p>
      <Button variant="ghost" c={m.hue} onClick={() => onOpen(ex)} style={{ alignSelf: "flex-start" }}>Open full document →</Button>
    </Card>
  );
}

export default function Examples() {
  const [open, setOpen] = useState(null);
  const star = byKey["form16_pro"];

  return (
    <div style={{ paddingBottom: 64 }}>
      {/* header */}
      <section style={{ ...wrap, padding: "48px 24px 8px" }}>
        <Reveal>
          <SectionHeader eyebrow="Annotated examples"
            title="What we detect — and exactly how"
            subtitle="Every case is a synthetic document (zero PII). The box is where our system ACTUALLY localized the edit; the tag says HOW it was caught — the learned model, pixel forensics, or cross-referencing the numbers. Click any document to open it full-size." />
        </Reveal>
      </section>

      {/* ── Model spotlight (the seamless edit the model catches) ─────────────── */}
      {star && (
        <section style={{ ...wrap, padding: "22px 24px" }}>
          <Reveal>
            <Card pad={18} tint={L.model.hue} glow>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.1fr) minmax(260px,1fr)", gap: 20, alignItems: "center" }} className="ts-docmodal-grid">
                <BoxedImage src={star.edited_img} alt={star.title} boxes={star.boxes} imgW={star.w} imgH={star.h}
                  hue={L.model.hue} label="our model localized this" onClick={() => setOpen(star)} style={{ maxHeight: 300 }} />
                <div>
                  <Badge c={L.model.hue}>Showcase · Learned model</Badge>
                  <h2 style={{ margin: "12px 0 8px", fontSize: 22, fontWeight: 800, letterSpacing: -0.4, color: C.text }}>
                    A seamless edit the pixel heuristics miss — our model catches it
                  </h2>
                  <p style={{ margin: "0 0 12px", fontSize: 13.5, color: C.textDim, lineHeight: 1.6 }}>
                    The gross-salary figure on this Form 16 was inflated with matched font, ink tone and
                    scan-noise — invisible to the eye and to the hand-tuned detectors. Our forgery-localization
                    <b style={{ color: L.model.hue }}> U-Net</b> still boxes the exact figure.
                    {star.old_value && star.new_value && (
                      <> <span style={{ fontFamily: "monospace", color: C.success }}>{star.old_value}</span>
                        <span style={{ color: C.textFaint }}> → </span>
                        <span style={{ fontFamily: "monospace", color: C.danger, fontWeight: 700 }}>{star.new_value}</span>.</>
                    )}
                  </p>
                  <p style={{ margin: "0 0 14px", fontSize: 12, color: C.textFaint, lineHeight: 1.55 }}>
                    Honest scope: the model is strong on synthetic documents (where it's trained) and stays
                    opt-in; it doesn't yet transfer to real phone-photos of ID cards. The default runtime is
                    the zero-false-positive heuristics.
                  </p>
                  <Button variant="primary" c={L.model.hue} onClick={() => setOpen(star)}>Open full document →</Button>
                </div>
              </div>
            </Card>
          </Reveal>
        </section>
      )}

      {/* ── Localized cases (model + pixel) ───────────────────────────────────── */}
      <section style={{ ...wrap, padding: "20px 24px" }}>
        <Reveal><SectionHeader eyebrow="Localized" title="Detected and boxed" subtitle="The model and the pixel-forensic detectors, each catching a different kind of edit." /></Reveal>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", marginTop: 20 }}>
          {CAUGHT.map((ex, i) => <Reveal key={ex.key} delay={(i % 3) * 70}><ExampleCard ex={ex} onOpen={setOpen} /></Reveal>)}
        </div>
      </section>

      {/* ── Seamless edits that evade the pixels → cross-reference ─────────────── */}
      {EVADED.length > 0 && (
        <section style={{ ...wrap, padding: "28px 24px" }}>
          <Reveal>
            <SectionHeader eyebrow="The hard cases" accent={C.textDim}
              title="So seamless they leave no pixel trace"
              subtitle="These edits matched the page perfectly — every pixel detector reads them as CLEAN. That's not a failure to hide; it's the honest reason the next layer exists: cross-referencing the numbers." />
          </Reveal>
          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", marginTop: 20 }}>
            {EVADED.map((ex, i) => (
              <Reveal key={ex.key} delay={(i % 3) * 70}>
                <Card pad={14} style={{ height: "100%", display: "flex", flexDirection: "column", opacity: 0.96 }}>
                  <BoxedImage src={ex.edited_img} alt={ex.title} boxes={[]} imgW={ex.w} imgH={ex.h} onClick={() => setOpen(ex)} style={{ maxHeight: 200 }} />
                  <div style={{ display: "flex", gap: 7, flexWrap: "wrap", margin: "12px 0 8px" }}>
                    <Badge c={C.success} solid>reads CLEAN</Badge>
                    <Badge c={C.textFaint}>evades pixel forensics</Badge>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{ex.title}</div>
                  <p style={{ margin: "6px 0 0", fontSize: 12.4, color: C.textDim, lineHeight: 1.55 }}>{ex.blurb}</p>
                </Card>
              </Reveal>
            ))}
          </div>
        </section>
      )}

      {/* ── Cross-referencing the numbers (the packet / cross-document method) ─── */}
      <section style={{ ...wrap, padding: "28px 24px" }}>
        <Reveal>
          <SectionHeader eyebrow="Cross-reference" accent={L.semantic.hue}
            title="When the pixels are perfect, the numbers still disagree"
            subtitle="Across a loan packet, the same income is stated many times. A forger rarely fixes them all — so we cross-check them." />
        </Reveal>
        <Reveal delay={80} style={{ marginTop: 20 }}>
          <Card pad={18} tint={L.semantic.hue} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(280px,1.1fr)", gap: 20, alignItems: "center" }} className="ts-docmodal-grid">
            <div style={{ display: "flex", gap: 12 }}>
              <BoxedImage src="examples/realistic_form16_edited.jpg" alt="Form 16" boxes={[]} style={{ flex: 1, maxHeight: 200 }} />
              <BoxedImage src="examples/realistic_bank.png" alt="Bank statement" boxes={[]} style={{ flex: 1, maxHeight: 200 }} />
            </div>
            <div>
              <Badge c={L.semantic.hue}>Semantic · cross-document</Badge>
              <div style={{ margin: "12px 0", display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "8px 12px", background: "rgba(148,163,184,0.05)", border: `1px solid ${C.border}`, borderRadius: radius.md }}>
                  <span style={{ color: C.textDim }}>Form 16 declares</span><span style={{ fontFamily: "monospace", color: C.text, fontWeight: 700 }}>₹18,20,000 / yr</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "8px 12px", background: "rgba(148,163,184,0.05)", border: `1px solid ${C.border}`, borderRadius: radius.md }}>
                  <span style={{ color: C.textDim }}>Bank salary credits imply</span><span style={{ fontFamily: "monospace", color: C.danger, fontWeight: 700 }}>≈ ₹8,19,000 / yr</span>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: 12.8, color: C.textDim, lineHeight: 1.6 }}>
                Each document is pixel-perfect, but the declared income and the banked income don't reconcile —
                flagged as a <b style={{ color: L.semantic.hue }}>cross-document inconsistency</b>. The same layer
                catches a tampered encumbrance vs the CERSAI registry, and an inflated valuation vs market value.
              </p>
              <Link to="/investigator" style={{ textDecoration: "none" }}>
                <Button variant="ghost" c={L.semantic.hue} style={{ marginTop: 12 }}>See it in a full packet →</Button>
              </Link>
            </div>
          </Card>
        </Reveal>
      </section>

      {/* honest note + CTA */}
      <section style={{ ...wrap, padding: "20px 24px 0" }}>
        <Reveal>
          <Card pad={18} tint={C.warning} style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
            <Badge c={C.warning} solid>HONEST LIMIT</Badge>
            <p style={{ margin: 0, flex: "1 1 320px", fontSize: 13, color: C.textDim, lineHeight: 1.6 }}>
              These are synthetic documents, where the learned model works. On real phone-photos of ID cards it
              does not yet transfer — so the guaranteed layer there is the zero-false-positive heuristics +
              semantic + QR, and the model stays opt-in. See the honest numbers on the Home page.
            </p>
          </Card>
        </Reveal>
        <Reveal style={{ textAlign: "center", marginTop: 26 }}>
          <Link to="/investigator" style={{ textDecoration: "none" }}>
            <Button variant="primary">Run the detector live →</Button>
          </Link>
        </Reveal>
      </section>

      {open && <DocModal ex={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
