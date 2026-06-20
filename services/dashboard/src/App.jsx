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
      {Array.isArray(item.values?.regions) && item.values.regions.length > 0 && (
        <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 4 }}>
          📍 localized:{" "}
          {item.values.regions.map((r, i) => (
            <span key={i}>
              {i > 0 ? ", " : ""}page {r.page}
              {Array.isArray(r.bbox) ? ` (${r.bbox[0]}, ${r.bbox[1]})` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── tamper localization (D3) ───────────────────────────────────────────────────
function TamperLocalization({ overlays }) {
  if (!overlays || overlays.length === 0) return null;
  return (
    <section>
      <h2 style={sectionTitle}>Tamper localization ({overlays.length})</h2>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {overlays.map((o, i) => (
          <figure key={i} style={{ margin: 0, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: 10 }}>
            <img
              src={`data:image/png;base64,${o.image_b64}`}
              alt={`Edit region on ${o.doc} page ${o.page}`}
              style={{ width: "100%", borderRadius: 6, border: "1px solid #334155", display: "block" }}
            />
            <figcaption style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>
              <span style={{ color: "#fca5a5" }}>◼</span> detected edit region — {o.doc}, page {o.page}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
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

// ── image edit detection (§10 — pixel forensics on scanned/photo documents) ─────
const VERDICT_C = { EDITED: "#ef4444", SUSPICIOUS: "#eab308", CLEAN: "#22c55e" };
const IMG_EXAMPLES = [
  { label: "Clean Form 16", path: "examples/clean_form16.jpg" },
  { label: "Edited number", path: "examples/edited_number_form16.jpg" },
  { label: "Spliced patch", path: "examples/spliced_form16.jpg" },
  { label: "Digital paint-over", path: "examples/digital_paintover_id.png" },
];
const panelCard = { background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 18 };
const exampleBtn = { cursor: "pointer", background: "#1e293b", border: "1px solid #334155", color: "#cbd5e1", borderRadius: 8, padding: "7px 12px", fontSize: 13 };
const figS = { margin: 0, background: "#0b1220", border: "1px solid #1e293b", borderRadius: 10, padding: 8 };
const imgS = { width: "100%", borderRadius: 6, border: "1px solid #334155", display: "block" };
const capS = { fontSize: 11, color: "#94a3b8", marginTop: 6 };

function ImageForensicsPanel() {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [name, setName] = useState(null);

  const analyze = async (file, label) => {
    setBusy(true); setErr(null); setRes(null); setName(label);
    try { setRes(await api.analyzeImage(file)); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };
  const runExample = async (ex) => {
    try {
      const r = await fetch(ex.path, { cache: "no-store" });
      if (!r.ok) throw new Error(`example not found (${r.status})`);
      const b = await r.blob();
      await analyze(new File([b], ex.label, { type: b.type || "image/jpeg" }), ex.label);
    } catch (e) { setErr(e.message); }
  };
  const onUpload = (e) => { const f = e.target.files?.[0]; if (f) analyze(f, f.name); };

  const vc = res ? (VERDICT_C[res.verdict] || "#64748b") : "#64748b";
  return (
    <section style={{ ...panelCard, marginTop: 16 }}>
      <h2 style={{ ...sectionTitle, marginBottom: 6 }}>🖼️ Image edit detection — scanned / photo documents</h2>
      <p style={{ color: "#94a3b8", fontSize: 13, margin: "0 0 12px" }}>
        Detect &amp; localize edits in a document image (painted numbers, splices, clones) using pixel
        forensics — ELA, sensor-noise loss, copy-move — 100% local. Try an example, or edit a number in
        your own scan/photo and upload it.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {IMG_EXAMPLES.map((ex) => (
          <button key={ex.path} onClick={() => runExample(ex)} disabled={busy} style={exampleBtn}>{ex.label}</button>
        ))}
        <label style={{ ...exampleBtn, cursor: "pointer" }}>
          Upload image…
          <input type="file" accept="image/*" onChange={onUpload} style={{ display: "none" }} />
        </label>
      </div>

      {err && <div style={{ background: "rgba(239,68,68,0.1)", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px", color: "#fca5a5", fontSize: 14, marginTop: 10 }}>{err}</div>}
      {busy && <div style={{ color: "#94a3b8", marginTop: 12 }}>Analyzing {name}…</div>}

      {res && res.ok && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: vc, background: vc + "22", border: `1px solid ${vc}`, borderRadius: 8, padding: "4px 12px" }}>{res.verdict}</span>
            <span style={{ color: "#94a3b8", fontSize: 13 }}>image trust {Math.round(res.image_trust)}/100 · {name}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <figure style={figS}>
              <img src={`data:image/png;base64,${res.annotated_b64}`} alt="annotated edit regions" style={imgS} />
              <figcaption style={capS}><span style={{ color: "#fca5a5" }}>◼</span> detected edit region(s)</figcaption>
            </figure>
            {res.ela_b64 && (
              <figure style={figS}>
                <img src={`data:image/png;base64,${res.ela_b64}`} alt="ELA heatmap" style={imgS} />
                <figcaption style={capS}>ELA heatmap — compression-error energy</figcaption>
              </figure>
            )}
          </div>
          <h3 style={{ ...sectionTitle, marginTop: 14 }}>Findings ({res.findings.length})</h3>
          {res.findings.length === 0
            ? <div style={{ color: "#86efac", fontSize: 13 }}>No edit signals detected — looks clean.</div>
            : <div style={{ display: "grid", gap: 6 }}>{res.findings.map((f, i) => <EvidenceCard key={i} item={{ ...f, id: i }} />)}</div>}
        </div>
      )}
      {res && !res.ok && <div style={{ color: "#fca5a5", fontSize: 13, marginTop: 10 }}>Could not analyze: {res.error}</div>}
    </section>
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

      <ImageForensicsPanel />

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

              {/* tamper localization (D3) */}
              <TamperLocalization overlays={result.tamper_overlays} />

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
