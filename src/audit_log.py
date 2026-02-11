"""
Append-only audit log for CIB contract generation events.

Writes one JSON object per line to ``logs/cib_audit.log``.
Auto-creates the ``logs/`` directory if it does not exist.

Logging never blocks generation — all I/O is wrapped in try/except.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "cib_audit.log"


def _sha256_hash(data: Any) -> str:
    """Return SHA-256 hex digest of the JSON-serialised *data*."""
    serialised = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def log_cib_generation(event: dict) -> None:
    """Append *event* as a single JSON line to the audit log.

    Never raises — prints a warning to stderr on failure.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(
            f"[AUDIT WARNING] Could not write audit log: {exc}",
            file=sys.stderr,
        )


def build_audit_event(
    result: dict,
    gate_state: dict[str, Any],
    dossier: dict,
    clause_catalog_version: str,
) -> dict:
    """Build a structured audit event from generation result + inputs."""
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "dossier_id": result.get("dossier_id", "unknown"),
        "legal_user": (
            gate_state.get("legal_user")
            or dossier.get("managerId")
            or "unknown"
        ),
        "readiness_status": result["readiness_status"],
        "selected_clause_ids": [c["id"] for c in result["selected_clauses"]],
        "flags": [
            {
                "type": f["type"],
                "clause_id": f.get("clause_id", ""),
                "risk_level": f["risk_level"],
            }
            for f in result["flags"]
        ],
        "confidence": result["confidence_score"],
        "gate_state": gate_state,
        "omnicasa_data_hash": _sha256_hash(dossier),
        "clause_catalog_version": clause_catalog_version,
    }
