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

## Web app & roles (2026-06-18) — plan §8

- **Auth + case store live on the risk service, not a new gateway.** The SPA already talks to risk, and
  risk imports the forensics ingest/analyze code in-process, so it can own the whole user flow with no
  extra service. A dedicated BFF/gateway is a future refactor (noted in the plan). Kept the build simple.
- **Real auth, low-dep:** passwords hashed with stdlib **PBKDF2-HMAC-SHA256** (per-user salt) — no bcrypt
  dependency; bearer tokens are **JWTs** (PyJWT, one light dep). SQLite is stdlib. Two roles: user/admin.
- **Real-upload scoring neutralizes the synthetic-only velocity feature.** The case flow synthesizes a
  manifest with a normal ~1-week create→submit gap so the GBC's top feature (`submit_velocity_hours`,
  a synthetic-data artifact) doesn't false-flag genuine uploads. Real-upload trust leans on the
  deterministic **forensic + semantic + KYC** signals; the fraud model stays synthetic-trained
  (documented honesty line — real docs validate extraction, not fraud detection).
- **Reused the full pipeline for uploads:** `POST /cases` saves files to a per-case dir + a synthesized
  manifest, then calls `aggregator.score_packet_dir` — so forensic + semantic + model + evidence-chain
  assembly are identical to the synthetic path. Tamper overlays via the shared `app/overlays.py`.
- **Privacy:** the SQLite DB (`services/risk/app_data/`) + uploaded files (`services/risk/case_store/`)
  are runtime state with real user data — **gitignored, never committed**; log PII redaction already on.
- **Frontend stays simple now (per ask):** `react-router-dom` + existing inline dark theme; a polished
  design pass is deferred. The old single-page console's decision UI was refactored into a reusable
  `DecisionView` shared by the user result + admin case detail.

## Real-document KYC + underwriting (2026-06-18) — plan §9

- **Two separate axes: authenticity vs eligibility.** The trust score stays an *authenticity/
  consistency* measure (forensics + semantics + model + KYC/completeness). Loan **eligibility**
  (FOIR/affordability/LTV) is a *business-rule* outcome and **never** moves the trust score — a
  genuine-but-ineligible applicant must read as "REFER/DECLINE on affordability," not as fraud.
  *Why:* conflating the two would either tank authentic packets or hide real forgeries behind a
  passing eligibility verdict.
- **KYC/completeness/income findings fold into trust by a CAPPED penalty** (`underwriting.
  VERIFICATION_PENALTY_CAP = 25`, applied in `aggregator.apply_verification`). *Why:* a missing
  document or a name typo is a genuine consistency gap worth reflecting, but it must not tank an
  otherwise-authentic packet. Missing docs are **accept + flag** (LOW), not blocking (per interview).
- **Deterministic underwriting (no ML)** for completeness, identity/address established, name
  consistency, income reconciliation, FOIR/affordability. *Why:* there are no real fraud labels, so
  the *forgery* model stays synthetic-trained; the rules work on real documents on day one and are
  fully explainable. Documented constants (no magic numbers): FOIR cap 0.50, REFER ≤ 0.60, assumed
  rate 10.5% p.a., default tenure 60 mo, LTV cap 0.80, income-reconciliation tolerance ±15%,
  net-to-gross band [0.55, 1.05].
- **Purpose → document profile is one source of truth** (`profiles.py`) for both the completeness
  check and the upload form (served at `GET /cases/profiles`). *Why:* avoids the UI and the backend
  drifting on "what does a salaried loan need." Slot keys double as the per-file `doc_type` ingest
  hints, so we don't depend on the classifier for user-asserted documents.
- **New `address_proof` doc type.** Real KYC needs proof of address (POA), which the financial-first
  ingestion lacked. Added classifier keywords + a light `_extract_address_proof` + `DocType.
  ADDRESS_PROOF`. POI = {pan, aadhaar}; POA = {aadhaar, address_proof}.
- **Model store + seam, heuristics stay live.** Large assets live under gitignored `models/` with a
  committed registry (`REGISTRY.md` + `registry.json`); `ingest/model_registry.py` resolves a local
  path or returns `None`, and every consumer falls back to its heuristic. *Why:* keeps the runtime
  images light (no torch/transformers), makes a fresh clone run on heuristics, and lets Person 2 drop
  in fine-tuned weights later by flipping `live:true` — no code change. `verify_local_only.py` excludes
  `models/` (vendored upstream repos legitimately reference networks for *training*, never at runtime).
