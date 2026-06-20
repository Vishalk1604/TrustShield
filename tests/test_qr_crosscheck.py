"""QR cross-verification (plan §10 Phase 3).

The high-value logic — does the card's QR agree with the printed/OCR'd value? — is pure and tested
deterministically here (no QR image needed). Decoding itself is exercised gracefully (a non-QR image
must yield no findings and never raise)."""

from PIL import Image

from services.forensics.app.ingest.extract import qr_codes


def test_pan_mismatch_flagged():
    findings = qr_codes.cross_check({"pan": "PATPK4316K"}, ocr_pan="PATPK4316", ocr_aadhaar=None)
    assert findings and findings[0]["severity"] == "high"
    assert findings[0]["values"]["qr_pan"] == "PATPK4316K"
    assert findings[0]["values"]["printed_pan"] == "PATPK4316"


def test_pan_match_clean():
    assert qr_codes.cross_check({"pan": "PATPK4316K"}, ocr_pan="patpk4316k", ocr_aadhaar=None) == []


def test_aadhaar_signature_invalid_flagged():
    findings = qr_codes.cross_check({"aadhaar_qr": {"signature_valid": False, "last4": "1234"}},
                                    ocr_pan=None, ocr_aadhaar=None)
    assert any("signature" in f["title"].lower() for f in findings)


def test_aadhaar_last4_mismatch_flagged():
    findings = qr_codes.cross_check({"aadhaar_qr": {"signature_valid": None, "last4": "5678"}},
                                    ocr_pan=None, ocr_aadhaar="XXXX XXXX 1234")
    assert any("aadhaar" in f["title"].lower() for f in findings)


def test_unknown_signature_and_matching_last4_clean():
    findings = qr_codes.cross_check({"aadhaar_qr": {"signature_valid": None, "last4": "1234"}},
                                    ocr_pan=None, ocr_aadhaar="XXXX XXXX 1234")
    assert findings == []


def test_ids_from_plaintext_payload():
    ids = qr_codes.ids_from_payloads([{"text": "Name: VISHAL KARUN PAN: PATPK4316K DOB 16/08/2005",
                                       "bytes": b"...", "type": "QRCODE"}])
    assert ids.get("pan") == "PATPK4316K"


def test_decode_is_graceful_on_non_qr_image(tmp_path):
    p = tmp_path / "plain.png"
    Image.new("RGB", (200, 120), (240, 240, 240)).save(p)
    assert qr_codes.decode_qrs(str(p)) == []           # no QR → empty, no raise
    findings, info = qr_codes.qr_check(str(p), {"pan": "PATPK4316K"})
    assert findings == [] and info["qr_found"] == 0
