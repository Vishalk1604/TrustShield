// TrustShield design tokens — single source of truth for color/type/spacing/motion.
// Premium dark-glass system: near-black base, frosted-glass surfaces, neon-edge accents,
// per-layer hues for the 5-layer pipeline. Inline-style components read from here so the
// look stays consistent across Home / Investigator / Examples without a CSS framework.

export const color = {
  // near-black base (slightly blue) → raised panels
  bg: "#06080f",
  bgRaised: "#0b0f1a",
  bgPanel: "#0b1018",
  bgInset: "#070a12",
  // hairline glass borders
  border: "rgba(148,163,184,0.14)",
  borderStrong: "rgba(148,163,184,0.26)",
  // text
  text: "#e8eef7",
  textDim: "#9fb0c6",
  textFaint: "#62748e",
  // brand accent (cyan)
  accent: "#38bdf8",
  accentDim: "#0ea5e9",
  accentDeep: "#0284c7",
  // status
  success: "#34d399",
  warning: "#fbbf24",
  danger: "#f43f5e",
  info: "#64748b",
};

// Per-layer accent hues — the 5-layer pipeline spine + Home "how it works" share these.
export const layer = {
  forensic: { hue: "#38bdf8", name: "Pixel forensics" },     // sky
  semantic: { hue: "#a78bfa", name: "Semantic ID + QR" },    // violet
  model: { hue: "#34d399", name: "Learned model" },          // emerald
  trust: { hue: "#fbbf24", name: "Trust aggregation" },      // amber
  graph: { hue: "#fb7185", name: "Cross-application" },      // rose
};

// Severity → color (shared by evidence cards / badges).
export const severity = {
  critical: "#f43f5e",
  high: "#fb923c",
  medium: "#fbbf24",
  low: "#38bdf8",
  info: "#64748b",
};

// Action → color/label/icon (recommended underwriting action).
export const action = {
  approve: { c: "#34d399", label: "APPROVE", glyph: "✓" },
  manual_review: { c: "#fbbf24", label: "MANUAL REVIEW", glyph: "⚠" },
  freeze: { c: "#f43f5e", label: "FREEZE", glyph: "⛔" },
};

export const font = {
  sans: '"Inter", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
  mono: '"Cascadia Code", "JetBrains Mono", "Consolas", ui-monospace, monospace',
};

export const radius = { sm: 8, md: 10, lg: 14, xl: 18, pill: 999 };

export const space = (n) => n * 4;

// Elevation + glow. `glow(c)` returns a soft colored halo for neon edges.
export const shadow = {
  sm: "0 1px 2px rgba(0,0,0,0.4)",
  md: "0 8px 24px -8px rgba(0,0,0,0.6)",
  lg: "0 24px 60px -20px rgba(0,0,0,0.75)",
  glow: (c, a = 0.35) => `0 0 0 1px ${hexA(c, 0.18)}, 0 0 28px ${hexA(c, a)}`,
  innerTop: "inset 0 1px 0 rgba(255,255,255,0.05)",
};

// Motion tokens — keep transitions consistent.
export const motion = {
  fast: "140ms",
  base: "240ms",
  slow: "420ms",
  ease: "cubic-bezier(0.22, 1, 0.36, 1)", // easeOutExpo-ish
  spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
};

// Type scale (px).
export const text = {
  display: 46,
  h1: 30,
  h2: 22,
  h3: 17,
  body: 14,
  small: 13,
  tiny: 11,
};

export const maxWidth = 1240;

// ── helpers ──────────────────────────────────────────────────────────────────
// Convert a #rrggbb to an rgba() string at alpha `a`.
export function hexA(hex, a) {
  const h = hex.replace("#", "");
  const n = h.length === 3 ? h.split("").map((x) => x + x).join("") : h;
  const r = parseInt(n.slice(0, 2), 16);
  const g = parseInt(n.slice(2, 4), 16);
  const b = parseInt(n.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

// Frosted-glass surface. `tint` optionally biases the fill toward a layer hue.
export function glass({ tint = null, fill = 0.05, blur = 14, border = color.border, radius: r = radius.lg } = {}) {
  return {
    background: tint
      ? `linear-gradient(180deg, ${hexA(tint, 0.10)}, ${hexA(tint, 0.02)}), rgba(148,163,184,${fill})`
      : `rgba(148,163,184,${fill})`,
    border: `1px solid ${border}`,
    borderRadius: r,
    backdropFilter: `blur(${blur}px)`,
    WebkitBackdropFilter: `blur(${blur}px)`,
    boxShadow: `${shadow.md}, ${shadow.innerTop}`,
  };
}

// ── shared style primitives (kept for backward-compat; values retuned) ─────────
export const card = glass();

export const pillBadge = {
  display: "inline-flex",
  alignItems: "center",
  gap: 7,
  fontSize: 12,
  fontWeight: 600,
  borderRadius: radius.pill,
  padding: "5px 13px",
  border: `1px solid ${hexA(color.success, 0.4)}`,
  background: hexA(color.success, 0.1),
  color: "#a7f3d0",
  backdropFilter: "blur(8px)",
  WebkitBackdropFilter: "blur(8px)",
};

export const buttonGhost = {
  cursor: "pointer",
  background: "rgba(148,163,184,0.06)",
  border: `1px solid ${color.borderStrong}`,
  color: "#dbe5f1",
  borderRadius: radius.md,
  padding: "9px 16px",
  fontSize: 13,
  fontWeight: 600,
  transition: `all ${motion.base} ${motion.ease}`,
};

export const buttonPrimary = {
  cursor: "pointer",
  background: `linear-gradient(180deg, ${color.accent}, ${color.accentDeep})`,
  border: `1px solid ${hexA(color.accent, 0.7)}`,
  color: "#04131c",
  borderRadius: radius.md,
  padding: "11px 20px",
  fontSize: 14,
  fontWeight: 700,
  boxShadow: shadow.glow(color.accent, 0.3),
  transition: `all ${motion.base} ${motion.ease}`,
};

export const sectionTitle = {
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: 1.4,
  fontWeight: 700,
  color: color.textDim,
  marginTop: 0,
  marginBottom: 12,
};
