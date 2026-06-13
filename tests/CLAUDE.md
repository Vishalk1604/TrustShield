# CLAUDE.md — tests

## Purpose
Pytest suite guarding the Phase 0 foundation: the schema contract, the mock adapters (incl. a hard
no-network assertion), and the synthetic-data corpus (count / fraud-type coverage / ground-truth
integrity).

## Key files
- `conftest.py` — puts the repo root on `sys.path` so `from shared... / from data...` resolve.
- `test_schemas.py` — every model instantiates + JSON round-trips; `PacketDecision` rejects an empty
  evidence chain; evidence sorts by severity; bounds are enforced.
- `test_mocks.py` — adapters read fixtures, missing keys don't raise, and a `socket` monkeypatch
  proves no adapter touches the network.
- `test_generator.py` — ≥20 packets, all nine fraud types present, every manifest's documents exist
  on disk with a sha256, a manifest validates as `ApplicationPacket`, and a template-reuse group exists.

## How it fits
This is the Phase 0 acceptance gate alongside `scripts/verify_local_only.py` and the Docker health
checks. Later phases add `test_forensics.py`, `test_rules.py`, etc.

## Local-only contract
`tests/` is exempt from the local-only scanner (it may reference `socket`/network names to *guard
against* them). It still must not make real network calls — and `test_mocks` actively asserts that.

## How to run / test just this part
```bash
pip install pytest
pytest tests/ -q          # run all
pytest tests/test_generator.py -q
```
Run from the repo root.

## Gotchas
- `test_generator` regenerates the corpus if it's missing (fresh checkout), so it needs PyMuPDF
  available in that case (`pip install -r data/generator/requirements.txt`).
- Schema equality tests rely on Pydantic model equality; keep models hashable/comparable by value.

## Status
- **Done (Phase 0):** schemas, mocks (no-network), generator corpus.
- TODO: per-service tests land with their phases.
