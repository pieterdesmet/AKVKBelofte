"""
Document assembler for tweezijdige aankoopbelofte.

STRICT RULES:
- NO new text.
- NO rewriting, improving, reformatting, summarizing or reordering.
- ONLY concatenate EXACT content_nl from selected clauses in given order.
- ONLY fill placeholders with values from dossier JSON.
- If a placeholder cannot be filled: leave {{placeholder}} and add a flag.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _parse_pand_adres(adres: str) -> dict:
    """Parse 'Berkenlaan 14, 2220 Heist-op-den-Berg' into components."""
    result = {}
    parts = adres.split(", ", 1)
    if len(parts) == 2:
        straat_num = parts[0].rsplit(" ", 1)
        result["straat"] = straat_num[0] if len(straat_num) == 2 else parts[0]
        result["huisnummer"] = straat_num[1] if len(straat_num) == 2 else None
        post_gem = parts[1].split(" ", 1)
        result["postcode"] = post_gem[0] if len(post_gem) == 2 else None
        result["gemeente"] = post_gem[1] if len(post_gem) == 2 else parts[1]
    return result


def _parse_kadaster(kadaster: str) -> dict:
    """Parse '1e afdeling, sectie C, nummer 312K, oppervlakte 620 m²'."""
    result = {}
    m = re.search(r"(\S+)\s+afdeling", kadaster)
    if m:
        result["afdeling"] = m.group(1)
    m = re.search(r"sectie\s+(\S+)", kadaster)
    if m:
        result["sectie"] = m.group(1).rstrip(",")
    m = re.search(r"nummer\s+(\S+)", kadaster)
    if m:
        result["perceelnummer"] = m.group(1).rstrip(",")
    m = re.search(r"oppervlakte\s+(\d+)", kadaster)
    if m:
        result["oppervlakte"] = m.group(1)
    return result


def _build_placeholder_map(dossier: dict) -> dict:
    """Build a flat placeholder → value map from dossier data."""
    pm: dict[str, str | None] = {}

    # Pand fields
    pand = dossier.get("pand", {})
    pm["type_pand"] = pand.get("pandtype")
    pm["kadastraal_inkomen"] = str(pand["ki"]) if pand.get("ki") is not None else None

    if pand.get("adres"):
        parsed = _parse_pand_adres(pand["adres"])
        pm["straat"] = parsed.get("straat")
        pm["huisnummer"] = parsed.get("huisnummer")
        pm["postcode"] = parsed.get("postcode")
        pm["gemeente"] = parsed.get("gemeente")

    if pand.get("kadaster"):
        parsed = _parse_kadaster(pand["kadaster"])
        pm.update(parsed)

    # Transactie fields
    tx = dossier.get("transactie", {})
    pm["verkoopprijs"] = str(tx["verkoopsprijs"]) if tx.get("verkoopsprijs") is not None else None
    pm["voorschot"] = str(tx["waarborg"]) if tx.get("waarborg") is not None else None

    # Fields not in dossier — will remain unresolved
    pm["notaris_verkoper"] = None
    pm["notaris_koper"] = None
    pm["asbest_optie"] = None
    pm["bodem_verklaring"] = None
    pm["datum_bodemattest"] = None
    pm["referentie_bodemattest"] = None
    pm["inhoud_bodemattest"] = None

    return pm


def _fill_placeholders(
    text: str,
    values: dict[str, str | None],
    unresolved: list[dict],
    clause_id: str,
) -> str:
    """Replace {{placeholder}} with values. Track unresolved ones."""
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        val = values.get(key)
        if val is not None:
            return val
        unresolved.append({
            "placeholder": f"{{{{{key}}}}}",
            "clause_id": clause_id,
            "reason": f"Geen waarde gevonden in dossier voor '{key}'",
        })
        return match.group(0)  # leave {{placeholder}} as-is

    return re.sub(r"\{\{(\w+)\}\}", replacer, text)


def _expand_party_clause(
    content_nl: str,
    persons: list[dict],
    clause_id: str,
    unresolved: list[dict],
) -> str:
    """Expand a party clause for each person, filling per-person placeholders."""
    # Split content into per-person template and shared tail
    # The per-person part ends at the first sentence that doesn't contain placeholders
    # For PARTIJEN_01/02: the personal part is before "Verklaren..."
    # Find the split point: first sentence starting with "Verklaren" or "Hoofdelijk"
    split_match = re.search(r"\.\s+(Verklaren\b)", content_nl)
    if split_match:
        per_person_template = content_nl[: split_match.start() + 1]
        shared_tail = content_nl[split_match.start() + 2 :]
    else:
        per_person_template = content_nl
        shared_tail = ""

    parts = []
    for person in persons:
        person_values = {
            "titel_adres": person.get("titel_adres"),
            "voornaam": person.get("voornaam"),
            "naam": person.get("naam"),
            "woonadres_volledig": person.get("adres"),
            "geboorteplaats": person.get("geboorteplaats"),
            "geboortedatum": person.get("geboortedatum"),
            "rijksregisternummer": person.get("rijksregisternummer"),
            "burgerlijke_staat": person.get("burgerlijke_staat"),
        }
        filled = _fill_placeholders(per_person_template, person_values, unresolved, clause_id)
        parts.append(filled)

    result = "\n".join(parts)
    if shared_tail:
        result += "\n" + shared_tail
    return result


def assemble(dossier: dict, selection: dict) -> dict:
    """Assemble document from dossier data and selected clauses."""
    placeholder_map = _build_placeholder_map(dossier)
    unresolved: list[dict] = []
    flags: list[dict] = []
    used_clauses: list[str] = []
    text_parts: list[str] = []

    for clause in selection["selected_clauses"]:
        clause_id = clause["id"]
        content_nl = clause["content_nl"]
        used_clauses.append(clause_id)

        # Party clauses: expand per person
        if clause_id == "PARTIJEN_01":
            assembled = _expand_party_clause(
                content_nl,
                dossier["partijen"]["verkopers"],
                clause_id,
                unresolved,
            )
            text_parts.append(assembled)
            continue

        if clause_id == "PARTIJEN_02":
            assembled = _expand_party_clause(
                content_nl,
                dossier["partijen"]["kopers"],
                clause_id,
                unresolved,
            )
            text_parts.append(assembled)
            continue

        # All other clauses: fill placeholders from global map
        if clause["subtype"] == "fixed":
            text_parts.append(content_nl)
        else:
            filled = _fill_placeholders(content_nl, placeholder_map, unresolved, clause_id)
            text_parts.append(filled)

    # Propagate risk_flags from selection as assembly flags
    for rf in selection.get("risk_flags", []):
        flags.append({
            "type": rf.get("type", "risk_flag"),
            "clause_id": rf["clause_id"],
            "detail": rf["flag"],
        })

    # Add unresolved placeholder flags
    for ur in unresolved:
        flags.append({
            "type": "unresolved_placeholder",
            "clause_id": ur["clause_id"],
            "detail": f"Placeholder {ur['placeholder']} niet ingevuld: {ur['reason']}",
        })

    # Confidence score
    total_placeholders = sum(
        len(re.findall(r"\{\{\w+\}\}", c["content_nl"]))
        for c in selection["selected_clauses"]
    )
    # Count party clause placeholders per person
    for c in selection["selected_clauses"]:
        if c["id"] == "PARTIJEN_01":
            n = len(dossier["partijen"]["verkopers"])
            per_person = len(re.findall(r"\{\{\w+\}\}", c["content_nl"].split(". Verklaren")[0]))
            total_placeholders += per_person * (n - 1)  # already counted once
        elif c["id"] == "PARTIJEN_02":
            n = len(dossier["partijen"]["kopers"])
            per_person = len(re.findall(r"\{\{\w+\}\}", c["content_nl"].split(". Verklaren")[0]))
            total_placeholders += per_person * (n - 1)

    resolved_count = total_placeholders - len(unresolved)
    confidence = round((resolved_count / total_placeholders) * 100) if total_placeholders > 0 else 0

    document_text = "\n\n".join(text_parts)

    return {
        "document_text": document_text,
        "used_clauses": used_clauses,
        "unresolved_placeholders": [
            {"placeholder": u["placeholder"], "clause_id": u["clause_id"]}
            for u in unresolved
        ],
        "flags": flags,
        "confidence_score": confidence,
    }


def main() -> None:
    dossier_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/dossier_001.json")
    selection_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("examples/dossier_001_clause_selection.json")
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("examples/dossier_001_assembled.json")

    with open(dossier_path, "r", encoding="utf-8") as f:
        dossier = json.load(f)
    with open(selection_path, "r", encoding="utf-8") as f:
        selection = json.load(f)

    result = assemble(dossier, selection)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Assembled: {len(result['used_clauses'])} clauses, "
          f"{len(result['unresolved_placeholders'])} unresolved, "
          f"confidence {result['confidence_score']}%")


if __name__ == "__main__":
    main()
