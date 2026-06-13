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
- TODO: Phase 2 rules engine, Phase 3 Isolation Forest (+ `train.py`), Phase 4 aggregation +
  `POST /risk/score`, Phase 5 NetworkX graph.
