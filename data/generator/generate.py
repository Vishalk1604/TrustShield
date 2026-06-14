"""Deterministic synthetic loan-packet generator for TrustShield.

Produces ~24 application packets into ``data/synthetic/packets/<PKT-id>/`` covering clean cases
and every fraud type, plus a ground-truth ``data/synthetic/labels.json``. Run from the repo root:

    python -m data.generator.generate

Deterministic (fixed seed + fixed dates) so a regenerated set matches the committed one. Every
packet folder gets a ``manifest.json`` (an ``ApplicationPacket``-shaped record + a ``ground_truth``
block with the claimed financials). No network, no real PII — all data is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import fitz  # PyMuPDF

from data.generator import pdf_builder as pb
from data.generator import tamper as tp

SEED = 20260613
random.seed(SEED)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "synthetic"
PACKETS_DIR = OUT_DIR / "packets"
LABELS_PATH = OUT_DIR / "labels.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
BASE_DATE = datetime(2024, 3, 1, 9, 0, 0)


# --------------------------------------------------------------------------------------
# Canonical synthetic roster — PANs/names/employers match shared/mocks/fixtures/*.json.
# (Keep in sync with the fixtures so later-phase cross-checks line up.)
# --------------------------------------------------------------------------------------
@dataclass
class Applicant:
    name: str
    pan: str
    employer: str
    account: str
    income: float          # declared annual gross (INR); equals AIS reported income for clean cases
    dob: str


ROSTER: list[Applicant] = [
    Applicant("Rahul Sharma", "ABMPS1234F", "Infosys Limited", "1234509876", 1820000, "1989-04-12"),
    Applicant("Priya Verma", "CDNPV5678L", "Tata Consultancy Services", "2233445566", 1450000, "1991-09-03"),
    Applicant("Amit Patel", "EFKPP9012Q", "Wipro Limited", "3344556677", 980000, "1990-01-22"),
    Applicant("Sneha Reddy", "GHJPR3456M", "HDFC Bank", "4455667788", 2100000, "1987-12-30"),
    Applicant("Vikram Singh", "KLMPS7777N", "Singh Traders", "5566778899", 1250000, "1985-06-15"),
    Applicant("Anjali Nair", "NOPPN2345T", "Tech Mahindra", "6677889900", 1100000, "1992-03-08"),
    Applicant("Karan Mehta", "QRSPM6789W", "Mehta Exports", "7788990011", 1600000, "1986-11-19"),
    Applicant("Deepak Joshi", "TUVPJ0123H", "Accenture", "8899001122", 1350000, "1988-07-25"),
]


def _tax(income: float) -> float:
    return round(income * (0.18 if income > 1500000 else 0.10))


def _monthly_credit(income: float) -> float:
    return round((income - _tax(income)) / 12)


# --------------------------------------------------------------------------------------
# Packet realization
# --------------------------------------------------------------------------------------
@dataclass
class DocSpec:
    filename: str
    doc_type: str
    doc: "fitz.Document"
    claimed: dict[str, Any] = field(default_factory=dict)
    post_save: Optional[Callable[[str], None]] = None  # e.g. incremental tamper applied to the file


@dataclass
class PacketSpec:
    packet_id: str
    applicant_name: str
    applicant_pan: str
    employer: str
    docs: list[DocSpec]
    created_at: datetime
    submitted_at: datetime
    label: str                      # "clean" | "fraud"
    fraud_types: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    affected_docs: list[str] = field(default_factory=list)
    template_group: Optional[str] = None
    property_group: Optional[str] = None     # shared property/collateral cluster (double-financing)
    ground_truth: dict[str, Any] = field(default_factory=dict)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def realize_packet(spec: PacketSpec) -> dict[str, Any]:
    """Save a packet's PDFs + manifest.json; return its labels.json entry."""
    pkt_dir = PACKETS_DIR / spec.packet_id
    if pkt_dir.exists():
        shutil.rmtree(pkt_dir)
    pkt_dir.mkdir(parents=True, exist_ok=True)

    doc_records: list[dict[str, Any]] = []
    claims: dict[str, Any] = {}
    for ds in spec.docs:
        path = pkt_dir / ds.filename
        ds.doc.save(str(path))
        ds.doc.close()
        if ds.post_save is not None:
            ds.post_save(str(path))  # e.g. incremental-update tamper rewrites the file
        raw = path.read_bytes()
        with fitz.open(stream=raw, filetype="pdf") as reread:
            page_count = reread.page_count
        doc_records.append(
            {
                "id": ds.filename.rsplit(".", 1)[0],
                "filename": ds.filename,
                "doc_type": ds.doc_type,
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "mime_type": "application/pdf",
                "page_count": page_count,
                "sha256": _sha256(raw),
            }
        )
        if ds.claimed:
            claims[ds.filename] = ds.claimed

    manifest = {
        "id": spec.packet_id,
        "applicant_name": spec.applicant_name,
        "documents": doc_records,
        "extracted": None,
        "created_at": _iso(spec.created_at),
        "submitted_at": _iso(spec.submitted_at),
        "source": "synthetic_generator",
        "ground_truth": {
            "applicant_pan": spec.applicant_pan,
            "employer": spec.employer,
            "claims": claims,
            **spec.ground_truth,
        },
    }
    (pkt_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "label": spec.label,
        "fraud_types": spec.fraud_types,
        "reasons": spec.reasons,
        "affected_docs": spec.affected_docs,
        "applicant_pan": spec.applicant_pan,
        "employer": spec.employer,
        "template_group": spec.template_group,
        "property_group": spec.property_group,
        "property_id": spec.ground_truth.get("property_id"),
    }


