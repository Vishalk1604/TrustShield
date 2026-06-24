import React from "react";
import { color as C, layer as L, hexA, radius, motion, shadow } from "../../theme.js";

// The 5-layer detection pipeline — TrustShield's architecture, as a reusable visual.
// Shared by the Investigator (mode="spine", interactive + fired-status) and Home
// (mode="cards", static "what it catches"). Layer hues come from theme.layer.

export const LAYERS = [
  {
    id: "forensic",
    n: 1,
    hue: L.forensic.hue,
    name: "Pixel forensics",
    catches: "Painted numbers, splices, clones in scans & photos — ELA, sensor-noise loss, copy-move.",
    glyph: (p) => (
      <g {...p}>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M4 14l4-3 3 2 4-4 5 4" />
        <circle cx="9" cy="9" r="1.4" />
      </g>
    ),
  },
  {
    id: "semantic",
    n: 2,
    hue: L.semantic.hue,
    name: "Semantic ID + QR",
    catches: "Invalid PAN/Aadhaar structure, and the card's signed QR cross-checked against printed text.",
    glyph: (p) => (
      <g {...p}>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M7 9h4M7 13h6" />
        <rect x="14.5" y="8.5" width="3.5" height="3.5" rx="0.6" />
      </g>
    ),
  },
  {
    id: "anomaly",
    n: 3,
    hue: L.model.hue,
    name: "Learned model",
    catches: "Our U-Net flags seamless edits the heuristics miss — opt-in, honest synthetic→real limits.",
    glyph: (p) => (
      <g {...p}>
        <circle cx="6" cy="7" r="2" />
        <circle cx="18" cy="7" r="2" />
        <circle cx="12" cy="17" r="2" />
        <path d="M7.6 8.4L11 15M16.4 8.4L13 15M8 7h8" />
      </g>
    ),
  },
  {
    id: "trust",
    n: 4,
    hue: L.trust.hue,
    name: "Trust aggregation",
    catches: "Weighted, documented blend → 0–100 trust score + ordered evidence chain + an action.",
    glyph: (p) => (
      <g {...p}>
        <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />
        <path d="M9 12l2 2 4-4" />
      </g>
    ),
  },
  {
    id: "graph",
    n: 5,
    hue: L.graph.hue,
    name: "Cross-application",
    catches: "Fraud rings and double-financed collateral linked across separate loan applications.",
    glyph: (p) => (
      <g {...p}>
        <circle cx="6" cy="6" r="2.2" />
        <circle cx="18" cy="8" r="2.2" />
        <circle cx="9" cy="18" r="2.2" />
        <path d="M7.8 7.4l6.6 1.4M7.4 7.8l1 8.2M10.8 17l5.6-7" />
      </g>
    ),
  },
];

function LayerGlyph({ layer, size = 22, stroke }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke || layer.hue} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {layer.glyph({})}
    </svg>
  );
}

// One node in the interactive spine.
function SpineNode({ layer, fired, count, label, active, onClick }) {
  const lit = fired || active || !!label;
  return (
    <button
      onClick={onClick}
      title={layer.catches}
      style={{
        flex: "1 1 0",
        minWidth: 120,
        cursor: "pointer",
        textAlign: "left",
        background: lit ? `linear-gradient(180deg, ${hexA(layer.hue, 0.16)}, ${hexA(layer.hue, 0.04)})` : "rgba(148,163,184,0.04)",
        border: `1px solid ${active ? hexA(layer.hue, 0.7) : lit ? hexA(layer.hue, 0.38) : C.border}`,
        borderRadius: radius.md,
        padding: "12px 12px 11px",
        position: "relative",
        transition: `all ${motion.base} ${motion.ease}`,
        boxShadow: active ? shadow.glow(layer.hue, 0.3) : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span
          style={{
            display: "inline-flex",
            width: 30,
            height: 30,
            borderRadius: 9,
            alignItems: "center",
            justifyContent: "center",
            background: lit ? hexA(layer.hue, 0.16) : "rgba(148,163,184,0.06)",
            border: `1px solid ${hexA(layer.hue, lit ? 0.5 : 0.2)}`,
            opacity: lit ? 1 : 0.55,
          }}
        >
          <LayerGlyph layer={layer} size={17} stroke={lit ? layer.hue : C.textFaint} />
        </span>
        {label ? (
          <span style={{ fontSize: 10.5, fontWeight: 800, color: layer.hue, background: hexA(layer.hue, 0.14), border: `1px solid ${hexA(layer.hue, 0.4)}`, borderRadius: 999, padding: "2px 8px" }}>
            {label}
          </span>
        ) : fired ? (
          <span style={{ fontSize: 10.5, fontWeight: 800, color: layer.hue, background: hexA(layer.hue, 0.14), border: `1px solid ${hexA(layer.hue, 0.4)}`, borderRadius: 999, padding: "2px 8px" }}>
            {count != null ? `${count} finding${count === 1 ? "" : "s"}` : "fired"}
          </span>
        ) : (
          <span style={{ fontSize: 10, fontWeight: 700, color: C.textFaint, letterSpacing: 0.4 }}>clear</span>
        )}
      </div>
      <div style={{ marginTop: 9, fontSize: 9.5, fontWeight: 800, letterSpacing: 0.6, color: lit ? layer.hue : C.textFaint }}>
        LAYER {layer.n}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: lit ? C.text : C.textDim, marginTop: 1, letterSpacing: -0.2 }}>{layer.name}</div>
    </button>
  );
}

/**
 * mode="spine": interactive status row for the Investigator.
 *   status = { forensic:{fired,count}, semantic:{...}, anomaly, trust, graph }
 *   onLayerClick(id), activeId.
 * mode="cards": static "what it catches" grid for Home.
 */
export default function PipelineDiagram({ mode = "spine", status = {}, activeId = null, onLayerClick }) {
  if (mode === "cards") {
    return (
      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {LAYERS.map((ly) => (
          <div key={ly.id} style={{ background: `linear-gradient(180deg, ${hexA(ly.hue, 0.08)}, transparent)`, border: `1px solid ${hexA(ly.hue, 0.28)}`, borderRadius: radius.lg, padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span style={{ display: "inline-flex", width: 38, height: 38, borderRadius: 11, alignItems: "center", justifyContent: "center", background: hexA(ly.hue, 0.14), border: `1px solid ${hexA(ly.hue, 0.4)}` }}>
                <LayerGlyph layer={ly} size={20} />
              </span>
              <div>
                <div style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.6, color: ly.hue }}>LAYER {ly.n}</div>
                <div style={{ fontSize: 14.5, fontWeight: 700, color: C.text, letterSpacing: -0.2 }}>{ly.name}</div>
              </div>
            </div>
            <p style={{ margin: 0, fontSize: 12.5, color: C.textDim, lineHeight: 1.55 }}>{ly.catches}</p>
          </div>
        ))}
      </div>
    );
  }

  // spine
  return (
    <div className="ts-pipeline-spine" style={{ display: "flex", alignItems: "stretch", gap: 8, position: "relative", flexWrap: "wrap" }}>
      {LAYERS.map((ly, i) => {
        const st = status[ly.id] || {};
        return (
          <React.Fragment key={ly.id}>
            <SpineNode
              layer={ly}
              fired={!!st.fired}
              count={st.count}
              label={st.label}
              active={activeId === ly.id}
              onClick={() => onLayerClick && onLayerClick(ly.id)}
            />
            {i < LAYERS.length - 1 && (
              <span aria-hidden className="ts-pipeline-connector" style={{ alignSelf: "center", color: C.textFaint, fontSize: 14, opacity: 0.6 }}>›</span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
