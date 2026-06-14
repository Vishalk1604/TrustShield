"""Semantic cross-document rules engine — Phase 2.

Takes the extracted entities from all documents in a packet and applies cross-document
consistency rules to produce EvidenceItems (category=semantic).

Financial rules:
  - Income declared on Form 16 vs implied by bank credits (annualized).
  - Income declared on Form 16 vs implied by salary slip (annualized).
  - Name/PAN consistency across all documents.

Property/legal rules (secured loans):
  - Owner name on sale deed must match the applicant.
  - Property ID must be consistent across sale deed, EC, valuation, legal opinion.
  - Loan-to-Value (LTV) sanity: flag if loan > 90% of valuation.
  - EC vs CERSAI charge cross-check: EC claims NIL but CERSAI records active charges.

Local-only: CERSAI is accessed via the local mock adapter (no network).
"""

from __future__ import annotations

from typing import Any, Optional

from shared.schemas import EvidenceCategory, EvidenceItem, Severity

# Tolerance for income comparison (20% deviation before flagging).
_INCOME_TOLERANCE = 0.20

# LTV threshold above which we flag as potentially excessive.
_LTV_FLAG_THRESHOLD = 0.90


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _pct_diff(a: float, b: float) -> float:
    """Absolute percentage difference relative to the larger value."""
    if max(abs(a), abs(b)) < 1:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


def _money_str(amount: Optional[float]) -> str:
    if amount is None:
        return "unknown"
    return f"Rs. {int(amount):,}"


def _ev(
    title: str,
    description: str,
    severity: Severity,
    values: dict,
    source: Optional[str] = None,
    confidence: float = 0.90,
) -> EvidenceItem:
    return EvidenceItem(
        category=EvidenceCategory.SEMANTIC,
        severity=severity,
        title=title,
        description=description,
        source_location=source,
        values=values,
        confidence=confidence,
    )


# --------------------------------------------------------------------------
# Financial rules
# --------------------------------------------------------------------------

def check_income_vs_bank(
    form16: dict,
    bank: dict,
    *,
    tolerance: float = _INCOME_TOLERANCE,
) -> list[EvidenceItem]:
    """Form 16 declared income vs annualized bank salary credits."""
    items: list[EvidenceItem] = []
    f16_income = form16.get("gross_income")
    implied_annual = bank.get("implied_annual")
    if f16_income is None or implied_annual is None:
        return items

    diff = _pct_diff(f16_income, implied_annual)
    if diff > tolerance:
        ratio = implied_annual / f16_income if f16_income else 0
        sev = Severity.HIGH if diff > 0.40 else Severity.MEDIUM
        items.append(_ev(
            title="Income declared on Form 16 inconsistent with bank credits",
            description=(
                f"Form 16 declares {_money_str(f16_income)} annual gross income, "
                f"but bank salary credits annualise to only {_money_str(implied_annual)} "
                f"({ratio:.0%} of declared). A {diff:.0%} discrepancy exceeds the {tolerance:.0%} "
                "tolerance and suggests the Form 16 income may be inflated."
            ),
            severity=sev,
            values={
                "form16_income": f16_income,
                "bank_implied_annual": implied_annual,
                "deviation_pct": round(diff * 100, 1),
            },
            source="form16.pdf vs bank_statement.pdf",
        ))
    return items


def check_income_vs_salary_slip(
    form16: dict,
    salary: dict,
    *,
    tolerance: float = _INCOME_TOLERANCE,
) -> list[EvidenceItem]:
    """Form 16 declared income vs annualized salary slip net pay."""
    items: list[EvidenceItem] = []
    f16_income = form16.get("gross_income")
    net_monthly = salary.get("net_monthly")
    if f16_income is None or net_monthly is None:
        return items

    slip_annual = net_monthly * 12
    diff = _pct_diff(f16_income, slip_annual)
    if diff > tolerance:
        ratio = slip_annual / f16_income if f16_income else 0
        sev = Severity.HIGH if diff > 0.40 else Severity.MEDIUM
        items.append(_ev(
            title="Income declared on Form 16 inconsistent with salary slip",
            description=(
                f"Form 16 declares {_money_str(f16_income)} annual gross income, "
                f"but the salary slip's net monthly pay of {_money_str(net_monthly)} "
                f"annualises to {_money_str(slip_annual)} ({ratio:.0%} of declared). "
                f"A {diff:.0%} deviation exceeds the {tolerance:.0%} tolerance."
            ),
            severity=sev,
            values={
                "form16_income": f16_income,
                "slip_net_monthly": net_monthly,
                "slip_implied_annual": slip_annual,
                "deviation_pct": round(diff * 100, 1),
            },
            source="form16.pdf vs salary_slip.pdf",
        ))
    return items