# --------------------------------------------------------------------------------------
# Document factory helpers (clean documents for an applicant)
# --------------------------------------------------------------------------------------
def _clean_docs(app: Applicant, created: datetime) -> list[DocSpec]:
    tax = _tax(app.income)
    monthly = _monthly_credit(app.income)
    meta = lambda title_dt: pb.DocMeta(creation_date=title_dt, mod_date=title_dt)
    return [
        DocSpec("identity.pdf", "identity",
                pb.build_identity(app.name, app.pan, app.dob, meta(created)),
                {"pan": app.pan, "name": app.name}),
        DocSpec("form16.pdf", "form16",
                pb.build_form16(app.name, app.pan, app.employer, app.income, tax, "2023-24", meta(created + timedelta(days=2))),
                {"gross_income": app.income, "tax_paid": tax}),
        DocSpec("salary_slip.pdf", "salary_slip",
                pb.build_salary_slip(app.name, app.employer, "Jun 2024", monthly, meta(created + timedelta(days=4))),
                {"net_monthly": monthly}),
        DocSpec("bank_statement.pdf", "bank_statement",
                pb.build_bank_statement(app.name, app.account, monthly, MONTHS, meta(created + timedelta(days=5))),
                {"monthly_credit": monthly, "implied_annual": monthly * 12}),
    ]


# --------------------------------------------------------------------------------------
# Category builders — each returns a list[PacketSpec]
# --------------------------------------------------------------------------------------
def build_clean() -> list[PacketSpec]:
    specs = []
    for i, app in enumerate(ROSTER):
        created = BASE_DATE + timedelta(days=i * 3)
        submitted = created + timedelta(days=7)
        specs.append(PacketSpec(
            packet_id="",  # assigned sequentially in main()
            applicant_name=app.name, applicant_pan=app.pan, employer=app.employer,
            docs=_clean_docs(app, created), created_at=created, submitted_at=submitted,
            label="clean",
            ground_truth={"declared_income": app.income, "ais_reported_income": app.income},
        ))
    return specs


