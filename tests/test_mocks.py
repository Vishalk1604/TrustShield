"""Tests for the mock external-verification adapters — including a hard no-network guard."""

import socket

import pytest

from shared.mocks import (
    ADAPTERS,
    AisAdapter,
    CersaiAdapter,
    GstinAdapter,
    Mca21Adapter,
)


def test_all_adapters_load_fixtures():
    for name, cls in ADAPTERS.items():
        adapter = cls()
        keys = adapter.available_keys()
        assert keys, f"{name} adapter has no fixture data"


def test_known_lookup_returns_record():
    r = AisAdapter().verify("ABMPS1234F")
    assert r.found is True
    assert r.status == "active"
    assert r.source == "local_mock_fixture"
    assert r.data["reported_income"] == 1820000


def test_missing_lookup_is_not_found_and_does_not_raise():
    r = AisAdapter().verify("DOES_NOT_EXIST")
    assert r.found is False
    assert r.status == "not_found"
    assert r.data == {}


def test_convenience_accessors():
    assert AisAdapter().reported_income("CDNPV5678L") == 1450000
    assert GstinAdapter().legal_name("29KLMPS7777N1Z5") == "Singh Traders"
    assert Mca21Adapter().is_active("L72200KA1981PLC013115") is True
    assert len(CersaiAdapter().existing_charges("GHJPR3456M")) == 1
    assert CersaiAdapter().existing_charges("ABMPS1234F") == []


def test_cersai_charge_carries_property_id():
    """The tampered-EC packet (Sneha, property SY-058/1A) must have a queryable CERSAI charge so
    the Phase 2 EC-vs-registry cross-check has something to contradict the forged 'NIL' EC."""
    charges = CersaiAdapter().existing_charges("GHJPR3456M")
    assert charges and charges[0]["property_id"] == "SY-058/1A"
    assert charges[0]["lender"] == "HDFC Bank"


def test_cersai_lookup_by_property():
    cersai = CersaiAdapter()
    hits = cersai.charges_for_property("SY-058/1A")
    assert len(hits) == 1
    assert hits[0]["pan"] == "GHJPR3456M" and hits[0]["lender"] == "HDFC Bank"
    assert cersai.charges_for_property("SY-000/0") == []


def test_adapters_make_no_network_calls(monkeypatch):
    """If any adapter touched the network, constructing a socket would explode."""
    def _boom(*args, **kwargs):
        raise RuntimeError("network access attempted by a mock adapter")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)

    for cls in ADAPTERS.values():
        adapter = cls()
        for key in adapter.available_keys():
            result = adapter.verify(key)
            assert result.source == "local_mock_fixture"
            break  # one lookup per adapter is enough to exercise the read path
