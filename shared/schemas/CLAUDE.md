# CLAUDE.md — shared/schemas

## Purpose
The single Pydantic v2 contract every service depends on. If a model changes here, the forensics service, risk service, and dashboard all have to agree. Treat this as an API: keep changes backward-compatible.

## Key files
- `models.py` — all enums and models (the real definitions).
- `__init__.py` — re-exports so callers can `from shared.schemas import EvidenceItem`.

## The contract
- **Enums:** `DocType`, `EvidenceCategory`, `Severity` (has `.rank` for sorting), `Action`.
- **Models:** `Document`, `ExtractedEntities`, `EvidenceItem`, `TrustScore`, `Recommendation`, `ApplicationPacket`, and the envelope `PacketDecision` (score + evidence chain + recommendation).
- `EvidenceItem` is the atom of explainability — every finding becomes one, with a plain-English `description`, a `source_doc_id`/`source_location`, the concrete `values`, and a `confidence`.

## How it fits
- `services/forensics/` emits `EvidenceItem`s (category=forensic) from `POST /forensics/analyze`.
- `services/risk/` emits semantic/anomaly/graph `EvidenceItem`s and assembles the final `PacketDecision`.
- `data/generator/` builds `ApplicationPacket`s (well, the PDFs + a labels manifest that mirrors them).

## Local-only contract
Pure data models — no I/O, no network. `Document.path` is always a local path, never a URL.

## How to run / test just this part
```bash
pytest tests/test_schemas.py
python -c "from shared.schemas.models import EvidenceItem, Severity; print(Severity.CRITICAL.rank)"
```
Run from the repo root so `shared` is importable.

## Gotchas
- `PacketDecision` **enforces a non-empty `evidence_chain`** at construction (raises if empty) — this bakes the "never a score without evidence" rule into the type. Tests that build a decision must include at least one `EvidenceItem`.
- Datetimes are timezone-aware UTC (`_utcnow`); don't compare against naive datetimes.
- `Severity.rank` (not the enum order) is the sort key for evidence chains.

## Status
- **Done (Phase 0):** all six required models + `PacketDecision` envelope + enums.
- TODO: populated `ExtractedEntities` arrives with the Phase 2 extraction pipeline; `TrustScore.version` wiring arrives in Phase 4.
