import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { ui } from "../theme.js";

export default function SignIn() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      const r = await login(email, password);
      navigate(r.role === "admin" ? "/admin" : "/app");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ ...ui.page, maxWidth: 420 }}>
      <h1 style={{ fontSize: 24 }}>Sign in</h1>
      <form onSubmit={submit} style={{ ...ui.card, display: "grid", gap: 12 }}>
        {error && <div style={ui.error}>{error}</div>}
        <label style={ui.label}>Email
          <input style={ui.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label style={ui.label}>Password
          <input style={ui.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button style={ui.btn} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <div style={{ fontSize: 13, color: "#94a3b8" }}>
          No account? <Link to="/signup">Create one</Link>
        </div>
      </form>
    </div>
  );
}
