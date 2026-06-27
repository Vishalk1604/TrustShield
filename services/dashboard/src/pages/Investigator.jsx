import React, { useEffect, useState, useCallback, useRef } from "react";
import { SERVICES } from "../config.js";
import { api } from "../api.js";
import GraphView from "../GraphView.jsx";
import {
  color as C, layer as LY, severity as SEV, action as ACT,
  hexA, radius, motion, shadow, maxWidth, font,
} from "../theme.js";
import Gauge from "../components/ui/Gauge.jsx";
import PipelineDiagram from "../components/ui/PipelineDiagram.jsx";
import { Card, Badge, Button } from "../components/ui/primitives.jsx";
import BoxedImage from "../components/ui/BoxedImage.jsx";
import DocModal from "../components/ui/DocModal.jsx";
import { METHOD } from "../data/methods.js";
import { DEMO_DECISIONS } from "../data/demoDecisions.js";
import { CURATED_PACKETS, CURATED_IMAGES } from "../data/curatedCases.js";

// ── category → layer mapping ───────────────────────────────────────────────────
const CAT = {
  forensic: { label: "Pixel forensics", hue: LY.forensic.hue, spine: "forensic" },
  semantic: { label: "Semantic ID + QR", hue: LY.semantic.hue, spine: "semantic" },
  anomaly: { label: "Learned model", hue: LY.model.hue, spine: "anomaly" },
  graph: { label: "Cross-application graph", hue: LY.graph.hue, spine: "graph" },
};
const PIPELINE_ORDER = ["forensic", "semantic", "anomaly", "graph"];
const VERDICT_C = { EDITED: C.danger, SUSPICIOUS: C.warning, CLEAN: C.success };

// ── service health ─────────────────────────────────────────────────────────────
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

function Dot({ status }) {
  const c = status === "ok" ? C.success : status === "down" ? C.danger : C.warning;
  return <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, boxShadow: `0 0 7px ${c}`, display: "inline-block" }} />;
}

function ServiceDot({ label, base }) {
  const { status, detail } = useHealth(base);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: C.textDim }}>
      <Dot status={status} />
      {label.split(" ")[0]} {status === "ok" ? `v${detail}` : status === "down" ? "down" : "…"}
    </span>
  );
}

