// Top navigation: brand + public links + auth state + live service-health dots.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { SERVICES } from "../config.js";
import { api } from "../api.js";

function useHealth(base) {
  const [status, setStatus] = useState("loading");
  useEffect(() => {
    let alive = true;
    const ping = () => api.health(base)
      .then((b) => alive && setStatus(b.status === "ok" ? "ok" : "down"))
      .catch(() => alive && setStatus("down"));
    ping();
    const id = setInterval(ping, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [base]);
  return status;
}

function HealthDot({ label, base }) {
  const status = useHealth(base);
  const color = status === "ok" ? "#22c55e" : status === "down" ? "#ef4444" : "#eab308";
  return (
    <span style={{ fontSize: 12, color: "#94a3b8", display: "inline-flex", alignItems: "center" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}`, marginRight: 5 }} />
      {label}
    </span>
  );
}

const link = { color: "#cbd5e1", textDecoration: "none", fontSize: 14 };

export default function Nav() {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const signOut = () => { logout(); navigate("/"); };

  return (
    <nav style={{ borderBottom: "1px solid #1e293b", background: "#0b1220" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "12px 24px", display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
        <Link to="/" style={{ ...link, fontWeight: 800, fontSize: 17, color: "#e2e8f0" }}>
          🛡️ TrustShield
        </Link>
        <Link to="/" style={link}>Home</Link>
        <Link to="/about" style={link}>About</Link>
        {auth && <Link to={auth.role === "admin" ? "/admin" : "/app"} style={link}>Dashboard</Link>}

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          {SERVICES.map((s) => <HealthDot key={s.key} label={s.key} base={s.base} />)}
          {auth ? (
            <>
              <span style={{ fontSize: 12, color: "#64748b" }}>{auth.email} · {auth.role}</span>
              <button onClick={signOut} style={{ cursor: "pointer", background: "#1e293b", border: "1px solid #334155", color: "#cbd5e1", borderRadius: 8, padding: "6px 12px", fontSize: 13 }}>Sign out</button>
            </>
          ) : (
            <Link to="/signin" style={{ ...link, color: "#38bdf8", fontWeight: 700 }}>Sign in</Link>
          )}
        </div>
      </div>
    </nav>
  );
}
