# TrustShield — Judge-Facing Dashboard: Continuous Build Plan (routine)

> This file drives a recurring autonomous routine (runs 01:00 and every ~5h: 01/06/11/16/21).
> Each run is a COLD start — this file + the repo are your only memory. Read it fully first.

## Routine protocol (do this every run)
1. **Orient:** read this whole file, then `PROGRESS.md`, `plan.md` (esp. §1, §10, §11), and `git log --oneline -15`.
2. **Clean tree first:** if there is uncommitted work, evaluate it — if it's finished §11 forensics work, commit it (msg `…(§11)…`); otherwise stash. Start each dashboard task from a clean tree.
3. **Pick the FIRST unchecked task** in the Backlog below. Do it fully in this run. If it's too big, split it, make real incremental progress, and leave a clear sub-note.
4. **Verify:** `cd services/dashboard && npm run build` must pass. Don't break the Python suite (`pytest -q` should stay green) or `python scripts/verify_local_only.py`.
5. **Commit** to `main` (no Claude co-author trailer — owner's rule). Then **tick the task** here and **append one line to the Worklog** (date — what landed — short commit hash).
6. **Deep-think (5 min):** consider the project holistically (story, gaps, what would impress judges). Log ideas in the Ideas section. Only act on dashboard ideas; non-dashboard ideas just get logged.
7. If the whole Backlog is checked, start a **Polish loop**: pick the weakest screen and make it better (visual quality, copy, motion, responsiveness, a guided judge tour), log it as a new R-task.

## Constraints (non-negotiable)
- **100% local-first.** No runtime network except the local services (forensics `:8001`, risk `:8002`). `verify_local_only.py` must keep passing. No external CDNs at runtime — vendor assets/fonts locally.
- **Demo must work with the backend DOWN.** Every judge-facing screen renders from baked-in demo data (see Assets) so the home + examples work with zero setup. Live calls are an enhancement, not a requirement.
- **No real PII.** Use synthetic samples only (`data/synthetic/_preview/`, `results/image_forensics/samples/`). Never bundle anything from `data/real/`.
- **Honest claims only.** Use the real numbers from `results/`. Where the model has limits (the synthetic→real gap), present it as a strength of our rigor, not hidden.
- Keep commits small and frequent. Don't rewrite working code without reason.

---

## Context — what we're presenting (the pitch)
**TrustShield** is a **100% local-first underwriting copilot** that detects document tampering/forgery
across a loan packet and returns an **explainable trust score (0–100) + evidence chain + recommended
action**. Audience: **hackathon judges**. Everything runs on-device — privacy is a core selling point.

The engine is a **5-layer pipeline**: (1) **pixel/image forensics** (ELA, sensor-noise, copy-move,
JPEG-ghost, recapture/moiré), (2) **semantic identifier checks** (PAN/Aadhaar validation + **QR
cross-verification** of the card's signed data vs the printed text), (3) a **learned forgery-localization
model** (our own U-Net, trained on realistic synthetic edits), (4) **trust-score aggregation** (weighted,
documented) producing an evidence chain + action, (5) a **cross-application graph** (fraud rings,
double-financing). Plus **KYC/underwriting** (identity/address established, income reconciliation, FOIR).

Recent work (§11): a **realistic synthetic dataset** (TRACES Form 16, real bank statement, salary slip,
PAN/Aadhaar) with **seamless, no-hard-edge tampering** on the fields fraudsters actually edit, used to
train/measure the forgery model. Honest result: heuristics keep **precision 1.0 (zero false positives)**;
the learned model detects seamless edits well **on synthetic** docs but **does not yet transfer to real**
documents (the synthetic→real gap) — so heuristics + semantic + QR are the guaranteed-local layer and the
model is opt-in. See `results/forgery_training/summary.md`, `results/image_forensics/`, `DECISIONS.md §11`.

## Vision for the dashboard
A polished, **judge-facing** dashboard, built fresh, that **opens on a HOME/LANDING screen** telling the
TrustShield story end-to-end, then lets judges explore **live detection** and **annotated examples**.
Think: "if a judge opens this cold, in 60 seconds they understand the problem, our approach, the proof,
and can click one button to watch us catch a forged document."

## Information architecture
### A. Home / Landing (the hero — first thing judges see)
1. **Hero** — name + tagline + one-liner + a prominent **"100% on-device · no network"** badge; primary CTA "Watch it catch a forgery", secondary "How it works".
2. **The problem** — loan fraud via forged Form 16 / bank statements / PAN / Aadhaar; seamless digital edits slip past human review. A crisp visual (a "spot the edit" before/after that judges can't tell apart).
3. **How it works** — the **5-layer pipeline** as an interactive diagram; each layer a card with a one-line "what it catches".
4. **Key features grid** — every capability (icon + 1-liner): pixel forensics; semantic ID + QR cross-verify; learned forgery localization; trust score + evidence chain + action; cross-application graph (rings/double-financing); KYC/underwriting (FOIR); **privacy / local-only**.
5. **Proof / results** — the honest numbers as small charts/stat cards: heuristics **precision 1.0 / zero FP**, detection-by-difficulty, the forgery-model uplift on synthetic, the **synthetic→real** honesty note, 209 tests passing, `verify_local_only` green.
6. **Annotated examples** — a gallery of before/after seamless edits with **detection overlays** + captions explaining the edit and how we catch (or honestly miss) it.
7. **Footer** — tech stack, "no data leaves the device", links to the layers.

### B. Live Investigator (the working tool)
- Pick a **sample packet** or upload a doc → call forensics `:8001` (`/forensics/analyze-image` for images) → render **verdict, trust score gauge, evidence chain cards, recommended action, region overlays**. Falls back to baked-in demo JSON when the backend is down.

### C. Examples / Evidence deep-dive
- Curated clean-vs-tampered cases with the mask overlay, the finding list, and a plain-English explanation per case.

## Tech approach
- **React + Vite** in `services/dashboard/` — build a NEW polished front-end (new Home + restructured
  routes/components); reuse `src/api.js` wiring + the existing investigator logic where useful.
- Styling: use the **ui-styling / ui-ux-pro-max / design** skills for quality (Tailwind ok; vendor
  locally). Aim for a clean, trustworthy, fintech-grade look (the brand is *trust*).
- **Demo mode**: a `src/demo/` module with baked-in JSON/handcrafted results (derived from `results/` +
  `data/synthetic/_preview/`) so Home + Examples render with no backend. A small toggle "Live / Demo".
- Keep `npm run build` green every commit.

## Assets to use (already in the repo)
- Annotated detection overlays: `results/image_forensics/samples/*.png`
- Clean + edited preview renders (Form 16 / bank / salary / PAN / Aadhaar + zoom crops): `data/synthetic/_preview/*.png`
- Real numbers: `results/image_forensics/metrics.json`, `results/forgery_training/summary.md`
- Contracts/types: `shared/schemas/models.py` (TrustScore, EvidenceItem, Recommendation)
- Existing UI to mine for logic: `services/dashboard/src/App.jsx`, `src/api.js`

## Backlog (ordered — do the first unchecked each run; split if large)
- [x] **R1 — Shell + design system.** New routing (Home / Investigator / Examples), brand tokens (palette, type, the local-first badge), responsive layout, vendored fonts/icons. `npm run build` green.
- [x] **R2 — Home: Hero + Problem.** Hero (badge + headline + 3 stat callouts + CTAs) and an interactive "spot the edit" reveal using the REALISTIC Form 16 clean/edited pair (committed to `public/examples/`).
- [x] **R3 — Home: How-it-works pipeline.** Reuses `PipelineDiagram mode="cards"` — the 5 layers with "what it catches".
- [x] **R4 — Home: Key features grid.** 8 capability cards (per-layer icon hues): forensics, semantic+QR, learned model, trust+evidence, graph, KYC/FOIR, explainability, on-device.
- [x] **R5 — Home: Proof/results.** Honest stat cards (0/95 FP, 5 layers, 0.00→0.29 pro-edit, no-network) + a HONEST-LIMIT callout (synthetic→real gap framed as rigor) + closing CTA.
- [ ] **R6 — Annotated examples gallery.** Before/after + overlay + caption per case (Form 16 gross-salary, bank salary-credit, PAN swap); pull from samples/_preview.
- [x] **R7 — Live Investigator.** Sample-or-upload → forensics call → verdict/evidence/overlay; demo-mode fallback wired. *(Delivered by the user-directed redesign — two modes, Live/Demo toggle + baked-in fallback.)*
- [x] **R8 — Trust score + evidence chain + action viz.** Gauge + ordered evidence cards + recommendation banding. *(Animated neon gauge + action chip + sub-scores + evidence grouped by pipeline layer.)*
- [x] **R9 — Cross-application graph mini-view.** Rings / double-financing (static demo data or from risk `:8002`). *(Graph panel in the packet result, live `:8002` or baked-in subgraph.)*
- [ ] **R10 — Polish + judge tour.** Motion, transitions, mobile, a11y, copy editing, a guided "click-through tour" overlay; capture screenshots for the deck under `docs/`. *(Partial: motion/reveal, focus rings, responsive done in the redesign; guided tour + deck screenshots remain.)*
- [ ] **R11+ — Iterate.** KYC/underwriting (FOIR) panel; refine weakest screens; demo script in `DEMO.md`.

## Worklog (append one line per run)
- 2026-06-23 (setup) — plan created; routine scheduled (01:00 + every ~5h). First run starts at R1.
- 2026-06-24 — R1 landed: react-router-dom shell (Home/Investigator/Examples), theme.js tokens, inline-SVG
  icon set, local-first badge, responsive nav; old console moved to pages/Investigator.jsx unchanged — `e4c5605`.
- 2026-06-24 — **Redesign Phase A** (user-directed): premium dark-glass design system — theme.js retuned
  (near-black + glass() + per-layer hues + glow/motion tokens), vendored Inter (no CDN), index.css, and
  reusable UI primitives (Gauge, Reveal, PipelineDiagram, Card/Badge/Stat/Button); glassier Shell — `0e46165`.
- 2026-06-25 — **R2–R5 landed (user-directed): the judge-facing Home page.** Full narrative — hero
  (local-first badge + headline + 3 stat callouts + CTAs), interactive "spot the edit" with the realistic
  Form 16 clean/edited pair (copied into public/examples/), the 5-layer pipeline (cards), an 8-card
  features grid, and honest proof stats + a synthetic→real "honest limit" callout + closing CTA. Verified
  in preview (hero/problem/features/proof screenshots, reveal interaction, no console errors); `npm run
  build` green.
- 2026-06-24 — **Redesign Phase B** (user-directed, satisfies R7/R8/R9): Investigator rebuilt first-principles
  around the 5-layer pipeline spine — two modes (packet / single doc), curated entry chips, neon verdict
  header, evidence grouped by layer w/ inline localization, graph panel, Live/Demo toggle + baked-in
  fallback (src/data/demoDecisions.js + public/demo). Verified Live (:5173) + Demo paths — `9837b5c`.

## Ideas (deep-think log — record, act only on dashboard ones)
- **[dashboard] Lead with the honest synthetic→real gap, don't hide it.** Most hackathon entries oversell
  "AI detects fraud." Our actual differentiator is the opposite: we *measured* where heuristics are
  bulletproof (precision 1.0, zero FP on clean — both synthetic and real anchors) vs where the learned
  model shines only in-domain (`results/forgery_training/summary.md` §5). R5 (Proof) should frame this as
  rigor, and Home copy must stay precise — never claim a blanket "AI catches all forgeries"; say
  heuristics+semantic+QR are the guaranteed-local layer, the U-Net is opt-in/synthetic-domain.
- **[dashboard] The gallery's most dramatic exhibit is invisibility, not the overlay.** `data/synthetic/
  _preview/zoom_pro.png` vs `zoom_clean.png` — a seamless "pro"-tier edit a human can't spot at all — is a
  stronger "spot the edit" hook for the Home hero than the existing `results/image_forensics/samples/*`
  (which are mostly splice/recompress, the *easy* tier). Pair the hard-to-spot pro example with an honest
  caption: "even our heuristics miss this one — this is why the semantic/QR layer exists."
- **[dashboard] R9's cross-application graph (fraud rings / double-financing) is the most unique
  capability vs typical "tampered PDF detector" hackathon projects** — most competitors stop at
  single-document checks. Worth a visually strong standalone demo, not just a footnote feature card.
- **[dashboard] Local-first should be framed as a compliance/data-residency story for judges, not just
  "fast/private"** — Indian NBFC/bank underwriting data leaving the device is a real regulatory concern;
  tie the badge's tooltip/expansion to that angle in R2.
- **[non-dashboard, logged only] The Examples gallery is thin on "pro"-difficulty samples** (only 5 curated
  PNGs in `results/image_forensics/samples/`, skewed toward splice/recompress). A future generator run
  producing a handful of curated naive/blended/pro before-after pairs *with ground-truth masks* purely for
  the gallery (distinct from the eval dataset) would make R6 much stronger — flagging for a forensics/
  generator session, not this dashboard routine.
- **[dashboard] The redesign created a shared visual grammar — reuse it on Home, don't reinvent.** The
  `PipelineDiagram` (mode="cards") already exists for R3's "how it works"; the `Gauge`/`Card`/`Stat`/`Badge`
  primitives + per-layer hues should drive R2/R4/R5 so Home and the console look like one product. The
  Home "spot the edit" (R2) and the Investigator's single-doc mode tell the same story from two angles —
  keep the captions consistent.
- **[dashboard] A guided judge tour (R10) is now high-leverage.** The console packs a lot (two modes, the
  spine, grouped evidence, the graph). A 4-step coachmark overlay ("1 pick a case → 2 read the verdict →
  3 click a pipeline layer → 4 see the edit located") would let a judge self-drive in 60s. Build it as a
  reusable overlay so Home can trigger "take the tour" too.
- **[dashboard, known-gap] The preview-screenshot tool stalls on this app** (likely the 5s health-poll
  interval never reaching network-idle + backdrop-filter). Verified the redesign via DOM/computed-style
  inspection instead. For R10's deck screenshots, consider a transient "screenshot mode" that pauses the
  health poll, or capture from the real browser.
