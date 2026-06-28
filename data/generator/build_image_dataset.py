"""Build a labeled clean/tampered IMAGE dataset for the image-forensics eval + forgery training (§11 → v2).

Generator v3. Builds **layout-FAMILY** documents in-process (variable formats / row counts / column
widths / fonts / bands — see `pdf_builder.build_*_v2`) for **hundreds of procedurally-generated synthetic
identities**, rasterises each to a 300-dpi "scan", then forges **field-targeted, seamless** edits across
*many* fields at *varied positions* (not 2 fixed ones) over a difficulty spectrum:

    naive    — hard rectangle-fill + stamped text (the easy tier the heuristics can catch)
    blended  — feathered alpha composite
    pro      — inpaint + font/colour-matched render + matched noise + single recompress (no hard edges)

…plus geometric pixel tampers (copy-move / splice / recompress). Volume is weighted to the hard
`blended`/`pro` tiers. Every tampered image carries a ground-truth mask; records carry the field,
difficulty, old/new value, format id and a deterministic by-source train/val/test split.

Deterministic (fixed seed), synthetic (zero PII). Output (gitignored) under data/synthetic/images/:
    clean/<src>.jpg
    tampered/<src>__<field>_<difficulty>.jpg   |  tampered/<src>__<geom>.jpg
    masks/<src>__….png        (255 = tampered pixels)
    labels.json               (records + summary; per-record file/label/tamper_type/difficulty/
                               field_name/old_value/new_value/variant/split/doc_type/format_id/mask/boxes/source)

    python -m data.generator.build_image_dataset --applicants 112      # ~10k tampered @ 300 dpi
    python -m data.generator.build_image_dataset --applicants 4        # quick smoke
"""

from __future__ import annotations

import argparse
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
DEFAULT_APPLICANTS = 112        # × 5 doc types × ~18 edits/source ≈ ~10k tampered

# Doc types the image dataset covers + the realistic "headline" fraud fields always exercised (full
# difficulty spectrum) so the dataset always spans naive→pro on the fields fraudsters actually edit. Many
# OTHER recorded fields are also edited (weighted to blended/pro) to spread edits across the page.
DOC_TYPES = ["form16", "salary_slip", "bank_statement", "identity", "aadhaar"]
PRIORITY_FIELDS: dict[str, list[str]] = {
    "form16": ["gross_salary", "tds", "total_paid", "taxable"],
    "salary_slip": ["net_pay", "gross", "basic"],
    "bank_statement": ["salary_credit", "closing_balance", "opening_balance"],
    "identity": ["pan", "name", "dob"],
    "aadhaar": ["aadhaar_number", "name", "dob"],
}
GEOM_TAMPERS = {"copy_move": ti.copy_move, "splice": ti.splice, "recompress": ti.recompress_patch}

N_FULL = 3      # fields edited at ALL difficulties (guarantees the naive→pro spectrum)
N_HARD = 5      # extra fields edited at blended+pro only (weights volume to the hard tiers)

# ── procedural synthetic identities (zero PII) ───────────────────────────────────────
_FIRST = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Karan", "Deepak", "Meera", "Rohit",
          "Fatima", "Arjun", "Kavya", "Sandeep", "Neha", "Rajesh", "Divya", "Manish", "Pooja", "Imran",
          "Sara", "Yash", "Tara", "Nikhil", "Aditi", "Varun", "Isha", "Gaurav", "Riya", "Aman"]
_LAST = ["Sharma", "Verma", "Patel", "Reddy", "Singh", "Nair", "Mehta", "Joshi", "Iyer", "Bose",
         "Sheikh", "Menon", "Pillai", "Yadav", "Agarwal", "Rao", "Gupta", "Desai", "Khan", "Das"]
_EMPLOYERS = ["Infosys Limited", "Tata Consultancy Services", "Wipro Limited", "HDFC Bank", "Tech Mahindra",
              "Accenture", "Cognizant", "IBM India", "Capgemini", "Oracle India", "Deloitte India",
              "Zoho Corporation", "Flipkart", "Reliance Jio", "Bajaj Finserv", "Larsen & Toubro"]