- **torchvision backbone not downloaded.** DocTamper ships its own Swin backbone + pretrained `.pk`
  checkpoints, so a separate torchvision CNN backbone is unnecessary. PaddleOCR weights deliberately
  not bundled — Tesseract remains the live OCR; PP-OCRv4 is an optional dev-time pre-cache.
- **DB migration is additive + guarded** (`db._migrate`: `ALTER TABLE cases ADD COLUMN` for
  `verification_json`, `loan_amount`, `tenure_months` when missing) so existing case stores upgrade in
  place. `pytest.ini` scopes collection to `tests/` (keeps pytest out of the vendored `models/` tree).

## Hackathon sprint §10 — Day 1: image / pixel forensics (2026-06-19)

- **New `image_forensics.py` for raster (scan/photo) edits — the judges' core problem.** The §6.D2/D3
  forensics only catch PDF *text-layer* edits; an edited scan/photo has no text layer. This module adds
  the standard pixel-forensics toolkit (ELA, noise-residual, copy-move, JPEG-ghost, EXIF/software-trace).
  *Why these:* they are the established, explainable, CPU-local techniques for tamper localization —
  no training data or GPU needed, so they work on day one and on documents the judge edits live.
- **Robust thresholds (median + k·MAD), contiguous clusters, and corroboration** — not raw mean/std and
  not single-block hits. *Why:* real scans have heavy-tailed ELA/noise; naive thresholds light up clean
  documents. A finding requires a coherent region, and two pixel detectors agreeing on an area escalate
  the severity while a lone weak signal stays low. This keeps clean documents clean (the acceptance bar).
- **Copy-move is verified by pixel NCC**, not keypoint matches alone. *Why:* documents are full of
  repeated glyphs (every "0" matches every other "0"); ORB offset-clustering alone false-positives.
  Requiring normalized cross-correlation ≥ 0.90 on the actual patches admits only true clones.
- **Graduated trust, not binary.** `image_trust` uses a per-severity base risk (low .15 / medium .45 /
  high .85 / critical 1.0) + a small per-extra-region bump — so a lone HIGH lands in the freeze band
  (~15) without a hard 0, and corroboration/multiple regions push it to 0. *Why:* a defensible score
  with gradation beats an all-or-nothing flag.
- **`opencv-python-headless` (not full opencv)** added to the forensics image. *Why:* headless drops the
  GUI/X11 libs — correct for a server and smaller. Copy-move **degrades gracefully** if cv2 is missing;
  ELA/noise/EXIF need only numpy + Pillow, so the core still runs. Image-level forensics lives in the
  forensics service (v1.3.0): `POST /forensics/analyze-image` + image routing in `/forensics/ingest`.
- **Frontend reverted to the single-page investigator console** (§10 decision; the §8/§9 multi-page app
  is retired to git `66d9165`, recoverable). *Why:* the judges want a simple "upload → see what's edited"
  view, not an auth/role product; the §9 KYC/underwriting **backend** stays for depth.

## Hackathon sprint §10 — Day 2: tamper-image dataset + detector robustness (2026-06-20)

- **Synthetic clean docs need a realistic SCAN baseline.** Vector-clean PDF renders are noise-free, so a
  synthetic "edit" leaves no forensic trace and nothing is detectable. `build_image_dataset._simulate_scan`
  adds a lighting gradient + optical blur + a **sensor-noise floor (σ≈12 pre-JPEG → ~4 after)** so that an
  edited region, which lacks that noise, becomes detectable. This mirrors how DocTamper-style datasets are
  built and is the honest way to demonstrate the detectors.
- **Noise must be estimated on FLAT pixels, not raw high-pass residual.** Text/line edges produce a huge
  residual unrelated to sensor noise; flagging "high-residual" blocks lit up every line of text (100%
  false positives on clean documents). `_block_noise_sigma` keeps only low-gradient (flat) pixels and
  takes their residual std → a true local noise floor. We then flag regions whose noise drops below
  ~50% of the page floor (paint/splice/recompress destroy the noise). Result: **zero false positives on
  clean documents** while catching the realistic edits.
- **Copy-move is corroboration-only on documents.** Repeated glyphs/amounts are pixel-identical, so
  ORB+NCC (even with a noise-residual cross-check, which text-edge structure defeats on tiny patches)
  cannot reliably tell a clone from legitimately-repeated text. Rather than ship false positives, a clone
  is reported only where it overlaps a noise/ELA region; robust clone detection on dense text is the job
  of the learned DocTamper model (Day 3). Documented as a known limitation in the eval summary.
