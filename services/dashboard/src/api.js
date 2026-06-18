// Thin fetch wrappers around the LOCAL risk + forensics services. No remote hosts.
import { RISK_URL, FORENSICS_URL } from "./config.js";

const TOKEN_KEY = "ts_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
}

async function toError(res) {
  let body = {};
  try { body = await res.json(); } catch { /* ignore */ }
  return new Error(body.detail || `${res.status} ${res.statusText}`);
}

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw await toError(res);
  return res.json();
}

async function postForm(url, formData) {
  const res = await fetch(url, { method: "POST", headers: authHeaders(), body: formData, cache: "no-store" });
  if (!res.ok) throw await toError(res);
  return res.json();
}

export const api = {
  health: (base) => fetch(`${base}/health`, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }),

  // ── auth ──
  register: (email, password, role) => postJSON(`${RISK_URL}/auth/register`, { email, password, role }),
  login: (email, password) => postJSON(`${RISK_URL}/auth/login`, { email, password }),
  me: () => getJSON(`${RISK_URL}/auth/me`),

  // ── cases (user submissions / admin review) ──
  submitCase: (purpose, files, loanAmount) => {
    const fd = new FormData();
    fd.append("purpose", purpose);
    if (loanAmount) fd.append("loan_amount", String(loanAmount));
    for (const f of files) fd.append("files", f);
    return postForm(`${RISK_URL}/cases`, fd);
  },
  listCases: () => getJSON(`${RISK_URL}/cases`),
  getCase: (id) => getJSON(`${RISK_URL}/cases/${id}`),

  // ── synthetic demo (kept) ──
  listPackets: () => getJSON(`${RISK_URL}/risk/demo/packets`),
  seedGraph: () => postJSON(`${RISK_URL}/risk/demo/seed`, {}),
  scorePacket: (id, useGraph = true) => postJSON(`${RISK_URL}/risk/demo/score/${id}?use_graph=${useGraph}`, {}),
};

export { RISK_URL, FORENSICS_URL };
