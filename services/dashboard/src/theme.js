// Shared palette + style tokens (dark fintech theme). Kept simple; polish later.

export const SEVERITY = {
  critical: { c: "#ef4444", label: "CRITICAL" },
  high: { c: "#f97316", label: "HIGH" },
  medium: { c: "#eab308", label: "MEDIUM" },
  low: { c: "#38bdf8", label: "LOW" },
  info: { c: "#64748b", label: "INFO" },
};

export const CATEGORY = {
  forensic: "Forensic",
  semantic: "Semantic",
  anomaly: "Model",
  graph: "Graph",
};

export const ACTION = {
  approve: { c: "#22c55e", label: "APPROVE", icon: "✓" },
  manual_review: { c: "#eab308", label: "MANUAL REVIEW", icon: "⚠" },
  freeze: { c: "#ef4444", label: "FREEZE", icon: "⛔" },
};

export const ui = {
  page: { maxWidth: 1100, margin: "0 auto", padding: "28px 24px" },
  card: { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 18 },
  sectionTitle: { fontSize: 13, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginTop: 0, marginBottom: 10 },
  btn: { cursor: "pointer", background: "#38bdf8", border: "none", color: "#06283d", borderRadius: 8, padding: "10px 16px", fontSize: 14, fontWeight: 700 },
  btnGhost: { cursor: "pointer", background: "#1e293b", border: "1px solid #334155", color: "#cbd5e1", borderRadius: 8, padding: "9px 14px", fontSize: 13 },
  input: { width: "100%", background: "#0b1220", border: "1px solid #334155", color: "#e2e8f0", borderRadius: 8, padding: "10px 12px", fontSize: 14, marginTop: 4 },
  label: { fontSize: 12, color: "#94a3b8" },
  error: { background: "rgba(239,68,68,0.1)", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px", color: "#fca5a5", fontSize: 14 },
};
