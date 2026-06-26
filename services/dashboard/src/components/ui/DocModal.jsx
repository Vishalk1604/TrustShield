import React, { useEffect, useState } from "react";
import { color as C, hexA, radius, shadow, motion, maxWidth } from "../../theme.js";
import { Badge, Button } from "./primitives.jsx";
import BoxedImage from "./BoxedImage.jsx";
import { METHOD, DETECTOR_LABEL } from "../../data/methods.js";

const VERDICT_C = { EDITED: C.danger, SUSPICIOUS: C.warning, CLEAN: C.success };

// Full-screen lightbox for an example: the full document large (with the detected box on the edited
// view), a clean⇄edited toggle, and a "how it was caught" panel. `ex` is a DEMO_EXAMPLES record.
export default function DocModal({ ex, onClose }) {
  const [view, setView] = useState("edited");
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  if (!ex) return null;

  const m = METHOD[ex.method] || METHOD.none;
  const vc = VERDICT_C[ex.verdict] || C.info;
  const isEdited = view === "edited";
  const boxes = isEdited && ex.method !== "clean" ? ex.boxes : [];

  return (
    <div onClick={onClose} role="dialog" aria-modal="true"
      style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(3,5,10,0.8)",
        backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: 20,
        animation: `ts-fade-in ${motion.base} ${motion.ease}` }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "min(1040px, 96vw)", maxHeight: "92vh", overflow: "auto", maxWidth,
          background: C.bgRaised, border: `1px solid ${C.borderStrong}`, borderRadius: radius.xl,
          boxShadow: shadow.lg }}>
        {/* header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 18px",
          borderBottom: `1px solid ${C.border}`, position: "sticky", top: 0, background: C.bgRaised, zIndex: 1 }}>
          <Badge c={vc} solid>{ex.verdict}</Badge>
          <span style={{ fontWeight: 700, color: C.text, fontSize: 15, letterSpacing: -0.2 }}>{ex.title}</span>
          <span style={{ flex: 1 }} />
          <Button variant="ghost" onClick={onClose} style={{ padding: "6px 12px" }}>✕ Close</Button>
        </div>

        {/* body */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(260px, 1fr)", gap: 18, padding: 18 }}
          className="ts-docmodal-grid">
          {/* image + toggle */}
          <div>
            <div style={{ display: "inline-flex", gap: 6, marginBottom: 10, background: "rgba(148,163,184,0.06)",
              border: `1px solid ${C.border}`, borderRadius: radius.pill, padding: 3 }}>
              {["clean", "edited"].map((v) => (
                <button key={v} onClick={() => setView(v)} style={{
                  cursor: "pointer", border: "none", borderRadius: radius.pill, padding: "5px 14px",
                  fontSize: 12.5, fontWeight: 700, transition: `all ${motion.fast} ${motion.ease}`,
                  background: view === v ? (v === "edited" ? hexA(vc, 0.18) : hexA(C.success, 0.16)) : "transparent",
                  color: view === v ? (v === "edited" ? vc : C.success) : C.textDim }}>
                  {v === "clean" ? "Genuine" : "As submitted"}
                </button>
              ))}
            </div>
            <BoxedImage src={ex[isEdited ? "edited_img" : "clean_img"]} alt={ex.title}
              boxes={boxes} imgW={ex.w} imgH={ex.h} hue={m.hue}
              label={boxes.length ? "detected region" : null} />
            <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 8, textAlign: "center" }}>
              {boxes.length ? "◼ the box is where our system localized the edit" : "full synthetic document (zero PII)"}
            </div>
          </div>

          {/* how it was caught */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: 1.2, textTransform: "uppercase", color: C.textFaint, marginBottom: 8 }}>How it was caught</div>
              <Badge c={m.hue}>{m.label}{ex.detector ? ` · ${DETECTOR_LABEL[ex.detector] || ex.detector}` : ""}</Badge>
              <p style={{ margin: "10px 0 0", fontSize: 12.8, color: C.textDim, lineHeight: 1.6 }}>{m.blurb}</p>
            </div>

            <div style={{ display: "flex", gap: 18 }}>
              <div>
                <div style={{ fontSize: 26, fontWeight: 800, color: vc, lineHeight: 1 }}>{ex.trust}<span style={{ fontSize: 13, color: C.textFaint }}>/100</span></div>
                <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 3 }}>trust score</div>
              </div>
              {ex.difficulty && ex.difficulty !== "clean" && (
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.text, lineHeight: 1, textTransform: "capitalize" }}>{ex.difficulty}</div>
                  <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 5 }}>edit difficulty</div>
                </div>
              )}
            </div>

            {ex.old_value && ex.new_value && (
              <div style={{ background: "rgba(148,163,184,0.05)", border: `1px solid ${C.border}`, borderRadius: radius.md, padding: 12 }}>
                <div style={{ fontSize: 11, color: C.textFaint, marginBottom: 6 }}>what changed</div>
                <div style={{ fontSize: 13.5, fontFamily: "monospace" }}>
                  <span style={{ color: C.success }}>{ex.old_value}</span>
                  <span style={{ color: C.textFaint }}>  →  </span>
                  <span style={{ color: vc, fontWeight: 700 }}>{ex.new_value}</span>
                </div>
              </div>
            )}

            {ex.finding && (
              <div style={{ borderLeft: `2px solid ${hexA(m.hue, 0.6)}`, paddingLeft: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 4 }}>{ex.finding.title}</div>
                <p style={{ margin: 0, fontSize: 12.4, color: C.textDim, lineHeight: 1.55 }}>{ex.finding.description}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
