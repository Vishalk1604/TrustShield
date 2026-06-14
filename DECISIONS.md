# TrustShield — Decision Log

Append-only. Each entry: date · decision · why · alternatives considered. Newest at the bottom of each phase.

## Phase 0 (2026-06-13)

- **NetworkX over Neo4j** for the cross-application graph (Phase 5). *Why:* the build must run on a single laptop with no external services; an in-memory NetworkX graph (persisted to pickle/SQLite) covers the demo's clustering needs without the operational weight of a graph DB. A Neo4j upgrade would be a separate, explicitly-approved change logged here.
- **SQLite over Postgres** for local persistence. *Why:* zero-setup, file-based, laptop-friendly; the data volume in a demo is tiny.
- **PyMuPDF (fitz) as the single PDF library** for both *building* and *tampering* synthetic documents. *Why:* fitz is already a hard dependency for the forensics service, can author PDFs, set arbitrary metadata, perform incremental saves (to forge revision artifacts), and copy/redact regions — so we avoid pulling in a second lib (reportlab) just for generation.
- **Deterministic generator (fixed RNG seed); committing the generated synthetic PDFs.** *Why:* the PDFs are tiny, fully synthetic (no real PII), and committing them means a fresh clone can run the demo with zero setup. The generator is deterministic, so they can also be regenerated identically. Alternative (gitignore the PDFs, regenerate on clone) rejected for adding a setup step before the demo works.
- **Python 3.11-slim base images** for the FastAPI service containers; local host development runs 3.12. *Why:* 3.11 is the stated floor and yields smaller, well-supported wheels (PyMuPDF, scikit-learn); the code stays 3.11/3.12 compatible.
- **Import model: repo root is the PYTHONPATH root.** `shared` and `data` are top-level packages; Python services run as module paths (`uvicorn services.forensics.app.main:app`); Compose bind-mounts the repo into `/app` with `PYTHONPATH=/app`. *Why:* both services and the generator share one schema/mocks codebase without packaging/publishing a wheel; bind-mount gives hot reload for the demo.
- **Service requirements are scoped per phase.** Phase 0 service `requirements.txt` only pins `fastapi/uvicorn/pydantic`; heavier deps (PyMuPDF, pytesseract, scikit-learn, networkx) are added in the phase that first needs them. *Why:* keeps early images small and build times fast; avoids implying capabilities that don't exist yet.
- **Ports:** forensics 8001, risk 8002, dashboard 5173. CORS on the FastAPI services allows `http://localhost:5173` so the browser dashboard can call them directly.
- **Git: commit straight to `main`** (no per-phase feature branches). *Why:* early-stage, effectively solo cadence; revisit if multiple teammates start working in parallel.

## Build prerequisites installed (2026-06-13) — for the unattended `trustshield-autobuild` routine

To let the every-6-hours routine progress through later phases without stalling on a missing host
dependency, these were pre-installed:

- **Tesseract OCR 5.4.0** (UB-Mannheim build) at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
  - **Gotcha:** winget added it to the *machine* PATH, but the already-running app (and the shells
    its tools spawn) won't see that PATH update until the app is restarted. So **Phase 2 code must
    set `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`**
    (or prepend that dir to PATH) rather than relying on a bare `tesseract` on PATH. Verified
    end-to-end: pytesseract OCRs a rendered Form 16 and recovers "FORM 16 / Rahul Sharma / PAN".
  - The **forensics Docker image** needs its own copy for in-container OCR: add
    `apt-get install -y tesseract-ocr` to `services/forensics/Dockerfile` and `pytesseract` to its
    requirements when Phase 2 lands.
- **Python libs added to `.venv`** for host-side dev/tests of later phases: `pytesseract 0.3.13`,
  `scikit-learn 1.9.0`, `joblib 1.5.3`, `networkx 3.6.1`, `pandas 3.0.3` (+ `numpy`/`scipy`/`Pillow`
  pulled in). Each service still pins its own scoped `requirements.txt` per phase (the venv is for
  local runs, not the container images).

## Phase 2 (2026-06-14) — Semantic rules design decisions

- **Valuation inflation requires external market comparison.** LTV using the claimed valuation
  alone cannot detect a fraudulently inflated appraisal (e.g., loan=9.5M vs claimed_val=11M →
  LTV=86%, which looks fine). Added `PropertyRegistryAdapter` with a `property_registry.json`
  fixture (keyed by survey number) to compare claimed valuation vs registered market value. This
  makes the "check valuation against state registry" narrative concrete for the demo.
