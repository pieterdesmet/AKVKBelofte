"""
Snapshot tests for fixture dossiers.
Runs the full pipeline on each fixture and asserts deterministic outputs
against stored expected snapshots in tests/snapshots/.

Guards against selector drift: any change in clause selection, risk flags,
confidence scoring, or placeholder resolution will fail these tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "examples" / "fixtures"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
LIBRARY_PATH = REPO_ROOT / "clause_library" / "clauses_v0.2.json"

# Fixture definitions: (fixture_filename, dossier_id, short description)
FIXTURES = [
    ("f1_happy_path_confirmed_financing.json", "fixture_f1", "happy path: all ok, financing confirmed"),
    ("f2_financing_lopend.json", "fixture_f2", "financing lopend → OPSCH_FIN_01 high risk"),
    ("f3_electricity_niet_conform.json", "fixture_f3", "elektriciteit niet_conform → VERKL_ELEC_01 high risk"),
    ("f4_bodem_risico.json", "fixture_f4", "bodem risico → BODEM_02 instead of BODEM_01"),
    ("f5_bouwjaar_2005_no_asbest.json", "fixture_f5", "bouwjaar 2005 → VERKL_ASBEST_01 skipped"),
    ("f6_missing_required_field.json", "fixture_f6", "missing notaris.verkoper + bodemattest.inhoud → unresolved"),
]


def _load_expected(fixture_name: str) -> dict:
    """Load the expected snapshot for a fixture."""
    # fixture_name like "f1_happy_path_confirmed_financing.json" → snapshot "f1.expected.json"
    snap_key = fixture_name.split("_")[0]  # "f1", "f2", etc.
    snap_path = SNAPSHOTS_DIR / f"{snap_key}.expected.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_pipeline(fixture_file: str, tmp_path: Path) -> tuple[dict, dict]:
    """Run pipeline and return (selection, assembled) dicts."""
    fixture_path = FIXTURES_DIR / fixture_file
    outdir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable, "-m", "src.generate",
            str(fixture_path),
            "--library", str(LIBRARY_PATH),
            "--outdir", str(outdir),
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Pipeline failed for {fixture_file}:\n{result.stderr}"

    # Read dossier_id from fixture to find output files
    with open(fixture_path, "r", encoding="utf-8") as f:
        dossier_id = json.load(f)["dossier_id"]

    with open(outdir / f"{dossier_id}.selection.json", "r", encoding="utf-8") as f:
        selection = json.load(f)
    with open(outdir / f"{dossier_id}.assembled.json", "r", encoding="utf-8") as f:
        assembled = json.load(f)

    return selection, assembled


@pytest.mark.parametrize(
    "fixture_file,dossier_id,description",
    FIXTURES,
    ids=[f[1] for f in FIXTURES],
)
class TestFixtureSnapshot:
    """Snapshot tests: compare pipeline output against stored expected values."""

    def test_selected_clause_ids_exact_match(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: selected_clause_ids must match snapshot exactly (order + content)."""
        expected = _load_expected(fixture_file)
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        assert selection["selected_clause_ids"] == expected["selected_clause_ids"], (
            f"[{dossier_id}] selected_clause_ids drift detected"
        )

    def test_skipped_clause_ids_match(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: skipped clause IDs must match snapshot."""
        expected = _load_expected(fixture_file)
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        actual_skipped = [s["id"] for s in selection["skipped_clause_ids"]]
        assert actual_skipped == expected["skipped_clause_ids"], (
            f"[{dossier_id}] skipped_clause_ids drift detected"
        )

    def test_risk_flags_high_count(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: high risk flag count must match snapshot."""
        expected = _load_expected(fixture_file)
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        assert selection["summary"]["risk_flags_high"] == expected["risk_flags_high"], (
            f"[{dossier_id}] risk_flags_high drift: "
            f"got {selection['summary']['risk_flags_high']}, expected {expected['risk_flags_high']}"
        )

    def test_risk_flags_high_clause_ids(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: high risk flag clause IDs must match snapshot."""
        expected = _load_expected(fixture_file)
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        actual_high = [f["clause_id"] for f in selection["risk_flags"] if f["risk_level"] == "high"]
        assert actual_high == expected["risk_flags_high_clause_ids"], (
            f"[{dossier_id}] risk_flags_high clause_ids drift"
        )

    def test_confidence_score(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: confidence_score must match snapshot exactly."""
        expected = _load_expected(fixture_file)
        _, assembled = _run_pipeline(fixture_file, tmp_path)
        assert assembled["confidence_score"] == expected["confidence_score"], (
            f"[{dossier_id}] confidence drift: "
            f"got {assembled['confidence_score']}, expected {expected['confidence_score']}"
        )

    def test_unresolved_count(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: unresolved placeholder count must match snapshot."""
        expected = _load_expected(fixture_file)
        _, assembled = _run_pipeline(fixture_file, tmp_path)
        actual_count = len(assembled["unresolved_placeholders"])
        assert actual_count == expected["unresolved_count"], (
            f"[{dossier_id}] unresolved count drift: "
            f"got {actual_count}, expected {expected['unresolved_count']}"
        )

    def test_unresolved_placeholders_match(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: exact unresolved placeholder names must match snapshot."""
        expected = _load_expected(fixture_file)
        _, assembled = _run_pipeline(fixture_file, tmp_path)
        actual = [u["placeholder"] for u in assembled["unresolved_placeholders"]]
        assert actual == expected["unresolved_placeholders"], (
            f"[{dossier_id}] unresolved placeholders drift"
        )

    def test_selection_has_guardrail_fields(self, fixture_file, dossier_id, description, tmp_path):
        """Guard: selection output must contain anti-drift guardrail fields."""
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        assert "derived_fields" in selection, "Missing derived_fields in selection output"
        assert "activation_evaluation" in selection, "Missing activation_evaluation in selection output"
        assert len(selection["derived_fields"]) == 3, "Expected 3 derived fields"
        assert len(selection["activation_evaluation"]) == 30, "Expected 30 clause evaluations (full library)"


@pytest.mark.parametrize(
    "fixture_file,dossier_id,description",
    FIXTURES,
    ids=[f[1] for f in FIXTURES],
)
class TestFixtureOutputSchema:
    """Schema validation: ensure all outputs have required keys."""

    def test_assembled_schema(self, fixture_file, dossier_id, description, tmp_path):
        _, assembled = _run_pipeline(fixture_file, tmp_path)
        for key in ("document_text", "used_clauses", "unresolved_placeholders", "flags", "confidence_score"):
            assert key in assembled, f"Missing key '{key}' in assembled output"

    def test_selection_schema(self, fixture_file, dossier_id, description, tmp_path):
        selection, _ = _run_pipeline(fixture_file, tmp_path)
        for key in ("selected_clause_ids", "selected_clauses", "risk_flags", "skipped_clause_ids", "validated_against"):
            assert key in selection, f"Missing key '{key}' in selection output"

    def test_risk_flags_merged_in_assembled(self, fixture_file, dossier_id, description, tmp_path):
        """Risk flags from selection must be present in assembled flags."""
        selection, assembled = _run_pipeline(fixture_file, tmp_path)
        risk_count = len(selection["risk_flags"])
        merged = [f for f in assembled["flags"] if f["type"] != "unresolved_placeholder"]
        assert len(merged) == risk_count, (
            f"Expected {risk_count} risk flags in assembled, got {len(merged)}"
        )
