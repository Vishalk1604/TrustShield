# data/real/ — real document collection kit (LOCAL ONLY)

This folder is where you and your teammates drop **real / consented sample documents** so we can build
and validate TrustShield's real-document pipeline (Milestone 1: financial docs first).

## 🔒 Golden rules (read first)
1. **Nothing here is ever committed to git.** This folder is gitignored (only this README + the empty
   folder structure are tracked). Double-check with `git status` before any commit — you should never
   see a real file listed.
2. **Local only.** These never leave your machine. TrustShield makes zero network calls at runtime.
3. **Use your OWN documents, or ones you have explicit consent to use.** Don't use anyone else's
   financial documents without permission.
4. **Anonymize what you don't need** (see below). When in doubt, redact.
5. You can **delete everything here after testing** — we only need them transiently to validate accuracy.

---

## ✅ What to collect

Bring a **mix of clean digital PDFs and phone photos / scans** (JPG/PNG/PDF) so we test both the
text-PDF fast path and the OCR/scan path. Variety of issuers/banks matters more than volume — different
employers and banks = different layouts, which is exactly what we need to harden against.

### Priority 1 — Financial (needed for Milestone 1) → `financial/`
| Document | Put it in | Notes | Target |
|---|---|---|---|
| **Form 16** (Part A + B) | `financial/form16/` | PDF from employer/TRACES. 2–3 from **different employers**. | 5–10 |
| **Salary slip / payslip** | `financial/salary_slip/` | 1–3 months; different employers = different templates. | 5–10 |
| **Bank statement** (6 months) | `financial/bank_statement/` | PDF. **Often password-protected — record the password** (see below). 2–3 **different banks**. | 5–10 |
| *(optional)* ITR-V / ITR ack, Form 26AS / AIS | `financial/` | From the income-tax portal. Helps tax-reconciliation later. | a few |

### Priority 2 — Identity / KYC (cheap to add) → `identity/`
| Document | Put it in | Notes |
|---|---|---|
| **PAN card** | `identity/pan/` | Photo or PDF. |
| **Aadhaar (MASKED only)** | `identity/aadhaar/` | Use the **masked** download (mAadhaar / "masked Aadhaar"): first 8 digits hidden. Never put a full Aadhaar here. |

### Priority 3 — Legal / land (later milestone) → `legal/`
Sale deed, Encumbrance Certificate (state portal, e.g. Karnataka Kaveri), property valuation report,
legal opinion, property tax receipt / Khata. These are the hardest (scanned, regional language, stamps)
— collect opportunistically; not required for Milestone 1.

### Bonus — for testing the forensics layer
If anyone is comfortable, take **one clean doc and make a deliberately edited copy** (e.g. change an
income figure in a PDF editor, or photoshop a number on a scan) and drop it next to the original with a
`_TAMPERED` suffix. This lets us prove the tamper-detection layer on real formats. Mark it clearly; it's
fake-for-testing, not a real document.

---

## 📁 Folder layout
```
data/real/
  financial/
    form16/            ← Form 16 PDFs
    salary_slip/       ← payslips
    bank_statement/    ← bank statements (+ passwords.txt if protected)
  identity/
    pan/               ← PAN card photo/PDF
    aadhaar/           ← MASKED Aadhaar only
  legal/               ← (later) sale deed, EC, valuation, legal opinion
```

## 🏷️ Naming convention (helps us track issuers without exposing identity)
`<doctype>_<issuer-or-bank>_<NN>[_TAMPERED].<ext>` — e.g.
`form16_TCS_01.pdf`, `bankstmt_HDFC_01.pdf`, `salaryslip_Infosys_02.pdf`, `bankstmt_SBI_03_TAMPERED.pdf`.
No need to put real names in filenames.

## 🔑 Password-protected bank statements
If a bank statement PDF needs a password to open, create `financial/bank_statement/passwords.txt` with
one `filename = password` per line (this file is gitignored too). The pipeline will use it to decrypt
locally. Example:
```
bankstmt_HDFC_01.pdf = ABCD1234
```

## ✂️ Anonymization guidance (do what you can; the pipeline also redacts logs)
- **Aadhaar:** masked version only.
- **Account numbers:** fine to leave (the app masks them in logs) — or black out all but the last 4.
- **Don't** black out the fields we need to extract: **name, PAN, employer, gross income / TDS, salary
  credits, dates, IFSC** — those are what we validate extraction against.
- The app already redacts PII in logs ([shared/privacy.py](../../shared/privacy.py)); the redaction is
  for logs, not the on-screen evidence (which legitimately shows the values to the investigator, locally).

## ▶️ What happens to these
They're used **only to validate** that the real-document pipeline (OCR → doc-type → extraction →
forensics → score) reads genuine Indian formats correctly. Bulk model training uses the **synthetic
generator v2** (no PII); your real set is the small held-out reality check. See the project plan and
`plan.md` §6 for the full roadmap.
