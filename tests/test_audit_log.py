"""
Tests for the CIB audit log system.

Covers:
- Log file creation and directory auto-creation
- JSON line structure and required fields
- Append-only behaviour (multiple calls do not overwrite)
- Generation does not fail when logging raises an exception
- SHA-256 hash consistency
"""

import json
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

from src.audit_log import (
    LOG_DIR,
    LOG_FILE,
    build_audit_event,
    log_cib_generation,
    _sha256_hash,
    _sha256_text,
)
from src.cib_catalog import VERSION as CATALOG_VERSION
from src.cib_engine import ENGINE_VERSION, generate_cib_document
from src.legal_gate import prefill_from_dossier

FIXTURES_DIR = Path(__file__).parent.parent / "examples" / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_cleared_gate(dossier: dict) -> dict:
    gate = prefill_from_dossier(dossier)
    if gate.get("bodem_variant") is None:
        gate["bodem_variant"] = "geen_risicogrond"
    if gate.get("mede_eigendom") is None:
        gate["mede_eigendom"] = "nee"
    if gate.get("voorkooprecht") is None or gate.get("voorkooprecht") == "onbekend":
        gate["voorkooprecht"] = "nee"
    if gate.get("elektriciteit_variant") is None:
        gate["elektriciteit_variant"] = "conform"
    if gate.get("epc_label") is None:
        gate["epc_label"] = "B"
    gate["bodemattest_uploaded"] = True
    gate["epc_uploaded"] = True
    gate["elektriciteit_keuring_uploaded"] = True
    gate["asbest_uploaded"] = True
    gate["overstromingszone"] = True
    gate["stedenbouwkundig_uittreksel_uploaded"] = True
    gate["syndicus_info_received"] = True
    return gate


# Use a temporary log directory so tests don't pollute the real one.
@pytest.fixture(autouse=True)
def _isolate_log_dir(tmp_path, monkeypatch):
    """Redirect audit log to a temp directory for every test."""
    tmp_log_dir = tmp_path / "logs"
    tmp_log_file = tmp_log_dir / "cib_audit.log"
    monkeypatch.setattr("src.audit_log.LOG_DIR", tmp_log_dir)
    monkeypatch.setattr("src.audit_log.LOG_FILE", tmp_log_file)
    yield tmp_log_dir, tmp_log_file


# ===========================================================================
# Unit tests for audit_log module
# ===========================================================================

class TestLogCIBGeneration:
    def test_log_file_created(self, _isolate_log_dir):
        _, log_file = _isolate_log_dir
        log_cib_generation({"test": True})
        assert log_file.exists()

    def test_log_dir_auto_created(self, _isolate_log_dir):
        log_dir, log_file = _isolate_log_dir
        # Dir should not exist yet
        assert not log_dir.exists()
        log_cib_generation({"test": True})
        assert log_dir.exists()
        assert log_file.exists()

    def test_json_line_valid(self, _isolate_log_dir):
        _, log_file = _isolate_log_dir
        event = {"dossier_id": "test_001", "status": "OK"}
        log_cib_generation(event)
        line = log_file.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["dossier_id"] == "test_001"
        assert parsed["status"] == "OK"

    def test_append_not_overwrite(self, _isolate_log_dir):
        _, log_file = _isolate_log_dir
        log_cib_generation({"call": 1})
        log_cib_generation({"call": 2})
        log_cib_generation({"call": 3})
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0])["call"] == 1
        assert json.loads(lines[1])["call"] == 2
        assert json.loads(lines[2])["call"] == 3

    def test_does_not_raise_on_write_failure(self, _isolate_log_dir, monkeypatch, tmp_path):
        """Logging must never block generation."""
        # Create a file where the directory is expected → mkdir will fail
        blocker = tmp_path / "blocker_file"
        blocker.write_text("x")
        monkeypatch.setattr("src.audit_log.LOG_DIR", blocker)
        monkeypatch.setattr("src.audit_log.LOG_FILE", blocker / "cib_audit.log")
        # Should NOT raise
        log_cib_generation({"should": "not crash"})

    def test_prints_warning_on_failure(self, _isolate_log_dir, monkeypatch, capsys, tmp_path):
        blocker = tmp_path / "blocker_file"
        blocker.write_text("x")
        monkeypatch.setattr("src.audit_log.LOG_DIR", blocker)
        monkeypatch.setattr("src.audit_log.LOG_FILE", blocker / "cib_audit.log")
        log_cib_generation({"test": True})
        captured = capsys.readouterr()
        assert "AUDIT WARNING" in captured.err


# ===========================================================================
# build_audit_event tests
# ===========================================================================

