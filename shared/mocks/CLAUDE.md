# CLAUDE.md — shared/mocks

## Purpose
Local mock adapters for the external registries a real underwriting system would call — GSTIN,
MCA21, CERSAI, AIS (Income Tax), DigiLocker. Each reads a synthetic JSON fixture and makes **zero
network calls**, while presenting a production-shaped interface so the "swap the adapter for the
real API later" story is honest.

## Key files
- `base.py` — `ExternalVerificationAdapter` ABC + `VerificationResult` model. `verify(key)` is the
  public API; `_fetch(key)` is the seam a real implementation overrides with an HTTPS call.
- `gstin.py` / `mca21.py` / `cersai.py` / `ais.py` / `digilocker.py` — concrete adapters; each sets
  `service_name` (= fixture filename stem) and `key_field`, plus a convenience accessor.
- `__init__.py` — exports the classes and an `ADAPTERS` name→class registry.
- `fixtures/*.json` — synthetic records keyed by PAN / GSTIN / CIN.

## How it fits
Later phases (semantic rules, scoring) call these to cross-check a packet's claims — e.g.
`AisAdapter().reported_income(pan)` vs the income declared on the uploaded documents. Not wired
into any service yet in Phase 0.

## Local-only contract
- **No network, ever.** `_fetch` reads a local file. The only "real API" code is commented and
  illustrative; it is never executed. `scripts/verify_local_only.py` allows the URL strings that
  appear in these docstrings precisely because they live under `shared/mocks/`.
- Fixtures are synthetic — no real PII.

## Fixture roster (keep in sync with the generator)
The fixtures use the same 8 synthetic applicants the generator builds packets for (PANs like
`ABMPS1234F` Rahul Sharma, `KLMPS7777N` Vikram Singh, ...). `ais.json` is keyed by PAN and holds
`reported_income` — the main income cross-check. `gstin.json`/`mca21.json` cover the two
self-employed applicants (Singh Traders, Mehta Exports). If you add applicants to the generator's
roster, add matching fixture rows here.

## How to run / test just this part
```bash
pytest tests/test_mocks.py
python -c "from shared.mocks import AisAdapter; print(AisAdapter().reported_income('ABMPS1234F'))"
```
Run from the repo root.

## Gotchas
- `verify()` never raises on a missing key — it returns `found=False, status='not_found'`. Check
  `.found` before trusting `.data`.
- Fixtures are cached per-adapter instance after first read; create a new instance (or clear
  `_cache`) if a test rewrites a fixture on disk.

## Status
- **Done (Phase 0):** all five adapters + fixtures + registry, verified no-network in tests.
- TODO: wire into the semantic rules engine (Phase 2) and scoring (Phase 4).
