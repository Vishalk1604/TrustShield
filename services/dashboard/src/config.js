// Local service endpoints. Defaults point at the LOCAL services only — never a remote host.
// Override at build/dev time with VITE_FORENSICS_URL / VITE_RISK_URL if ports change.
export const FORENSICS_URL = import.meta.env.VITE_FORENSICS_URL || "http://localhost:8001";
export const RISK_URL = import.meta.env.VITE_RISK_URL || "http://localhost:8002";

export const SERVICES = [
  { key: "forensics", label: "Forensics + Ingestion", base: FORENSICS_URL },
  { key: "risk", label: "Risk + Scoring", base: RISK_URL },
];