class TestBuildAuditEvent:
    def _make_result_and_inputs(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        return result, gate, dossier

    def test_required_fields_present(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION,
                                  engine_version=ENGINE_VERSION)
        required = {
            "timestamp", "dossier_id", "legal_user",
            "readiness_status", "selected_clause_ids", "flags",
            "confidence", "gate_state", "omnicasa_data_hash",
            "document_hash", "clause_catalog_version",
            "engine_version", "app_version",
        }
        assert required.issubset(set(event.keys()))

    def test_timestamp_iso_format(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        # Should parse without error
        ts = event["timestamp"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_dossier_id_matches(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert event["dossier_id"] == dossier["dossier_id"]

    def test_catalog_version_matches(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert event["clause_catalog_version"] == CATALOG_VERSION

    def test_omnicasa_hash_is_sha256(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        h = event["omnicasa_data_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_omnicasa_hash_deterministic(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        h1 = _sha256_hash(dossier)
        h2 = _sha256_hash(dossier)
        assert h1 == h2

    def test_omnicasa_hash_changes_on_different_input(self):
        d1 = _load_fixture("f1_happy_path_confirmed_financing.json")
        d2 = _load_fixture("f2_financing_lopend.json")
        assert _sha256_hash(d1) != _sha256_hash(d2)

    def test_gate_state_snapshot_included(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert event["gate_state"] == gate

    def test_flags_structure(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        for f in event["flags"]:
            assert "type" in f
            assert "risk_level" in f

    def test_legal_user_from_dossier_managerid(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        dossier["managerId"] = "mgr_42"
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert event["legal_user"] == "mgr_42"

    def test_legal_user_from_gate_state(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        gate["legal_user"] = "jurist_jan"
        result = generate_cib_document(dossier, gate)
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        # gate_state legal_user takes precedence
        assert event["legal_user"] == "jurist_jan"

    # ── document_hash tests ────────────────────────────────────────────

    def test_document_hash_exists_and_is_sha256(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        h = event["document_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_document_hash_deterministic(self):
        result, gate, dossier = self._make_result_and_inputs()
        e1 = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        e2 = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert e1["document_hash"] == e2["document_hash"]

    def test_document_hash_equals_sha256_of_document_text(self):
        """Hash must be sha256 of the raw document_text, not JSON-serialised."""
        import hashlib
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        expected = hashlib.sha256(
            result["document_text"].encode("utf-8")
        ).hexdigest()
        assert event["document_hash"] == expected

    def test_document_hash_differs_for_different_document(self):
        d1 = _load_fixture("f1_happy_path_confirmed_financing.json")
        d2 = _load_fixture("f2_financing_lopend.json")
        g1 = _make_cleared_gate(d1)
        g2 = _make_cleared_gate(d2)
        r1 = generate_cib_document(d1, g1)
        r2 = generate_cib_document(d2, g2)
        e1 = build_audit_event(r1, g1, d1, CATALOG_VERSION)
        e2 = build_audit_event(r2, g2, d2, CATALOG_VERSION)
        assert e1["document_hash"] != e2["document_hash"]

    # ── version fields tests ───────────────────────────────────────────

    def test_engine_version_included(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION,
                                  engine_version=ENGINE_VERSION)
        assert event["engine_version"] == ENGINE_VERSION

    def test_app_version_included(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION,
                                  app_version="0.1.0")
        assert event["app_version"] == "0.1.0"

    def test_version_defaults_to_unknown(self):
        result, gate, dossier = self._make_result_and_inputs()
        event = build_audit_event(result, gate, dossier, CATALOG_VERSION)
        assert event["engine_version"] == "unknown"
        assert event["app_version"] == "unknown"


# ===========================================================================
# Integration: engine writes audit log
# ===========================================================================

class TestEngineAuditIntegration:
    def test_generation_writes_audit_line(self, _isolate_log_dir):
        _, log_file = _isolate_log_dir
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        generate_cib_document(dossier, gate)
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        event = json.loads(lines[-1])
        assert event["dossier_id"] == "fixture_f1"
        assert event["engine_version"] == ENGINE_VERSION
        assert event["clause_catalog_version"] == CATALOG_VERSION

    def test_generation_succeeds_when_logging_fails(self, monkeypatch):
        """Generation must never fail because of an audit log error."""
        def _failing_log(event):
            raise OSError("disk full")

        monkeypatch.setattr("src.cib_engine.log_cib_generation", _failing_log)
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert "readiness_status" in result

    def test_multiple_generations_append(self, _isolate_log_dir):
        _, log_file = _isolate_log_dir
        d1 = _load_fixture("f1_happy_path_confirmed_financing.json")
        d2 = _load_fixture("f2_financing_lopend.json")
        g1 = _make_cleared_gate(d1)
        g2 = _make_cleared_gate(d2)
        generate_cib_document(d1, g1)
        generate_cib_document(d2, g2)
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2
        assert json.loads(lines[-2])["dossier_id"] == "fixture_f1"
        assert json.loads(lines[-1])["dossier_id"] == "fixture_f2"
