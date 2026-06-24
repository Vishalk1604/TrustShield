import React from "react";
import { color as C, glass, radius, motion, hexA, shadow } from "../../theme.js";

// Frosted-glass surface. `tint` biases the fill toward a layer hue; `glow` adds a colored halo.
export function Card({ tint = null, glow = false, fill, blur, pad = 18, style, children, ...rest }) {
  const base = glass({ tint, fill, blur });
  return (
    <div
      style={{
        ...base,
        padding: pad,
        boxShadow: glow && tint ? `${base.boxShadow}, ${shadow.glow(tint, 0.22)}` : base.boxShadow,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

// Small pill badge. Pass `c` (hex) to tint; `solid` for a filled look.
export function Badge({ c = C.accent, solid = false, style, children }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 0.4,
        borderRadius: radius.pill,
        padding: "3px 9px",
        color: solid ? "#04131c" : c,
        background: solid ? c : hexA(c, 0.12),
        border: `1px solid ${hexA(c, solid ? 0.7 : 0.4)}`,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

// Big stat for proof/header strips. `accent` colors the number.
export function Stat({ value, label, sub, accent = C.accent, align = "left" }) {
  return (
    <div style={{ textAlign: align }}>
      <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1, color: accent, letterSpacing: -0.5 }}>{value}</div>
      <div style={{ fontSize: 12.5, color: C.text, marginTop: 6, fontWeight: 600 }}>{label}</div>
      {sub && <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// Uppercase section eyebrow + optional title/subtitle.
export function SectionHeader({ eyebrow, title, subtitle, accent = C.accent, style }) {
  return (
    <div style={{ ...style }}>
      {eyebrow && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ width: 22, height: 2, background: accent, borderRadius: 2, boxShadow: shadow.glow(accent, 0.4) }} />
          <span style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: 1.6, textTransform: "uppercase", color: accent }}>{eyebrow}</span>
        </div>
      )}
      {title && <h2 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: -0.5, color: C.text }}>{title}</h2>}
      {subtitle && <p style={{ margin: "8px 0 0", color: C.textDim, fontSize: 14, lineHeight: 1.6, maxWidth: 640 }}>{subtitle}</p>}
    </div>
  );
}

// Button. variant: primary | ghost | subtle. `c` overrides the accent.
export function Button({ variant = "primary", c = C.accent, active = false, style, children, ...rest }) {
  const shared = {
    cursor: "pointer",
    borderRadius: radius.md,
    fontWeight: 700,
    fontSize: 13.5,
    padding: "10px 16px",
    transition: `all ${motion.base} ${motion.ease}`,
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
  };
  const variants = {
    primary: {
      background: `linear-gradient(180deg, ${c}, ${hexA(c, 0.75)})`,
      border: `1px solid ${hexA(c, 0.7)}`,
      color: "#04131c",
      boxShadow: shadow.glow(c, 0.28),
    },
    ghost: {
      background: active ? hexA(c, 0.14) : "rgba(148,163,184,0.06)",
      border: `1px solid ${active ? hexA(c, 0.5) : C.borderStrong}`,
      color: active ? c : "#dbe5f1",
    },
    subtle: {
      background: "transparent",
      border: "1px solid transparent",
      color: C.textDim,
      padding: "6px 10px",
    },
  };
  return (
    <button style={{ ...shared, ...variants[variant], ...style }} {...rest}>
      {children}
    </button>
  );
}
