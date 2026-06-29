import React, { useEffect, useState } from "react";
import { color as C, hexA, radius, shadow, motion, maxWidth } from "../../theme.js";
import { Badge, Button } from "./primitives.jsx";
import BoxedImage from "./BoxedImage.jsx";
import { METHOD } from "../../data/methods.js";

const VERDICT_C = { EDITED: C.danger, CLEAN: C.success };

// Full-screen viewer for the documents inside a loan packet: page large via BoxedImage, a marking
// toggle (only when the doc carries a detected edit), and Prev/Next to step through the packet's docs.
// `docs` is the baked DEMO_DECISIONS[pkt].documents array. Keyboard: Esc close, ←/→ navigate.
export default function PacketDocsModal({ docs, startIndex = 0, onClose }) {
  const [i, setI] = useState(startIndex);
  const [showMark, setShowMark] = useState(true);

  const go = (ni) => { setI((ni + docs.length) % docs.length); setShowMark(true); };
  useEffect(() => {
    const k = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") go(i + 1);
      else if (e.key === "ArrowLeft") go(i - 1);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [i, docs.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!docs || !docs.length) return null;
  const d = docs[i];
  const m = METHOD[d.method] || METHOD.none;
  const vc = VERDICT_C[d.verdict] || C.info;
  const hasMark = d.edited && (d.boxes?.length || 0) > 0;
  const boxes = hasMark && showMark ? d.boxes : [];
  const label = (d.doc_type || "document").replace(/_/g, " ");

  return (
    <div onClick={onClose} role="dialog" aria-modal="true"
      style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(3,5,10,0.8)",
        backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: 20,
        animation: `ts-fade-in ${motion.base} ${motion.ease}` }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "min(900px, 96vw)", maxHeight: "94vh", display: "flex", flexDirection: "column", maxWidth,
          background: C.bgRaised, border: `1px solid ${C.borderStrong}`, borderRadius: radius.xl, boxShadow: shadow.lg,
          overflow: "hidden" }}>
        {/* header + controls — pinned; the page scrolls beneath them */}
        <div style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.bgRaised }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 18px" }}>
            <Badge c={vc} solid>{d.verdict}</Badge>
            <span style={{ fontWeight: 700, color: C.text, fontSize: 15, letterSpacing: -0.2, textTransform: "capitalize" }}>{label}</span>
            {hasMark && <Badge c={m.hue}>{m.label}</Badge>}
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 12, color: C.textFaint }}>{i + 1} / {docs.length}</span>
            <Button variant="ghost" onClick={onClose} style={{ padding: "6px 12px" }}>✕ Close</Button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 18px 12px", flexWrap: "wrap" }}>
            {hasMark ? (
              <button onClick={() => setShowMark((s) => !s)}
                style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 7,
                  border: `1px solid ${showMark ? hexA(m.hue, 0.5) : C.border}`, borderRadius: radius.pill, padding: "6px 13px",
                  fontSize: 12.5, fontWeight: 700, background: showMark ? hexA(m.hue, 0.16) : "transparent",
                  color: showMark ? m.hue : C.textDim, transition: `all ${motion.fast} ${motion.ease}` }}>
                <span style={{ width: 9, height: 9, borderRadius: 2, border: "2px solid currentColor" }} />
                {showMark ? "Marking on" : "Marking off"}
              </button>
            ) : (
              <span style={{ fontSize: 12, color: C.textFaint }}>No edit detected in this document.</span>
            )}
            <span style={{ flex: 1 }} />
            <Button variant="ghost" onClick={() => go(i - 1)} disabled={docs.length < 2}>◀ Prev</Button>
            <Button variant="ghost" onClick={() => go(i + 1)} disabled={docs.length < 2}>Next ▶</Button>
          </div>
        </div>

        {/* page — scrolls; BoxedImage renders the FULL page at natural height so the SVG boxes stay aligned */}
        <div style={{ overflow: "auto", padding: "14px 18px 18px" }}>
          <div style={{ maxWidth: 760, margin: "0 auto" }}>
            <BoxedImage src={d.img} alt={label} boxes={boxes} imgW={d.w} imgH={d.h} hue={m.hue}
              label={boxes.length ? "detected edit" : null} />
          </div>
          <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 8, textAlign: "center" }}>
            {hasMark ? (showMark ? "◼ where the pipeline localized the edit — toggle “Marking” to compare"
              : "marking hidden — toggle it back on to see the detected region")
              : "full document page (synthetic, zero PII)"}
          </div>
          {hasMark && d.finding && (
            <div style={{ marginTop: 12, borderLeft: `2px solid ${hexA(m.hue, 0.6)}`, paddingLeft: 12, maxWidth: 760, margin: "12px auto 0" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 4 }}>{d.finding.title}</div>
              <p style={{ margin: 0, fontSize: 12.4, color: C.textDim, lineHeight: 1.55 }}>{d.finding.description}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