def build_forensic() -> list[PacketSpec]:
    """Five packets, one forensic tamper technique each (clean financials underneath)."""
    specs: list[PacketSpec] = []

    # 1) Suspicious metadata on the bank statement.
    app = ROSTER[0]
    created = datetime(2024, 6, 1, 10, 0, 0)
    docs = _clean_docs(app, created)
    bank = docs[-1]
    bad_producer = tp.pick_producer(0)
    bank.doc.set_metadata({})  # clear, then apply suspicious metadata
    tp.make_metadata_suspicious(
        bank.doc, producer=bad_producer,
        creation_date=created, mod_date=created + timedelta(days=41),
    )
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=42),
        label="fraud", fraud_types=["suspicious_metadata"],
        reasons=[f"Bank statement producer is '{bad_producer}' and it was modified 41 days after creation."],
        affected_docs=["bank_statement.pdf"],
        ground_truth={"declared_income": app.income},
    ))

    # 2) White-box edited income figure on Form 16 (income inflated).
    app = ROSTER[1]
    created = datetime(2024, 6, 5, 10, 0, 0)
    docs = _clean_docs(app, created)
    form16 = docs[1]
    inflated = app.income * 1.9
    tp.edit_money_figure(form16.doc, app.income, inflated)  # default body font; covers original
    form16.claimed["edited_to"] = inflated
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["edited_income_figure"],
        reasons=[f"Form 16 gross income was white-boxed and redrawn from {int(app.income)} to {int(inflated)}; original value remains in the text layer."],
        affected_docs=["form16.pdf"],
        ground_truth={"declared_income": app.income, "displayed_income": inflated},
    ))

    # 3) Font inconsistency: edited income drawn in a serif font unlike the body.
    app = ROSTER[2]
    created = datetime(2024, 6, 9, 10, 0, 0)
    docs = _clean_docs(app, created)
    form16 = docs[1]
    inflated = app.income * 2.1
    tp.edit_money_figure(form16.doc, app.income, inflated, font=pb.FONT_ALT)
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["font_inconsistency", "edited_income_figure"],
        reasons=[f"Form 16 income figure is rendered in a serif font ({pb.FONT_ALT}) inconsistent with the sans-serif body."],
        affected_docs=["form16.pdf"],
        ground_truth={"declared_income": app.income, "displayed_income": inflated},
    ))

    # 4) Copy-paste: duplicated salary-credit row + duplicated seal image on the bank statement.
    app = ROSTER[3]
    created = datetime(2024, 6, 13, 10, 0, 0)
    docs = _clean_docs(app, created)
    monthly = _monthly_credit(app.income)
    dup_bank = pb.build_bank_statement(
        app.name, app.account, monthly, MONTHS,
        pb.DocMeta(creation_date=created + timedelta(days=5), mod_date=created + timedelta(days=5)),
        duplicate_row=True,
    )
    tp.duplicate_seal(dup_bank, pb.make_seal_png())
    docs[-1] = DocSpec("bank_statement.pdf", "bank_statement", dup_bank,
                       {"monthly_credit": monthly, "duplicated": True})
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["copy_paste"],
        reasons=["Bank statement contains a verbatim-duplicated salary-credit row and an identical seal image pasted twice."],
        affected_docs=["bank_statement.pdf"],
        ground_truth={"declared_income": app.income},
    ))

    # 5) Incremental-update revision on Form 16 (extra xref / %%EOF after the fact).
    app = ROSTER[7]
    created = datetime(2024, 6, 18, 10, 0, 0)
    docs = _clean_docs(app, created)
    docs[1].post_save = lambda path: tp.incremental_overlay(path, note="re-verified 2024-08-01")
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["incremental_update"],
        reasons=["Form 16 was saved with an incremental update after creation, leaving a second cross-reference section (post-hoc revision)."],
        affected_docs=["form16.pdf"],
        ground_truth={"declared_income": app.income},
    ))
    return specs


