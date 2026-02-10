"""
Strict document assembler. Output ONLY valid JSON, exact schema, rule-based confidence.
confidence_score = round(100 - (2 * unresolved_placeholders) - (5 * high_risk_flags))
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _parse_pand_adres(adres: str) -> dict:
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
    pm: dict[str, str | None] = {}
    pand = dossier.get("pand", {})
    pm["type_pand"] = pand.get("pandtype")
    pm["kadastraal_inkomen"] = str(pand["ki"]) if pand.get("ki") is not None else None
    if pand.get("adres"):
        pm.update(_parse_pand_adres(pand["adres"]))
    if pand.get("kadaster"):
        pm.update(_parse_kadaster(pand["kadaster"]))
    tx = dossier.get("transactie", {})
    pm["verkoopprijs"] = str(tx["verkoopsprijs"]) if tx.get("verkoopsprijs") is not None else None
    pm["voorschot"] = str(tx["waarborg"]) if tx.get("waarborg") is not None else None
    return pm


def _fill_placeholders(text, values, unresolved_list, clause_id):
    def replacer(match):
        key = match.group(1)
        val = values.get(key)
        if val is not None:
            return val
        unresolved_list.append({"placeholder": f"{{{{{key}}}}}", "clause_id": clause_id, "reason": "missing"})
        return match.group(0)
    return re.sub(r"\{\{(\w+)\}\}", replacer, text)


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
    pm = _build_placeholder_map(dossier)
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
            text_parts.append(_fill_placeholders(cnl, pm, unresolved, cid))

    # Count high risk flags
    high_risk_count = sum(
        1 for rf in selection.get("risk_flags", [])
        if rf.get("risk_level") == "high"
    )

    # Rule-based confidence
    confidence_score = round(100 - (2 * len(unresolved)) - (5 * high_risk_count))
    confidence_score = max(0, min(100, confidence_score))

    flags = [
        {"type": "unresolved_placeholder", "placeholder": u["placeholder"], "clause_id": u["clause_id"]}
        for u in unresolved
    ]

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