// ── evidence card (severity strip + inline localization note) ───────────────────
function EvidenceCard({ item }) {
  const c = SEV[item.severity] || SEV.info;
  const regions = Array.isArray(item.values?.regions) ? item.values.regions : [];
  return (
    <div style={{ background: "rgba(148,163,184,0.04)", border: `1px solid ${C.border}`, borderLeft: `3px solid ${c}`, borderRadius: radius.md, padding: "12px 14px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, fontWeight: 800, color: c, letterSpacing: 0.6 }}>{(item.severity || "info").toUpperCase()}</span>
        <span style={{ fontWeight: 700, fontSize: 14, color: C.text, letterSpacing: -0.2 }}>{item.title}</span>
        {item.confidence != null && item.confidence < 1 && (
          <span style={{ marginLeft: "auto", fontSize: 10.5, color: C.textFaint }}>conf {Math.round(item.confidence * 100)}%</span>
        )}
      </div>
      <div style={{ fontSize: 13, color: C.textDim, lineHeight: 1.55 }}>{item.description}</div>
      {(item.source_location || regions.length > 0) && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 7, fontSize: 11, color: C.textFaint }}>
          {item.source_location && <span>source: {item.source_location}</span>}
          {regions.length > 0 && (
            <span style={{ color: hexA(C.danger, 0.85) }}>
              ◼ localized: {regions.map((r, i) => `${i ? ", " : ""}page ${r.page}${Array.isArray(r.bbox) ? ` (${r.bbox[0]}, ${r.bbox[1]})` : ""}`).join("")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ── evidence group (one pipeline layer) ─────────────────────────────────────────
function EvidenceGroup({ cat, items, overlays, innerRef, active }) {
  const meta = CAT[cat];
  return (
    <section ref={innerRef} style={{ scrollMarginTop: 80 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ width: 9, height: 9, borderRadius: 3, background: meta.hue, boxShadow: shadow.glow(meta.hue, 0.5) }} />
        <h3 style={{ margin: 0, fontSize: 13.5, fontWeight: 800, letterSpacing: 0.3, color: active ? meta.hue : C.text }}>
          {meta.label}
        </h3>
        <span style={{ fontSize: 11, color: C.textFaint }}>{items.length} finding{items.length === 1 ? "" : "s"}</span>
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        {items.map((it) => <EvidenceCard key={it.id} item={it} />)}
      </div>
      {cat === "forensic" && overlays.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11.5, fontWeight: 700, color: C.textDim, marginBottom: 8 }}>Where the edit is — annotated page{overlays.length > 1 ? "s" : ""}</div>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {overlays.map((o, i) => (
              <figure key={i} style={{ margin: 0, background: C.bgInset, border: `1px solid ${C.border}`, borderRadius: radius.md, padding: 8 }}>
                <img src={o.img} alt={`Edit on ${o.doc} page ${o.page}`} style={{ width: "100%", borderRadius: 6, border: `1px solid ${C.borderStrong}`, display: "block" }} />
                <figcaption style={{ fontSize: 11, color: C.textDim, marginTop: 6 }}>
                  <span style={{ color: hexA(C.danger, 0.9) }}>◼</span> {o.doc}, page {o.page}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ── verdict header (gauge + action + rationale + subscores + export) ────────────
function MiniBar({ label, value, hue }) {
  if (value == null) return null;
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.textDim, marginBottom: 4 }}>
        <span>{label}</span><span style={{ color: C.text, fontWeight: 700 }}>{Math.round(value)}</span>
      </div>
      <div style={{ height: 6, background: "rgba(148,163,184,0.12)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: `linear-gradient(90deg, ${hexA(hue, 0.6)}, ${hue})`, transition: `width ${motion.slow} ${motion.ease}` }} />
      </div>
    </div>
  );
}

function VerdictHeader({ decision, onExport, innerRef }) {
  const ts = decision.trust_score;
  const act = ACT[decision.recommendation.action] || ACT.manual_review;
  return (
    <div ref={innerRef} style={{ scrollMarginTop: 80 }}>
    <Card tint={act.c} glow pad={20}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ position: "relative", display: "grid", placeItems: "center" }}>
          <Gauge value={ts.overall} accent={act.c} size={170} />
        </div>
        <div style={{ flex: 1, minWidth: 240 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8, background: hexA(act.c, 0.14), border: `1px solid ${hexA(act.c, 0.6)}`, color: act.c, borderRadius: radius.pill, padding: "6px 15px", fontWeight: 800, fontSize: 14, letterSpacing: 0.4, boxShadow: shadow.glow(act.c, 0.25) }}>
            <span>{act.glyph}</span>{act.label}
          </span>
          <p style={{ color: C.text, fontSize: 14, lineHeight: 1.6, margin: "12px 0 0", maxWidth: 560 }}>{decision.recommendation.rationale}</p>
          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            <Button variant="ghost" onClick={onExport}>⬇ Export evidence report</Button>
            <span style={{ fontSize: 11.5, color: C.textFaint, alignSelf: "center" }}>
              scoring v{ts.version} · {decision.evidence_chain.length} evidence items
            </span>
          </div>
        </div>
        <div style={{ width: 190 }}>
          <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 1, color: C.textFaint, marginBottom: 10 }}>SUB-SCORES</div>
          <MiniBar label="Forensic" value={ts.forensic_subscore} hue={LY.forensic.hue} />
          <MiniBar label="Semantic" value={ts.semantic_subscore} hue={LY.semantic.hue} />
          <MiniBar label="Model" value={ts.anomaly_subscore} hue={LY.model.hue} />
        </div>
      </div>
    </Card>
    </div>
  );
}

// ── normalise overlays (live base64 vs baked-in path) ───────────────────────────
function normOverlays(result) {
  if (Array.isArray(result?.overlays)) return result.overlays.map((o) => ({ doc: o.doc, page: o.page, img: o.src }));
  if (Array.isArray(result?.tamper_overlays)) return result.tamper_overlays.map((o) => ({ doc: o.doc, page: o.page, img: `data:image/png;base64,${o.image_b64}` }));
  return [];
}

// ── PACKET MODE ─────────────────────────────────────────────────────────────────
function PacketMode({ live }) {
  const [packets, setPackets] = useState([]);     // live list (browse all)
  const [selected, setSelected] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [source, setSource] = useState(null);      // 'live' | 'demo'
  const [showAll, setShowAll] = useState(false);
  const [packetFilter, setPacketFilter] = useState("all"); // all | fraud | clean
  const [activeLayer, setActiveLayer] = useState(null);

  const groupRefs = useRef({});
  const verdictRef = useRef(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!live) { setPackets([]); return; }
      try {
        const [pk] = await Promise.all([api.listPackets(), api.seedGraph().catch(() => null)]);
        if (alive) setPackets(pk.packets || []);
      } catch {
        /* live list unavailable — curated chips + demo fallback still work */
      }
    })();
    return () => { alive = false; };
  }, [live]);

  const scoreOne = useCallback(async (pktId) => {
    setSelected(pktId);
    setActiveLayer(null);
    setError(null);
    setResult(null);
    // Demo mode (or backend down) → baked-in decision if we have one.
    const useDemo = !live;
    if (useDemo) {
      const d = DEMO_DECISIONS[pktId];
      if (d) { setResult(d); setSource("demo"); return; }
      setError("This case isn't in the baked-in demo set — switch to Live to score all packets.");
      return;
    }
    setLoading(true);
    try {
      const r = await api.scorePacket(pktId, true);
      setResult(r); setSource("live");
    } catch (e) {
      // graceful fallback to baked-in if available
      const d = DEMO_DECISIONS[pktId];
      if (d) { setResult(d); setSource("demo"); }
      else setError(`Scoring failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [live]);

  const exportReport = () => {
    if (!result?.decision) return;
    const blob = new Blob([JSON.stringify(result.decision, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${selected}_trustshield_report.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const decision = result?.decision;
  const overlays = normOverlays(result);

  // spine status + grouped evidence
  const counts = { forensic: 0, semantic: 0, anomaly: 0, graph: 0 };
  (decision?.evidence_chain || []).forEach((e) => { if (counts[e.category] != null) counts[e.category]++; });
  const spineStatus = decision ? {
    forensic: { fired: counts.forensic > 0, count: counts.forensic },
    semantic: { fired: counts.semantic > 0, count: counts.semantic },
    anomaly: { fired: counts.anomaly > 0, count: counts.anomaly },
    trust: { fired: true, label: `score ${Math.round(decision.trust_score.overall)}` },
    graph: { fired: counts.graph > 0, count: counts.graph },
  } : {};
  const groups = PIPELINE_ORDER
    .map((cat) => ({ cat, items: (decision?.evidence_chain || []).filter((e) => e.category === cat) }))
    .filter((g) => g.items.length);

  const onLayerClick = (id) => {
    setActiveLayer(id);
    const target = id === "trust" ? verdictRef.current : groupRefs.current[id];
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div>
      {/* curated entry points */}
      <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 1, color: C.textFaint, marginBottom: 9 }}>
        START HERE — HIGHLIGHTED CASES
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        {CURATED_PACKETS.map((c) => {
          const on = selected === c.id;
          const hue = c.tone === "clean" ? C.success : C.danger;
          return (
            <button key={c.id} onClick={() => scoreOne(c.id)} title={c.blurb}
              style={{
                cursor: "pointer", textAlign: "left", minWidth: 200, flex: "1 1 200px",
                background: on ? hexA(hue, 0.1) : "rgba(148,163,184,0.04)",
                border: `1px solid ${on ? hexA(hue, 0.5) : C.border}`,
                borderRadius: radius.md, padding: "12px 14px",
                transition: `all ${motion.base} ${motion.ease}`,
                boxShadow: on ? shadow.glow(hue, 0.2) : "none",
              }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: hue, boxShadow: `0 0 6px ${hue}` }} />
                <span style={{ fontWeight: 700, fontSize: 13.5, color: C.text }}>{c.name}</span>
              </div>
              <div style={{ fontSize: 11.5, color: C.textDim, marginTop: 5, lineHeight: 1.45 }}>{c.blurb}</div>
            </button>
          );
        })}
      </div>

      {/* browse-all (live only) — collapsed by default, calm + filterable when open */}
      {live && packets.length > 0 && (() => {
        const nFraud = packets.filter((p) => p.ground_truth_label === "fraud").length;
        const nClean = packets.length - nFraud;
        const shown = packets.filter((p) =>
          packetFilter === "all" ? true
          : packetFilter === "fraud" ? p.ground_truth_label === "fraud"
          : p.ground_truth_label !== "fraud");
        return (
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
              <button onClick={() => setShowAll((v) => !v)}
                style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8, background: showAll ? hexA(C.accent, 0.08) : "rgba(148,163,184,0.04)", border: `1px solid ${showAll ? hexA(C.accent, 0.3) : C.border}`, borderRadius: radius.pill, padding: "6px 13px", color: showAll ? C.accent : C.textDim, fontSize: 12, fontWeight: 700, transition: `all ${motion.base} ${motion.ease}` }}>
                <span style={{ fontSize: 10, opacity: 0.8 }}>{showAll ? "▾" : "▸"}</span>
                Browse all {packets.length} packets
                <span style={{ fontSize: 10.5, fontWeight: 600, color: C.textFaint }}>· {nClean} clean · {nFraud} flagged</span>
              </button>
              {showAll && (
                <div style={{ display: "inline-flex", background: "rgba(148,163,184,0.05)", border: `1px solid ${C.border}`, borderRadius: radius.pill, padding: 3 }}>
                  {[["all", "All"], ["fraud", "Flagged"], ["clean", "Clean"]].map(([k, label]) => {
                    const on = packetFilter === k;
                    const hue = k === "fraud" ? C.danger : k === "clean" ? C.success : C.accent;
                    return (
                      <button key={k} onClick={() => setPacketFilter(k)}
                        style={{ cursor: "pointer", border: "none", borderRadius: radius.pill, padding: "4px 12px", fontSize: 11.5, fontWeight: 700, color: on ? "#04131c" : C.textDim, background: on ? hue : "transparent", transition: `all ${motion.base} ${motion.ease}` }}>
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {showAll && (
              <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(190px,1fr))", maxHeight: 320, overflowY: "auto", marginTop: 12, paddingRight: 4 }}>
                {shown.map((p) => {
                  const fraud = p.ground_truth_label === "fraud";
                  const on = selected === p.packet_id;
                  const hue = fraud ? C.danger : C.success;
                  const ftype = fraud ? (p.ground_truth_fraud_types?.[0] || "fraud").replace(/_/g, " ") : null;
                  return (
                    <button key={p.packet_id} onClick={() => scoreOne(p.packet_id)}
                      title={(p.ground_truth_fraud_types || []).join(", ")}
                      style={{ cursor: "pointer", textAlign: "left", background: on ? hexA(C.accent, 0.1) : "rgba(148,163,184,0.03)", border: `1px solid ${on ? hexA(C.accent, 0.5) : C.border}`, borderRadius: radius.md, padding: "9px 11px", color: C.text, transition: `all ${motion.base} ${motion.ease}` }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: hue, boxShadow: `0 0 6px ${hexA(hue, 0.7)}`, flexShrink: 0 }} />
                        <span style={{ fontWeight: 700, fontSize: 12.5 }}>{p.packet_id}</span>
                      </div>
                      <div style={{ fontSize: 10.5, color: C.textFaint, marginTop: 4 }}>{p.applicant_name || "—"} · {p.n_docs} docs</div>
                      <div style={{ fontSize: 10, color: fraud ? hexA(C.danger, 0.85) : C.textFaint, marginTop: 3, textTransform: "capitalize", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {ftype || "no findings expected"}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })()}

      {error && <Card style={{ borderColor: hexA(C.danger, 0.4), background: hexA(C.danger, 0.06), color: "#fca5a5", fontSize: 13.5 }} pad={14}>{error}</Card>}

      {!decision && !loading && !error && (
        <div style={{ color: C.textFaint, padding: "64px 20px", textAlign: "center", border: `1px dashed ${C.borderStrong}`, borderRadius: radius.lg }}>
          Pick a case above to run the full <span style={{ color: C.textDim }}>forensic → semantic → model → trust → graph</span> pipeline.
        </div>
      )}
      {loading && (
        <div style={{ color: C.textDim, padding: "64px 20px", textAlign: "center" }}>
          <span style={{ display: "inline-block", width: 18, height: 18, border: `2px solid ${hexA(C.accent, 0.3)}`, borderTopColor: C.accent, borderRadius: "50%", animation: "ts-spin 0.7s linear infinite", verticalAlign: "middle", marginRight: 10 }} />
          Analyzing {selected} — forensics, semantics, model, graph…
        </div>
      )}

      {decision && (
        <div style={{ display: "grid", gap: 16 }}>
          {source === "demo" && (
            <div style={{ fontSize: 11.5, color: C.warning, display: "inline-flex", alignItems: "center", gap: 7 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.warning }} /> Showing baked-in demo data (backend offline) — captured from a real backend run.
            </div>
          )}
          <VerdictHeader decision={decision} onExport={exportReport} innerRef={verdictRef} />

          {/* the 5-layer pipeline spine — click a layer to jump to its evidence */}
          <Card pad={16}>
            <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 1, color: C.textFaint, marginBottom: 12 }}>5-LAYER DETECTION PIPELINE — click a layer to inspect its findings</div>
            <PipelineDiagram mode="spine" status={spineStatus} activeId={activeLayer} onLayerClick={onLayerClick} />
          </Card>

          {/* evidence grouped by layer */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 460px", gap: 16, alignItems: "start" }} className="ts-evidence-grid">
            <div style={{ display: "grid", gap: 20 }}>
              {groups.map((g) => (
                <EvidenceGroup
                  key={g.cat}
                  cat={g.cat}
                  items={g.items}
                  overlays={overlays}
                  active={activeLayer === CAT[g.cat].spine}
                  innerRef={(el) => { groupRefs.current[g.cat] = el; }}
                />
              ))}
            </div>
            <Card pad={16} style={{ position: "sticky", top: 80 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ width: 9, height: 9, borderRadius: 3, background: LY.graph.hue, boxShadow: shadow.glow(LY.graph.hue, 0.5) }} />
                <h3 style={{ margin: 0, fontSize: 13.5, fontWeight: 800, color: C.text }}>Cross-application graph</h3>
              </div>
              <p style={{ fontSize: 11.5, color: C.textFaint, margin: "0 0 10px", lineHeight: 1.5 }}>
                Links this applicant to shared PANs, employers, collateral & templates — how rings and double-financing surface.
              </p>
              <GraphView subgraph={result.subgraph} focusId={`app:${selected}`} />
            </Card>
          </div>
        </div>
      )}

      <style>{`@media (max-width: 900px){ .ts-evidence-grid{ grid-template-columns:1fr !important; } }`}</style>
    </div>
  );
}

// ── SINGLE-DOCUMENT MODE ────────────────────────────────────────────────────────
function SingleDocMode({ live }) {
  const [busy, setBusy] = useState(false);
  const [deepBusy, setDeepBusy] = useState(false);   // the opt-in learned-model re-run
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [name, setName] = useState(null);
  const [lastFile, setLastFile] = useState(null);    // kept so a deep scan can re-run the same file
  const [openEx, setOpenEx] = useState(null);   // baked-detection lightbox (Demo mode)

  const analyze = async (file, label, deep = false) => {
    if (deep) setDeepBusy(true); else { setBusy(true); setRes(null); }
    setErr(null); setName(label); setLastFile(file);
    try { setRes(await api.analyzeImage(file, deep)); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); setDeepBusy(false); }
  };
  const deepScan = () => { if (lastFile) analyze(lastFile, name, true); };
  const runExample = async (ex) => {
    try {
      const r = await fetch(ex.path, { cache: "no-store" });
      if (!r.ok) throw new Error(`example not found (${r.status})`);
      const b = await r.blob();
      await analyze(new File([b], ex.label, { type: b.type || "image/jpeg" }), ex.label);
    } catch (e) { setErr(e.message); }
  };
  const onUpload = (e) => { const f = e.target.files?.[0]; if (f) analyze(f, f.name); };

  const vc = res ? (VERDICT_C[res.verdict] || C.info) : C.info;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Card pad={18}>
        <p style={{ color: C.textDim, fontSize: 13.5, margin: "0 0 14px", lineHeight: 1.6, maxWidth: 720 }}>
          Drop one scanned or photographed document. TrustShield runs <b style={{ color: LY.forensic.hue }}>pixel forensics</b> (ELA,
          sensor-noise loss, copy-move), a <b style={{ color: LY.semantic.hue }}>semantic ID check</b> (PAN/Aadhaar validity + QR
          cross-verify), and reports a verdict with the edit <b>localized</b> — 100% on-device.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {CURATED_IMAGES.map((ex) => (
            <Button key={ex.key} variant="ghost" disabled={busy}
              onClick={() => (live ? runExample(ex) : setOpenEx(ex))}>
              {`${ex.doc_type.replace("_", " ")} · ${ex.difficulty}`}
            </Button>
          ))}
          <label style={{
            cursor: live ? "pointer" : "not-allowed", opacity: live ? 1 : 0.5,
            display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13.5, fontWeight: 700,
            background: "rgba(148,163,184,0.06)", border: `1px solid ${C.borderStrong}`,
            color: "#dbe5f1", borderRadius: radius.md, padding: "10px 16px",
          }}>
            Upload image…
            <input type="file" accept="image/*" onChange={onUpload} disabled={!live} style={{ display: "none" }} />
          </label>
        </div>
        {!live && (
          <div style={{ marginTop: 12, fontSize: 12.5, color: C.warning }}>
            Live analysis needs the forensics service (:8001). Below are the <b>real</b> results these examples produce.
          </div>
        )}
      </Card>

      {/* offline: the new realistic docs with their REAL baked detection — click to open boxed */}
      {!live && (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(250px,1fr))" }}>
          {CURATED_IMAGES.map((ex) => {
            const c = VERDICT_C[ex.verdict] || C.info;
            const m = METHOD[ex.method] || METHOD.none;
            const caught = ex.boxes.length > 0 && ex.method !== "clean" && ex.method !== "none";
            return (
              <Card key={ex.key} pad={10} style={{ cursor: "pointer" }} onClick={() => setOpenEx(ex)}>
                <BoxedImage src={ex.edited_img} alt={ex.label} boxes={caught ? ex.boxes : []} imgW={ex.w} imgH={ex.h}
                  hue={m.hue} label={caught ? "detected" : null} style={{ maxHeight: 180 }} />
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 10, flexWrap: "wrap" }}>
                  <Badge c={c} solid>{ex.verdict}</Badge>
                  <Badge c={m.hue}>{m.label}</Badge>
                </div>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: C.text, marginTop: 8 }}>{ex.label}</div>
                <div style={{ fontSize: 11.5, color: C.textFaint, marginTop: 4 }}>Click to open · trust {ex.trust}/100</div>
              </Card>
            );
          })}
        </div>
      )}

      {err && <Card pad={14} style={{ borderColor: hexA(C.danger, 0.4), background: hexA(C.danger, 0.06), color: "#fca5a5", fontSize: 13.5 }}>{err}</Card>}
      {busy && (
        <div style={{ color: C.textDim, padding: "20px", textAlign: "center" }}>
          <span style={{ display: "inline-block", width: 16, height: 16, border: `2px solid ${hexA(C.accent, 0.3)}`, borderTopColor: C.accent, borderRadius: "50%", animation: "ts-spin 0.7s linear infinite", verticalAlign: "middle", marginRight: 8 }} />
          Analyzing {name}…
        </div>
      )}

      {res && res.ok && (
        <div style={{ display: "grid", gap: 16 }}>
          <Card tint={vc} glow pad={18}>
            <div style={{ display: "flex", gap: 22, alignItems: "center", flexWrap: "wrap" }}>
              <Gauge value={res.image_trust} accent={vc} size={150} label="image trust" />
              <div style={{ flex: 1, minWidth: 220 }}>
                <Badge c={vc} solid style={{ fontSize: 13, padding: "5px 13px" }}>{res.verdict}</Badge>
                <div style={{ fontSize: 13, color: C.textDim, marginTop: 10 }}>{name}</div>
                {res.identifier_check?.fields?.pan && (() => {
                  const ok = res.identifier_check.kyc?.pan?.valid;
                  return (
                    <div style={{ marginTop: 8, fontSize: 13, color: C.textDim }}>
                      Document number — <span style={{ color: ok ? C.success : C.danger, fontWeight: 700 }}>PAN {res.identifier_check.fields.pan}: {ok ? "valid" : "INVALID"}</span>
                      {!ok && res.identifier_check.kyc?.pan?.reason ? ` (${res.identifier_check.kyc.pan.reason})` : ""}
                    </div>
                  );
                })()}
                <div style={{ marginTop: 6, fontSize: 11.5, color: C.textFaint }}>
                  Layers: pixel · recapture · semantic ID · QR{res.identifier_check?.qr?.qr_found ? " (read)" : ""}
                  {res.deep_used ? <> · <span style={{ color: LY.model.hue }}>learned model (deep scan)</span></> : " (heuristics)"}.
                </div>

                {/* deep scan: opt-in learned model — higher recall on seamless edits, ~19% clean-doc FP */}
                {!res.deep_used && res.deep_available && (
                  <div style={{ marginTop: 12 }}>
                    <Button variant="ghost" c={LY.model.hue} disabled={deepBusy} onClick={deepScan}>
                      {deepBusy
                        ? <><span style={{ display: "inline-block", width: 13, height: 13, border: `2px solid ${hexA(LY.model.hue, 0.3)}`, borderTopColor: LY.model.hue, borderRadius: "50%", animation: "ts-spin 0.7s linear infinite", verticalAlign: "middle", marginRight: 7 }} />Running learned model…</>
                        : "🔬 Run learned model (deep scan)"}
                    </Button>
                    <div style={{ fontSize: 11, color: C.textFaint, marginTop: 6, lineHeight: 1.5, maxWidth: 360 }}>
                      Catches seamless edits the pixel heuristics miss — but the model has a measured
                      <b style={{ color: C.warning }}> ~19% false-positive rate on clean docs</b>, so it's opt-in, never the default.
                    </div>
                  </div>
                )}
                {res.deep_used && (
                  <div style={{ marginTop: 12, fontSize: 11.5, color: C.textDim, lineHeight: 1.55, maxWidth: 380, borderLeft: `2px solid ${hexA(LY.model.hue, 0.5)}`, paddingLeft: 10 }}>
                    Learned model {res.findings?.some((f) => f.values?.detector === "forgery_model") ? "flagged a region above" : "found nothing"}.
                    Treat with care — it false-flags <b style={{ color: C.warning }}>~19%</b> of clean documents (it over-flags the Form-16 salary area).
                  </div>
                )}
                {!res.deep_used && !res.deep_available && res.verdict === "CLEAN" && (
                  <div style={{ marginTop: 10, fontSize: 11, color: C.textFaint, maxWidth: 360, lineHeight: 1.5 }}>
                    Learned-model deep scan unavailable here (needs torch/weights) — heuristics only.
                  </div>
                )}
              </div>
            </div>
          </Card>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }} className="ts-img-grid">
            <figure style={{ margin: 0, background: C.bgInset, border: `1px solid ${C.border}`, borderRadius: radius.md, padding: 8 }}>
              <img src={`data:image/png;base64,${res.annotated_b64}`} alt="annotated edit regions" style={{ width: "100%", borderRadius: 6, border: `1px solid ${C.borderStrong}`, display: "block" }} />
              <figcaption style={{ fontSize: 11, color: C.textDim, marginTop: 6 }}><span style={{ color: hexA(C.danger, 0.9) }}>◼</span> detected edit region(s)</figcaption>
            </figure>
            {res.ela_b64 && (
              <figure style={{ margin: 0, background: C.bgInset, border: `1px solid ${C.border}`, borderRadius: radius.md, padding: 8 }}>
                <img src={`data:image/png;base64,${res.ela_b64}`} alt="ELA heatmap" style={{ width: "100%", borderRadius: 6, border: `1px solid ${C.borderStrong}`, display: "block" }} />
                <figcaption style={{ fontSize: 11, color: C.textDim, marginTop: 6 }}>ELA heatmap — compression-error energy</figcaption>
              </figure>
            )}
          </div>

          <section>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span style={{ width: 9, height: 9, borderRadius: 3, background: LY.forensic.hue, boxShadow: shadow.glow(LY.forensic.hue, 0.5) }} />
              <h3 style={{ margin: 0, fontSize: 13.5, fontWeight: 800, color: C.text }}>Findings</h3>
              <span style={{ fontSize: 11, color: C.textFaint }}>{res.findings.length}</span>
            </div>
            {res.findings.length === 0
              ? <div style={{ color: "#86efac", fontSize: 13 }}>No edit signals detected — looks clean.</div>
              : <div style={{ display: "grid", gap: 8 }}>{res.findings.map((f, i) => <EvidenceCard key={i} item={{ ...f, id: i }} />)}</div>}
          </section>
        </div>
      )}
      {res && !res.ok && <Card pad={14} style={{ color: "#fca5a5", fontSize: 13 }}>Could not analyze: {res.error}</Card>}

      {openEx && <DocModal ex={openEx} onClose={() => setOpenEx(null)} />}
      <style>{`@media (max-width: 720px){ .ts-img-grid{ grid-template-columns:1fr !important; } }`}</style>
    </div>
  );
}

// ── page shell ──────────────────────────────────────────────────────────────────
export default function Investigator() {
  const [mode, setMode] = useState("packet");      // 'packet' | 'single'
  const [live, setLive] = useState(true);           // Live (backend) vs Demo (baked-in)
  const [autoChecked, setAutoChecked] = useState(false);
  const risk = useHealth(SERVICES[1].base);
  const forensics = useHealth(SERVICES[0].base);

  // Auto-pick demo mode once if the relevant backend is down on first health resolve.
  useEffect(() => {
    if (autoChecked) return;
    if (risk.status === "loading") return;
    if (risk.status === "down") setLive(false);
    setAutoChecked(true);
  }, [risk.status, autoChecked]);

  return (
    <div style={{ maxWidth, margin: "0 auto", padding: "28px 24px 56px", fontFamily: font.sans }}>
      {/* header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 14, marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, letterSpacing: -0.6 }}>Investigator console</h1>
          <p style={{ color: C.textDim, margin: "6px 0 0", fontSize: 14, maxWidth: 620, lineHeight: 1.55 }}>
            Run the full detection pipeline on a loan packet, or examine a single document. Every verdict is
            explainable — trust score, evidence chain, and the edit located on the page.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 11.5, color: C.textDim, background: hexA(C.success, 0.08), border: `1px solid ${hexA(C.success, 0.3)}`, borderRadius: radius.pill, padding: "5px 11px" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.success, boxShadow: `0 0 7px ${C.success}` }} /> on-device
          </span>
          {/* live / demo toggle */}
          <div style={{ display: "inline-flex", background: "rgba(148,163,184,0.06)", border: `1px solid ${C.border}`, borderRadius: radius.pill, padding: 3 }}>
            {[["live", "Live"], ["demo", "Demo"]].map(([k, label]) => {
              const on = (k === "live") === live;
              return (
                <button key={k} onClick={() => setLive(k === "live")}
                  style={{ cursor: "pointer", border: "none", borderRadius: radius.pill, padding: "5px 13px", fontSize: 12, fontWeight: 700, color: on ? "#04131c" : C.textDim, background: on ? C.accent : "transparent", transition: `all ${motion.base} ${motion.ease}` }}>
                  {label}
                </button>
              );
            })}
          </div>
          {live && (
            <span style={{ display: "inline-flex", gap: 12 }}>
              <ServiceDot label={SERVICES[0].label} base={SERVICES[0].base} />
              <ServiceDot label={SERVICES[1].label} base={SERVICES[1].base} />
            </span>
          )}
        </div>
      </div>

      {/* mode toggle */}
      <div style={{ display: "inline-flex", background: "rgba(148,163,184,0.05)", border: `1px solid ${C.border}`, borderRadius: radius.md, padding: 4, marginBottom: 18 }}>
        {[["packet", "Loan packet", "Full 5-layer pipeline"], ["single", "Single document", "Pixel + semantic forensics"]].map(([k, label, sub]) => {
          const on = mode === k;
          return (
            <button key={k} onClick={() => setMode(k)}
              style={{ cursor: "pointer", border: "none", borderRadius: radius.sm, padding: "9px 16px", textAlign: "left", background: on ? hexA(C.accent, 0.14) : "transparent", color: on ? C.accent : C.textDim, transition: `all ${motion.base} ${motion.ease}` }}>
              <div style={{ fontSize: 13.5, fontWeight: 800 }}>{label}</div>
              <div style={{ fontSize: 10.5, color: on ? hexA(C.accent, 0.8) : C.textFaint, marginTop: 1 }}>{sub}</div>
            </button>
          );
        })}
      </div>

      {mode === "packet"
        ? <PacketMode live={live && risk.status !== "down"} />
        : <SingleDocMode live={live && forensics.status !== "down"} />}
    </div>
  );
}
