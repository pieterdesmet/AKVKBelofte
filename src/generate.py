"""
Single entrypoint CLI for the full contract generation pipeline.

Usage:
    python -m src.generate [dossier_path] [--library PATH] [--outdir PATH] [--strict]

Pipeline:
    1. Load dossier JSON
    2. Validate → write <dossier_id>.validation.json
    3. Select clauses → write <dossier_id>.selection.json
    4. Assemble document → write <dossier_id>.assembled.json
    5. Export plain text → write <dossier_id>.contract.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .selector import select_clauses
from .assembler_strict import assemble_strict


def _validate_dossier_raw(dossier: dict) -> dict:
    """
    Lightweight dossier validation operating directly on the raw JSON dict.
    Checks structural requirements without requiring the full ContractInput model,
    which expects a different schema (eigendom vs pand, etc.).
    Returns a validation result dict.
    """
    flags: list[dict] = []

    def _flag(field: str, msg: str, severity: str = "required") -> None:
        flags.append({"field": field, "message": msg, "severity": severity})

    # Partijen
    partijen = dossier.get("partijen", {})
    verkopers = partijen.get("verkopers", [])
    kopers = partijen.get("kopers", [])

    if not verkopers:
        _flag("partijen.verkopers", "Geen verkopers opgegeven (minimum 1 vereist)")
    for i, v in enumerate(verkopers):
        for field in ("naam", "voornaam", "adres", "geboortedatum"):
            if not v.get(field):
                _flag(f"partijen.verkopers[{i}].{field}", f"Verkoper {i+1}: {field} ontbreekt")

    if not kopers:
        _flag("partijen.kopers", "Geen kopers opgegeven (minimum 1 vereist)")
    for i, k in enumerate(kopers):
        for field in ("naam", "voornaam", "adres", "geboortedatum"):
            if not k.get(field):
                _flag(f"partijen.kopers[{i}].{field}", f"Koper {i+1}: {field} ontbreekt")

    # Pand
    pand = dossier.get("pand", {})
    if not pand:
        _flag("pand", "Pandgegevens ontbreken volledig")
    else:
        for field in ("pandtype", "straat", "huisnummer", "gemeente"):
            if not pand.get(field):
                _flag(f"pand.{field}", f"Pand: {field} ontbreekt")
        kadaster = pand.get("kadaster", {})
        if not kadaster:
            _flag("pand.kadaster", "Kadastrale gegevens ontbreken")

    # Transactie
    tx = dossier.get("transactie", {})
    if not tx.get("verkoopsprijs"):
        _flag("transactie.verkoopsprijs", "Verkoopprijs ontbreekt")
    if not tx.get("waarborg"):
        _flag("transactie.waarborg", "Waarborg/optieprijs ontbreekt")

    # Notaris (recommended)
    if not dossier.get("notaris"):
        _flag("notaris", "Notarisgegevens ontbreken", severity="recommended")

    # Bodemattest (recommended)
    ba = dossier.get("bodemattest")
    if ba:
        if not ba.get("datum"):
            _flag("bodemattest.datum", "Datum bodemattest ontbreekt", severity="recommended")
        if not ba.get("referentie"):
            _flag("bodemattest.referentie", "Referentie bodemattest ontbreekt", severity="recommended")

    required_missing = sum(1 for f in flags if f["severity"] == "required")
    recommended_missing = sum(1 for f in flags if f["severity"] == "recommended")

    return {
        "dossier_id": dossier.get("dossier_id", "unknown"),
        "is_valid": required_missing == 0,
        "total_required_missing": required_missing,
        "total_recommended_missing": recommended_missing,
        "flags": flags,
    }


def run_pipeline(
    dossier_path: Path,
    library_path: Path,
    outdir: Path,
) -> dict:
    """
    Run the full generation pipeline and write all artifacts.
    Returns the assembled result dict for programmatic use.
    """
    # Load inputs
    with open(dossier_path, "r", encoding="utf-8") as f:
        dossier = json.load(f)
    with open(library_path, "r", encoding="utf-8") as f:
        library = json.load(f)

    dossier_id = dossier.get("dossier_id", "unknown")
    outdir.mkdir(parents=True, exist_ok=True)

    # Step 1: Validate
    validation = _validate_dossier_raw(dossier)
    val_path = outdir / f"{dossier_id}.validation.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    # Step 2: Select clauses
    selection = select_clauses(dossier, library)
    sel_path = outdir / f"{dossier_id}.selection.json"
    with open(sel_path, "w", encoding="utf-8") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    # Step 3: Assemble (strict)
    assembled = assemble_strict(dossier, selection)
    asm_path = outdir / f"{dossier_id}.assembled.json"
    with open(asm_path, "w", encoding="utf-8") as f:
        json.dump(assembled, f, ensure_ascii=False, indent=2)

    # Step 4: Export plain text
    txt_path = outdir / f"{dossier_id}.contract.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(assembled["document_text"])

    return assembled


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate tweezijdige aankoopbelofte from dossier JSON.",
    )
    parser.add_argument(
        "dossier_path",
        nargs="?",
        default="examples/dossier_001.json",
        help="Path to dossier JSON (default: examples/dossier_001.json)",
    )
    parser.add_argument(
        "--library",
        default="clause_library/clauses_v0.2.json",
        help="Path to clause library JSON (default: clause_library/clauses_v0.2.json)",
    )
    parser.add_argument(
        "--outdir",
        default="examples/out",
        help="Output directory (default: examples/out)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Use strict assembler (default: true)",
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

    assembled = run_pipeline(dossier_path, library_path, outdir)

    # Load selection for summary stats
    with open(dossier_path, "r", encoding="utf-8") as f:
        dossier = json.load(f)
    dossier_id = dossier.get("dossier_id", "unknown")

    with open(outdir / f"{dossier_id}.selection.json", "r", encoding="utf-8") as f:
        selection = json.load(f)

    high_risk = selection["summary"]["risk_flags_high"]

    print(f"dossier_id:              {dossier_id}")
    print(f"selected_clauses:        {len(assembled['used_clauses'])}")
    print(f"unresolved_placeholders: {len(assembled['unresolved_placeholders'])}")
    print(f"risk_flags_high:         {high_risk}")
    print(f"confidence_score:        {assembled['confidence_score']}")
    print(f"outputs:")
    print(f"  validation:  {outdir / f'{dossier_id}.validation.json'}")
    print(f"  selection:   {outdir / f'{dossier_id}.selection.json'}")
    print(f"  assembled:   {outdir / f'{dossier_id}.assembled.json'}")
    print(f"  contract:    {outdir / f'{dossier_id}.contract.txt'}")


if __name__ == "__main__":
    main()