def build_cross_doc() -> list[PacketSpec]:
    """Four packets where Form 16 income, bank credits, and salary slip disagree (no forensic tamper)."""
    specs: list[PacketSpec] = []
    cases = [
        (ROSTER[4], 1.0, 0.45, 0.5),   # bank credits imply ~45% of declared income
        (ROSTER[5], 1.0, 0.6, 1.4),    # salary slip far above bank credits
        (ROSTER[6], 1.0, 0.35, 0.4),   # severe under-banking of declared income
        (ROSTER[0], 1.0, 0.55, 0.7),   # moderate mismatch
    ]
    for k, (app, f16_mult, bank_mult, slip_mult) in enumerate(cases):
        created = datetime(2024, 7, 1, 10, 0, 0) + timedelta(days=k * 3)
        tax = _tax(app.income)
        declared = app.income * f16_mult
        monthly_bank = round((app.income * bank_mult) / 12)
        monthly_slip = round((app.income * slip_mult) / 12)
        meta = lambda d: pb.DocMeta(creation_date=created + timedelta(days=d), mod_date=created + timedelta(days=d))
        docs = [
            DocSpec("identity.pdf", "identity", pb.build_identity(app.name, app.pan, app.dob, meta(0)),
                    {"pan": app.pan}),
            DocSpec("form16.pdf", "form16",
                    pb.build_form16(app.name, app.pan, app.employer, declared, tax, "2023-24", meta(2)),
                    {"gross_income": declared}),
            DocSpec("salary_slip.pdf", "salary_slip",
                    pb.build_salary_slip(app.name, app.employer, "Jun 2024", monthly_slip, meta(4)),
                    {"net_monthly": monthly_slip, "implied_annual": monthly_slip * 12}),
            DocSpec("bank_statement.pdf", "bank_statement",
                    pb.build_bank_statement(app.name, app.account, monthly_bank, MONTHS, meta(5)),
                    {"monthly_credit": monthly_bank, "implied_annual": monthly_bank * 12}),
        ]
        specs.append(PacketSpec(
            "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=7),
            label="fraud", fraud_types=["cross_document_inconsistency"],
            reasons=[
                f"Form 16 declares {int(declared)} but bank credits imply ~{monthly_bank * 12} "
                f"and the salary slip implies ~{monthly_slip * 12} annually."
            ],
            affected_docs=["form16.pdf", "bank_statement.pdf", "salary_slip.pdf"],
            ground_truth={
                "declared_income": declared,
                "bank_implied_income": monthly_bank * 12,
                "slip_implied_income": monthly_slip * 12,
            },
        ))
    return specs


def build_template_reuse() -> list[PacketSpec]:
    """Four fabricated identities whose documents are built from ONE shared template with identical
    employer + identical fabricated figures — a fraud ring reusing a forged statement."""
    group = "ring_quickcash"
    employer = "QuickCash Finance Pvt Ltd"
    ring = [
        ("Mohit Kumar", "ZZAPK1111A", "9001112221"),
        ("Rohit Gupta", "ZZBPG2222B", "9002223332"),
        ("Sahil Khan", "ZZCPK3333C", "9003334443"),
        ("Nikhil Rao", "ZZDPR4444D", "9004445554"),
    ]
    fixed_income = 1500000
    tax = _tax(fixed_income)
    monthly = _monthly_credit(fixed_income)
    specs: list[PacketSpec] = []
    for k, (name, pan, acct) in enumerate(ring):
        # Same template, same calendar dates → structurally identical fingerprint across the ring.
        created = datetime(2024, 8, 5, 11, 0, 0)
        meta = lambda d: pb.DocMeta(producer="QuickDocs Generator", creation_date=created + timedelta(days=d),
                                    mod_date=created + timedelta(days=d))
        docs = [
            DocSpec("identity.pdf", "identity", pb.build_identity(name, pan, "1990-01-01", meta(0)), {"pan": pan}),
            DocSpec("form16.pdf", "form16",
                    pb.build_form16(name, pan, employer, fixed_income, tax, "2023-24", meta(0)),
                    {"gross_income": fixed_income}),
            DocSpec("salary_slip.pdf", "salary_slip",
                    pb.build_salary_slip(name, employer, "Jun 2024", monthly, meta(0)),
                    {"net_monthly": monthly}),
            DocSpec("bank_statement.pdf", "bank_statement",
                    pb.build_bank_statement(name, acct, monthly, MONTHS, meta(0)),
                    {"monthly_credit": monthly}),
        ]
        specs.append(PacketSpec(
            "", name, pan, employer, docs, created, created + timedelta(minutes=20),
            label="fraud", fraud_types=["template_reuse", "behavioral_velocity"],
            reasons=[
                f"Documents reuse a shared template and identical figures across applicants "
                f"(employer '{employer}'); submitted within 20 minutes of creation.",
            ],
            affected_docs=["form16.pdf", "bank_statement.pdf", "salary_slip.pdf", "identity.pdf"],
            template_group=group,
            ground_truth={"declared_income": fixed_income, "ais_reported_income": None},
        ))
    return specs