- **EC-vs-CERSAI rule detects the tampered EC.** Although the visual EC says "NIL", the Tesseract
  approach isn't needed: the tampered PDF's text layer contains both the forged "NIL ENCUMBRANCES"
  text AND the hidden original charge (as forensic residue). The semantic rule checks for "NIL
  ENCUMBRANCES" in EC text AND active CERSAI charges for the same property/PAN — both are present
  in the tampered EC, so the rule correctly fires. Phase 1 forensics also fires (whitebox edit),
  giving double coverage.
- **Name/owner consistency from embedded text layer.** For forged_title (owner name whitebox-edited),
  the embedded text still shows the original name in residue. The semantic owner-vs-applicant rule
  uses embedded text, so it may not flag the edit (forensic covers it). This is an acceptable
  limitation; Phase 1 forensic detection is the primary signal for whitebox edits.
- **Extraction uses embedded text fast-path + Tesseract fallback.** All synthetic PDFs have
  embedded text; Tesseract is only exercised on image-only scans. The Tesseract path is correct
  for production scanned documents.

## Phase 1 (2026-06-14) — Forensic analysis design decisions

- **Template fingerprint = producer + font-set + image/drawing counts per page (no text content).**
  *Why:* we want "same template → same hash" even when the data (name/PAN/amounts) differs. Using
  structural features (fonts, layout image counts, producer) achieves this while keeping the hash
  stable across different applicants on the same template. Text content is intentionally excluded.
  The different producer ("QuickDocs Generator" vs "TrustShield SynthGen 1.0") makes the ring
  fingerprint distinct from clean-packet fingerprints.
- **White-box edit detection via drawing-object overlap.** After a whiteout edit, the PDF content
  stream contains a white-filled rect + new text, while the original text remains in the text layer.
  We detect overlap (>30% of text span covered by a white rect) rather than trying to re-OCR, since
  fitz's text extraction still sees the original bytes. False-positive threshold guards against
  legitimate white backgrounds in headers.
- **behavioral_velocity and template_reuse are NOT flagged as per-document forensic fraud.**
  These are cross-document (identical timestamps across multiple docs) or cross-packet (same
  fingerprint in multiple applications) signals — they require comparison with other documents/packets
  that Phase 1 doesn't have. Phase 3 (behavioral) and Phase 5 (graph) are the correct homes.
- **timestamp_anomaly with behavioral_velocity = "identical timestamps" behavioral signal (not
  per-doc forensic).** Only pure timestamp_anomaly packets (future dates, reversed dates) are
  expected to produce Phase 1 findings.

## Phase 7 (2026-06-14) — Privacy & Trust Layer

- **Redaction scrubs logs, not evidence.** Evidence items shown to the investigator legitimately
  contain PANs / property IDs (that *is* the product); the contract is specifically "never log raw
  PII." So `shared/privacy.py` is wired into the logging path (`install_log_redaction()` at service
  startup + a `PIIRedactionFilter`), and `PacketDecision`/evidence payloads returned to the UI are
  left intact. The dashboard runs locally, so showing them there does not transmit anything.
- **Partial, format-preserving masks** (PAN → `AB*******F`, account → keep last 4, property →
  `SY-***`) rather than full `[REDACTED]`. *Why:* a redacted log is still debuggable and lets an
  operator correlate events without exposing the raw identifier — the standard logging-PII tradeoff.
- **Amounts are not masked.** The account-number masker only fires on 9–18 digit runs; loan/income
  figures are ≤ 8 digits, so operational logs keep their useful numbers. Documented tradeoff.
- **Name redaction is field-based, best-effort in free text.** Names have no reliable regex, so
  `redact_mapping` masks values under known PII keys (`name`/`owner_name`/…), and the discipline is to
  not log name fields. Pattern maskers (PAN/account/property) cover the structured identifiers in free
  text. Honest limitation noted in `PRIVACY.md`.
- **`PRIVACY.md` is the auditable statement** of the on-premise posture, the log-redaction mechanism,
  data retention (synthetic data committed; graph store gitignored; models local), and the
  evidence-chain auditability — plus honest limitations.

## Phase 5 (2026-06-14) — Cross-Application Graph

- **NetworkX attribute graph; node kinds = app / pan / employer / property / template.** Edges link an
  application to each of its attributes; two applications are "related" iff they share a (non-hub)
  attribute node. Persisted to a pickle under `services/risk/graph_store/` (gitignored — it is runtime
  state, rebuilt deterministically by `ApplicationGraph.build_from_packets`).