- **Measure everything; store the results.** `scripts/eval_image_forensics.py` writes
  `results/image_forensics/` (metrics.json + summary.md + sample overlays) — committed as the durable
  showcase. The image dataset itself (`data/synthetic/images/`) is gitignored and regenerated
  deterministically. Headline: detection precision 1.0 / recall 0.73; localization IoU 0.84–0.86 on
  paint/splice.
- **Dashboard source is bind-mounted** (`docker-compose` volumes + Vite `usePolling`). *Why:* the dashboard
  image bakes its code (`COPY . .`), so a frontend change needs a rebuild — which twice left a stale UI in
  the running container. Mounting `src/`, `public/`, `index.html` makes edits hot-reload; node_modules
  stays in the image. The new **image edit-detection panel** (overlay + ELA heatmap) lives on the
  single-page console with curated synthetic examples under `public/examples/`.

## Hackathon sprint §10 — Day 3: digital paint-over + DocTamper status (2026-06-20)

- **Heuristics catch scanned/photo edits, NOT pristine-digital edits — by nature.** Real feedback: a PAN
  edited in a drawing app (flat paint over the number) returned CLEAN. Root cause: the noise-loss and
  ELA detectors rely on a sensor-noise floor / JPEG history that a pristine digital image (e-PAN
  screenshot, vector render, PNG export) does not have. Confirmed by reproduction: `photo+paint` is
  caught (g=3.04 -> EDITED); `digital+paint` (g=0) is not. This is a real, honest limitation of trace-
  based forensics, and motivates the learned model.
- **New flat-fill (paint-over) detector** (`_flat_fill_regions`). A deliberate cover-up is an
  unnaturally uniform colour rectangle whose shade differs from the paper. We flag SOLID blocks
  (std < 4) that are mid-tone (exclude near-black text/lines and near-white paper) and differ from the
  page-background mean by > 12 gray levels, clustered. Reported MEDIUM standalone (a fill can be a legit
  form field), HIGH when corroborated. Validated: catches the digital paint-over (PNG + JPG) while the
  synthetic eval's clean precision **stays 1.0** (zero new false positives). For the live demo, a
  photo/scan of a document is the strongest case; a pristine digital edit relies on flat-fill or the
  learned model.
- **DocTamper ships NO weights.** Inspection: the repo has the model code + `pks/*.pk` per-image JPEG
  **quantisation tables** (dicts of 2k-30k entries), but no `.pth/.pt/.ckpt`. The trained DTD checkpoint
  is gated (request from the authors with an education email, like the dataset). So DTD inference is not
  runnable from what is on disk. `ingest/doctamper.py` is the **seam**: `available()` is False until a
  checkpoint is placed under `models/doctamper/weights/` (+ torch); `localize()` returns None and the
  heuristics stay live; `status()` is surfaced in every analysis (`signals.learned_model`) for honesty.
  registry.json + REGISTRY.md corrected (previously, incorrectly, said the `.pk` files were checkpoints).
- **No torch in the runtime.** The DTD seam keeps torch out of the slim forensics image; the learned
  model would run on the Person-2 GPU machine once weights are obtained. Heuristics remain the
  guaranteed local path.

## §10 Day 3 follow-up: flat-fill gated to white-paper docs (2026-06-20)

- **Real feedback:** two photographed PAN cards both came back SUSPICIOUS with boxes on the card
  BACKGROUND, not the edit. Cause: the flat-fill detector mistook the PAN card's smooth COLOURED
  security background for a 'fill'. Fix: flat-fill now applies only when the page is predominantly
  white paper (`>30%` near-white pixels) + a region-size cap; colored ID cards (PAN/Aadhaar) gate it
  off and rely on noise-loss (real photos carry sensor noise an edit destroys) + the learned model.
  Validated: colored card → CLEAN; white-paper digital paint still caught; synthetic eval precision
  stays 1.0. Honest scope: flat-fill = white-paper documents; ID-card edits = noise-loss / DocTamper.

## §10 Day 3 follow-up: semantic identifier check on real ID photos (2026-06-20)

