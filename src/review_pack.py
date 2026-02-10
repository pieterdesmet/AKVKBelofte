"""
Legal review pack generator.

Generates a folder per dossier with all artifacts needed for jurist/makelaar review:
- assembled.json (full assembled output incl. readiness_status + next_actions)
- selection.json (clause selection with activation evaluation)
- risk_flags.json (extracted risk flags for quick review)
- jurist_review.json (jurist_required + jurist_recommended clause lists)
- review_checklist.txt (human-readable checklist with 4-status explanation)

Usage:
    python -m src.review_pack <fixture_path> [--library PATH] [--outdir PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .selector import select_clauses
from .assembler_strict import assemble_strict


def generate_review_pack(
    dossier_path: Path,
    library_path: Path,
    outdir: Path,
) -> Path:
    """
    Generate a legal review pack for a single dossier.
    Returns the path to the generated review pack folder.
    """
    with open(dossier_path, "r", encoding="utf-8") as f:
        dossier = json.load(f)
    with open(library_path, "r", encoding="utf-8") as f:
        library = json.load(f)

    dossier_id = dossier.get("dossier_id", "unknown")

    # Run pipeline
    selection = select_clauses(dossier, library)
    assembled = assemble_strict(dossier, selection)

    # Create review pack folder
    pack_dir = outdir / dossier_id
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write assembled.json
    with open(pack_dir / "assembled.json", "w", encoding="utf-8") as f:
        json.dump(assembled, f, ensure_ascii=False, indent=2)

    # 2. Write selection.json
    with open(pack_dir / "selection.json", "w", encoding="utf-8") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    # 3. Write risk_flags.json (extracted for quick review)
    risk_flags_data = {
        "dossier_id": dossier_id,
        "readiness_status": assembled["readiness_status"],
        "confidence_score": assembled["confidence_score"],
        "risk_flags": selection["risk_flags"],
        "risk_summary": {
            "high": selection["summary"]["risk_flags_high"],
            "medium": selection["summary"]["risk_flags_medium"],
            "low": selection["summary"]["risk_flags_low"],
        },
        "requires_jurist_clauses": [
            c["id"] for c in selection["selected_clauses"]
            if c.get("requires_jurist")
        ],
        "next_actions": assembled["next_actions"],
    }
    with open(pack_dir / "risk_flags.json", "w", encoding="utf-8") as f:
        json.dump(risk_flags_data, f, ensure_ascii=False, indent=2)

    # 4. Write jurist_review.json
    jurist_review = selection.get("jurist_review_clauses", {})
    jurist_review_data = {
        "dossier_id": dossier_id,
        "jurist_required_count": selection["summary"].get("jurist_required_count", 0),
        "jurist_recommended_count": selection["summary"].get("jurist_recommended_count", 0),
        "jurist_required": jurist_review.get("required", []),
        "jurist_recommended": jurist_review.get("recommended", []),
    }
    with open(pack_dir / "jurist_review.json", "w", encoding="utf-8") as f:
        json.dump(jurist_review_data, f, ensure_ascii=False, indent=2)

    # 5. Write review_checklist.txt
    checklist_lines = [
        f"LEGAL REVIEW PACK — {dossier_id}",
        f"Gegenereerd: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Readiness status: {assembled['readiness_status']}",
        f"Confidence score: {assembled['confidence_score']}",
        "",
        "=" * 60,
        "READINESS STATUSSEN",
        "=" * 60,
        "  DRAFT_OK               — Klaar voor interne review en handtekening.",
        "  DRAFT_REVIEW_RECOMMENDED — Standaardclausules met aanbevolen jurist review.",
        "  DRAFT_REVIEW_REQUIRED  — Verplichte juridische review (hoog risico of bodem).",
        "  DRAFT_BLOCKED          — Ontbrekende velden, kan niet worden afgerond.",
        "",
        "=" * 60,
        "NEXT ACTIONS",
        "=" * 60,
    ]
    for i, action in enumerate(assembled["next_actions"], 1):
        checklist_lines.append(f"  {i}. {action}")
    if not assembled["next_actions"]:
        checklist_lines.append("  (geen)")

    checklist_lines.extend([
        "",
        "=" * 60,
        "RISICOVLAGGEN",
        "=" * 60,
    ])
    for rf in selection["risk_flags"]:
        checklist_lines.append(
            f"  [{rf['risk_level'].upper()}] {rf['clause_id']}: {rf['flag']}"
        )
    if not selection["risk_flags"]:
        checklist_lines.append("  (geen risicovlaggen)")

    checklist_lines.extend([
        "",
        "=" * 60,
        "JURIST REVIEW — REQUIRED",
        "=" * 60,
    ])
    req_ids = jurist_review.get("required", [])
    if req_ids:
        for cid in req_ids:
            checklist_lines.append(f"  - {cid}")
    else:
        checklist_lines.append("  (geen)")

    checklist_lines.extend([
        "",
        "=" * 60,
        "JURIST REVIEW — RECOMMENDED",
        "=" * 60,
    ])
    rec_ids = jurist_review.get("recommended", [])
    if rec_ids:
        for cid in rec_ids:
            checklist_lines.append(f"  - {cid}")
    else:
        checklist_lines.append("  (geen)")

    checklist_lines.extend([
        "",
        "=" * 60,
        "ONOPGELOSTE PLACEHOLDERS",
        "=" * 60,
    ])
    for u in assembled["unresolved_placeholders"]:
        checklist_lines.append(f"  - {u['placeholder']} (clausule: {u['clause_id']})")
    if not assembled["unresolved_placeholders"]:
        checklist_lines.append("  (geen)")

    checklist_lines.extend([
        "",
        "=" * 60,
        "GESELECTEERDE CLAUSULES ({count})".format(count=len(assembled["used_clauses"])),
        "=" * 60,
    ])
    for cid in assembled["used_clauses"]:
        checklist_lines.append(f"  - {cid}")

    checklist_lines.extend([
        "",
        "=" * 60,
        "OVERGESLAGEN CLAUSULES ({count})".format(
            count=len(selection["skipped_clause_ids"])
        ),
        "=" * 60,
    ])
    for s in selection["skipped_clause_ids"]:
        checklist_lines.append(f"  - {s['id']}: {s['reason']}")
    if not selection["skipped_clause_ids"]:
        checklist_lines.append("  (geen)")

    checklist_lines.append("")

    with open(pack_dir / "review_checklist.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(checklist_lines))

    return pack_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate legal review pack for a dossier.",
    )
    parser.add_argument(
        "dossier_path",
        help="Path to dossier JSON",
    )
    parser.add_argument(
        "--library",
        default="clause_library/clauses_v0.2.json",
        help="Path to clause library JSON (default: clause_library/clauses_v0.2.json)",
    )
    parser.add_argument(
        "--outdir",
        default="examples/review_packs",
        help="Output directory (default: examples/review_packs)",
    )
    args = parser.parse_args()

    dossier_path = Path(args.dossier_path)
    library_path = Path(args.library)
    outdir = Path(args.outdir)

    if not dossier_path.exists():
        print(f"ERROR: Dossier niet gevonden: {dossier_path}", file=sys.stderr)
        sys.exit(1)
    if not library_path.exists():
        print(f"ERROR: Clause library niet gevonden: {library_path}", file=sys.stderr)
        sys.exit(1)

    pack_dir = generate_review_pack(dossier_path, library_path, outdir)

    print(f"Review pack gegenereerd: {pack_dir}")
    print(f"  - assembled.json")
    print(f"  - selection.json")
    print(f"  - risk_flags.json")
    print(f"  - jurist_review.json")
    print(f"  - review_checklist.txt")


if __name__ == "__main__":
    main()