- **Hub suppression is the key idea.** The generator emits a *default* document template that 25 of 33
  packets share — linking on it would collapse nearly every clean packet into one giant false "ring."
  Any attribute node connected to more applications than `max(6, ⌈0.33·n_apps⌉)` (= 11 here) is treated
  as a non-discriminative hub and ignored for clustering, evidence, and subgraph extraction. Only
  *minority* shared attributes form links. This is what makes "unrelated packets stay unlinked" true.
- **Ring discriminator = an employer (or template) claimed by ≥2 DISTINCT applicant PANs.** In the
  synthetic set every legitimate employer maps to exactly one PAN (the same person re-applying), while
  "QuickCash Finance Pvt Ltd" maps to 4 distinct PANs — uniquely identifying the fraud ring. Template
  fingerprint is corroboration, not the primary signal (the default template is a hub and useless alone).
- **Double-financed collateral = a property pledged across ≥2 applications by ≥2 distinct PANs.** SY-911/2C
  surfaces across 4 applications (1 valuation-inflation + 3 double-financing) → the hero cluster. The two
  2-app property clusters (SY-217/3B, SY-058/1A) pair a clean owner with a fraud application; surfacing
  them is correct (the asset is contested), not a false positive.
- **Graph evidence is an ADDITIVE risk overlay, not a blend channel.** `total_risk =
  min(1, per_packet_blend + 0.5·graph_risk)`. *Why additive:* folding the graph into the weighted blend
  would have to steal weight from the per-packet channels and weaken Phase 4's document-backed freezes.
  The overlay leaves every Phase-4 score unchanged when no graph evidence is present (verified) and only
  *adds* risk for relational findings. A graph CRITICAL (collateral across ≥3 apps, or a ≥3-PAN ring)
  also trips the same `CRITICAL_TRUST_CEILING` (25) used for document criticals.
- **Severity ladder:** collateral/ring across ≥3 distinct applicants → CRITICAL (→ freeze); across 2 →
  MEDIUM (collateral) / HIGH (ring); same-applicant repeat → INFO (context only, never escalates — so a
  clean packet that merely shares a PAN with its own fraud sibling stays APPROVE).
- **This closes the Phase 4 loop.** Phase 4 deliberately routed evidence-less model flags (the QuickCash
  ring at trust 43, the double-financing packets at 43) to "manual review + check the graph." Phase 5
  supplies that concrete relational evidence: the ring (PKT-0018–21) and the double-financing packets
  (PKT-0031–33) drop to ~13 trust → **FREEZE**, while all 10 clean packets remain APPROVE. The graph is
  the demo's hero: a single-document tool is structurally blind to both of these frauds.

## Phase 4 (2026-06-14) — Trust Score Aggregation & Evidence Chain

- **Explicit, documented blend weights (sum = 1.0):** model 0.55, forensic 0.25, semantic 0.15,
  Isolation-Forest anomaly 0.05. *Why these:* the GBC is the calibrated learned signal and the
  primary driver; forensic + semantic are deterministic, auditable document evidence; the IF is a
  weak novelty signal (only 10 clean training packets — see Phase 3) so it gets a near-token weight.
  The model's contribution is **surfaced as its own evidence item** (with feature attributions), never
  hidden inside the number — judges/underwriters can see exactly how much the model moved the score.
- **Risk-blend, not naive average.** Each channel is converted to a 0–1 risk; `trust = 100·(1−blend)`.
  Forensic/semantic risk = Σ severity penalties / 100 (critical 60, high 35, medium 18, low 6),
  capped at 1.0. This lets a single strong document finding meaningfully drop the score instead of
  being diluted by clean channels.
- **CRITICAL findings cap trust at 25** (freeze band). A registered-charge contradiction (EC-vs-CERSAI)
  or loan-exceeds-market-value is near-certain fraud; it should force a freeze regardless of the blend.
- **Thresholds:** trust ≥ 70 → APPROVE; 40–70 → MANUAL_REVIEW; < 40 → FREEZE.
- **"No freeze without document evidence" safeguard.** A FREEZE requires a concrete forensic/semantic
  finding (or a CRITICAL). A low score driven **only** by the learned model (no attributable document
  evidence) is softened to MANUAL_REVIEW and explicitly **routed to the cross-application graph**. This
  encodes the product rule "never a hard action without explainable evidence" and is exactly what the
  double-financing case needs — the fraud is relational, not in any single document.
