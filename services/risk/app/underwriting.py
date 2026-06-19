"""Deterministic KYC + underwriting verification (plan §9).

This is the layer that makes TrustShield verify *the applicant against the bank's process*, not
just whether a PDF was edited. It runs on top of the ingested documents (doc_type + extracted
fields + KYC validation) and produces a structured `verification` block with four parts:

  1. completeness  — are the documents this purpose requires actually present?
  2. kyc           — is identity & address established, and are the names consistent?
  3. income        — does declared income reconcile across Form 16 / bank credits / salary slips?
  4. eligibility   — (loans) FOIR, max-eligible amount, LTV → ELIGIBLE / REFER / DECLINE.

Two axes, kept separate (the honesty point):
  - completeness + KYC + income are *consistency/authenticity* concerns → they become evidence
    items that nudge the trust score down by a CAPPED penalty (genuine gaps, never a "fraud" tank).
  - eligibility is a *business-rule* outcome → it NEVER touches the trust score. Genuine documents
    can still be REFER/DECLINE on affordability, and that reads as such.

All constants are explicit and documented here + in DECISIONS.md (project rule: no magic numbers).
Pure local computation; no ML, so it works on real documents on day one.
"""

from __future__ import annotations

import re
from typing import Optional

from shared.schemas import EvidenceCategory, EvidenceItem, Severity

from services.risk.app import profiles

# ── documented underwriting constants ────────────────────────────────────────────
FOIR_CAP = 0.50              # max (existing + proposed EMI) / net monthly income for ELIGIBLE
FOIR_REFER_CAP = 0.60        # FOIR in (0.50, 0.60] → REFER; above → DECLINE
ANNUAL_RATE = 0.105          # assumed personal-loan interest rate (10.5% p.a.) for EMI/eligibility
DEFAULT_TENURE_MONTHS = 60   # assumed tenure when the applicant doesn't specify
LTV_CAP = 0.80               # max loan / collateral value (secured tier; rarely triggered now)
RECON_TOL = 0.15             # ±15% tolerance for like-for-like income reconciliation
NET_TO_GROSS_MIN = 0.55      # banked net salary expected to be ≥55% of declared gross (after TDS/PF)
NET_TO_GROSS_MAX = 1.05      # …and not materially above gross (banked > gross is suspicious)

# Verification findings are consistency gaps, not tamper evidence: cap their total trust penalty so
# a missing document or a name typo can never tank an otherwise-authentic packet.
VERIFICATION_PENALTY_CAP = 25.0

_HONORIFICS = re.compile(r"\b(mr|mrs|ms|smt|shri|sri|dr|kum|m/s)\.?\b", re.IGNORECASE)


# ── helpers ───────────────────────────────────────────────────────────────────────

def _ok_docs(ingested: list[dict]) -> list[dict]:
    return [d for d in ingested if d.get("ok")]


def _by_type(ingested: list[dict]) -> dict[str, list[dict]]:
    """Group OK docs by their fine doc_type (the slot hint)."""
    out: dict[str, list[dict]] = {}
    for d in _ok_docs(ingested):
        out.setdefault(d.get("doc_type") or "other", []).append(d)
    return out