def check_name_pan_consistency(entities_by_type: dict[str, dict]) -> list[EvidenceItem]:
    """Name and PAN must be consistent across all documents that carry them."""
    items: list[EvidenceItem] = []
    # Collect (name, pan) by doc_type
    names: dict[str, str] = {}
    pans: dict[str, str] = {}
    for doc_type, ent in entities_by_type.items():
        n = ent.get("name")
        p = ent.get("pan")
        if n:
            names[doc_type] = n.strip()
        if p:
            pans[doc_type] = p.strip()

    # Check name consistency — compare all to the first seen
    if len(names) > 1:
        ref_type, ref_name = next(iter(names.items()))
        for dt, nm in names.items():
            if dt == ref_type:
                continue
            if nm.lower() != ref_name.lower():
                items.append(_ev(
                    title="Applicant name inconsistency across documents",
                    description=(
                        f"'{ref_type}' records name as '{ref_name}' but '{dt}' records "
                        f"'{nm}'. All documents in a loan packet must identify the same applicant."
                    ),
                    severity=Severity.HIGH,
                    values={"reference_doc": ref_type, "reference_name": ref_name,
                            "conflicting_doc": dt, "conflicting_name": nm},
                    source=f"{ref_type} vs {dt}",
                ))

    # Check PAN consistency
    if len(pans) > 1:
        ref_type, ref_pan = next(iter(pans.items()))
        for dt, pan in pans.items():
            if dt == ref_type:
                continue
            if pan != ref_pan:
                items.append(_ev(
                    title="PAN inconsistency across documents",
                    description=(
                        f"'{ref_type}' records PAN as '{ref_pan}' but '{dt}' records '{pan}'. "
                        "PAN must be identical across all loan-packet documents."
                    ),
                    severity=Severity.CRITICAL,
                    values={"reference_doc": ref_type, "reference_pan": ref_pan,
                            "conflicting_doc": dt, "conflicting_pan": pan},
                    source=f"{ref_type} vs {dt}",
                    confidence=0.97,
                ))
    return items


# --------------------------------------------------------------------------
# Property / legal rules
# --------------------------------------------------------------------------

def check_owner_vs_applicant(sale_deed: dict, identity: dict) -> list[EvidenceItem]:
    """Sale deed owner must match the applicant (from identity / Form 16)."""
    items: list[EvidenceItem] = []
    owner = sale_deed.get("owner_name", "")
    applicant = identity.get("name", "")
    if not owner or not applicant:
        return items
    if owner.lower().strip() != applicant.lower().strip():
        items.append(_ev(
            title="Sale deed owner does not match applicant",
            description=(
                f"The sale deed names '{owner}' as the property owner, but the applicant "
                f"is '{applicant}'. For a secured loan the applicant must be the property owner."
            ),
            severity=Severity.CRITICAL,
            values={"deed_owner": owner, "applicant": applicant},
            source="sale_deed.pdf vs identity.pdf",
            confidence=0.88,
        ))
    return items