- **double_financing honesty caveat.** The full-data GBC outputs ~1.0 for the three double-financing
  packets, but that separation leans on a **synthetic-data artifact**: those packets were generated with
  a 120 h create→submit velocity vs ~168–192 h for clean packets, so `submit_velocity_hours` (the top
  model feature) flags them. In production these packets would have normal velocity and be
  per-packet-**indistinguishable** from clean. The principled detector is the Phase 5 graph (shared
  collateral across applications). Phase 4 therefore (correctly) lands them at trust ≈ 43 →
  MANUAL_REVIEW with a "route to graph" rationale, rather than a confident freeze. Documented so the
  demo narrative ("per-packet scoring is blind to collateral reuse; the graph is the hero") stays honest.
- **Every decision carries a non-empty evidence chain** (enforced by `PacketDecision`). Even a clean
  packet gets the model-verdict item ("low fraud probability; no tampering detected"), so the contract
  holds with zero document findings.
- **Endpoint `POST /risk/score`** orchestrates Phase 1→4 from local document paths (in-memory manifest;
  no manifest.json required). Returns the full `PacketDecision`. `httpx` added as a **test-only** dep
  (FastAPI `TestClient` talks to the ASGI app in-process — no sockets; local-only contract intact).

## Phase 3 (2026-06-14) — Anomaly + Learned Risk Model

- **Feature vector = 16 scalar features** (forensic counts, semantic counts, behavioral, property)
  assembled from Phase 1 (forensic findings) + Phase 2 (semantic rule violations) + PDF metadata
  timestamps. Fixed-length; safe for scikit-learn without dynamic sizing.
- **Isolation Forest trained on clean packets only** (10 samples). Gives a novelty/anomaly sub-score
  in [0, 1] via `0.5 - decision_function(x)`. With only 10 training samples the IF produces weak
  separation (clean mean 0.50 vs fraud mean 0.50) — it functions as a light anomaly heuristic,
  not a primary signal. Production use would require hundreds of clean baseline packets.
- **GradientBoostingClassifier (supervised) on all 33 packets** — ROC-AUC 0.9696 (5-fold CV);
  0 false positives; 1 false negative (a double_financing packet). This is the primary signal.
  `submit_velocity_hours` (0.49), `n_semantic_total` (0.22), `has_income_inconsistency` (0.15)
  are the three dominant features — exactly what the domain expects.
- **1 FN (double_financing packet) is intentional, not a bug.** Double_financing fraud (same
  property pledged across multiple applications) produces zero per-packet signals — no forensic
  tampering, no internal inconsistency, fair valuation. It REQUIRES cross-packet graph comparison
  (Phase 5). Training the Phase 3 model on these samples would teach a spurious correlation.
  Decision: include all 33 in training, document the limitation; Phase 5 closes the gap.
- **Feature attributions use global importance × |normalized feature value|** (not SHAP) to stay
  dependency-free (no shap library needed). This is an approximation — acceptable for
  the demo's "why did it flag this?" story; a SHAP upgrade can be added later.
- **StandardScaler fit on CLEAN packets only** (not all data). This is the standard practice for
  novelty detection: the scaler defines the "normal" reference; scaling must not be contaminated
  by fraud samples. The same scaler is reused for the GBC (normalization doesn't hurt trees,
  but keeps the IF and GBC on consistent scales).