_CITIES = [("MG Road", "Bengaluru, Karnataka 560001"), ("Park Street", "Kolkata, West Bengal 700016"),
           ("SG Highway", "Ahmedabad, Gujarat 380015"), ("Banjara Hills", "Hyderabad, Telangana 500034"),
           ("Civil Lines", "Jaipur, Rajasthan 302006"), ("Marine Drive", "Kochi, Kerala 682011"),
           ("FC Road", "Pune, Maharashtra 411004"), ("Anna Salai", "Chennai, Tamil Nadu 600002")]


def _gen_applicant(i: int, rng: np.random.Generator) -> dict:
    first = _FIRST[int(rng.integers(0, len(_FIRST)))]
    last = _LAST[int(rng.integers(0, len(_LAST)))]
    name = f"{first} {last}"
    L = "ABCDEFGHIJKLMNPQRSTUVWXYZ"
    pan = ("".join(L[int(rng.integers(0, len(L)))] for _ in range(3)) + "P" + last[0].upper()
           + "".join(str(int(rng.integers(0, 10))) for _ in range(4)) + L[int(rng.integers(0, len(L)))])
    aad = " ".join("".join(str(int(rng.integers(0, 10))) for _ in range(4)) for _ in range(3))
    street, city = _CITIES[int(rng.integers(0, len(_CITIES)))]
    return {
        "key": f"app{i:03d}_{first.lower()}",
        "name": name, "pan": pan,
        "employer": _EMPLOYERS[int(rng.integers(0, len(_EMPLOYERS)))],
        "account": "".join(str(int(rng.integers(0, 10))) for _ in range(10)),
        "income": int(rng.integers(7, 30)) * 100000,
        "dob": f"{int(rng.integers(1,28)):02d}/{int(rng.integers(1,13)):02d}/{int(rng.integers(1980,1998))}",
        "gender": "Male" if rng.integers(0, 2) else "Female",
        "aadhaar": aad, "father": f"{_FIRST[int(rng.integers(0,len(_FIRST)))]} {last}",
        "address": [f"{int(rng.integers(1,99))} {street}", city],
    }


def _tax(income: float) -> float:
    return round(income * (0.18 if income > 1500000 else 0.10))


def _net(income: float) -> float:
    return round((income - _tax(income)) / 12)


