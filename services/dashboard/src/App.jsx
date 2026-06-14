import React, { useEffect, useState, useCallback } from "react";
import { SERVICES } from "./config.js";
import { api } from "./api.js";
import GraphView from "./GraphView.jsx";

// ── palette ──────────────────────────────────────────────────────────────────
const SEVERITY = {
  critical: { c: "#ef4444", label: "CRITICAL" },
  high: { c: "#f97316", label: "HIGH" },
  medium: { c: "#eab308", label: "MEDIUM" },
  low: { c: "#38bdf8", label: "LOW" },
  info: { c: "#64748b", label: "INFO" },
};
const CATEGORY = {
  forensic: "Forensic",
  semantic: "Semantic",
  anomaly: "Model",
  graph: "Graph",
};
const ACTION = {
  approve: { c: "#22c55e", label: "APPROVE", icon: "✓" },
  manual_review: { c: "#eab308", label: "MANUAL REVIEW", icon: "⚠" },
  freeze: { c: "#ef4444", label: "FREEZE", icon: "⛔" },
};

// ── service health (kept from Phase 0) ────────────────────────────────────────
function useHealth(base) {
  const [state, setState] = useState({ status: "loading", detail: "" });
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const body = await api.health(base);
        if (alive) setState({ status: body.status === "ok" ? "ok" : "down", detail: body.version || "" });
      } catch {
        if (alive) setState({ status: "down", detail: "" });
      }
    };
    ping();
    const id = setInterval(ping, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [base]);
  return state;
}

