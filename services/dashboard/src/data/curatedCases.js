// Curated entry points for the Investigator — judge-friendly named cases instead of raw IDs.
// Packet cases map to real synthetic packet ids (baked-in fallback lives in demoDecisions.js).
// Image cases are the committed examples under public/examples/ with their REAL verdicts
// (from results / PROGRESS) so single-document mode stays alive when forensics is down.

export const CURATED_PACKETS = [
  {
    id: "PKT-0001",
    name: "Clean salaried applicant",
    blurb: "A well-formed packet — approves cleanly with a full evidence trail.",
    tone: "clean",
  },
  {
    id: "PKT-0010",
    name: "Forged Form 16",
    blurb: "An income figure was painted over — caught by pixel forensics + re-OCR cross-check.",
    tone: "fraud",
  },
  {
    id: "PKT-0028",
    name: "Tampered encumbrance",
    blurb: "The EC hides a ₹42L charge that the CERSAI registry still shows — critical semantic hit.",
    tone: "fraud",
  },
  {
    id: "PKT-0031",
    name: "Double-financing ring",
    blurb: "The same collateral is pledged across three applications — only the graph sees it.",
    tone: "fraud",
  },
];

export const CURATED_IMAGES = [
  {
    label: "Clean Form 16",
    path: "examples/clean_form16.jpg",
    verdict: "CLEAN",
    trust: 100,
    note: "No edit signals — the page's sensor-noise floor is intact everywhere. Zero false positives is the heuristics' guarantee (precision 1.0).",
  },
  {
    label: "Edited number",
    path: "examples/edited_number_form16.jpg",
    verdict: "EDITED",
    trust: 0,
    note: "A salary figure was repainted. The repaint erased the local noise residual; the detector localizes it to the edited box.",
  },
  {
    label: "Spliced patch",
    path: "examples/spliced_form16.jpg",
    verdict: "EDITED",
    trust: 15,
    note: "A patch pasted from elsewhere. Splice detection on the eval set: hit-rate 1.0, IoU 0.82.",
  },
  {
    label: "Digital paint-over (ID)",
    path: "examples/digital_paintover_id.png",
    verdict: "EDITED",
    trust: 15,
    note: "A PAN digit painted in a drawing app — caught by the flat-fill detector plus the invalid-PAN semantic check.",
  },
];