- **Model artifacts committed to the repo** (services/risk/models/*.joblib + *.json). They are
  deterministic (fixed random_state=42), <200KB total, and required to run the inference path
  without re-running train.py on every fresh clone.

## Scope + model expansion (2026-06-14) — aligning to the problem statement

The hackathon problem statement is explicitly *"tampering/forgery across **land records, legal
documents and financial statements** … in real time … intelligent insights for underwriting."*
The original build was financial-only. Two strategic changes (reflected in `plan.md`):

- **Document scope expanded to legal + land records**, not just financial. New doc types:
  `sale_deed`, `encumbrance_certificate`, `property_valuation`, `legal_opinion`. New fraud types:
  `forged_title`, `tampered_encumbrance`, `valuation_inflation`, `property_mismatch`,
  `double_financing`. *Why:* it's literally in the theme, and most teams will only do "is this PDF
  edited." The breadth (financial + legal + land) is a differentiator.
- **Collateral-fraud as the hero feature.** The Phase 5 graph gains **property/title-ID nodes** so the
  *same property pledged across multiple applications* (double-financing / loan stacking — what
  CERSAI exists to catch) forms a cluster. A single-document tool is blind to this; the cross-
  application graph is the demo "wow." Also adds property-consistency + LTV rules in Phase 2 and an
  EC-vs-CERSAI charge cross-check.
- **Add a supervised, explainable model** (gradient-boosted trees / random forest) alongside the
  Isolation Forest (Phase 3). *Why:* judges expect "a trained model with metrics" (AUC/PR/confusion
  + feature importance), and learned weights beat hand-tuned ones in Phase 4 — while tree-based +
  feature attribution stays auditable. **No deep/black-box models:** in regulated lending an
  unexplainable rejection is a compliance problem, not a feature. Models are trained on *synthetic*
  data to prove the pipeline; the honest production answer is "retrain on the bank's labeled history."

## Phase 9 (2026-06-14) — Forensic/OCR depth (roadmap §6.D2 + §6.D3)

First slice picked off the `plan.md` §6 production roadmap: the re-OCR vs text-layer cross-check (D2)
and tamper localization (D3). Both use the already-installed Tesseract + PyMuPDF; no new heavy deps.

- **D2 makes the never-exercised OCR path real.** Until now every synthetic PDF carried a text layer,
  so `extractor.py`'s Tesseract fallback never ran. The new `DocumentAnalyzer._check_reocr_mismatch`
  renders each page, OCRs it, and compares the *visible* currency amounts / PANs against the embedded
  text layer. A "whiteout" edit leaves the original value in the text layer while the page shows the
  forged value (or, for the tampered EC, nothing) — so a text-layer value with no visible counterpart
  is the signal. It reads pixels, not PDF structure, so it is layout-independent and would survive
  flattening/re-scanning that defeats the structural checks. Fires on PKT-0010/0011 (hidden original
  income) and PKT-0028 (the EC shows NIL but hides a Rs. 4,200,000 charge); **zero** findings on all
  10 clean packets.
- **D2 is EVIDENCE, not a model feature — deliberately.** `features.py` runs the analyzer in-process
  and feeds `n_forensic_total` etc. into the committed GBC + Isolation Forest. Feeding an OCR-dependent
  signal would make model inputs nondeterministic across environments (Tesseract present or not) =
  train/serve skew. So re-OCR findings are tagged `values["check"]="reocr"` and excluded from the
  model-feature counts; the model-feature pass also calls `analyze_pdf(enable_reocr=False)` so it pays
  no OCR cost. Result: the 16-feature vectors are byte-identical to before → **no retrain, committed
  model artifacts unchanged**, and the end-to-end confusion matrix is preserved. D2 still surfaces in
  the evidence chain and the forensic subscore (via the aggregator's forensic channel). Feeding D2 into
  the model is a future step, once OCR is bundled everywhere (F6) and generator-v2 supplies
  flattened-forgery training data.
- **Precision over recall: OCR misreads must not masquerade as edits.** Two guards make the check
  honest: (1) **currency-prefixed amounts only** — bare numbers (PIN codes, dates, survey/ref numbers)
  render inconsistently under OCR (internal spaces, line breaks) and would false-positive; requiring
  "Rs."/"INR"/"₹" keeps the check on real money. (2) An **"explained-away" guard** (`_is_visible`):
  a text-layer value is treated as visible if an OCR token is within one edit of it, *unless* that OCR
  token exactly equals a different real text-layer value. This distinguishes an OCR misread
  (143,500 rendered, read as 43,500 — 43,500 is not its own value → visible) from a genuine hide
  (1,450,000 covered; the only near token, 145,000, is the real separate TDS value → still hidden).
  This is why PKT-0012's OCR digit-drop does **not** false-fire.
- **D3 localizes the edit.** White-box findings now carry `values.regions = [{page, bbox}]` (the
  analyzer already computed the overlapping rects — they were just not surfaced), and re-OCR findings
  carry the hidden value's bbox via `page.search_for`. `render_tamper_overlay()` (pure PyMuPDF, no
  Tesseract) renders the page with semi-transparent red boxes over the regions. The risk demo-score
  endpoint returns these as `tamper_overlays:[{doc,page,image_b64}]` **outside** the `decision` payload
  so exported reports stay lean; the dashboard renders them as a "Tamper localization" panel and shows
  per-finding region badges in the evidence chain. Overlay rendering uses only PyMuPDF, so it works in
  every environment even where Tesseract (hence D2) is absent.
- **Container parity (partial §6.F6).** `pytesseract`/`Pillow` added to both services' requirements and
  `tesseract-ocr` to both Dockerfiles (the risk image needs it because it runs the analyzer in-process).
  Everything degrades gracefully: without Tesseract, `ocr.tesseract_available()` is False and the
  re-OCR check returns `[]` — scoring, the overlay, and all other checks are unaffected.
