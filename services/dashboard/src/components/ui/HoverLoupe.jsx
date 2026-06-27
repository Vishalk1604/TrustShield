import React, { useState, useRef } from "react";
import { color as C, layer as L, hexA, radius, shadow, motion } from "../../theme.js";

// Side-by-side "spot the edit" with a hover magnifier. Hovering either document shows a floating
// loupe that magnifies the SAME spot on BOTH the genuine and the submitted page, and — once revealed
// — draws our model's detection box on the submitted side. Pure inline-style/DOM, no deps.
//
// `data` = HOME_REVEAL: { clean_img, edited_img, w, h, box:[x0,y0,x1,y1]|null, method }.

const D = 150;        // loupe diameter (px)
const Z = 2.6;        // magnification

// object-fit:contain content rect inside an element rect, given the image's natural aspect.
function contentRect(elRect, natW, natH) {
  const elAR = elRect.width / elRect.height;
  const imgAR = natW / natH;
  let cw, ch;
  if (imgAR > elAR) { cw = elRect.width; ch = cw / imgAR; }
  else { ch = elRect.height; cw = ch * imgAR; }
  return { cw, ch, ox: elRect.left + (elRect.width - cw) / 2, oy: elRect.top + (elRect.height - ch) / 2 };
}

function Panel({ src, label, tone, revealed, onMove, onLeave }) {
  const lit = revealed && tone === "danger";
  return (
    <div style={{ flex: "1 1 240px", minWidth: 220 }}>
      <div onMouseMove={onMove} onMouseLeave={onLeave}
        style={{
          position: "relative", borderRadius: radius.lg, overflow: "hidden", background: "#11161f",
          border: `1px solid ${lit ? hexA(C.danger, 0.6) : C.border}`,
          boxShadow: lit ? shadow.glow(C.danger, 0.3) : shadow.md,
          transition: `border-color ${motion.slow} ${motion.ease}, box-shadow ${motion.slow} ${motion.ease}`,
          cursor: "crosshair",
        }}>
        <img src={src} alt={label} draggable={false}
          style={{ display: "block", width: "100%", height: 320, objectFit: "contain", objectPosition: "center",
            opacity: revealed && tone !== "danger" ? 0.92 : 1, pointerEvents: "none" }} />
        {revealed && (
          <div style={{
            position: "absolute", top: 10, left: 10,
            background: tone === "danger" ? hexA(C.danger, 0.94) : hexA(C.success, 0.94),
            color: "#04131c", fontWeight: 800, fontSize: 11.5, letterSpacing: 0.4,
            padding: "4px 10px", borderRadius: radius.pill,
          }}>{tone === "danger" ? "EDITED — gross salary inflated" : "GENUINE"}</div>
        )}
        <div style={{ position: "absolute", bottom: 8, right: 10, fontSize: 10.5, color: C.textFaint,
          background: hexA("#0a0e15", 0.6), borderRadius: radius.pill, padding: "2px 8px", pointerEvents: "none" }}>
          hover to magnify
        </div>
      </div>
      <div style={{ textAlign: "center", marginTop: 8, fontSize: 12, color: C.textFaint, fontWeight: 600 }}>{label}</div>
    </div>
  );
}

