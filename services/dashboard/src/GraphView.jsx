import React from "react";

// Colors per node kind.
const KIND_STYLE = {
  app: { fill: "#0ea5e9", label: "Application" },
  property: { fill: "#f97316", label: "Property" },
  employer: { fill: "#a78bfa", label: "Employer" },
  pan: { fill: "#34d399", label: "Applicant" },
  template: { fill: "#94a3b8", label: "Template" },
};

function shortLabel(node) {
  const raw = node.label ?? node.id;
  if (node.kind === "template") return raw.slice(0, 6); // fingerprint hash
  return raw.length > 16 ? raw.slice(0, 15) + "…" : raw;
}

/**
 * Small SVG layout: the focused application is centered; every other node is placed
 * evenly on a surrounding circle. Edges are drawn underneath. Good for the <=30-node
 * subgraphs the backend returns.
 */
export default function GraphView({ subgraph, focusId }) {
  if (!subgraph || subgraph.nodes.length === 0) {
    return (
      <div style={{ color: "#64748b", fontSize: 14, padding: 20 }}>
        No cross-application links for this packet.
      </div>
    );
  }

  const W = 460;
  const H = 320;
  const cx = W / 2;
  const cy = H / 2;
  const R = 120;

  const focus = subgraph.nodes.find((n) => n.id === focusId) || subgraph.nodes[0];
  const others = subgraph.nodes.filter((n) => n.id !== focus.id);

  const pos = {};
  pos[focus.id] = { x: cx, y: cy };
  others.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, others.length) - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  });

  const kindsPresent = [...new Set(subgraph.nodes.map((n) => n.kind))];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, height: "auto" }}>
        {/* edges */}
        {subgraph.edges.map((e, i) => {
          const a = pos[e.source];
          const b = pos[e.target];
          if (!a || !b) return null;
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="#334155" strokeWidth={1.5} />
          );
        })}
        {/* nodes */}
        {subgraph.nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const style = KIND_STYLE[n.kind] || { fill: "#64748b" };
          const isFocus = n.id === focus.id;
          const r = n.kind === "app" ? 16 : 11;
          return (
            <g key={n.id}>
              <circle
                cx={p.x} cy={p.y} r={r}
                fill={style.fill}
                stroke={isFocus ? "#fbbf24" : "#0f172a"}
                strokeWidth={isFocus ? 3 : 1.5}
              />
              <text
                x={p.x} y={p.y + r + 12}
                textAnchor="middle" fontSize={11} fill="#cbd5e1"
              >
                {shortLabel(n)}
              </text>
            </g>
          );
        })}
      </svg>
      {/* legend */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8 }}>
        {kindsPresent.map((k) => (
          <span key={k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8" }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: (KIND_STYLE[k] || {}).fill }} />
            {(KIND_STYLE[k] || {}).label || k}
          </span>
        ))}
      </div>
    </div>
  );
}
