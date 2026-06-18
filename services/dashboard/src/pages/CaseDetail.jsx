import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api.js";
import { ui } from "../theme.js";
import DecisionView from "../components/DecisionView.jsx";

function KycBadge({ kyc }) {
  const entries = Object.entries(kyc || {});
  if (!entries.length) return null;
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
      {entries.map(([k, v]) => {
        const ok = v.valid;
        const c = ok ? "#22c55e" : "#ef4444";
        return (
          <span key={k} title={v.reason} style={{ fontSize: 11, color: c, border: `1px solid ${c}`, borderRadius: 6, padding: "1px 6px" }}>
            {k.toUpperCase()}: {ok ? "valid" : "invalid"}{v.masked ? " (masked)" : ""}
          </span>
        );
      })}
    </div>
  );
}

export default function CaseDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getCase(id).then(setData).catch((e) => setError(e.message));
  }, [id]);

  const exportReport = () => {
    if (!data?.decision) return;
    const blob = new Blob([JSON.stringify(data.decision, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${id}_trustshield_report.json`; a.click();
    URL.revokeObjectURL(url);
  };

  if (error) return <div style={ui.page}><div style={ui.error}>{error}</div><Link to="/app">← back</Link></div>;
  if (!data) return <div style={ui.page}><div style={{ color: "#94a3b8" }}>Loading case…</div></div>;

  return (
    <div style={ui.page}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>Case {id}</h1>
        <span style={{ color: "#94a3b8", fontSize: 13 }}>{data.user_email} · {data.purpose}</span>
      </div>

      <section style={{ margin: "16px 0" }}>
        <h2 style={ui.sectionTitle}>Submitted documents ({data.documents?.length || 0})</h2>
        <div style={{ display: "grid", gap: 8 }}>
          {(data.documents || []).map((d, i) => (
            <div key={i} style={{ ...ui.card, padding: "10px 14px" }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 13 }}>{d.filename}</span>
                <span style={{ fontSize: 11, color: "#64748b", border: "1px solid #334155", borderRadius: 4, padding: "1px 6px" }}>{d.doc_type || "?"}</span>
              </div>
              <KycBadge kyc={d.kyc} />
            </div>
          ))}
        </div>
      </section>

      <DecisionView
        decision={data.decision}
        tamperOverlays={data.tamper_overlays}
        onExport={exportReport}
      />
    </div>
  );
}