def check_property_id_consistency(entities_by_type: dict[str, dict]) -> list[EvidenceItem]:
    """Property ID must be identical across sale deed, EC, valuation, and legal opinion."""
    items: list[EvidenceItem] = []
    prop_types = ["sale_deed", "encumbrance_certificate", "property_valuation", "legal_opinion"]
    property_ids: dict[str, str] = {}
    for dt in prop_types:
        ent = entities_by_type.get(dt, {})
        pid = ent.get("property_id")
        if pid:
            property_ids[dt] = pid.strip()

    if len(property_ids) < 2:
        return items

    # Compare all against the first found
    ref_type, ref_id = next(iter(property_ids.items()))
    for dt, pid in property_ids.items():
        if dt == ref_type:
            continue
        if pid != ref_id:
            items.append(_ev(
                title="Property ID inconsistency across collateral documents",
                description=(
                    f"'{ref_type}' describes property '{ref_id}' but '{dt}' describes "
                    f"'{pid}'. All collateral documents must reference the same property."
                ),
                severity=Severity.HIGH,
                values={"reference_doc": ref_type, "reference_property_id": ref_id,
                        "conflicting_doc": dt, "conflicting_property_id": pid},
                source=f"{ref_type} vs {dt}",
            ))
    return items


def check_ltv(
    valuation: dict,
    loan_amount: Optional[float],
    *,
    threshold: float = _LTV_FLAG_THRESHOLD,
) -> list[EvidenceItem]:
    """Loan-to-value ratio sanity check. Flag if loan exceeds threshold × valuation."""
    items: list[EvidenceItem] = []
    val_amount = valuation.get("valuation_amount")
    if val_amount is None or loan_amount is None:
        return items

    ltv = loan_amount / val_amount
    if ltv > threshold:
        sev = Severity.CRITICAL if ltv > 1.0 else Severity.HIGH
        items.append(_ev(
            title="Abnormal loan-to-value ratio",
            description=(
                f"The requested loan of {_money_str(loan_amount)} against a property "
                f"valued at {_money_str(val_amount)} gives an LTV of {ltv:.0%}, "
                f"which exceeds the {threshold:.0%} threshold. "
                + ("The loan exceeds the property's assessed value." if ltv > 1.0 else
                   "This indicates either an inflated valuation or an excessive loan request.")
            ),
            severity=sev,
            values={"loan_amount": loan_amount, "valuation_amount": val_amount,
                    "ltv": round(ltv, 3), "threshold": threshold},
            source="property_valuation.pdf",
        ))
    return items


def check_valuation_vs_registry(
    valuation: dict,
    loan_amount: Optional[float],
    *,
    inflation_threshold: float = 0.20,
) -> list[EvidenceItem]:
    """Cross-check the claimed valuation against the state property registry.

    Flags when the appraiser's figure is materially higher than the registry market value
    (possible valuation inflation to justify an oversized loan).

    Uses the local property-registry mock adapter (no network).
    """
    items: list[EvidenceItem] = []
    claimed_val = valuation.get("valuation_amount")
    property_id = valuation.get("property_id")
    if not claimed_val or not property_id:
        return items

    from shared.mocks import PropertyRegistryAdapter

    registry = PropertyRegistryAdapter()
    market_value = registry.registered_market_value(property_id)
    if market_value is None:
        return items  # property not in registry — can't cross-check

    if claimed_val > market_value * (1 + inflation_threshold):
        inflation_pct = (claimed_val - market_value) / market_value
        sev = Severity.CRITICAL if inflation_pct > 0.40 else Severity.HIGH
        items.append(_ev(
            title="Property valuation inflated above registry market value",
            description=(
                f"The appraiser's valuation of {_money_str(claimed_val)} for property "
                f"{property_id} exceeds the state property registry's market value of "
                f"{_money_str(market_value)} by {inflation_pct:.0%} — above the "
                f"{inflation_threshold:.0%} tolerance. Possible valuation inflation to "
                "justify a larger loan."
            ),
            severity=sev,
            values={
                "property_id": property_id,
                "claimed_valuation": claimed_val,
                "registry_market_value": market_value,
                "inflation_pct": round(inflation_pct * 100, 1),
            },
            source="property_valuation.pdf vs property_registry",
        ))

    # Also check LTV against the registry market value (may be > 100% even if LTV vs claimed is OK)
    if loan_amount and loan_amount > market_value:
        ltv_market = loan_amount / market_value
        items.append(_ev(
            title="Loan exceeds registered market value (LTV vs registry > 100%)",
            description=(
                f"The requested loan of {_money_str(loan_amount)} for property {property_id} "
                f"exceeds the registry's registered market value of {_money_str(market_value)}, "
                f"giving an LTV of {ltv_market:.0%} against the true market value. "
                "This is only possible if the appraiser's figure is inflated."
            ),
            severity=Severity.CRITICAL,
            values={
                "property_id": property_id,
                "loan_amount": loan_amount,
                "registry_market_value": market_value,
                "ltv_vs_registry": round(ltv_market, 3),
            },
            source="property_valuation.pdf vs property_registry",
            confidence=0.92,
        ))

    return items


