"""Real-document ingestion pipeline (plan.md §7) — financial + KYC first.

Turns an uploaded file (PDF text/scan, or image) into the shared `ExtractedEntities`
contract + forensic findings, so the existing five analysis layers run unchanged.

Modules (built incrementally, Person 1 / Week 1):
  - normalize : Indian number/date parsing + PAN/Aadhaar/IFSC validators (no deps).
  - classify  : heuristic doc-type classifier over document text (no deps).
  - loader    : multi-format intake (PDF text/image, JPG/PNG, password PDFs).        [next]
  - preprocess: OpenCV scan cleanup (deskew/denoise/binarize).                        [next]
  - ocr_engine: PaddleOCR primary + Tesseract fallback.                               [next]
  - extract/  : per-doc-type heuristic extractors.                                    [next]

Local-only: pure local computation; no network calls.
"""
