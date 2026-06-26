// Detection METHOD vocabulary — "how was this caught?" — shared by Examples + Investigator.
// Maps a finding's detector/category to one of: model | pixel | semantic | none | clean,
// each with a layer hue + a one-line explanation. Mirrors the backend's values.detector.

import { layer as L, color as C } from "../theme.js";

export const METHOD = {
  model: {
    key: "model", label: "Learned model", hue: L.model.hue,
    blurb: "Our forgery-localization U-Net localized the edited pixels — it catches seamless edits the pixel heuristics miss.",
  },
  pixel: {
    key: "pixel", label: "Pixel forensics", hue: L.forensic.hue,
    blurb: "A hand-tuned pixel detector (sensor-noise loss / ELA / clone / JPEG-ghost) found the edit. Zero false positives on clean docs.",
  },
  semantic: {
    key: "semantic", label: "Cross-reference", hue: L.semantic.hue,
    blurb: "The number disagrees with another source — the card's signed QR, a checksum, or another document in the packet.",
  },
  none: {
    key: "none", label: "Evades pixel forensics", hue: C.textFaint,
    blurb: "So seamless it leaves no pixel trace. Catching it needs cross-referencing the numbers (packet checks) or the signed QR on a real card.",
  },
  clean: {
    key: "clean", label: "No tampering", hue: C.success,
    blurb: "Genuine — no edit signals; the page's sensor-noise floor is intact everywhere.",
  },
};

const _PIXEL = new Set(["ela", "noise", "flat_fill", "copy_move", "jpeg_ghost", "recapture"]);

// Derive the method key from a finding's detector + category (matches build_demo_examples.py).
export function methodFor(detector, category) {
  if (detector === "forgery_model") return "model";
  if (category === "semantic" || (detector || "").startsWith("qr")) return "semantic";
  if (_PIXEL.has(detector)) return "pixel";
  return category === "semantic" ? "semantic" : "pixel";
}

// The detector label shown alongside the method (e.g. "noise-loss", "U-Net").
export const DETECTOR_LABEL = {
  forgery_model: "U-Net", noise: "noise-loss", ela: "ELA", flat_fill: "flat-fill",
  copy_move: "clone", jpeg_ghost: "JPEG-ghost", recapture: "recapture",
  qr_cross_check: "QR vs print", qr_aadhaar_signature: "Aadhaar signature",
};
