import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ui, ACTION } from "../theme.js";
import DecisionView from "../components/DecisionView.jsx";

function ActionBadge({ action }) {
  const a = ACTION[action] || {};
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color: a.c, background: (a.c || "#888") + "22", border: `1px solid ${a.c}`, borderRadius: 6, padding: "1px 8px" }}>
      {a.label || action}
    </span>
  );
}

export default function UserDashboard() {
  const [purpose, setPurpose] = useState("kyc");
  const [files, setFiles] = useState([]);
  const [loanAmount, setLoanAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [cases, setCases] = useState([]);

  const loadCases = () => api.listCases().then((d) => setCases(d.cases || [])).catch(() => {});
  useEffect(() => { loadCases(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!files.length) { setError("Select at least one document to upload."); return; }
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.submitCase(purpose, files, loanAmount || null);
      setResult(r);
      loadCases();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={ui.page}>
      <h1 style={{ fontSize: 26 }}>New submission</h1>
      <form onSubmit={submit} style={{ ...ui.card, display: "grid", gap: 12, maxWidth: 620 }}>
        {error && <div style={ui.error}>{error}</div>}
        <label style={ui.label}>Purpose
          <select style={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="kyc">KYC verification</option>
            <option value="loan">Loan application</option>
            <option value="other">Other</option>
          </select>
        </label>
        {purpose === "loan" && (
          <label style={ui.label}>Requested loan amount (INR, optional)
            <input style={ui.input} type="number" value={loanAmount} onChange={(e) => setLoanAmount(e.target.value)} />
          </label>
        )}
        <label style={ui.label}>Documents (PDF or image — PAN, Aadhaar, Form 16, salary slip, bank statement…)
          <input style={{ ...ui.input, padding: 8 }} type="file" multiple
            onChange={(e) => setFiles(Array.from(e.target.files))} />
        </label>
        {files.length > 0 && <div style={{ fontSize: 12, color: "#94a3b8" }}>{files.length} file(s) selected</div>}
        <button style={ui.btn} disabled={busy}>{busy ? "Analyzing…" : "Submit for analysis"}</button>
      </form>

      {result && (
        <div style={{ marginTop: 24 }}>
          <h2 style={ui.sectionTitle}>Result</h2>
          <DecisionView decision={result.decision} tamperOverlays={result.tamper_overlays} />
        </div>
      )}

      <h2 style={{ ...ui.sectionTitle, marginTop: 28 }}>My submissions ({cases.length})</h2>
      <div style={{ display: "grid", gap: 6 }}>
        {cases.length === 0 && <div style={{ color: "#64748b", fontSize: 14 }}>No submissions yet.</div>}
        {cases.map((c) => (
          <Link key={c.id} to={`/case/${c.id}`} style={{ textDecoration: "none" }}>
            <div style={{ ...ui.card, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 13 }}>{c.purpose.toUpperCase()}</span>
              <span style={{ color: "#94a3b8", fontSize: 12 }}>trust {Math.round(c.trust_score)}</span>
              <ActionBadge action={c.action} />
              <span style={{ marginLeft: "auto", color: "#64748b", fontSize: 12 }}>
                {new Date(c.created_at * 1000).toLocaleString()}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
