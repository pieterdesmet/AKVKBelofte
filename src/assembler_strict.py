"""
Strict document assembler. Output ONLY valid JSON, exact schema, rule-based confidence.
confidence_score = round(100 - (2 * unresolved_placeholders) - (5 * high_risk_flags))
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Regex matches {{dotted.path}} placeholders (e.g. {{pand.gemeente}}, {{titel_adres}})
_PLACEHOLDER_RE = re.compile(r"\{\{([\w.]+)\}\}")


def _resolve_dot_path(data: dict, path: str) -> str | None:
    """Resolve a dot-notation path against a nested dict. Returns string or None."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    if current is None:
        return None
    return str(current)


def _fill_placeholders(text, dossier, unresolved_list, clause_id):
    def replacer(match):
        path = match.group(1)
        val = _resolve_dot_path(dossier, path)
        if val is not None:
            return val
        unresolved_list.append({"placeholder": f"{{{{{path}}}}}", "clause_id": clause_id, "reason": "missing"})
        return match.group(0)
    return _PLACEHOLDER_RE.sub(replacer, text)


def _expand_party(content_nl, persons, clause_id, unresolved_list):
    split_match = re.search(r"\.\s+(Verklaren\b)", content_nl)
    if split_match:
        tpl = content_nl[: split_match.start() + 1]
        tail = content_nl[split_match.start() + 2 :]
    else:
        tpl = content_nl
        tail = ""
    parts = []
    for p in persons:
        pv = {
            "titel_adres": p.get("titel_adres"),
            "voornaam": p.get("voornaam"),
            "naam": p.get("naam"),
            "woonadres_volledig": p.get("adres"),
            "geboorteplaats": p.get("geboorteplaats"),
            "geboortedatum": p.get("geboortedatum"),
            "rijksregisternummer": p.get("rijksregisternummer"),
            "burgerlijke_staat": p.get("burgerlijke_staat"),
        }
        parts.append(_fill_placeholders(tpl, pv, unresolved_list, clause_id))
    result = "\n".join(parts)
    if tail:
        result += "\n" + tail
    return result


def assemble_strict(dossier: dict, selection: dict) -> dict:
    unresolved: list[dict] = []
    used: list[str] = []
    text_parts: list[str] = []

    for clause in selection["selected_clauses"]:
        cid = clause["id"]
        cnl = clause["content_nl"]
        used.append(cid)

        if cid == "PARTIJEN_01":
            text_parts.append(_expand_party(cnl, dossier["partijen"]["verkopers"], cid, unresolved))
            continue
        if cid == "PARTIJEN_02":
            text_parts.append(_expand_party(cnl, dossier["partijen"]["kopers"], cid, unresolved))
            continue
        if clause["subtype"] == "fixed":
            text_parts.append(cnl)
        else:
            text_parts.append(_fill_placeholders(cnl, dossier, unresolved, cid))

    # Count high risk flags
    high_risk_count = sum(
        1 for rf in selection.get("risk_flags", [])
        if rf.get("risk_level") == "high"
    )

    # Rule-based confidence
    confidence_score = round(100 - (2 * len(unresolved)) - (5 * high_risk_count))
    confidence_score = max(0, min(100, confidence_score))

    flags: list[dict] = []

    # Merge risk_flags from selection into assembled flags
    for rf in selection.get("risk_flags", []):
        flags.append({
            "type": rf.get("type", "risk_flag"),
            "clause_id": rf["clause_id"],
            "risk_level": rf["risk_level"],
            "detail": rf["flag"],
        })

    # Add unresolved placeholder flags
    for u in unresolved:
        flags.append({
            "type": "unresolved_placeholder",
            "placeholder": u["placeholder"],
            "clause_id": u["clause_id"],
        })

    return {
        "document_text": "\n\n".join(text_parts),
        "used_clauses": used,
        "unresolved_placeholders": unresolved,
        "flags": flags,
        "confidence_score": confidence_score,
    }


def main():
    dossier_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/dossier_001.json")
    selection_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("examples/dossier_001_clause_selection.json")
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("examples/dossier_001_assembled_strict.json")

    with open(dossier_path, "r", encoding="utf-8") as f:
        dossier = json.load(f)
    with open(selection_path, "r", encoding="utf-8") as f:
        selection = json.load(f)

    result = assemble_strict(dossier, selection)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