- **Real PAN cards exposed the limit of pixel forensics — and the value of the layered design.** Two
  photographed PAN cards (one with the trailing PAN letter painted out) were both denoised by the phone
  (`page_noise g~0.3`) and colour-backgrounded (`white_frac 0`), so EVERY pixel detector correctly stays
  silent (no false positives) but also can't see the edit. The edit is still obvious semantically: the
  edited PAN `PATPK4316` is 9 chars, not a valid PAN.
- **`/forensics/analyze-image` now runs a SEMANTIC identifier check** alongside pixel forensics: OCR the
  image, extract any PAN/Aadhaar, validate it (`validate_pan` / Verhoeff), and emit a HIGH `semantic`
  finding when an ID number is invalid. Verdict/trust are recomputed over the merged findings
  (`image_forensics.compute_verdict`, factored out for reuse). Result on the real cards: original ->
  CLEAN (PAN valid), edited -> EDITED (PAN invalid). This is the honest, robust catch for ID-card edits
  that leave no pixel trace — and a clean demo of why authenticity is multi-layer, not pixels-only.
- **`extract_pan` now captures a malformed PAN** (final letter optional) so a tampered card whose PAN
  lost/gained a character is captured and then *fails* validation, instead of being silently dropped.
- **Honest scope, stated for the demo:** photo/scan edits that disturb sensor noise -> noise-loss;
  white-paper digital paint -> flat-fill; ID-number value edits -> semantic identifier check; subtle
  pristine-pixel edits -> the learned DocTamper model (gated weights). No single layer is sufficient.

## §10 pivot — cut the LLM-explainer; deepen detection (2026-06-21)

- **LLM-for-explanation cut.** Convenient, not impactful — the evidence chain already reads in plain
  English. Reinvest in detection: recapture/synthetic detector, QR cross-verification, a learned
  forgery-localization model (pretrained + **our own DTD trained on the DocTamper dataset we already
  hold**), and face-match. No Person-1/Person-2 split (one team). Single GPU, **no clustering** — the
  forgery models are 2-4 GB and fit one 8 GB GPU; extra VRAM is only for fine-tuning. plan.md §10 updated.
- **Recapture detector (`recapture.py`).** A photo of a screen / a halftone copy imposes a periodic grid
  → sharp high-frequency FFT peaks; a genuine paper scan/photo has a smooth spectrum. Two guards make it
  not false-fire on documents: (1) **off-axis** peaks only — a screen grid is a 2-D lattice, while
  repeated text/lines are 1-D periodicity on an axis; (2) **high prominence** (≥44 dB above the band
  median, ≥4 peaks) — real docs' text edges + JPEG 8x8 block grid sit at ~30-37 dB. Conservative by
  design: validated silent on all clean/real/tampered docs (incl. the real PAN photos), fires on screen
  grids. MEDIUM severity. Subtle real-screen recapture is best left to the learned model (honest limit).

## §10 Phases 4–6 — forgery-model seam, train-our-own DTD, face-match (2026-06-21)

- **Generalized forgery-model seam** (`ingest/forgery_model.py`) over the heuristic baseline: backends
  `dtd | trufor | catnet` selected by `TRUSTSHIELD_FORGERY_BACKEND` (default `dtd`, which delegates to the
  existing `doctamper.py`). `mask_to_regions()` converts a model's tamper-probability mask into
  image-space boxes + overlay (pure numpy/PIL/cv2). **torch stays optional** — `available()`/`localize()`
  return False/None unless a backend's weights + adapter + torch are all local, so the heuristics remain
  the guaranteed path. Non-DTD backends load a vendored `trustshield_infer.py` adapter that
  `scripts/setup_forgery_model.py` writes (so the committed repo ships no speculative model code). The
  setup script reads the clone URL from `registry.json` (not a literal) so `verify_local_only` stays clean.
- **Train our own DTD weights** (`services/forensics/train_forgery.py`). DocTamper's *training* code is
  gated, but we hold the dataset (LMDB) + the model def + losses + dataloader → we supply the training
  loop ourselves and save to `models/doctamper/weights/`, which the `dtd` backend auto-detects. This
  fills the gated-checkpoint gap with assets we already possess. The existing
  `scripts/eval_image_forensics.py` scores the uplift automatically (it routes through `analyze_image`).
- **Face-match across documents** (`ingest/extract/face_match.py`): embed the portrait on each document
  (insightface ArcFace, or face_recognition) and compare via cosine distance (threshold 0.62, documented);
  over-threshold → HIGH "face mismatch" (identity swap). Wired into `/forensics/ingest` (multi-doc),
  behind a seam (no-op without a face lib). The compare logic is pure + tested; embedding needs the lib.
