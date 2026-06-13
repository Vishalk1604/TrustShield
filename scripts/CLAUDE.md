# CLAUDE.md — scripts

## Purpose
Repo-wide utility scripts. Right now: the local-only network guard that proves TrustShield makes no
external calls at runtime — the machine-checkable evidence behind the privacy pitch.

## Key files
- `verify_local_only.py` — scans source files for outbound-network usage and hardcoded external
  URLs; exits non-zero on any violation. **Run at the end of every phase.**

## How it fits
Not part of the runtime. It's a CI/commit gate. The privacy story (Phase 7) and the README both
point at it as the proof.

## Local-only contract
This *is* the enforcement of the contract. It deliberately exempts `tests/` and `shared/mocks/`
(which may reference network APIs in guards/comments) and itself (it contains the detection
patterns).

## How to run / test just this part
```bash
python scripts/verify_local_only.py     # exit 0 = clean
```
To confirm it still bites: drop `requests.get("https://x.com")` into any non-exempt `.py`, run it
(should fail), then remove the line.

## Gotchas
- Allowed hosts: localhost / 127.0.0.1 / 0.0.0.0 / ::1 and the compose service names. Anything else
  in an `http(s)://` literal fails the check.
- Only scans `.py/.js/.jsx/.ts/.tsx`. Markdown (READMEs with GitHub links) is intentionally not
  scanned.
- If you add a genuinely-mocked external reference, put it under `shared/mocks/` so it's exempt.

## Status
- **Done (Phase 0):** guard implemented + verified (catches violations, passes when clean).
- Future phases add scripts here as needed (e.g. `seed_demo.py` lands at the root in Phase 8).
