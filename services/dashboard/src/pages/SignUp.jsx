import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { ui } from "../theme.js";

export default function SignUp() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      const r = await register(email, password, role);
      navigate(r.role === "admin" ? "/admin" : "/app");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ ...ui.page, maxWidth: 420 }}>
      <h1 style={{ fontSize: 24 }}>Create account</h1>
      <form onSubmit={submit} style={{ ...ui.card, display: "grid", gap: 12 }}>
        {error && <div style={ui.error}>{error}</div>}
        <label style={ui.label}>Email
          <input style={ui.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label style={ui.label}>Password (min 6 chars)
          <input style={ui.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <label style={ui.label}>Account type
          <select style={ui.input} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="user">Applicant (user)</option>
            <option value="admin">Underwriter (admin)</option>
          </select>
        </label>
        <button style={ui.btn} disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <div style={{ fontSize: 13, color: "#94a3b8" }}>
          Already have an account? <Link to="/signin">Sign in</Link>
        </div>
      </form>
    </div>
  );
}