def build_behavioral() -> list[PacketSpec]:
    """Three packets with anomalous metadata timestamps / submission velocity (financials clean)."""
    specs: list[PacketSpec] = []

    # 1) All documents created within the same minute + submitted 2 minutes later (mass-produced).
    app = ROSTER[2]
    created = datetime(2024, 9, 1, 3, 14, 0)
    docs = _clean_docs(app, created)
    for d in docs:  # force identical creation timestamp on every doc
        tp.make_metadata_suspicious(d.doc, producer="TrustShield SynthGen 1.0",
                                    creation_date=created, mod_date=created, title=d.doc_type)
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(minutes=2),
        label="fraud", fraud_types=["behavioral_velocity", "timestamp_anomaly"],
        reasons=["All four documents share an identical creation timestamp (03:14) and the packet was submitted 2 minutes later."],
        affected_docs=["identity.pdf", "form16.pdf", "salary_slip.pdf", "bank_statement.pdf"],
        ground_truth={"declared_income": app.income},
    ))

    # 2) Future creation date (document created after submission / in the future).
    app = ROSTER[5]
    created = datetime(2027, 1, 15, 10, 0, 0)
    docs = _clean_docs(app, created)
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, datetime(2024, 9, 5, 10, 0, 0),
        label="fraud", fraud_types=["timestamp_anomaly"],
        reasons=["Document creation timestamps are dated 2027 — in the future relative to submission."],
        affected_docs=["form16.pdf", "bank_statement.pdf"],
        ground_truth={"declared_income": app.income},
    ))

    # 3) Modification date precedes creation date (impossible ordering).
    app = ROSTER[6]
    created = datetime(2024, 9, 10, 10, 0, 0)
    docs = _clean_docs(app, created)
    bank = docs[-1]
    tp.make_metadata_suspicious(
        bank.doc, producer="TrustShield SynthGen 1.0",
        creation_date=created, mod_date=created - timedelta(days=30),  # modified BEFORE created
    )
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=5),
        label="fraud", fraud_types=["timestamp_anomaly"],
        reasons=["Bank statement modification date precedes its creation date by 30 days (impossible ordering)."],
        affected_docs=["bank_statement.pdf"],
        ground_truth={"declared_income": app.income},
    ))
    return specs


# --------------------------------------------------------------------------------------
# Legal & land-record (secured-lending) packets — the collateral-fraud category
# --------------------------------------------------------------------------------------
# Properties: (property_id, address, market_value INR)
PROP_A = ("SY-217/3B", "12 Jayanagar 4th Block, Bengaluru 560011", 9_000_000)
PROP_B = ("SY-058/1A", "House No 8, Indiranagar, Bengaluru 560038", 12_000_000)
PROP_RING = ("SY-911/2C", "Plot 23 Whitefield, Bengaluru 560066", 7_500_000)  # double-financed


def _secured_docs(
    app: Applicant, prop: tuple, owner_name: str, valuation: float, loan_amount: float,
    seller: str, ec_charges: list[dict], created: datetime,
) -> list[DocSpec]:
    """A secured-loan document set: income proof + the four land/legal collateral docs."""
    pid, addr, market = prop
    tax = _tax(app.income)
    monthly = _monthly_credit(app.income)
    m = lambda d: pb.DocMeta(creation_date=created + timedelta(days=d), mod_date=created + timedelta(days=d))
    return [
        DocSpec("identity.pdf", "identity", pb.build_identity(app.name, app.pan, app.dob, m(0)),
                {"pan": app.pan, "name": app.name}),
        DocSpec("form16.pdf", "form16",
                pb.build_form16(app.name, app.pan, app.employer, app.income, tax, "2023-24", m(1)),
                {"gross_income": app.income}),
        DocSpec("bank_statement.pdf", "bank_statement",
                pb.build_bank_statement(app.name, app.account, monthly, MONTHS, m(2)),
                {"monthly_credit": monthly}),
        DocSpec("sale_deed.pdf", "sale_deed",
                pb.build_sale_deed(owner_name, app.pan, pid, addr, market, seller, m(3)),
                {"property_id": pid, "owner": owner_name, "consideration": market}),
        DocSpec("encumbrance_certificate.pdf", "encumbrance_certificate",
                pb.build_encumbrance_certificate(owner_name, pid, addr, ec_charges, "2014-2024", m(4)),
                {"property_id": pid, "charges": ec_charges}),
        DocSpec("property_valuation.pdf", "property_valuation",
                pb.build_property_valuation(owner_name, pid, addr, valuation, m(5)),
                {"property_id": pid, "valuation": valuation, "loan_amount": loan_amount}),
        DocSpec("legal_opinion.pdf", "legal_opinion",
                pb.build_legal_opinion(owner_name, pid, "Adv. S. Rao", True, m(6)),
                {"property_id": pid}),
    ]