def _simulate_scan(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Give a vector-clean render the characteristics of a real scan: a faint per-source lighting gradient,
    mild optical blur, and a sensor-noise floor. This baseline is what lets a `pro` edit *match* the page
    (and what a naive flat fill breaks). Kept within a narrow band that holds the heuristics' zero-FP."""
    a = np.asarray(img, dtype=np.float32)
    h, w, _ = a.shape
    gy = np.linspace(rng.uniform(0.90, 0.96), 1.0, h)[:, None]
    gx = np.linspace(rng.uniform(0.95, 1.0), 1.0, w)[None, :]
    a *= (gy * gx)[:, :, None]
    img2 = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(rng.uniform(0.5, 0.8)))
    a = np.asarray(img2, dtype=np.float32)
    a += rng.normal(0.0, rng.uniform(10.0, 14.0), a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _build_doc(app: dict, doc_type: str, rng: np.random.Generator) -> tuple["object", dict]:
    """Build a layout-family document (v2 builders) + return its exact field map."""
    m = pb.DocMeta()
    f: dict = {}
    if doc_type == "form16":
        d = pb.build_form16_v2(app["name"], app["pan"], app["employer"], app["income"], _tax(app["income"]),
                               "2023-24", m, fields=f, rng=rng)
    elif doc_type == "salary_slip":
        d = pb.build_salary_slip_v2(app["name"], app["employer"], "Jun 2024", _net(app["income"]), m,
                                    fields=f, rng=rng)
    elif doc_type == "bank_statement":
        n_months = int(rng.integers(3, len(MONTHS) + 1))
        d = pb.build_bank_statement_v2(app["name"], app["account"], _net(app["income"]), MONTHS[:n_months],
                                       m, fields=f, rng=rng)
    elif doc_type == "identity":
        d = pb.build_identity_v2(app["name"], app["pan"], app["dob"], m, fields=f, father=app["father"], rng=rng)
    elif doc_type == "aadhaar":
        d = pb.build_aadhaar_v2(app["name"], app["aadhaar"], app["dob"], app["gender"], app["address"],
                                m, fields=f, rng=rng)
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


_SURNAMES = _LAST


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


def render_showcase_pair(doc_type: str, *, field: str | None = None, difficulty: str = "pro",
                         geom: str | None = None, dpi: int = 300, seed: int = 7,
                         applicant_idx: int = 0) -> dict:
    """Render a matched **full-page** clean+edited pair at `dpi` (the dashboard showcase needs full pages
    at the model's native 300-dpi domain — a downscaled/150-dpi page is out-of-distribution and false-fires).
    Reuses the dataset's own builders/editors so the showcase exactly matches the trained-on distribution.
    Returns {clean, edited, box(page px)|None, old, new, w, h}."""
    app = _gen_applicant(applicant_idx, np.random.default_rng(seed * 1000 + applicant_idx))
    doc, fmap = _build_doc(app, doc_type, np.random.default_rng(seed * 7 + 13))
    clean = _rasterize_scan(doc, dpi, np.random.default_rng(seed * 131 + 1))
    doc.close()
    buf = io.BytesIO(); clean.save(buf, "JPEG", quality=90)      # realistic compression history (as build_dataset)
    clean = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    out = {"clean": clean, "edited": None, "box": None, "old": None, "new": None, "w": clean.width, "h": clean.height}
    if geom:
        res = GEOM_TAMPERS[geom](clean.copy(), np.random.default_rng(seed * 31 + 5))
        out["edited"], out["box"] = res.image, [int(v) for v in res.boxes[0]]
        return out
    if field:
        fd = fmap.get(field)
        if fd is None:
            return out
        scale = dpi / 72.0
        box = _px_box(fd, scale)
        new_text = _new_value(fd, np.random.default_rng(seed * 99 + 3))
        edited, _ = se.edit_field(clean.copy(), box, new_text, difficulty=difficulty,
                                  font_px=round(fd["size"] * scale), bold=fd.get("font") == "hebo",
                                  rng=np.random.default_rng(seed * 99 + 7))
        out.update(edited=edited, box=[int(v) for v in box], old=fd["value"], new=new_text)
    return out


def _split_of(source_id: str) -> str:
    import hashlib
    h = int(hashlib.sha1(source_id.encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test")


def _px_box(field: dict, scale: float) -> tuple[int, int, int, int]:
    return tuple(int(round(v * scale)) for v in field["rect_pts"])


def _union_mask(masks: list[Image.Image]) -> Image.Image:
    acc = np.zeros(np.asarray(masks[0]).shape, dtype=np.uint8)
    for m in masks:
        acc = np.maximum(acc, np.asarray(m.convert("L")))
    return Image.fromarray(acc)


# Tampered pages are stored as CROPS around the edit (not full 8-MP pages) — a patch localizer only ever
# trains/evaluates on windows, so crops keep disk small while preserving native resolution + context.
# Clean docs stay full pages (needed for the doc-level clean-FP eval + as negative-patch sources).
CROP_PAD = 160
CROP_MIN = 512


def _crop_around(img: Image.Image, mask: Image.Image, boxes: list) -> tuple[Image.Image, Image.Image, list]:
    W, H = img.size
    xs0 = min(b[0] for b in boxes); ys0 = min(b[1] for b in boxes)
    xs1 = max(b[2] for b in boxes); ys1 = max(b[3] for b in boxes)
    cw = min(W, max(CROP_MIN, int(xs1 - xs0) + 2 * CROP_PAD))
    ch = min(H, max(CROP_MIN, int(ys1 - ys0) + 2 * CROP_PAD))
    cx, cy = (xs0 + xs1) // 2, (ys0 + ys1) // 2
    x0 = int(np.clip(cx - cw // 2, 0, W - cw)); y0 = int(np.clip(cy - ch // 2, 0, H - ch))
    crop = img.crop((x0, y0, x0 + cw, y0 + ch))
    cmask = mask.crop((x0, y0, x0 + cw, y0 + ch))
    nb = [[int(b[0]) - x0, int(b[1]) - y0, int(b[2]) - x0, int(b[3]) - y0] for b in boxes]
    return crop, cmask, nb


def _editable_fields(fmap: dict) -> dict:
    """Recorded fields a fraudster could edit (money/pan/aadhaar/date/text with a fraud direction)."""
    return {n: f for n, f in fmap.items()
            if isinstance(f, dict) and n != "_balance_column"
            and f.get("kind") in ("money", "pan", "aadhaar", "date", "text")
            and f.get("fraud", "none") != "none" and f.get("rect_pts")}


def build_dataset(out_dir: Path = DEFAULT_OUT, *, dpi: int = 300, jpeg_quality: int = 90, seed: int = 7,
                  n_applicants: int = DEFAULT_APPLICANTS, n_sources: int | None = None, **_legacy) -> dict:
    """Generate the dataset and return a summary dict. Idempotent (clears the output dir).
    `n_sources` caps the number of (applicant × doc-type) source documents (used by the tiny test);
    `n_applicants` sets the procedural-identity count for the full build."""
    out_dir = Path(out_dir)
    for sub in ("clean", "tampered", "masks"):
        d = out_dir / sub
        if d.exists():
            for f in d.glob("*"):
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    scale = dpi / 72.0
    id_rng = np.random.default_rng(seed * 911)
    applicants = [_gen_applicant(i, id_rng) for i in range(n_applicants)]
    sources = [(app, dt) for app in applicants for dt in DOC_TYPES]
    if n_sources is not None:
        sources = sources[:n_sources]

    records: list[dict] = []
    tamper_types: set[str] = set()

    for idx, (app, doc_type) in enumerate(sources):
        sid = f"{app['key']}_{doc_type}"
        split = _split_of(sid)
        rng = np.random.default_rng(seed * 131 + idx)
        doc, fmap = _build_doc(app, doc_type, rng)
        fmt_id = fmap.get("_format_id", "")
        scan = _rasterize_scan(doc, dpi, rng)
        doc.close()
        clean_path = out_dir / "clean" / f"{sid}.jpg"
        scan.save(clean_path, "JPEG", quality=jpeg_quality)
        scan = Image.open(clean_path).convert("RGB")     # reload → realistic compression history
        records.append({"id": sid, "file": f"clean/{sid}.jpg", "label": "clean", "tamper_type": None,
                        "difficulty": None, "doc_type": doc_type, "split": split, "source": sid})

        def _save(tid: str, img: Image.Image, mask: Image.Image, **rec) -> None:
            boxes = rec.get("boxes")
            if boxes:                                  # store a crop around the edit, not the full page
                img, mask, boxes = _crop_around(img, mask, boxes)
                rec["boxes"] = boxes
            img.save(out_dir / "tampered" / f"{tid}.jpg", "JPEG", quality=jpeg_quality)
            mask.save(out_dir / "masks" / f"{tid}.png")
            records.append({"id": tid, "file": f"tampered/{tid}.jpg", "label": "tampered",
                            "mask": f"masks/{tid}.png", "doc_type": doc_type, "split": split,
                            "source": sid, **rec})

        def _edit_field(fname: str, field: dict, diff: str) -> None:
            box = _px_box(field, scale)
            font_px, bold = round(field["size"] * scale), field.get("font") == "hebo"
            r2 = np.random.default_rng(seed * 7919 + idx * 97 + (hash(fname) % 997) + DIFFICULTIES.index(diff)
                                       if diff in DIFFICULTIES else seed)
            new_text = _new_value(field, r2)
            img, mask = se.edit_field(scan.copy(), box, new_text, difficulty=diff, font_px=font_px,
                                      bold=bold, rng=r2)
            tamper_types.add(fname)
            _save(f"{sid}__{fname}_{diff}", img, mask, tamper_type=fname, difficulty=diff,
                  field_name=fname, fraud_field=field.get("fraud"), old_value=field.get("value"),
                  new_value=new_text, format_id=fmt_id, boxes=[list(map(int, box))])

        # choose fields: priority (headline) fields first, then random others → spatially spread edits
        editable = _editable_fields(fmap)
        prio = [n for n in PRIORITY_FIELDS.get(doc_type, []) if n in editable]
        others = [n for n in editable if n not in prio]
        rng.shuffle(others)
        full_fields = (prio + others)[:N_FULL]                       # all 3 difficulties
        hard_fields = [n for n in (prio + others) if n not in full_fields][:N_HARD]   # blended+pro only
        for fname in full_fields:
            for diff in DIFFICULTIES:
                _edit_field(fname, editable[fname], diff)
        for fname in hard_fields:
            for diff in ("blended", "pro"):
                _edit_field(fname, editable[fname], diff)

        # bank: arithmetic-CONSISTENT pro variant (recompute the running balance so only pixels betray it)
        if doc_type == "bank_statement" and fmap.get("salary_credit") and fmap.get("_balance_column"):
            f = fmap["salary_credit"]
            r3 = np.random.default_rng(seed * 13 + idx)
            new_amt = round(f["amount"] * r3.uniform(1.3, 1.6))
            delta = new_amt - f["amount"]
            img = scan.copy(); masks = []
            img, m0 = se.edit_field(img, _px_box(f, scale), pb._money(new_amt), difficulty="pro",
                                    font_px=round(f["size"] * scale), rng=r3)
            masks.append(m0); boxes = [list(map(int, _px_box(f, scale)))]
            for cell in fmap["_balance_column"]:
                if cell["row"] >= f.get("row", 0):
                    cb = _px_box(cell, scale)
                    img, mc = se.edit_field(img, cb, pb._money(cell["amount"] + delta), difficulty="pro",
                                            font_px=round(cell["size"] * scale), rng=r3)
                    masks.append(mc); boxes.append(list(map(int, cb)))
            tamper_types.add("salary_credit")
            _save(f"{sid}__salary_credit_consistent", img, _union_mask(masks), tamper_type="salary_credit",
                  difficulty="pro", field_name="salary_credit", fraud_field="inflate",
                  old_value=f["value"], new_value=pb._money(new_amt), variant="consistent",
                  format_id=fmt_id, boxes=boxes)

        # geometric pixel tampers (copy-move / splice / recompress)
        for gname, fn in GEOM_TAMPERS.items():
            res = fn(scan.copy(), np.random.default_rng(seed * 31 + idx * 11 + hash(gname) % 131))
            tamper_types.add(gname)
            _save(f"{sid}__{gname}", res.image, res.mask, tamper_type=gname, difficulty="geom",
                  field_name=None, fraud_field=None, old_value=None, new_value=None,
                  format_id=fmt_id, boxes=[list(map(int, b)) for b in res.boxes])

    summary = {
        "n_sources": len(sources), "n_applicants": n_applicants, "dpi": dpi, "jpeg_quality": jpeg_quality,
        "seed": seed, "tamper_types": sorted(tamper_types), "difficulties": list(DIFFICULTIES),
        "n_clean": sum(1 for r in records if r["label"] == "clean"),
        "n_tampered": sum(1 for r in records if r["label"] == "tampered"),
        "splits": {s: sum(1 for r in records if r["split"] == s) for s in ("train", "val", "test")},
        "records": records,
    }
    (out_dir / "labels.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the layout-family image dataset (v3).")
    ap.add_argument("--applicants", type=int, default=DEFAULT_APPLICANTS, help="procedural identities")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    s = build_dataset(n_applicants=args.applicants, dpi=args.dpi, seed=args.seed)
    print(f"Built image dataset v3: {s['n_clean']} clean + {s['n_tampered']} tampered "
          f"from {s['n_sources']} sources ({s['n_applicants']} applicants) @ {s['dpi']} dpi -> {DEFAULT_OUT}")
    print(f"  tamper types: {len(s['tamper_types'])} | splits: {s['splits']}")


if __name__ == "__main__":
    main()
