import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ui, ACTION } from "../theme.js";

function ActionBadge({ action }) {
  const a = ACTION[action] || {};
  return (
    <span style={{ fontSize: 11, fontWeight: 700, color: a.c, background: (a.c || "#888") + "22", border: `1px solid ${a.c}`, borderRadius: 6, padding: "1px 8px" }}>
      {a.label || action}
    </span>
  );
}

export default function AdminDashboard() {
  const [cases, setCases] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.listCases().then((d) => setCases(d.cases || [])).catch((e) => setError(e.message));
  }, []);

  return (
    <div style={ui.page}>
      <h1 style={{ fontSize: 26 }}>Review queue <span style={{ color: "#64748b", fontSize: 16 }}>({cases.length})</span></h1>
      {error && <div style={ui.error}>{error}</div>}
      <div style={{ display: "grid", gap: 6, marginTop: 12 }}>
        <div style={{ display: "flex", gap: 12, padding: "0 14px", fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5 }}>
          <span style={{ flex: 1 }}>Applicant</span>
          <span style={{ width: 90 }}>Purpose</span>
          <span style={{ width: 70 }}>Trust</span>
          <span style={{ width: 130 }}>Action</span>
          <span style={{ width: 160 }}>Submitted</span>
        </div>
        {cases.length === 0 && <div style={{ color: "#64748b", fontSize: 14, padding: "12px 14px" }}>No submissions yet.</div>}
        {cases.map((c) => (
          <Link key={c.id} to={`/case/${c.id}`} style={{ textDecoration: "none" }}>
            <div style={{ ...ui.card, padding: "10px 14px", display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ flex: 1, color: "#e2e8f0", fontSize: 13 }}>{c.user_email}</span>
              <span style={{ width: 90, color: "#94a3b8", fontSize: 12 }}>{c.purpose}</span>
              <span style={{ width: 70, color: "#cbd5e1", fontSize: 13 }}>{Math.round(c.trust_score)}</span>
              <span style={{ width: 130 }}><ActionBadge action={c.action} /></span>
              <span style={{ width: 160, color: "#64748b", fontSize: 12 }}>{new Date(c.created_at * 1000).toLocaleString()}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