def check_ec_vs_cersai(
    ec: dict,
    applicant_pan: str,
    property_id: str,
) -> list[EvidenceItem]:
    """Cross-check the encumbrance certificate against the CERSAI registry.

    If CERSAI records active charges for the applicant's PAN on this property, but the
    EC claims NIL encumbrances, flag a critical semantic violation.

    Uses the local CERSAI mock adapter (no network).
    """
    items: list[EvidenceItem] = []
    if not applicant_pan or not property_id:
        return items

    from shared.mocks import CersaiAdapter

    cersai = CersaiAdapter()
    all_charges = cersai.existing_charges(applicant_pan)
    # Filter to charges for this specific property
    matching = [c for c in all_charges if c.get("property_id") == property_id]

    ec_says_nil = ec.get("claims_nil", False)

    if matching and ec_says_nil:
        charge_desc = "; ".join(
            f"{c.get('lender', 'unknown')} {_money_str(c.get('amount'))} "
            f"(registered {c.get('registered_on', 'unknown')})"
            for c in matching
        )
        items.append(_ev(
            title="Encumbrance certificate contradicts CERSAI registry",
            description=(
                f"The encumbrance certificate for property {property_id} claims no encumbrances, "
                f"but the CERSAI registry records {len(matching)} active charge(s) under "
                f"PAN {applicant_pan}: {charge_desc}. "
                "An undisclosed mortgage is a serious underwriting risk."
            ),
            severity=Severity.CRITICAL,
            values={
                "property_id": property_id,
                "applicant_pan": applicant_pan,
                "cersai_charges": matching,
                "ec_claims_nil": True,
            },
            source="encumbrance_certificate.pdf vs CERSAI registry",
            confidence=0.95,
        ))

    return items


# --------------------------------------------------------------------------
# Orchestration: run all rules on a packet
# --------------------------------------------------------------------------

def run_all_rules(
    entities_by_doc: dict[str, dict],
    loan_amount: Optional[float] = None,
    applicant_pan: Optional[str] = None,
) -> list[EvidenceItem]:
    """Run every configured rule and return all EvidenceItems.

    Args:
        entities_by_doc: {doc_type: extracted_entities_dict}
        loan_amount:    Loan requested (INR), from manifest or application form.
        applicant_pan:  Applicant's PAN, for CERSAI lookup.
    """
    items: list[EvidenceItem] = []

    form16 = entities_by_doc.get("form16", {})
    bank = entities_by_doc.get("bank_statement", {})
    salary = entities_by_doc.get("salary_slip", {})
    identity = entities_by_doc.get("identity", {})
    sale_deed = entities_by_doc.get("sale_deed", {})
    ec = entities_by_doc.get("encumbrance_certificate", {})
    valuation = entities_by_doc.get("property_valuation", {})

    # --- Financial rules ---
    if form16 and bank:
        items.extend(check_income_vs_bank(form16, bank))
    if form16 and salary:
        items.extend(check_income_vs_salary_slip(form16, salary))
    items.extend(check_name_pan_consistency(entities_by_doc))

    # --- Property/legal rules ---
    if sale_deed and identity:
        items.extend(check_owner_vs_applicant(sale_deed, identity))
    items.extend(check_property_id_consistency(entities_by_doc))
    if valuation:
        items.extend(check_ltv(valuation, loan_amount))
        items.extend(check_valuation_vs_registry(valuation, loan_amount))
    if ec and applicant_pan:
        prop_id = (
            sale_deed.get("property_id")
            or ec.get("property_id")
            or valuation.get("property_id")
        )
        if prop_id:
            items.extend(check_ec_vs_cersai(ec, applicant_pan, prop_id))

    return items