- **QR decode reality (Phase 3):** the dense PAN-card QR did NOT decode from the real low-res phone photos
  (pyzbar x1/x2/x3 + OpenCV all returned 0). So QR cross-check is reported gracefully (`qr_found:0`, no
  finding) and the semantic identifier check remains the catch for those; QR shines on higher-res scans
  and the signed Aadhaar QR. Honest limitation documented in plan.md §10.

## Real-doc hardening: noise-detector size + count guards (2026-06-22)

- **Real test set (4 PAN + 3 Aadhaar pairs) exposed noise-detector false positives.** On real PAN photos
  with moderate sensor noise (page σ≈2-3), the noise-loss detector flagged 6-28 regions on GENUINE cards —
  including huge low-noise blobs (up to 15.5% of the image = glare / lamination sheen / blurred
  background), flipping two originals to EDITED/SUSPICIOUS. A real number-edit, by contrast, is a FEW
  SMALL regions (≤2%). Fix: (1) **size cap** `NOISE_MAX_FRAC=0.02` drops large glare/background blobs;
  (2) **count guard** `NOISE_MAX_REGIONS=3` — many low-noise regions = diffuse photo noise (focus/glare/
  JPEG), not a targeted edit, so suppress all. Result: all 4 PAN originals → CLEAN (FPs gone), edited PANs
  still caught 3/4 (semantic + noise + forensic), synthetic eval **unchanged** (precision 1.0, IoU 0.84).
