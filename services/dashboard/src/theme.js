// TrustShield design tokens — single source of truth for color/type/spacing.
// Inline-style components read from here so the palette stays consistent across
// Home / Investigator / Examples without a CSS framework dependency.
export const color = {
  bg: "#0b1220",
  bgRaised: "#0f172a",
  bgPanel: "#0f172a",
  border: "#1e293b",
  borderStrong: "#334155",
  text: "#e2e8f0",
  textDim: "#94a3b8",
  textFaint: "#64748b",
  accent: "#38bdf8",
  accentDim: "#0ea5e9",
  success: "#22c55e",
  warning: "#eab308",
  danger: "#ef4444",
  info: "#64748b",
};

export const font = {
  sans: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
  mono: '"Cascadia Code", "Consolas", ui-monospace, monospace',
};

export const radius = { sm: 6, md: 8, lg: 12, xl: 16, pill: 999 };

export const space = (n) => n * 4;

export const shadow = {
  raised: "0 1px 2px rgba(0,0,0,0.4)",
  glow: (c) => `0 0 16px ${c}33`,
};

export const maxWidth = 1180;

// Shared primitives used by multiple pages.
export const card = {
  background: color.bgPanel,
  border: `1px solid ${color.border}`,
  borderRadius: radius.lg,
};

export const pillBadge = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  fontSize: 12,
  fontWeight: 600,
  borderRadius: radius.pill,
  padding: "5px 12px",
  border: `1px solid rgba(34,197,94,0.4)`,
  background: "rgba(34,197,94,0.08)",
  color: "#bbf7d0",
};

export const buttonGhost = {
  cursor: "pointer",
  background: color.border,
  border: `1px solid ${color.borderStrong}`,
  color: "#cbd5e1",
  borderRadius: radius.md,
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 500,
};

export const buttonPrimary = {
  cursor: "pointer",
  background: color.accent,
  border: `1px solid ${color.accent}`,
  color: "#04131c",
  borderRadius: radius.md,
  padding: "10px 18px",
  fontSize: 14,
  fontWeight: 700,
};

export const sectionTitle = {
  fontSize: 13,
  textTransform: "uppercase",
  letterSpacing: 1,
  color: color.textDim,
  marginTop: 0,
  marginBottom: 10,
};
