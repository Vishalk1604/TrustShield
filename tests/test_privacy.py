"""Phase 7 tests — PII redaction for logs.

Verifies the maskers, dict redaction, and the logging filter scrub PAN, account
numbers, and property IDs — the "grep a demo run's logs -> no raw PII" check.
"""

from __future__ import annotations

import json
import logging

from shared.privacy import (
    PIIRedactionFilter,
    install_log_redaction,
    mask_accounts,
    mask_pan,
    mask_property_ids,
    redact_mapping,
    redact_text,
)

# A real PAN + property id from the synthetic roster, used as leak canaries.
LEAK_PAN = "ABMPS1234F"
LEAK_PROPERTY = "SY-911/2C"
LEAK_ACCOUNT = "501200123456789"  # 15-digit account-like number


class TestMaskers:
    def test_mask_pan_keeps_first_two_last_one(self):
        out = mask_pan(LEAK_PAN)
        assert out == "AB*******F"
        assert LEAK_PAN not in out

    def test_mask_pan_in_sentence(self):
        out = mask_pan(f"applicant PAN {LEAK_PAN} verified")
        assert LEAK_PAN not in out
        assert "AB*******F" in out

    def test_mask_accounts_keeps_last_four(self):
        out = mask_accounts(f"credited to {LEAK_ACCOUNT} today")
        assert LEAK_ACCOUNT not in out
        assert out.endswith("6789 today")

    def test_mask_accounts_ignores_short_amounts(self):
        # A 7-digit income figure must NOT be masked as an account number.
        assert mask_accounts("income 1820000 rupees") == "income 1820000 rupees"

    def test_mask_property_ids(self):
        out = mask_property_ids(f"property {LEAK_PROPERTY} pledged")
        assert LEAK_PROPERTY not in out
        assert "SY-***" in out

    def test_redact_text_combines_all(self):
        text = f"PAN {LEAK_PAN}, acct {LEAK_ACCOUNT}, prop {LEAK_PROPERTY}"
        out = redact_text(text)
        for leak in (LEAK_PAN, LEAK_ACCOUNT, LEAK_PROPERTY):
            assert leak not in out


class TestDictRedaction:
    def test_pii_keys_masked_whole(self):
        d = {
            "applicant_name": "Rahul Sharma",
            "pan": LEAK_PAN,
            "property_id": LEAK_PROPERTY,
            "loan_amount": 5000000,
        }
        out = redact_mapping(d)
        assert "Rahul Sharma" not in json.dumps(out)
        assert LEAK_PAN not in json.dumps(out)
        assert LEAK_PROPERTY not in json.dumps(out)
        # non-PII numeric value preserved
        assert out["loan_amount"] == 5000000

    def test_nested_and_freetext(self):
        d = {"note": f"see PAN {LEAK_PAN}", "docs": [{"owner_name": "Priya Verma"}]}
        out = redact_mapping(d)
        blob = json.dumps(out)
        assert LEAK_PAN not in blob
        assert "Priya Verma" not in blob

    def test_account_numbers_list_key(self):
        d = {"account_numbers": [LEAK_ACCOUNT]}
        out = redact_mapping(d)
        assert LEAK_ACCOUNT not in json.dumps(out)


class TestLoggingFilter:
    def test_filter_scrubs_log_record(self, caplog):
        logger = logging.getLogger("trustshield.test.redact")
        logger.setLevel(logging.INFO)
        logger.addFilter(PIIRedactionFilter())
        with caplog.at_level(logging.INFO, logger="trustshield.test.redact"):
            logger.info("scoring packet for PAN %s on property %s", LEAK_PAN, LEAK_PROPERTY)
        text = caplog.text
        assert LEAK_PAN not in text
        assert LEAK_PROPERTY not in text

    def test_install_is_idempotent(self):
        logger = logging.getLogger("trustshield.test.idem")
        install_log_redaction(logger)
        install_log_redaction(logger)
        n = sum(1 for f in logger.filters if isinstance(f, PIIRedactionFilter))
        assert n == 1
