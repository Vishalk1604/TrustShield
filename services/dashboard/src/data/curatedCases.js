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
  {
    id: "PKT-0034",
    name: "Flattened forgery (image PDF)",
    blurb: "A Form 16 repainted then flattened to an image — no text layer to check. The learned model localizes it.",
    tone: "fraud",
  },
];

// Single-document entry examples — the NEW realistic synthetic docs, carrying their REAL baked
// detection (verdict / trust / method / region box) so Demo mode shows the actual result and Live mode
// re-analyzes the same file. Derived from demoExamples.js (see scripts/build_demo_examples.py).
import { DEMO_EXAMPLES } from "./demoExamples.js";

export const CURATED_IMAGES = DEMO_EXAMPLES.map((e) => ({
  ...e,
  label: e.title,
  path: e.edited_img,   // the file to fetch + analyze in Live mode
  note: e.blurb,
}));
