# TrustShield — 3-Minute Demo Script

> **The pitch:** *"Underwriters get a stack of PDFs — payslips, Form 16, bank statements, sale deeds,
> encumbrance certificates, valuations. Forgery and collateral fraud hide in that stack. TrustShield is a
> 100% on-premise copilot that reads the whole packet, scores its trustworthiness 0–100, and shows the
> exact evidence — including fraud only visible **across** applications."*

---

## 0. One-time setup (before the demo)

From the repo root:

```bash
# Option A — Docker (all three services)
docker compose up --build            # forensics :8001, risk :8002, dashboard :5173

# Option B — local
python -m services.risk.train        # train the models (writes services/risk/models/)
uvicorn services.forensics.app.main:app --port 8001 &
uvicorn services.risk.app.main:app --port 8002 &
cd services/dashboard && npm install && npm run dev      # :5173
```

Seed the cross-application graph and verify the whole demo reproduces from a clean state:

```bash
python scripts/seed_demo.py          # rebuilds the graph + replays every staged packet
```

You should see **"Demo replay OK — every staged packet matched its expected action."**
Open **http://localhost:5173**. The two health dots go green; the on-premise banner shows the graph
is seeded.

---

## 1. The narrative (≈3 minutes)

Each step = click the packet in the left list. The decision, evidence chain, and cross-application
graph render on the right. The little chip on each packet is the *ground-truth label* (so the audience
can see the system caught a known case).

| # | Packet | What you say | Expected result |
|---|--------|--------------|-----------------|
| 1 | **PKT-0001** | "A clean salaried applicant. Everything reconciles." | **APPROVE · trust ≈ 99.** Evidence chain: model says low risk, nothing flagged. |
| 2 | **PKT-0010** | "Same template, but the income on the Form 16 was edited." | **FREEZE · trust ≈ 35.** Forensic evidence: *White-box edit detected* — the original figure is still in the text layer. |
| 3 | **PKT-0014** | "No tampering this time — but the story doesn't add up." | **FREEZE · trust ≈ 33.** Semantic evidence: *Form 16 income inconsistent with bank credits / salary slip.* |
| 4 | **PKT-0028** | "The encumbrance certificate says the property is clean — 'NIL'." | **FREEZE · trust ≈ 16.** **Critical** semantic evidence: *EC contradicts the CERSAI registry* — there's an active mortgage they tried to hide. |
| 5 | **PKT-0031** | "Now a normal-looking secured loan. Documents check out individually." | **FREEZE · trust ≈ 13.** **The reveal:** *Collateral pledged across multiple applications.* |

### The double-financing reveal (the wow)

Click **PKT-0031 → PKT-0032 → PKT-0033** in sequence. Each is a *different applicant* (Imran Shaikh,
then two others) pledging **the same property `SY-911/2C`** as collateral. No single document is forged
— each packet looks fine on its own. But the **cross-application graph** lights up the shared property
node: the same asset is financed three times over. *"A single-document tool is structurally blind to
this. CERSAI exists precisely to catch it — and here it falls out of the graph automatically."*

> Bonus: click **PKT-0018** to show the **synthetic-identity ring** — four "applicants" sharing one
> employer (*QuickCash Finance*) and one document template. Same idea, different fraud shape.

---

## 2. How the score is built (if asked)

Every score is a **transparent blend** with documented weights (see `DECISIONS.md`):

- **model 0.55** (gradient-boosted trees — its probability *and top features are shown*, not hidden)
- **forensic 0.25** (per-document tamper signals) · **semantic 0.15** (cross-document rules) · **anomaly 0.05** (Isolation Forest)
- **+ cross-application graph** as an additive overlay; a critical relational finding caps trust into the freeze band.

Two rules make it defensible: **(a)** a score is *never* shown without a plain-English evidence chain;
**(b)** a **freeze** requires concrete document or graph evidence — a model hunch with nothing to point
at is routed to *manual review + graph check*, never an auto-reject.

## 3. The model-metrics slide

5-fold cross-validation on the synthetic set (`services/risk/models/metrics.json`):

- **ROC-AUC: 0.97**
- **Confusion matrix:** TN = 10, FP = 0, FN = 1, TP = 22 (the one miss is a double-financing packet —
  *which has no per-packet signal by design; the graph is what catches it*)
- **Top features:** submission velocity, count of cross-document inconsistencies, income mismatch.

## 4. Honest Q&A

- **"Is this calling real GSTIN / CERSAI / AIS?"** No — those are **local mock adapters** reading JSON
  fixtures, behind a production-shaped interface. The one seam (`_fetch`) is where a real HTTPS client
  drops in. `python scripts/verify_local_only.py` *fails the build* if any outbound call appears.
- **"Is the model trained on real fraud?"** No — it's trained on **synthetic** packets to prove the
  pipeline. The honest production answer is **"retrain on the bank's own labelled history, on the
  bank's own hardware."** The architecture (explainable trees + rules + graph) is what transfers.
- **"Where does customer data go?"** Nowhere. **100% on-premise**, no runtime network, PII scrubbed
  from logs (`PRIVACY.md`). The dashboard says so to the investigator.
- **"Can we audit a decision?"** Yes — every decision exports as a JSON evidence report from the
  dashboard.

---

## 5. Reproducibility

`python scripts/seed_demo.py` rebuilds the graph from a clean state and asserts every staged packet
lands on its expected action — so the demo replays identically, twice in a row, with no manual setup.