def _norm_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = _HONORIFICS.sub("", str(name))
    n = re.sub(r"[^A-Za-z ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().upper()
    return n or None


def _finding(severity: Severity, title: str, description: str, values: dict | None = None,
             confidence: float = 0.9) -> EvidenceItem:
    """A verification finding — SEMANTIC category (cross-document consistency)."""
    return EvidenceItem(
        category=EvidenceCategory.SEMANTIC,
        severity=severity,
        title=title,
        description=description,
        source_location="KYC / underwriting verification",
        values=values or {},
        confidence=confidence,
    )


# ── 1. completeness ─────────────────────────────────────────────────────────────

def check_completeness(purpose: str, ingested: list[dict]) -> tuple[dict, list[EvidenceItem]]:
    """Which required documents for `purpose` are present vs missing."""
    prof = profiles.profile_for(purpose)
    if not prof:
        return ({"applicable": False, "complete": True, "present": [], "missing": []}, [])

    present_types = set(_by_type(ingested).keys())
    required = prof["required"]
    present = [s for s in required if s in present_types]
    missing = [s for s in required if s not in present_types]
    optional_present = [s for s in prof["optional"] if s in present_types]

    findings: list[EvidenceItem] = []
    for slot in missing:
        label = profiles.SLOTS.get(slot, {}).get("label", slot)
        findings.append(_finding(
            Severity.LOW,
            f"Required document missing: {label}",
            f"The {prof['label']} checklist requires a {label}, which was not uploaded. "
            f"The case is scored on what is present and flagged as incomplete.",
            values={"slot": slot, "purpose": purpose},
        ))

    result = {
        "applicable": True,
        "purpose": purpose,
        "complete": not missing,
        "present": present,
        "missing": missing,
        "optional_present": optional_present,
        "required": required,
    }
    return result, findings


# ── 2. KYC: identity + address established, name consistency ───────────────────────

def verify_kyc(ingested: list[dict]) -> tuple[dict, list[EvidenceItem]]:
    by_type = _by_type(ingested)
    findings: list[EvidenceItem] = []

    # identity established = a POI doc whose identifier validates.
    identity_doc = None
    for slot in ("pan", "aadhaar"):
        for d in by_type.get(slot, []):
            kyc = d.get("kyc", {})
            ident_ok = (kyc.get("pan", {}).get("valid") if slot == "pan"
                        else kyc.get("aadhaar", {}).get("valid"))
            if ident_ok:
                identity_doc = slot
                break
        if identity_doc:
            break
    identity_established = identity_doc is not None

    # address established = an Aadhaar or an address-proof document is present.
    address_doc = next((s for s in ("aadhaar", "address_proof") if by_type.get(s)), None)
    address_established = address_doc is not None

    # name consistency across all docs that carry a name.
    names: dict[str, str] = {}
    for d in _ok_docs(ingested):
        nm = _norm_name((d.get("fields") or {}).get("name"))
        if nm:
            names[d.get("doc_type", "doc")] = nm
    distinct = sorted(set(names.values()))
    name_consistent = len(distinct) <= 1

    if not identity_established:
        findings.append(_finding(
            Severity.MEDIUM, "Identity not established",
            "No valid proof of identity (PAN/Aadhaar) was found, so the applicant's identity "
            "could not be established for KYC.",
            values={"checked": list(set(by_type) & profiles.POI_SLOTS)},
        ))
    if not address_established:
        findings.append(_finding(
            Severity.LOW, "Address not established",
            "No proof of address (Aadhaar / utility bill / passport / voter ID) was found.",
        ))
    if not name_consistent:
        findings.append(_finding(
            Severity.MEDIUM, "Name mismatch across documents",
            "The applicant's name differs across the submitted documents — this must be "
            "resolved before KYC can pass (possible mixed or substituted documents).",
            values={"names": names},
        ))

    established = identity_established and address_established and name_consistent
    result = {
        "identity_established": identity_established,
        "address_established": address_established,
        "name_consistent": name_consistent,
        "names": names,
        "verdict": "ESTABLISHED" if established else "INCOMPLETE",
    }
    return result, findings


# ── 3. income reconciliation ───────────────────────────────────────────────────────

def _first(by_type: dict[str, list[dict]], slot: str) -> dict:
    docs = by_type.get(slot)
    return (docs[0].get("fields") or {}) if docs else {}


def reconcile_income(ingested: list[dict]) -> tuple[dict, list[EvidenceItem]]:
    by_type = _by_type(ingested)
    form16 = _first(by_type, "form16")
    bank = _first(by_type, "bank_statement")
    slip = _first(by_type, "salary_slip")

    form16_gross = form16.get("gross_income")
    bank_annual = bank.get("implied_annual")
    slip_annual = (slip.get("net_monthly") * 12.0) if slip.get("net_monthly") else None

    checks: list[dict] = []
    findings: list[EvidenceItem] = []

    # (a) salary slip net*12 vs bank implied annual — both net take-home, expect ≈ equal.
    if slip_annual and bank_annual:
        diff = abs(slip_annual - bank_annual) / max(slip_annual, bank_annual)
        ok = diff <= RECON_TOL
        checks.append({"name": "salary_slip_vs_bank", "ok": ok,
                       "slip_annual": round(slip_annual), "bank_annual": round(bank_annual),
                       "diff_pct": round(diff * 100, 1)})
        if not ok:
            findings.append(_finding(
                Severity.MEDIUM, "Salary slip vs bank credits mismatch",
                f"Annualised salary-slip pay (₹{round(slip_annual):,}) and banked salary credits "
                f"(₹{round(bank_annual):,}) differ by {round(diff*100)}% (> {int(RECON_TOL*100)}% "
                f"tolerance). Possible inflated or forged payslip.",
                values={"slip_annual": round(slip_annual), "bank_annual": round(bank_annual)},
            ))

    # (b) form16 gross vs banked net — net should sit in [55%, 105%] of gross.
    if form16_gross and bank_annual:
        ratio = bank_annual / form16_gross
        ok = NET_TO_GROSS_MIN <= ratio <= NET_TO_GROSS_MAX
        checks.append({"name": "bank_vs_form16_gross", "ok": ok,
                       "form16_gross": round(form16_gross), "bank_annual": round(bank_annual),
                       "ratio": round(ratio, 2)})
        if ratio > NET_TO_GROSS_MAX:
            findings.append(_finding(
                Severity.MEDIUM, "Banked salary exceeds declared gross",
                f"Banked salary (₹{round(bank_annual):,}) is higher than the gross income declared "
                f"on Form 16 (₹{round(form16_gross):,}). Net pay cannot exceed gross — the Form 16 "
                f"or the statement may be inconsistent.",
                values={"form16_gross": round(form16_gross), "bank_annual": round(bank_annual)},
            ))
        elif ratio < NET_TO_GROSS_MIN:
            findings.append(_finding(
                Severity.LOW, "Declared gross far above banked salary",
                f"Form 16 declares gross income of ₹{round(form16_gross):,} but only "
                f"₹{round(bank_annual):,} is credited to the bank — the declared income may be "
                f"overstated. Worth a manual look.",
                values={"form16_gross": round(form16_gross), "bank_annual": round(bank_annual)},
            ))

    have_any = any(v is not None for v in (form16_gross, bank_annual, slip_annual))
    reconciled = have_any and all(c["ok"] for c in checks)
    result = {
        "applicable": have_any,
        "sources": {"form16_gross": form16_gross, "bank_annual": bank_annual,
                    "salary_slip_annual": slip_annual},
        "checks": checks,
        "reconciled": reconciled,
    }
    return result, findings


# ── 4. affordability / eligibility (does NOT touch the trust score) ─────────────────

def _emi(principal: float, annual_rate: float, n_months: int) -> float:
    """Standard reducing-balance EMI."""
    r = annual_rate / 12.0
    if r <= 0:
        return principal / n_months
    f = (1 + r) ** n_months
    return principal * r * f / (f - 1)


def _max_principal(affordable_emi: float, annual_rate: float, n_months: int) -> float:
    """Invert the EMI formula: the largest principal whose EMI ≤ affordable_emi."""
    if affordable_emi <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r <= 0:
        return affordable_emi * n_months
    f = (1 + r) ** n_months
    return affordable_emi * (f - 1) / (r * f)


def _net_monthly(ingested: list[dict]) -> Optional[float]:
    """Best available net monthly income: salary slip → bank credit → Form16 gross×0.7/12."""
    by_type = _by_type(ingested)
    slip = _first(by_type, "salary_slip")
    if slip.get("net_monthly"):
        return float(slip["net_monthly"])
    bank = _first(by_type, "bank_statement")
    if bank.get("monthly_credit"):
        return float(bank["monthly_credit"])
    form16 = _first(by_type, "form16")
    if form16.get("gross_income"):
        return float(form16["gross_income"]) * 0.7 / 12.0
    return None


def assess_affordability(
    ingested: list[dict],
    requested_amount: Optional[float],
    tenure_months: Optional[int],
    existing_emi: Optional[float] = None,
) -> dict:
    net_monthly = _net_monthly(ingested)
    tenure = int(tenure_months or DEFAULT_TENURE_MONTHS)
    existing = float(existing_emi or 0.0)

    if not net_monthly or net_monthly <= 0:
        return {"applicable": False, "reason": "no income document to size affordability",
                "net_monthly": net_monthly, "tenure_months": tenure}

    affordable_emi = max(0.0, FOIR_CAP * net_monthly - existing)
    max_eligible = round(_max_principal(affordable_emi, ANNUAL_RATE, tenure))

    # LTV only when a collateral valuation is present (secured tier — rarely now).
    by_type = _by_type(ingested)
    valuation = None
    for slot in ("property_valuation", "sale_deed"):
        v = _first(by_type, slot)
        valuation = valuation or v.get("valuation_amount") or v.get("consideration")
    ltv = round(requested_amount / valuation, 3) if (requested_amount and valuation) else None

    result = {
        "applicable": True,
        "net_monthly": round(net_monthly),
        "tenure_months": tenure,
        "existing_emi": round(existing),
        "assumed_rate": ANNUAL_RATE,
        "max_eligible_amount": max_eligible,
        "foir_cap": FOIR_CAP,
        "collateral_value": round(valuation) if valuation else None,
        "ltv": ltv,
        "ltv_cap": LTV_CAP,
    }

    if requested_amount:
        proposed_emi = _emi(float(requested_amount), ANNUAL_RATE, tenure)
        foir = (existing + proposed_emi) / net_monthly
        result.update({
            "requested_amount": round(float(requested_amount)),
            "proposed_emi": round(proposed_emi),
            "foir": round(foir, 3),
        })
        ltv_fail = ltv is not None and ltv > LTV_CAP
        if foir <= FOIR_CAP and not ltv_fail:
            verdict = "ELIGIBLE"
        elif foir <= FOIR_REFER_CAP and not ltv_fail:
            verdict = "REFER"
        else:
            verdict = "DECLINE"
        result["verdict"] = verdict
        reasons = []
        if foir > FOIR_CAP:
            reasons.append(f"FOIR {round(foir*100)}% exceeds the {int(FOIR_CAP*100)}% norm")
        if ltv_fail:
            reasons.append(f"LTV {round(ltv*100)}% exceeds the {int(LTV_CAP*100)}% cap")
        if not reasons:
            reasons.append(f"FOIR {round(foir*100)}% within norm; affordable at the requested amount")
        result["reason"] = "; ".join(reasons)
    else:
        result["verdict"] = "INFO"
        result["reason"] = (f"No amount requested. Indicative max eligible ≈ "
                            f"₹{max_eligible:,} over {tenure} months.")
    return result


# ── orchestration ───────────────────────────────────────────────────────────────

def build_verification(
    purpose: str,
    ingested: list[dict],
    loan_amount: Optional[float] = None,
    tenure_months: Optional[int] = None,
    existing_emi: Optional[float] = None,
) -> dict:
    """Run all verification layers → one block + the (capped) authenticity penalty for the score.

    `findings` (completeness + KYC + income) are authenticity-axis EvidenceItems folded into the
    trust score by the caller. `eligibility` is the business-rule outcome and is NOT in `findings`.
    """
    completeness, c_find = check_completeness(purpose, ingested)
    kyc, k_find = verify_kyc(ingested)
    income, i_find = reconcile_income(ingested)

    prof = profiles.profile_for(purpose)
    eligibility = None
    if prof and prof.get("needs_loan_terms"):
        eligibility = assess_affordability(ingested, loan_amount, tenure_months, existing_emi)

    findings = [*c_find, *k_find, *i_find]

    from services.risk.app.aggregator import SEVERITY_PENALTY
    penalty = min(VERIFICATION_PENALTY_CAP,
                  sum(SEVERITY_PENALTY.get(f.severity, 0.0) for f in findings))

    return {
        "purpose": purpose,
        "completeness": completeness,
        "kyc": kyc,
        "income": income,
        "eligibility": eligibility,
        "findings": findings,           # list[EvidenceItem] — folded into trust by the caller
        "trust_penalty": round(penalty, 1),
    }
