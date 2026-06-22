"""Build a labeled clean/tampered IMAGE dataset for the image-forensics eval + forgery training (§11).

Generator v2. Builds realistic documents IN-PROCESS (so we hold each editable value's exact field box),
rasterises them to a "scan", then forges **field-targeted, seamless** edits on the fields fraudsters
actually edit (gross salary / TDS, salary credit / closing balance, net pay / basic, PAN / Aadhaar /
name / DOB) across a difficulty spectrum:

    naive    — hard rectangle-fill + stamped text (the easy tier the heuristics can catch)
    blended  — feathered alpha composite
    pro      — inpaint + font/colour-matched render + matched noise + single recompress (no hard edges)

…plus the geometric pixel tampers (copy-move / splice / recompress) that exercise the pixel detectors.
Every tampered image carries a ground-truth mask; records carry the field, difficulty, old/new value
and a deterministic train/val/test split (by source id, so a page never crosses splits).

Deterministic (fixed seed), synthetic (zero PII). Output (gitignored) under data/synthetic/images/:
    clean/<src>.jpg
    tampered/<src>__<field>_<difficulty>.jpg   |  tampered/<src>__<geom>.jpg
    masks/<src>__….png        (255 = tampered pixels)
    labels.json               (records: file, label, tamper_type, difficulty, field_name, fraud_field,
                               old_value, new_value, variant, split, doc_type, mask, boxes, source)

    python -m data.generator.build_image_dataset
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from data.generator import pdf_builder as pb
from data.generator import seamless_edit as se
from data.generator import tamper_image as ti

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKETS = REPO_ROOT / "data" / "synthetic" / "packets"   # kept for callers/tests
DEFAULT_OUT = REPO_ROOT / "data" / "synthetic" / "images"

DIFFICULTIES = ("naive", "blended", "pro")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]

# Synthetic applicants for the image dataset (zero PII). Aadhaar numbers are obviously synthetic.
APPLICANTS: list[dict] = [
    {"key": "rahul", "name": "Rahul Sharma", "pan": "ABMPS1234F", "employer": "Infosys Limited",
     "account": "1234509876", "income": 1820000, "dob": "12/04/1989", "gender": "Male",
     "aadhaar": "2847 5163 9024", "father": "Mahesh Sharma",
     "address": ["12 MG Road", "Bengaluru, Karnataka 560001"]},
    {"key": "priya", "name": "Priya Verma", "pan": "CDNPV5678L", "employer": "Tata Consultancy Services",
     "account": "2233445566", "income": 1450000, "dob": "03/09/1991", "gender": "Female",
     "aadhaar": "5012 7788 1346", "father": "Suresh Verma",
     "address": ["44 Park Street", "Kolkata, West Bengal 700016"]},
    {"key": "amit", "name": "Amit Patel", "pan": "EFKPP9012Q", "employer": "Wipro Limited",
     "account": "3344556677", "income": 980000, "dob": "22/01/1990", "gender": "Male",
     "aadhaar": "7690 2231 5508", "father": "Dinesh Patel",
     "address": ["7 SG Highway", "Ahmedabad, Gujarat 380015"]},
    {"key": "sneha", "name": "Sneha Reddy", "pan": "GHJPR3456M", "employer": "HDFC Bank",
     "account": "4455667788", "income": 2100000, "dob": "30/12/1987", "gender": "Female",
     "aadhaar": "3318 9047 2261", "father": "Ram Reddy",
     "address": ["9 Banjara Hills", "Hyderabad, Telangana 500034"]},
    {"key": "vikram", "name": "Vikram Singh", "pan": "KLMPS7777N", "employer": "Larsen & Toubro",
     "account": "5566778899", "income": 1250000, "dob": "15/06/1985", "gender": "Male",
     "aadhaar": "6204 8851 7390", "father": "Joginder Singh",
     "address": ["21 Civil Lines", "Jaipur, Rajasthan 302006"]},
    {"key": "anjali", "name": "Anjali Nair", "pan": "NOPPN2345T", "employer": "Tech Mahindra",
     "account": "6677889900", "income": 1100000, "dob": "08/03/1992", "gender": "Female",
     "aadhaar": "8125 6634 9071", "father": "Krishnan Nair",
     "address": ["3 Marine Drive", "Kochi, Kerala 682011"]},
    {"key": "karan", "name": "Karan Mehta", "pan": "QRSPM6789W", "employer": "Accenture",
     "account": "7788990011", "income": 1600000, "dob": "19/11/1986", "gender": "Male",
     "aadhaar": "4471 9920 3358", "father": "Naresh Mehta",
     "address": ["18 FC Road", "Pune, Maharashtra 411004"]},
    {"key": "deepak", "name": "Deepak Joshi", "pan": "TUVPJ0123H", "employer": "Cognizant",
     "account": "8899001122", "income": 1350000, "dob": "25/07/1988", "gender": "Male",
     "aadhaar": "9032 4417 6685", "father": "Anil Joshi",
     "address": ["5 Hazratganj", "Lucknow, Uttar Pradesh 226001"]},
    {"key": "meera", "name": "Meera Iyer", "pan": "WXYPI4567K", "employer": "IBM India",
     "account": "9900112233", "income": 1720000, "dob": "14/02/1990", "gender": "Female",
     "aadhaar": "2259 6741 8803", "father": "Ganesh Iyer",
     "address": ["27 Anna Salai", "Chennai, Tamil Nadu 600002"]},
    {"key": "rohit", "name": "Rohit Bose", "pan": "BCDPB8910R", "employer": "Capgemini",
     "account": "1011121314", "income": 990000, "dob": "06/10/1991", "gender": "Male",
     "aadhaar": "5583 1209 7746", "father": "Subir Bose",
     "address": ["11 Salt Lake Sec V", "Kolkata, West Bengal 700091"]},
]

# Fraud fields exercised per doc type (kept to 2 → a balanced dataset across the spectrum).
DOC_FIELDS: dict[str, list[str]] = {
    "form16": ["gross_salary", "tds"],
    "salary_slip": ["net_pay", "basic"],
    "bank_statement": ["salary_credit", "closing_balance"],
    "identity": ["pan", "dob"],
    "aadhaar": ["aadhaar_number", "name"],
}
GEOM_TAMPERS = {"copy_move": ti.copy_move, "splice": ti.splice, "recompress": ti.recompress_patch}
_SURNAMES = ["Kumar", "Singh", "Nair", "Iyer", "Das", "Khan", "Gupta", "Rao", "Mehta", "Reddy", "Bose"]


def _tax(income: float) -> float:
    return round(income * (0.18 if income > 1500000 else 0.10))


def _net(income: float) -> float:
    return round((income - _tax(income)) / 12)


def _simulate_scan(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Give a vector-clean render the characteristics of a real scan/photo: a faint lighting gradient,
    mild optical blur, and a consistent sensor-noise floor. This baseline is what lets a `pro` edit
    *match* the page (and what makes a naive flat fill stand out)."""
    a = np.asarray(img, dtype=np.float32)
    h, w, _ = a.shape
    gy = np.linspace(rng.uniform(0.90, 0.96), 1.0, h)[:, None]
    gx = np.linspace(rng.uniform(0.95, 1.0), 1.0, w)[None, :]
    a *= (gy * gx)[:, :, None]
    img2 = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    a = np.asarray(img2, dtype=np.float32)
    a += rng.normal(0.0, 12.0, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _build_doc(app: dict, doc_type: str, template: int) -> tuple["object", dict]:
    m = pb.DocMeta()
    f: dict = {}
    if doc_type == "form16":
        d = pb.build_form16(app["name"], app["pan"], app["employer"], app["income"], _tax(app["income"]),
                            "2023-24", m, fields=f, template=template)
    elif doc_type == "salary_slip":
        d = pb.build_salary_slip(app["name"], app["employer"], "Jun 2024", _net(app["income"]), m,
                                 fields=f, template=template)
    elif doc_type == "bank_statement":
        d = pb.build_bank_statement(app["name"], app["account"], _net(app["income"]), MONTHS, m,
                                    fields=f, template=template)
    elif doc_type == "identity":
        d = pb.build_identity(app["name"], app["pan"], app["dob"], m, fields=f, father=app["father"])
    elif doc_type == "aadhaar":
        d = pb.build_aadhaar(app["name"], app["aadhaar"], app["dob"], app["gender"], app["address"],
                             m, fields=f)
    else:
        raise ValueError(doc_type)
    return d, f


def _rasterize_scan(doc, dpi: int, rng: np.random.Generator) -> Image.Image:
    pix = doc[0].get_pixmap(dpi=dpi)
    return _simulate_scan(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"), rng)


# ── realistic replacement values (the fraud) ────────────────────────────────────────

def _swap_one_digit(s: str, rng: np.random.Generator) -> str:
    chars = list(s)
    pos = [i for i, c in enumerate(chars) if c.isdigit()]
    if not pos:
        return s
    i = int(rng.choice(pos))
    chars[i] = str((int(chars[i]) + int(rng.integers(1, 9))) % 10)
    return "".join(chars)


def _shift_year(dob: str, rng: np.random.Generator) -> str:
    try:
        d, mn, y = dob.split("/")
        return f"{d}/{mn}/{int(y) + int(rng.choice([-4, -3, -2, 2, 3, 4]))}"
    except Exception:
        return dob


def _swap_surname(name: str, rng: np.random.Generator) -> str:
    parts = name.split()
    alt = [s for s in _SURNAMES if s != parts[-1]]
    return " ".join(parts[:-1] + [str(rng.choice(alt))]) if len(parts) >= 2 else name


def _new_value(field: dict, rng: np.random.Generator) -> str:
    kind = field["kind"]
    if kind == "money":
        return pb._money(round(field["amount"] * rng.uniform(1.3, 1.6)))    # inflate
    if kind in ("pan", "aadhaar"):
        return _swap_one_digit(field["value"], rng)
    if kind == "date":
        return _shift_year(field["value"], rng)
    return _swap_surname(field["value"], rng)


def _split_of(source_id: str) -> str:
    h = int(hashlib.sha1(source_id.encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test")


def _px_box(field: dict, scale: float) -> tuple[int, int, int, int]:
    return tuple(int(round(v * scale)) for v in field["rect_pts"])


def _union_mask(masks: list[Image.Image]) -> Image.Image:
    acc = np.zeros(np.asarray(masks[0]).shape, dtype=np.uint8)
    for m in masks:
        acc = np.maximum(acc, np.asarray(m.convert("L")))
    return Image.fromarray(acc)


def build_dataset(out_dir: Path = DEFAULT_OUT, *, dpi: int = 150, jpeg_quality: int = 90, seed: int = 7,
                  n_sources: int | None = None, **_legacy) -> dict:
    """Generate the dataset and return a summary dict. Idempotent (clears the output dir).
    `n_sources` caps the number of (applicant × doc-type) source documents (used by the tiny test)."""
    out_dir = Path(out_dir)
    for sub in ("clean", "tampered", "masks"):
        d = out_dir / sub
        if d.exists():
            for f in d.glob("*"):
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    scale = dpi / 72.0
    doc_types = list(DOC_FIELDS)
    sources = [(app, dt) for app in APPLICANTS for dt in doc_types]
    if n_sources is not None:
        sources = sources[:n_sources]

    records: list[dict] = []
    tamper_types: set[str] = set()
    for idx, (app, doc_type) in enumerate(sources):
        sid = f"{app['key']}_{doc_type}"
        split = _split_of(sid)
        template = (idx) % 3
        doc, fmap = _build_doc(app, doc_type, template)
        scan = _rasterize_scan(doc, dpi, np.random.default_rng(seed * 131 + idx))
        doc.close()
        clean_path = out_dir / "clean" / f"{sid}.jpg"
        scan.save(clean_path, "JPEG", quality=jpeg_quality)
        scan = Image.open(clean_path).convert("RGB")     # reload → realistic compression history
        records.append({"id": sid, "file": f"clean/{sid}.jpg", "label": "clean", "tamper_type": None,
                        "difficulty": None, "doc_type": doc_type, "split": split, "source": sid})

        def _save(tid: str, img: Image.Image, mask: Image.Image, **rec) -> None:
            img.save(out_dir / "tampered" / f"{tid}.jpg", "JPEG", quality=jpeg_quality)
            mask.save(out_dir / "masks" / f"{tid}.png")
            records.append({"id": tid, "file": f"tampered/{tid}.jpg", "label": "tampered",
                            "mask": f"masks/{tid}.png", "doc_type": doc_type, "split": split,
                            "source": sid, **rec})

        # field-targeted seamless edits across the difficulty spectrum
        for fname in DOC_FIELDS[doc_type]:
            field = fmap.get(fname)
            if not field:
                continue
            box = _px_box(field, scale)
            font_px, bold = round(field["size"] * scale), field["font"] == "hebo"
            for diff in DIFFICULTIES:
                rng = np.random.default_rng(seed * 7919 + idx * 97 + hash(fname) % 997 + DIFFICULTIES.index(diff))
                new_text = _new_value(field, rng)
                img, mask = se.edit_field(scan.copy(), box, new_text, difficulty=diff, font_px=font_px,
                                          bold=bold, rng=rng)
                tamper_types.add(fname)
                _save(f"{sid}__{fname}_{diff}", img, mask, tamper_type=fname, difficulty=diff,
                      field_name=fname, fraud_field=field["fraud"], old_value=field["value"],
                      new_value=new_text, variant=("broken" if fname == "salary_credit" else None),
                      boxes=[list(map(int, box))])

        # bank: arithmetic-CONSISTENT pro variant (recompute the running balance so only pixels betray it)
        if doc_type == "bank_statement" and fmap.get("salary_credit") and fmap.get("_balance_column"):
            f = fmap["salary_credit"]
            rng = np.random.default_rng(seed * 13 + idx)
            new_amt = round(f["amount"] * rng.uniform(1.3, 1.6))
            delta = new_amt - f["amount"]
            img = scan.copy()
            masks = []
            img, m0 = se.edit_field(img, _px_box(f, scale), pb._money(new_amt), difficulty="pro",
                                    font_px=round(f["size"] * scale), rng=rng)
            masks.append(m0)
            boxes = [list(map(int, _px_box(f, scale)))]
            for cell in fmap["_balance_column"]:
                if cell["row"] >= f.get("row", 0):
                    cb = _px_box(cell, scale)
                    img, mc = se.edit_field(img, cb, pb._money(cell["amount"] + delta), difficulty="pro",
                                            font_px=round(cell["size"] * scale), rng=rng)
                    masks.append(mc)
                    boxes.append(list(map(int, cb)))
            tamper_types.add("salary_credit")
            _save(f"{sid}__salary_credit_consistent", img, _union_mask(masks), tamper_type="salary_credit",
                  difficulty="pro", field_name="salary_credit", fraud_field="inflate",
                  old_value=f["value"], new_value=pb._money(new_amt), variant="consistent", boxes=boxes)

        # geometric pixel tampers (copy-move / splice / recompress) — the pixel-detector targets
        for gname, fn in GEOM_TAMPERS.items():
            res = fn(scan.copy(), np.random.default_rng(seed * 31 + idx * 11 + hash(gname) % 131))
            tamper_types.add(gname)
            _save(f"{sid}__{gname}", res.image, res.mask, tamper_type=gname, difficulty="geom",
                  field_name=None, fraud_field=None, old_value=None, new_value=None, variant=None,
                  boxes=[list(map(int, b)) for b in res.boxes])

    summary = {
        "n_sources": len(sources), "dpi": dpi, "jpeg_quality": jpeg_quality, "seed": seed,
        "tamper_types": sorted(tamper_types), "difficulties": list(DIFFICULTIES),
        "n_clean": sum(1 for r in records if r["label"] == "clean"),
        "n_tampered": sum(1 for r in records if r["label"] == "tampered"),
        "splits": {s: sum(1 for r in records if r["split"] == s) for s in ("train", "val", "test")},
        "records": records,
    }
    (out_dir / "labels.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    s = build_dataset()
    print(f"Built image dataset v2: {s['n_clean']} clean + {s['n_tampered']} tampered "
          f"from {s['n_sources']} sources -> {DEFAULT_OUT}")
    print(f"  tamper types: {', '.join(s['tamper_types'])}")
    print(f"  splits: {s['splits']}")


if __name__ == "__main__":
    main()
