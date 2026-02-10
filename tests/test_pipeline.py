"""
Smoke tests for the full generation pipeline CLI.
Runs python -m src.generate on dossier_001 and verifies all output artifacts.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DOSSIER_PATH = REPO_ROOT / "examples" / "dossier_001.json"
LIBRARY_PATH = REPO_ROOT / "clause_library" / "clauses_v0.2.json"


@pytest.fixture
def outdir(tmp_path):
    """Provide a clean temp output directory."""
    return tmp_path / "out"


class TestPipelineCLI:
    def _run_pipeline(self, outdir, extra_args=None):
        cmd = [
            sys.executable, "-m", "src.generate",
            str(DOSSIER_PATH),
            "--library", str(LIBRARY_PATH),
            "--outdir", str(outdir),
        ]
        if extra_args:
            cmd.extend(extra_args)
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        return result

    def test_pipeline_runs_successfully(self, outdir):
        result = self._run_pipeline(outdir)
        assert result.returncode == 0, f"Pipeline failed:\n{result.stderr}"

    def test_outdir_created(self, outdir):
        self._run_pipeline(outdir)
        assert outdir.exists()
        assert outdir.is_dir()

    def test_assembled_json_valid(self, outdir):
        self._run_pipeline(outdir)
        asm_path = outdir / "dossier_001.assembled.json"
        assert asm_path.exists(), "assembled.json not found"
        with open(asm_path) as f:
            data = json.load(f)
        assert "document_text" in data
        assert "used_clauses" in data
        assert "unresolved_placeholders" in data
        assert "flags" in data
        assert "confidence_score" in data
        assert "readiness_status" in data
        assert "next_actions" in data

    def test_contract_txt_exists_and_not_empty(self, outdir):
        self._run_pipeline(outdir)
        txt_path = outdir / "dossier_001.contract.txt"
        assert txt_path.exists(), "contract.txt not found"
        content = txt_path.read_text(encoding="utf-8")
        assert len(content) > 100, "contract.txt is too short"

    def test_confidence_score_90(self, outdir):
        """With dossier_001: 2 high risk flags, 0 unresolved → confidence = 90."""
        self._run_pipeline(outdir)
        with open(outdir / "dossier_001.assembled.json") as f:
            data = json.load(f)
        assert data["confidence_score"] == 90

    def test_zero_unresolved_placeholders(self, outdir):
        self._run_pipeline(outdir)
        with open(outdir / "dossier_001.assembled.json") as f:
            data = json.load(f)
        assert len(data["unresolved_placeholders"]) == 0

    def test_risk_flags_merged_in_assembled(self, outdir):
        """Risk flags from selection must appear in assembled.json flags."""
        self._run_pipeline(outdir)
        with open(outdir / "dossier_001.assembled.json") as f:
            data = json.load(f)
        risk_flags = [f for f in data["flags"] if f["type"] != "unresolved_placeholder"]
        assert len(risk_flags) >= 2, "Expected at least 2 risk flags in assembled output"

    def test_validation_json_written(self, outdir):
        self._run_pipeline(outdir)
        val_path = outdir / "dossier_001.validation.json"
        assert val_path.exists()
        with open(val_path) as f:
            data = json.load(f)
        assert "is_valid" in data

    def test_selection_json_written(self, outdir):
        self._run_pipeline(outdir)
        sel_path = outdir / "dossier_001.selection.json"
        assert sel_path.exists()
        with open(sel_path) as f:
            data = json.load(f)
        assert "selected_clause_ids" in data
        assert "selected_clauses" in data
        assert "risk_flags" in data
        assert "skipped_clause_ids" in data
        assert "validated_against" in data

    def test_stdout_summary(self, outdir):
        result = self._run_pipeline(outdir)
        assert "dossier_id:" in result.stdout
        assert "confidence_score:" in result.stdout
        assert "90" in result.stdout
