// Reusable decision renderer: trust gauge + action + sub-scores + tamper overlays +
// evidence chain + optional cross-application graph. Used by user result + admin case detail.
import React from "react";
import GraphView from "../GraphView.jsx";
import { SEVERITY, CATEGORY, ACTION, ui } from "../theme.js";

function TrustGauge({ trust, action }) {
  const r = 64, stroke = 12, C = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, trust)) / 100;
  const color = (ACTION[action] || {}).c || "#38bdf8";
  return (
    <svg width={160} height={160} viewBox="0 0 160 160">
      <circle cx={80} cy={80} r={r} fill="none" stroke="#1e293b" strokeWidth={stroke} />
      <circle cx={80} cy={80} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={C} strokeDashoffset={C * (1 - pct)} strokeLinecap="round"
        transform="rotate(-90 80 80)" style={{ transition: "stroke-dashoffset 0.6s ease" }} />
      <text x={80} y={74} textAnchor="middle" fontSize={36} fontWeight="700" fill="#f1f5f9">{Math.round(trust)}</text>
      <text x={80} y={98} textAnchor="middle" fontSize={12} fill="#94a3b8">/ 100 trust</text>
    </svg>
  );
}

function SubScoreBar({ label, value }) {
  if (value === null || value === undefined) return null;
  const c = value >= 70 ? "#22c55e" : value >= 40 ? "#eab308" : "#ef4444";
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#94a3b8", marginBottom: 3 }}>
        <span>{label}</span><span>{Math.round(value)}</span>
      </div>
      <div style={{ height: 6, background: "#1e293b", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: c }} />
      </div>
    </div>
  );
}

function EvidenceCard({ item }) {
  const sev = SEVERITY[item.severity] || SEVERITY.info;
  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderLeft: `4px solid ${sev.c}`, borderRadius: 8, padding: "12px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: sev.c, letterSpacing: 0.5 }}>{sev.label}</span>
        <span style={{ fontSize: 10, color: "#64748b", border: "1px solid #334155", borderRadius: 4, padding: "1px 6px" }}>
          {CATEGORY[item.category] || item.category}
        </span>
        <span style={{ fontWeight: 600, fontSize: 14, color: "#e2e8f0" }}>{item.title}</span>
      </div>
      <div style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.5 }}>{item.description}</div>
      {item.source_location && (
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 6 }}>source: {item.source_location}</div>
      )}
      {Array.isArray(item.values?.regions) && item.values.regions.length > 0 && (
        <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 4 }}>
          📍 localized: {item.values.regions.map((r, i) => (
            <span key={i}>{i > 0 ? ", " : ""}page {r.page}{Array.isArray(r.bbox) ? ` (${r.bbox[0]}, ${r.bbox[1]})` : ""}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function TamperLocalization({ overlays }) {
  if (!overlays || overlays.length === 0) return null;
  return (
    <section>
      <h2 style={ui.sectionTitle}>Tamper localization ({overlays.length})</h2>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {overlays.map((o, i) => (
          <figure key={i} style={{ margin: 0, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: 10 }}>
            <img src={`data:image/png;base64,${o.image_b64}`} alt={`Edit region on ${o.doc} page ${o.page}`}
              style={{ width: "100%", borderRadius: 6, border: "1px solid #334155", display: "block" }} />
            <figcaption style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>
              <span style={{ color: "#fca5a5" }}>◼</span> detected edit region — {o.doc}, page {o.page}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

export default function DecisionView({ decision, tamperOverlays, subgraph, focusId, onExport }) {
  if (!decision) return null;
  const action = decision.recommendation?.action;
  const act = ACTION[action] || {};
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 20, alignItems: "center", ...ui.card, flexWrap: "wrap" }}>
        <TrustGauge trust={decision.trust_score.overall} action={action} />
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: (act.c || "#888") + "22", border: `1px solid ${act.c}`, color: act.c, borderRadius: 8, padding: "6px 12px", fontWeight: 700, fontSize: 15 }}>
            <span>{act.icon}</span>{act.label || action}
          </div>
          <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5, marginTop: 10 }}>
            {decision.recommendation?.rationale}
          </p>
          {onExport && <button onClick={onExport} style={ui.btnGhost}>⬇ Export evidence report (JSON)</button>}
        </div>
        <div style={{ width: 200 }}>
          <SubScoreBar label="Forensic" value={decision.trust_score.forensic_subscore} />
          <SubScoreBar label="Semantic" value={decision.trust_score.semantic_subscore} />
          <SubScoreBar label="Model (anomaly)" value={decision.trust_score.anomaly_subscore} />
        </div>
      </div>

      <TamperLocalization overlays={tamperOverlays} />

      <div style={{ display: "grid", gridTemplateColumns: subgraph ? "1fr 460px" : "1fr", gap: 16, alignItems: "start" }}>
        <section>
          <h2 style={ui.sectionTitle}>Evidence chain ({decision.evidence_chain.length})</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {decision.evidence_chain.map((it) => <EvidenceCard key={it.id} item={it} />)}
          </div>
        </section>
        {subgraph && (
          <section>
            <h2 style={ui.sectionTitle}>Cross-application graph</h2>
            <div style={ui.card}><GraphView subgraph={subgraph} focusId={focusId} /></div>
          </section>
        )}
      </div>
    </div>
  );
}
