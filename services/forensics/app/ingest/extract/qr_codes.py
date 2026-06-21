"""QR cross-verification (plan §10 Phase 3) — does the card's QR agree with the printed text?

Indian ID cards carry a QR that encodes the *real* data: a newer PAN card's QR holds name/PAN/DOB; an
Aadhaar **Secure QR** holds name/DOB/gender/address + a photo and is **digitally signed by UIDAI**. So a
fraudster who edits the *printed* number but leaves the QR intact is caught by comparing the two — a
signal completely orthogonal to pixel forensics (it works even on a denoised, colored photo).

Honest limits, handled gracefully:
  - Dense PAN/Aadhaar QRs often **don't decode** from a low-res phone photo → we report "no readable QR"
    and raise **no** finding (never a false positive).
  - The PAN QR format is proprietary (not officially documented); we extract a PAN/Aadhaar token if the
    decoded payload exposes one. The Aadhaar **Secure QR** is parsed (and signature-verified when the
    UIDAI cert + `pyaadhaar` are available) — the strongest case.

Everything is local; `pyzbar`/`pyaadhaar` are optional (the module no-ops if they're absent).
"""

from __future__ import annotations

import re
from typing import Optional

_PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")


def decode_available() -> bool:
    try:
        import pyzbar.pyzbar  # noqa: F401
        return True
    except Exception:
        return False


def _safe_text(b: bytes) -> str:
    try:
        return b.decode("utf-8", "ignore")
    except Exception:
        return ""


def decode_qrs(image_path: str) -> list[dict]:
    """Decode QR/barcodes in an image → [{type, bytes, text}]. Retries upscaled for dense codes.
    Returns [] (never raises) if nothing decodes or the lib is unavailable."""
    out: list[dict] = []
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode

        img = Image.open(image_path).convert("RGB")
        results = decode(img)
        if not results:
            for scale in (2, 3):  # dense card QRs in a low-res photo need upscaling
                results = decode(img.resize((img.size[0] * scale, img.size[1] * scale)))
                if results:
                    break
        for r in results:
            out.append({"type": r.type, "bytes": bytes(r.data), "text": _safe_text(r.data)})
    except Exception:
        pass
    return out


def _parse_aadhaar_secure_qr(raw: bytes) -> Optional[dict]:
    """Parse + (best-effort) signature-verify an Aadhaar Secure QR. None if not applicable/unavailable."""
    if not (raw.isdigit() and len(raw) > 100):  # Secure QR payload is a large base-10 big integer
        return None
    try:
        from pyaadhaar.decode import AadhaarSecureQR

        obj = AadhaarSecureQR(int(raw))
        data = obj.decodeddata() or {}
        try:
            sig = bool(obj.verifySignature())  # type: ignore[attr-defined]
        except Exception:
            sig = None  # cert/lib unavailable → unknown (don't fabricate a verdict)
        return {
            "name": data.get("name"),
            "dob": data.get("dob"),
            "gender": data.get("gender"),
            "last4": data.get("adhaar_last_4_digit") or data.get("uid"),
            "signature_valid": sig,
        }
    except Exception:
        return None


def ids_from_payloads(payloads: list[dict]) -> dict:
    """Extract a PAN and/or Aadhaar-Secure-QR record from decoded QR payloads."""
    ids: dict = {}
    for p in payloads:
        text = (p.get("text") or "").upper()
        m = _PAN_RE.search(text)
        if m and "pan" not in ids:
            ids["pan"] = m.group(0)
        aad = _parse_aadhaar_secure_qr(p.get("bytes", b""))
        if aad and "aadhaar_qr" not in ids:
            ids["aadhaar_qr"] = aad
    return ids


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _finding(title: str, description: str, values: dict, confidence: float = 0.85) -> dict:
    return {"category": "semantic", "severity": "high", "title": title, "description": description,
            "source_location": "QR cross-verification (card QR vs printed text)",
            "values": values, "confidence": confidence}


def cross_check(qr_ids: dict, ocr_pan: Optional[str], ocr_aadhaar: Optional[str]) -> list[dict]:
    """Compare decoded-QR identity against the OCR'd printed identity. Pure logic (testable)."""
    findings: list[dict] = []
    qr_pan = qr_ids.get("pan")
    if qr_pan and ocr_pan and _norm(qr_pan) != _norm(ocr_pan):
        findings.append(_finding(
            "Printed PAN disagrees with the card's QR",
            f"The PAN printed on the card ('{ocr_pan}') does not match the PAN encoded in the card's QR "
            f"code ('{qr_pan}'). The QR is far harder to forge than the printed text — the printed value "
            f"appears to have been altered.",
            {"detector": "qr_cross_check", "printed_pan": ocr_pan, "qr_pan": qr_pan}))

    aad = qr_ids.get("aadhaar_qr")
    if aad:
        if aad.get("signature_valid") is False:
            findings.append(_finding(
                "Aadhaar QR signature INVALID (tampered)",
                "The Aadhaar Secure QR's UIDAI digital signature did not verify — the QR contents (or the "
                "card) have been tampered with. A genuine Aadhaar QR is cryptographically signed by UIDAI.",
                {"detector": "qr_aadhaar_signature", "signature_valid": False}, confidence=0.95))
        qr_last4 = _norm(str(aad.get("last4") or ""))[-4:]
        ocr_last4 = _norm(ocr_aadhaar or "")[-4:]
        if qr_last4 and ocr_last4 and qr_last4 != ocr_last4:
            findings.append(_finding(
                "Printed Aadhaar disagrees with the card's QR",
                f"The Aadhaar number printed on the card (…{ocr_last4}) does not match the QR-encoded "
                f"value (…{qr_last4}) — the printed digits appear altered.",
                {"detector": "qr_cross_check", "printed_last4": ocr_last4, "qr_last4": qr_last4}))
    return findings


def qr_check(image_path: str, ocr_fields: dict) -> tuple[list[dict], dict]:
    """Orchestrate: decode QRs → extract ids → cross-check vs OCR. Returns (findings, info)."""
    payloads = decode_qrs(image_path)
    info: dict = {"available": decode_available(), "qr_found": len(payloads)}
    if not payloads:
        return [], info
    ids = ids_from_payloads(payloads)
    info["qr_ids"] = {k: ({kk: vv for kk, vv in v.items() if kk != "photo"} if isinstance(v, dict) else v)
                      for k, v in ids.items()}
    findings = cross_check(ids, ocr_fields.get("pan"), ocr_fields.get("aadhaar"))
    return findings, info