// One magnified circle: shows `src` zoomed at fractional (fx,fy); optionally draws `box` (image px).
function Lens({ src, fx, fy, natW, natH, box, hue, caption }) {
  // rendered content dims are irrelevant for zoom math if we zoom in *natural* space then fit:
  // place an img sized Z*natW × Z*natH and offset so (fx,fy) sits at the centre.
  const sw = Z * natW, sh = Z * natH;
  const left = D / 2 - fx * sw;
  const top = D / 2 - fy * sh;
  const boxEl = box ? {
    left: D / 2 + (box[0] - fx * natW) * Z,
    top: D / 2 + (box[1] - fy * natH) * Z,
    width: (box[2] - box[0]) * Z,
    height: (box[3] - box[1]) * Z,
  } : null;
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{
        width: D, height: D, borderRadius: "50%", overflow: "hidden", position: "relative",
        border: `2px solid ${hexA(hue, 0.7)}`, boxShadow: shadow.glow(hue, 0.25), background: "#0d1119",
      }}>
        <img src={src} alt="" draggable={false}
          style={{ position: "absolute", left, top, width: sw, height: sh, maxWidth: "none", imageRendering: "auto" }} />
        {boxEl && (
          <div style={{ position: "absolute", left: boxEl.left, top: boxEl.top, width: boxEl.width, height: boxEl.height,
            border: `2px solid ${hue}`, boxShadow: `0 0 0 1px ${hexA("#04131c", 0.6)}, 0 0 10px ${hexA(hue, 0.6)}`,
            borderRadius: 2 }} />
        )}
        {/* crosshair */}
        <div style={{ position: "absolute", left: D / 2 - 0.5, top: 0, width: 1, height: D, background: hexA("#fff", 0.18) }} />
        <div style={{ position: "absolute", top: D / 2 - 0.5, left: 0, height: 1, width: D, background: hexA("#fff", 0.18) }} />
      </div>
      <div style={{ fontSize: 10.5, color: caption.color, fontWeight: 700, marginTop: 5 }}>{caption.text}</div>
    </div>
  );
}

export default function HoverLoupe({ data, revealed }) {
  const [lens, setLens] = useState(null);   // { fx, fy, px, py } in viewport coords for the popup
  const wrapRef = useRef(null);
  const natW = data?.w || 1000, natH = data?.h || 1400;
  const showBox = revealed && Array.isArray(data?.box);
  const hue = L.model?.hue || C.accent;

  const onMove = (e) => {
    const cr = contentRect(e.currentTarget.getBoundingClientRect(), natW, natH);
    const fx = (e.clientX - cr.ox) / cr.cw;
    const fy = (e.clientY - cr.oy) / cr.ch;
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) { setLens(null); return; }
    setLens({ fx, fy, px: e.clientX, py: e.clientY });
  };
  const onLeave = () => setLens(null);

  // popup position — follow cursor, clamped to viewport
  const popW = D * 2 + 58, popH = D + 64;
  let popLeft = 0, popTop = 0;
  if (lens) {
    popLeft = Math.min(Math.max(lens.px + 22, 12), (typeof window !== "undefined" ? window.innerWidth : 1200) - popW - 12);
    popTop = Math.min(Math.max(lens.py - popH / 2, 12), (typeof window !== "undefined" ? window.innerHeight : 800) - popH - 12);
  }

  return (
    <div ref={wrapRef} style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start", flex: "1 1 auto" }}>
      <Panel src={data.clean_img} label="Document A" tone="success" revealed={revealed} onMove={onMove} onLeave={onLeave} />
      <Panel src={data.edited_img} label="Document B" tone="danger" revealed={revealed} onMove={onMove} onLeave={onLeave} />

      {lens && (
        <div style={{
          position: "fixed", left: popLeft, top: popTop, zIndex: 60, width: popW,
          background: C.bgRaised, border: `1px solid ${C.borderStrong}`, borderRadius: radius.lg,
          boxShadow: shadow.lg, padding: "14px 16px 12px", pointerEvents: "none",
          animation: `ts-fade-in ${motion.fast} ${motion.ease}`,
        }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 1, color: C.textFaint, textAlign: "center", marginBottom: 10 }}>
            MAGNIFIED — SAME SPOT, BOTH PAGES
          </div>
          <div style={{ display: "flex", gap: 18, justifyContent: "center" }}>
            <Lens src={data.clean_img} fx={lens.fx} fy={lens.fy} natW={natW} natH={natH} box={null}
              hue={C.success} caption={{ text: "Genuine", color: C.success }} />
            <Lens src={data.edited_img} fx={lens.fx} fy={lens.fy} natW={natW} natH={natH}
              box={showBox ? data.box : null} hue={showBox ? hue : C.danger}
              caption={showBox ? { text: "Submitted · model box", color: hue } : { text: "Submitted", color: C.danger }} />
          </div>
        </div>
      )}
    </div>
  );
}
