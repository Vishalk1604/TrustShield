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

export const api = {
  health: (base) => getJSON(`${base}/health`),
  listPackets: () => getJSON(`${RISK_URL}/risk/demo/packets`),
  seedGraph: () => postJSON(`${RISK_URL}/risk/demo/seed`, {}),
  scorePacket: (packetId, useGraph = true) =>
    postJSON(`${RISK_URL}/risk/demo/score/${packetId}?use_graph=${useGraph}`, {}),
  clusters: () => getJSON(`${RISK_URL}/risk/graph/clusters`),
};

export { RISK_URL, FORENSICS_URL };
