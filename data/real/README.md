# data/real/ — real document collection kit (LOCAL ONLY)

Drop **real / consented sample documents** here so we can validate TrustShield's pipeline on genuine
Indian formats. The folders mirror the **upload slots** the app asks for, organized by **purpose**
(KYC and salaried personal loan — plan §9). Place each document in the slot folder it belongs to; the
demo maps the folder name straight to the upload slot.

## 🔒 Golden rules (read first)
1. **Nothing here is ever committed to git.** This folder is gitignored (only this README + the empty
   folder skeleton are tracked). Check `git status` before any commit — you should never see a real file.
2. **Local only.** These never leave your machine; TrustShield makes zero network calls at runtime.
3. **Use your OWN documents, or ones you have explicit consent to use.**
4. **Aadhaar: MASKED only.** Never place a full (unmasked) Aadhaar here.
5. You can **delete everything here after testing** — we only need it transiently to validate accuracy.

Bring a **mix of clean digital PDFs and phone photos/scans** (PDF/JPG/PNG) so we exercise both the
text-PDF fast path and the OCR path. Variety of issuers/banks > volume (different layouts harden us).

---

## ✅ What to collect — by purpose

### KYC set → `kyc/`
| Slot folder | Document | Format | Fields we read | Target |
|---|---|---|---|---|
| `kyc/pan/` | **PAN card** (proof of identity) | photo / PDF | name, PAN, DOB | 5–10 |
| `kyc/aadhaar/` | **Aadhaar — MASKED** (identity + address) | photo / PDF | name, masked no., DOB, address | 5–10 |
| `kyc/address_proof/` | **Address proof**: electricity/utility bill (≤2 months), passport, voter ID, or driving licence | photo / PDF | name, address, issue date | 5–10 |

### Salaried personal-loan set → `salaried_loan/`
| Slot folder | Document | Format | Fields we read | Target |
|---|---|---|---|---|
| `salaried_loan/salary_slip/` | **Salary slips — last 3 months** | PDF | name, employer, net monthly pay | 5–10 sets |
| `salaried_loan/form16/` | **Form 16** (Part A+B, TRACES) | PDF | name, PAN, employer, gross income, TDS, FY | 5–10 |
| `salaried_loan/bank_statement/` | **Bank statement — 6 months** (salary account) | PDF (often password) | holder, account, salary credits | 5–10 |
| `salaried_loan/itr/` *(optional)* | **ITR-V / 26AS / AIS** | PDF | declared income, TDS | a few |

> A loan submission also needs the **KYC set** (PAN + Aadhaar + address proof). The most valuable thing
> to assemble is **one complete applicant set** — the *same person's* PAN + masked Aadhaar + address
> proof + 3 salary slips + Form 16 + 6-month bank statement. That single set drives the full
> KYC → income-reconciliation → affordability → trust-score demo end to end.

### Forensics testing → `_tampered/`
Take one clean doc and make a **deliberately edited copy** (change an income figure in a PDF editor, or
edit a number on a scan), and drop it here with a `_TAMPERED` suffix. This proves the tamper-detection
layer on real formats. It's fake-for-testing — mark it clearly. 2–3 of these is plenty.

---

## 📁 Folder layout
```
data/real/
  kyc/
    pan/                 PAN card (photo/PDF)
    aadhaar/             MASKED Aadhaar only
    address_proof/       utility bill ≤2mo / passport / voter ID / DL
  salaried_loan/
    salary_slip/         last 3 months
    form16/              Part A+B
    bank_statement/      6 months (+ passwords.txt if protected)
    itr/                 (optional) ITR-V / 26AS / AIS
  _tampered/             deliberately edited copies, _TAMPERED suffix
```

## 🏷️ Naming convention
`<slot>_<issuer-or-bank>_<NN>[_TAMPERED].<ext>` — e.g. `form16_TCS_01.pdf`,
`bank_statement_HDFC_01.pdf`, `salary_slip_Infosys_02.pdf`, `pan_01.jpg`,
`address_proof_BESCOM_01.pdf`, `bank_statement_SBI_03_TAMPERED.pdf`. No real names needed in filenames.

## 🔑 Password-protected bank statements
If a statement needs a password, create `salaried_loan/bank_statement/passwords.txt` (gitignored) with
one `filename = password` per line — the pipeline decrypts locally:
```
bank_statement_HDFC_01.pdf = ABCD1234
```

## ✂️ Anonymization guidance
- **Aadhaar:** masked version only.
- **Account numbers:** fine to leave (the app masks them in logs), or black out all but the last 4.
- **Don't** black out the fields we extract/validate: **name, PAN, employer, gross income / TDS, salary
  credits, dates, IFSC, address** — those are exactly what the verification checks.
- The app already redacts PII in logs ([shared/privacy.py](../../shared/privacy.py)); redaction is for
  logs, not the on-screen evidence (which legitimately shows values to the investigator, locally).

## ▶️ What happens to these
They validate that the real-document pipeline (OCR → doc-type → extraction → KYC/underwriting →
forensics → trust score) reads genuine Indian formats. Bulk *fraud-model* training uses the synthetic
**generator v2** (no PII); your real set is the small held-out reality check. See `plan.md` §9.
