# CLAUDE.md — services/risk (Service B)

## Purpose
Risk + Scoring. Owns the semantic rules engine, the Isolation Forest anomaly model, the NetworkX
cross-application graph, trust-score aggregation, and evidence-chain assembly. Produces the final
`PacketDecision` (TrustScore + ordered evidence chain + recommendation) the dashboard renders.

## Key files
- `app/main.py` — FastAPI app. **Phase 0:** `GET /health`, `GET /` only. Phases 2–5 add the rules
  engine, anomaly scoring, graph, and `POST /risk/score` (the main orchestration endpoint).
- `requirements.txt` — Phase 0 scope (`fastapi/uvicorn/pydantic`); scikit-learn + networkx + joblib
  added in Phase 3/5.
- `Dockerfile` — `python:3.11-slim`; build context is the **repo root** so `shared/` is importable.

## How it fits
Receives a packet's forensic + semantic + anomaly analyses and composes the trust score. Calls the
mock adapters in `shared/mocks` (e.g. AIS reported income) for cross-checks. The dashboard calls
`POST /risk/score`.

## Local-only contract
No outbound network calls. External verifications go through `shared/mocks` (local fixtures only).
CORS opened only for `http://localhost:5173`.

## How to run / test just this part
```bash
# from the repo root (so `shared` resolves)
uvicorn services.risk.app.main:app --reload --port 8002
curl http://localhost:8002/health        # -> {"status":"ok","service":"risk",...}
# or via Docker:  docker compose up risk
```

## Gotchas
- Run from the **repo root** (PYTHONPATH) or shared imports fail; in Docker this is `/app`.
- Scoring weights/thresholds must be explicit and documented in `DECISIONS.md` (Phase 4) — never a
  magic constant. Never return a score without a non-empty evidence chain (the `PacketDecision`
  schema enforces this).

## Status
- **Done (Phase 0):** health + schema wiring.
- **Done (Phase 2):** `app/rules.py` cross-document rules engine + `POST /risk/rules/check`.
- **Done (Phase 3):** `app/features.py` (16-feature vector), `train.py` (Isolation Forest + GBC,
  joblib artifacts in `models/`), `app/scorer.py` inference wrapper.
- **Done (Phase 4):** `app/aggregator.py` (documented-weight blend → `TrustScore` + evidence chain +
  `Recommendation`) and `POST /risk/score` (main orchestration endpoint, Phase 1→4 in-process).
- TODO: Phase 5 NetworkX cross-application graph.

## Scoring weights (Phase 4 — documented, never magic constants)
`aggregator.WEIGHTS`: model 0.55 / forensic 0.25 / semantic 0.15 / IF-anomaly 0.05 (sum 1.0).
Thresholds: approve ≥ 70, freeze < 40, CRITICAL caps trust at 25. A freeze requires concrete
document evidence — a model-only low score softens to manual_review + graph routing. See DECISIONS.md.
