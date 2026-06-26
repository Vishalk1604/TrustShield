import React from "react";
import { color as C, hexA, radius, shadow } from "../../theme.js";

// An image with detected-region boxes overlaid via SVG. `boxes` are [x0,y0,x1,y1] in the IMAGE's own
// pixel coordinates; with viewBox = natural size and non-scaling strokes the rectangle stays aligned
// and crisp at any rendered size — no JS measuring. `hue` colors the box; `label` is a corner chip.
export default function BoxedImage({ src, alt = "", boxes = [], imgW, imgH, hue = C.accent,
                                    label, rounded = radius.md, bg = "#0e131c", style, onClick }) {
  const showBoxes = boxes.length > 0 && imgW && imgH;
  return (
    <div
      onClick={onClick}
      style={{ position: "relative", lineHeight: 0, borderRadius: rounded, overflow: "hidden",
               background: bg, border: `1px solid ${C.border}`, boxShadow: shadow.sm,
               cursor: onClick ? "zoom-in" : "default", ...style }}
    >
      <img src={src} alt={alt} style={{ display: "block", width: "100%", height: "auto" }} />
      {showBoxes && (
        <svg viewBox={`0 0 ${imgW} ${imgH}`} preserveAspectRatio="none" aria-hidden
             style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
          {boxes.map((b, i) => (
            <rect key={i} x={b[0]} y={b[1]} width={Math.max(1, b[2] - b[0])} height={Math.max(1, b[3] - b[1])}
                  fill={hexA(hue, 0.1)} stroke={hue} strokeWidth={2.5} vectorEffect="non-scaling-stroke" rx={2} />
          ))}
        </svg>
      )}
      {label && (
        <span style={{ position: "absolute", top: 8, left: 8, fontSize: 10.5, fontWeight: 800,
                       letterSpacing: 0.3, color: "#04131c", background: hexA(hue, 0.95),
                       padding: "3px 8px", borderRadius: radius.pill, lineHeight: 1.2 }}>
          {label}
        </span>
      )}
    </div>
  );
}