def build_property() -> list[PacketSpec]:
    """Secured-loan packets: 2 clean + 4 collateral-fraud types + a 3-applicant double-financing ring."""
    specs: list[PacketSpec] = []

    # --- 2 clean secured packets (applicants with a clear CERSAI record) -----------------
    clean_cases = [
        (ROSTER[1], PROP_A, 6_000_000, "R. Krishnan", datetime(2024, 5, 2, 10, 0, 0)),   # Priya, LTV 0.67
        (ROSTER[7], PROP_B, 8_000_000, "M. Fernandes", datetime(2024, 5, 6, 10, 0, 0)),  # Deepak, LTV 0.67
    ]
    for app, prop, loan, seller, created in clean_cases:
        docs = _secured_docs(app, prop, app.name, prop[2], loan, seller, [], created)
        specs.append(PacketSpec(
            "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=8),
            label="clean",
            ground_truth={"property_id": prop[0], "market_value": prop[2], "valuation": prop[2],
                          "loan_amount": loan, "ltv": round(loan / prop[2], 2)},
        ))

    # --- forged_title: sale-deed owner name altered (≠ applicant; edit residue in text) ---
    app = ROSTER[2]  # Amit Patel
    created = datetime(2024, 7, 5, 10, 0, 0)
    docs = _secured_docs(app, PROP_A, app.name, PROP_A[2], 6_500_000, "R. Krishnan", [], created)
    tp.edit_text(docs[3].doc, app.name, "Suresh Iyer")  # sale_deed is index 3
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["forged_title"],
        reasons=[f"Sale-deed owner name was altered to 'Suresh Iyer' (≠ applicant {app.name}); the original name remains in the text layer."],
        affected_docs=["sale_deed.pdf"],
        ground_truth={"property_id": PROP_A[0], "deed_owner": "Suresh Iyer", "applicant": app.name},
    ))

    # --- tampered_encumbrance: EC white-boxes a real CERSAI charge and stamps NIL ----------
    app = ROSTER[3]  # Sneha Reddy — CERSAI fixture shows an active residential charge
    created = datetime(2024, 7, 9, 10, 0, 0)
    charge = [{"type": "mortgage", "lender": "HDFC Bank", "amount": 4_200_000, "registered_on": "2021-11-04"}]
    docs = _secured_docs(app, PROP_B, app.name, PROP_B[2], 7_000_000, "M. Fernandes", charge, created)
    tp.edit_text(docs[4].doc, "HDFC Bank", "NIL ENCUMBRANCES REGISTERED", cover_to_margin=True)  # EC index 4
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["tampered_encumbrance"],
        reasons=["Encumbrance certificate was doctored to read 'NIL' but CERSAI records an active HDFC Bank mortgage on the property; the original charge row survives in the text layer."],
        affected_docs=["encumbrance_certificate.pdf"],
        ground_truth={"property_id": PROP_B[0], "hidden_charge_lender": "HDFC Bank", "hidden_charge_amount": 4_200_000},
    ))

    # --- valuation_inflation: valuation >> market; loan exceeds market value --------------
    app = ROSTER[4]  # Vikram Singh
    created = datetime(2024, 7, 13, 10, 0, 0)
    inflated_val = 11_000_000
    loan = 9_500_000  # > market value of 7.5M → impossible LTV vs market
    docs = _secured_docs(app, PROP_RING, app.name, inflated_val, loan, "K. Prasad", [], created)
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["valuation_inflation"],
        reasons=[f"Property valued at {inflated_val} vs market value {PROP_RING[2]}; requested loan {loan} exceeds the property's market value (abnormal LTV)."],
        affected_docs=["property_valuation.pdf"],
        ground_truth={"property_id": PROP_RING[0], "market_value": PROP_RING[2], "valuation": inflated_val,
                      "loan_amount": loan, "ltv_vs_market": round(loan / PROP_RING[2], 2)},
    ))

    # --- property_mismatch: property id/address differs across sale deed vs valuation ------
    app = ROSTER[6]  # Karan Mehta
    created = datetime(2024, 7, 17, 10, 0, 0)
    deed_prop = ("SY-330/7", "44 HSR Layout, Bengaluru 560102", 8_500_000)
    val_prop = ("SY-331/9", "44 HSR Layout, Bengaluru 560102", 8_500_000)  # different survey number
    tax = _tax(app.income); monthly = _monthly_credit(app.income)
    mm = lambda d: pb.DocMeta(creation_date=created + timedelta(days=d), mod_date=created + timedelta(days=d))
    docs = [
        DocSpec("identity.pdf", "identity", pb.build_identity(app.name, app.pan, app.dob, mm(0)), {"pan": app.pan}),
        DocSpec("sale_deed.pdf", "sale_deed",
                pb.build_sale_deed(app.name, app.pan, deed_prop[0], deed_prop[1], deed_prop[2], "G. Rao", mm(3)),
                {"property_id": deed_prop[0]}),
        DocSpec("property_valuation.pdf", "property_valuation",
                pb.build_property_valuation(app.name, val_prop[0], val_prop[1], val_prop[2], mm(5)),
                {"property_id": val_prop[0]}),
        DocSpec("legal_opinion.pdf", "legal_opinion",
                pb.build_legal_opinion(app.name, deed_prop[0], "Adv. S. Rao", True, mm(6)), {}),
    ]
    specs.append(PacketSpec(
        "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=6),
        label="fraud", fraud_types=["property_mismatch"],
        reasons=[f"Sale deed describes property {deed_prop[0]} but the valuation report is for {val_prop[0]} — the collateral documents reference different properties."],
        affected_docs=["sale_deed.pdf", "property_valuation.pdf"],
        ground_truth={"deed_property_id": deed_prop[0], "valuation_property_id": val_prop[0]},
    ))

    # --- double_financing: 3 applicants pledge the SAME property (the graph 'wow') ---------
    ring = [
        Applicant("Imran Shaikh", "ZZEPS5555E", "Shaikh Trading Co", "9101112221", 1_300_000, "1988-02-10"),
        Applicant("Vivek Menon", "ZZFPM6666F", "Menon & Sons", "9102223332", 1_250_000, "1986-05-22"),
        Applicant("Arjun Das", "ZZGPD7777G", "Das Enterprises", "9103334443", 1_400_000, "1990-09-15"),
    ]
    for k, app in enumerate(ring):
        created = datetime(2024, 8, 20, 10, 0, 0) + timedelta(days=k * 4)
        docs = _secured_docs(app, PROP_RING, app.name, PROP_RING[2], 5_000_000, "K. Prasad", [], created)
        specs.append(PacketSpec(
            "", app.name, app.pan, app.employer, docs, created, created + timedelta(days=5),
            label="fraud", fraud_types=["double_financing"],
            reasons=[f"Property {PROP_RING[0]} ({PROP_RING[1]}) is pledged as collateral across multiple loan applications — the same asset financed more than once."],
            affected_docs=["sale_deed.pdf", "property_valuation.pdf"],
            property_group="prop_ring_sy911",
            ground_truth={"property_id": PROP_RING[0], "market_value": PROP_RING[2], "loan_amount": 5_000_000},
        ))
    return specs


def main() -> None:
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    # Wipe previously generated packets for a clean, deterministic rebuild.
    for child in PACKETS_DIR.iterdir() if PACKETS_DIR.exists() else []:
        if child.is_dir():
            shutil.rmtree(child)

    all_specs: list[PacketSpec] = (
        build_clean() + build_forensic() + build_cross_doc() + build_template_reuse()
        + build_behavioral() + build_property()
    )

    labels: dict[str, Any] = {}
    for i, spec in enumerate(all_specs, start=1):
        spec.packet_id = f"PKT-{i:04d}"
        labels[spec.packet_id] = realize_packet(spec)

    LABELS_PATH.write_text(json.dumps(labels, indent=2), encoding="utf-8")

    n_clean = sum(1 for v in labels.values() if v["label"] == "clean")
    n_fraud = len(labels) - n_clean
    fraud_types = sorted({t for v in labels.values() for t in v["fraud_types"]})
    print(f"Generated {len(labels)} packets -> {PACKETS_DIR}")
    print(f"  clean: {n_clean}   fraud: {n_fraud}")
    print(f"  fraud types covered: {', '.join(fraud_types)}")
    print(f"  labels: {LABELS_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
