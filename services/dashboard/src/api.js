// Thin fetch wrappers around the LOCAL risk + forensics services. No remote hosts.
import { RISK_URL, FORENSICS_URL } from "./config.js";

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postFile(url, file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(url, { method: "POST", body: fd, cache: "no-store" });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: (base) => getJSON(`${base}/health`),
  listPackets: () => getJSON(`${RISK_URL}/risk/demo/packets`),
  seedGraph: () => postJSON(`${RISK_URL}/risk/demo/seed`, {}),
  scorePacket: (packetId, useGraph = true) =>
    postJSON(`${RISK_URL}/risk/demo/score/${packetId}?use_graph=${useGraph}`, {}),
  clusters: () => getJSON(`${RISK_URL}/risk/graph/clusters`),
  // §10 image/pixel forensics — detect & localize edits in a scanned/photo document.
  // `deep` opts into the learned U-Net (v2: ~100% recall on synthetic seamless edits, ~2-3% clean FP — opt-in).
  analyzeImage: (file, deep = false) =>
    postFile(`${FORENSICS_URL}/forensics/analyze-image${deep ? "?deep=true" : ""}`, file),
};

export { RISK_URL, FORENSICS_URL };