function StatusDot({ status }) {
  const color = status === "ok" ? "#22c55e" : status === "down" ? "#ef4444" : "#eab308";
  return <span style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}`, marginRight: 6 }} />;
}

// ── trust gauge ───────────────────────────────────────────────────────────────
function TrustGauge({ trust, action }) {
  const r = 64, stroke = 12, C = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, trust)) / 100;
  const color = (ACTION[action] || {}).c || "#38bdf8";
  return (
    <svg width={160} height={160} viewBox="0 0 160 160">
      <circle cx={80} cy={80} r={r} fill="none" stroke="#1e293b" strokeWidth={stroke} />
      <circle
        cx={80} cy={80} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={C} strokeDashoffset={C * (1 - pct)} strokeLinecap="round"
        transform="rotate(-90 80 80)"
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
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
    </div>
  );
}

function GroundTruthChip({ label, fraudTypes }) {
  if (!label) return null;
  const isFraud = label === "fraud";
  return (
    <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4, background: isFraud ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.15)", color: isFraud ? "#fca5a5" : "#86efac", border: `1px solid ${isFraud ? "#7f1d1d" : "#14532d"}` }} title={fraudTypes?.join(", ")}>
      {isFraud ? (fraudTypes?.[0] || "fraud") : "clean"}
    </span>
  );
}

// ── main ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [packets, setPackets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [seedInfo, setSeedInfo] = useState(null);

  // Load packet list + seed the graph once on mount.
  useEffect(() => {
    (async () => {
      try {
        const [pk, seed] = await Promise.all([api.listPackets(), api.seedGraph().catch(() => null)]);
        setPackets(pk.packets || []);
        setSeedInfo(seed);
      } catch (e) {
        setError(`Could not reach the risk service. Is it running on :8002? (${e.message})`);
      }
    })();
  }, []);

  const scoreOne = useCallback(async (pktId) => {
    setSelected(pktId);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.scorePacket(pktId, true);
      setResult(r);
    } catch (e) {
      setError(`Scoring failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const exportReport = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.decision, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${selected}_trustshield_report.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const decision = result?.decision;
  const action = decision?.recommendation?.action;
  const act = ACTION[action] || {};

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "32px 24px" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: -0.5 }}>
            🛡️ TrustShield <span style={{ color: "#38bdf8" }}>Investigator Console</span>
          </h1>
          <p style={{ color: "#94a3b8", margin: "4px 0 0" }}>
            Local-first underwriting copilot — forensic, semantic, behavioral & cross-application fraud detection.
          </p>
        </div>
        <div style={{ display: "flex", gap: 14 }}>
          {SERVICES.map((s) => <ServiceHealth key={s.key} {...s} />)}
        </div>
      </header>

      <div style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.4)", borderRadius: 10, padding: "9px 14px", margin: "16px 0", fontSize: 13, color: "#bbf7d0" }}>
        🔒 <strong>All processing on-premise.</strong> No customer data leaves this machine — every analysis is local.
        {seedInfo && <span style={{ color: "#86efac", marginLeft: 8 }}>· graph: {seedInfo.n_applications} apps, {seedInfo.employer_rings} ring(s), {seedInfo.collateral_clusters} collateral cluster(s)</span>}
      </div>

      {error && (
        <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px", margin: "12px 0", color: "#fca5a5", fontSize: 14 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20, marginTop: 8 }}>
        {/* packet picker */}
        <aside>
          <h2 style={sectionTitle}>Loan packets ({packets.length})</h2>
          <div style={{ display: "grid", gap: 5, maxHeight: 640, overflowY: "auto", paddingRight: 4 }}>
            {packets.map((p) => (
              <button
                key={p.packet_id}
                onClick={() => scoreOne(p.packet_id)}
                style={{
                  textAlign: "left", cursor: "pointer",
                  background: selected === p.packet_id ? "#1e293b" : "#0f172a",
                  border: `1px solid ${selected === p.packet_id ? "#38bdf8" : "#1e293b"}`,
                  borderRadius: 8, padding: "9px 11px", color: "#e2e8f0",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{p.packet_id}</span>
                  <GroundTruthChip label={p.ground_truth_label} fraudTypes={p.ground_truth_fraud_types} />
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                  {p.applicant_name || "—"} · {p.n_docs} docs
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* decision panel */}
        <main>
          {!decision && !loading && (
            <div style={{ color: "#64748b", padding: "60px 20px", textAlign: "center", border: "1px dashed #334155", borderRadius: 12 }}>
              Select a loan packet to run the full forensic → semantic → model → graph pipeline.
            </div>
          )}
          {loading && (
            <div style={{ color: "#94a3b8", padding: "60px 20px", textAlign: "center" }}>
              Analyzing {selected} — forensics, semantics, model, graph…
            </div>
          )}

          {decision && (
            <div style={{ display: "grid", gap: 16 }}>
              {/* verdict header */}
              <div style={{ display: "flex", gap: 20, alignItems: "center", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 18, flexWrap: "wrap" }}>
                <TrustGauge trust={decision.trust_score.overall} action={action} />
                <div style={{ flex: 1, minWidth: 240 }}>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: act.c + "22", border: `1px solid ${act.c}`, color: act.c, borderRadius: 8, padding: "6px 12px", fontWeight: 700, fontSize: 15 }}>
                    <span>{act.icon}</span>{act.label}
                  </div>
                  <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5, marginTop: 10 }}>
                    {decision.recommendation.rationale}
                  </p>
                  <button onClick={exportReport} style={exportBtn}>⬇ Export evidence report (JSON)</button>
                </div>
                <div style={{ width: 200 }}>
                  <SubScoreBar label="Forensic" value={decision.trust_score.forensic_subscore} />
                  <SubScoreBar label="Semantic" value={decision.trust_score.semantic_subscore} />
                  <SubScoreBar label="Model (anomaly)" value={decision.trust_score.anomaly_subscore} />
                </div>
              </div>

              {/* evidence + graph */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 480px", gap: 16, alignItems: "start" }}>
                <section>
                  <h2 style={sectionTitle}>Evidence chain ({decision.evidence_chain.length})</h2>
                  <div style={{ display: "grid", gap: 8 }}>
                    {decision.evidence_chain.map((it) => <EvidenceCard key={it.id} item={it} />)}
                  </div>
                </section>
                <section>
                  <h2 style={sectionTitle}>Cross-application graph</h2>
                  <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 14 }}>
                    <GraphView subgraph={result.subgraph} focusId={`app:${selected}`} />
                  </div>
                </section>
              </div>
            </div>
          )}
        </main>
      </div>

      <footer style={{ marginTop: 36, fontSize: 12, color: "#475569", borderTop: "1px solid #1e293b", paddingTop: 12 }}>
        TrustShield — synthetic data, zero PII, 100% local. Scores always carry a full evidence chain.
      </footer>
    </div>
  );
}

function ServiceHealth({ label, base }) {
  const { status, detail } = useHealth(base);
  const text = status === "ok" ? `v${detail}` : status === "down" ? "down" : "…";
  return (
    <span style={{ fontSize: 12, color: "#94a3b8", display: "flex", alignItems: "center" }}>
      <StatusDot status={status} />{label.split(" ")[0]} {text}
    </span>
  );
}

const sectionTitle = { fontSize: 13, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", marginTop: 0, marginBottom: 10 };
const exportBtn = { marginTop: 12, cursor: "pointer", background: "#1e293b", border: "1px solid #334155", color: "#cbd5e1", borderRadius: 8, padding: "7px 12px", fontSize: 13 };