- **Aadhaar Verhoeff on OCR is NOT verdict-safe.** Both the genuine AND edited Aadhaar numbers OCR'd to
  Verhoeff-INVALID values — i.e. OCR misread a digit on the *genuine* card too. A 12-digit checksum is
  broken by any single OCR error, so validating an OCR'd Aadhaar would false-flag real cards. We do NOT
  put it in the verdict. Aadhaar edits need the **signed QR** (didn't decode on these low-res photos) or
  the **learned forgery model** — the honest limit. (PAN's 10-char *format* check is far more OCR-robust,
  which is why PAN edits are caught and Aadhaar's aren't.)

## Phase 5 training — torch-only forgery U-Net (not the exact DTD) (2026-06-22)

- **The exact DocTamper DTD is Windows-blocked.** DTD consumes JPEG **DCT coefficients via `jpegio`**
  (+ `segmentation_models_pytorch`, `timm`, `albumentations`), and `jpegio` is extremely hard to build
  on Windows. Rather than force that, we **train our own** compact **U-Net** (`forgery_unet.py`,
  torch-only) on the data we DO hold — the DocTamper **LMDB** (validated intact: **120k** RGB 512x512
  document images + tamper masks, ~1.8% tampered px). Same goal (a learned per-pixel tamper localizer),
  achievable locally. `train_forgery.py` reads the LMDB directly (RGB+mask, no jpegio), trains with
  Dice+BCE + AMP, fine-tunes on our Day-2 synthetic set, → `models/forgery/unet/weights/forgery.pth`.
- **`unet` is the default forgery backend** (`forgery_model.py`); inference is in-repo (`forgery_unet.infer`
  → the seam's `mask_to_regions`). `dtd`/`trufor`/`catnet` remain selectable for the gated/external models.
  Still optional + behind the seam: no torch in the slim runtime; `available()` False → heuristics live.
- **Blackwell GPU (RTX 5060, sm_120) needs torch `cu128`** (`--index-url .../whl/cu128`); the default
  cu124 wheels don't have sm_120 kernels. Honest caveats: full convergence on 120k images is hours; and
  DocTamper is Chinese-document tampering, so cross-domain transfer to Indian ID edits is uncertain
  (DocForge-Bench) — the eval harness measures any real uplift before we rely on it.

## Phase 5 training — RESULT: trained, but cross-domain transfer fails (2026-06-22)

- **Trained our own forgery U-Net on the GPU** (RTX 5060 Blackwell, torch 2.11+cu128): 12k DocTamper
  images × 3 epochs at 256px, ~72 img/s, loss 1.49→1.02 → `models/forgery/unet/weights/forgery.pth`.
  The full GPU train+inference pipeline works end-to-end — the gated-DocTamper-checkpoint blocker is gone.
- **Honest outcome — NO uplift (measured).** Eval is identical to heuristics-only (precision 1.0, recall
  0.729). Raw model probabilities cluster at 0.45–0.59 **regardless of tampered vs clean** on both the
  synthetic eval and the real PAN/Aadhaar photos → the DocTamper-trained model does not discriminate on
  our document types. This is cross-domain failure (DocForge-Bench): DocTamper is Chinese-document
  tampering and does not transfer to Indian forms/IDs. Stored in `results/forgery_training/summary.md`.
- **Decision:** **heuristics + semantic + QR stay the default** (reliable on our docs). The U-Net is
  trained, integrated behind the seam, and **opt-in** (`TRUSTSHIELD_FORGERY_BACKEND=unet`) but **not
  auto-enabled** (it adds latency without benefit). DEFAULT_BACKEND reverted to the no-op. Path to value:
  **fine-tune on domain data** (our synthetic + labelled real Indian-doc edits) via `--finetune`, then
  re-measure on a held-out split.

## §11 — Realistic synthetic data: real layouts + field-targeted, no-hard-edge tampering (2026-06-23)

- **Why:** the old synthetic corpus was unrealistic on two axes that made it useless as training/eval
  data — flat-text layouts and **hard-edged rectangle-fill** image tampers. That crudeness is *why*
  nothing transferred (the §10 forgery model showed no uplift). Rebuilt the generator (v2).
- **Realistic layouts** (`data/generator/pdf_builder.py`): TRACES-style Form 16 (Part A/B + quarterly-
  TDS table), bank statement with a correct running-balance table, balancing salary slip; PAN/Aadhaar
  kept doc-style per scope (Aadhaar marked SYNTHETIC). Builders stay backward-compatible (keyword-only
  `fields`/`template`) so the existing PDF packets + PDF-level tampers + tests are unaffected.
- **Field map + seamless engine** (`seamless_edit.py`): edits target the fields fraudsters actually
  edit, on a tagged **naive→blended→pro** spectrum. `pro` = cv2.inpaint (no flat box) → font/colour/
  **bold**-matched render → re-added page-matched sensor noise → single recompress. cv2 optional (pro
  degrades to blended). Validated by eye: the pro edits are seamless (matched tone/weight/softness).
- **Dataset v2 + splits** (`build_image_dataset.py`): builds docs in-process (to hold exact field
  boxes), applies field + geometric tampers with masks, deterministic **train/val/test split by source
  id** (no leakage). `labels.json` carries field_name/fraud_field/difficulty/old_value/new_value/
  variant/split. Eval gains a per-difficulty breakdown + an optional split filter.
- **Honest measured finding:** on realistic documents the pixel heuristics hold **precision 1.0 (zero
  FP on clean)** but **recall collapses** — detection by difficulty: `geom` 0.57, `naive`/`blended`/
  `pro` field edits ≈ **0.0** (a number in a table is below the size-guarded heuristics' floor). The
  seamless `pro` tier evades them by construction. This is the precise, honest motivation for the
  learned model — and the domain-matched data it was missing. Decision: heuristics stay the default
  guarantee (no FP); the forgery U-Net is fine-tuned on the v2 `train` split and re-measured on the
  held-out `test` split (`results/forgery_training/`). GPU note: CUDA was unavailable this session
  (dGPU not visible), so the fine-tune ran on CPU on the small (~283-sample) domain set.

### §11 fine-tune RESULT — domain data works (2026-06-23)
GPU came back (RTX 5060). Trained DocTamper base (12k×3) → fine-tuned on the v2 **train** split (25
epochs) → eval on the held-out **test** split. **Heuristics:** P=1.0 R=0.17 (geom only). **+U-Net:**
R=**0.915** — pro edits **0.83** (heuristics 0.0), naive 1.0 / blended 0.95 / geom 0.90, loc IoU 0.48.
So the realistic §11 dataset IS good training data — it turns the cross-domain-useless model into the
primary detector. **Caveat:** the U-Net false-fires on 5/10 clean test docs (~50% clean FP) → precision
0.945 is flattered by the tampered-heavy split. Default runtime stays heuristic (P=1.0); U-Net is opt-in.
This is within-synthetic-domain generalization (shared generator/fonts/edit-method), **not** yet
synthetic→real. Upgrades next: scale+diversity + tamper-crop/tiled-inference + real-doc eval anchor +
clean-FP calibration. Full writeup in `results/forgery_training/summary.md`.
