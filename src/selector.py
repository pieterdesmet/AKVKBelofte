"""
Clause selection engine.
Evaluates activation rules from the clause library against dossier data.
Generates risk flags. Never invents legal text or draws legal conclusions (GN-001).

Guardrails:
- Activation rules evaluate ONLY on dossier paths via simple equals checks.
- All derived variables are explicitly logged in "derived_fields" with source path.
- Per-clause activation evaluation is logged in "activation_evaluation".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _resolve_dot_path(data: dict, path: str) -> Any:
    """Resolve a dot-notation path against a nested dict."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


# Each derived field: (variable_name, source_dossier_path, derivation_logic_description)
_DERIVATION_SPECS = [
    {
        "variable": "bodem_optie",
        "source_path": "attesten.bodem",
        "logic": "attesten.bodem == 'ok' → GEEN_RISICOGROND; anders → WEL_RISICOGROND",
    },
    {
        "variable": "financiering_vereist",
        "source_path": "financiering_status",
        "logic": "financiering_status != 'bevestigd' → true; anders → false",
    },
    {
        "variable": "bouwvergunning_voor_2001",
        "source_path": "pand.bouwjaar",
        "logic": "pand.bouwjaar < 2001 → true; anders → false",
    },
]


def _derive_activation_vars(dossier: dict) -> tuple[dict[str, str], list[dict]]:
    """
    Derive activation variables from dossier data for rule matching.
    Returns (activation_vars, derived_fields_log).
    Each derived variable is traceable back to its source dossier field.
    """
    v: dict[str, str] = {}
    log: list[dict] = []

    # bodem_optie: attesten.bodem == "ok" → GEEN_RISICOGROND
    bodem = _resolve_dot_path(dossier, "attesten.bodem")
    if bodem == "ok":
        v["bodem_optie"] = "GEEN_RISICOGROND"
    elif bodem:
        v["bodem_optie"] = "WEL_RISICOGROND"
    log.append({
        "variable": "bodem_optie",
        "source_path": "attesten.bodem",
        "source_value": bodem,
        "derived_value": v.get("bodem_optie"),
        "logic": _DERIVATION_SPECS[0]["logic"],
    })

    # financiering_vereist: financiering_status != "bevestigd"
    fin = dossier.get("financiering_status")
    if fin and fin != "bevestigd":
        v["financiering_vereist"] = "true"
    else:
        v["financiering_vereist"] = "false"
    log.append({
        "variable": "financiering_vereist",
        "source_path": "financiering_status",
        "source_value": fin,
        "derived_value": v["financiering_vereist"],
        "logic": _DERIVATION_SPECS[1]["logic"],
    })

    # bouwvergunning_voor_2001: pand.bouwjaar < 2001
    bouwjaar = _resolve_dot_path(dossier, "pand.bouwjaar")
    if bouwjaar is not None and int(bouwjaar) < 2001:
        v["bouwvergunning_voor_2001"] = "true"
    else:
        v["bouwvergunning_voor_2001"] = "false"
    log.append({
        "variable": "bouwvergunning_voor_2001",
        "source_path": "pand.bouwjaar",
        "source_value": bouwjaar,
        "derived_value": v["bouwvergunning_voor_2001"],
        "logic": _DERIVATION_SPECS[2]["logic"],
    })

    return v, log


def _evaluate_rule(rule: str, activation_vars: dict[str, str]) -> bool:
    """Evaluate a single activation rule like 'bodem_optie == GEEN_RISICOGROND'."""
    parts = rule.strip().split(" == ", 1)
    if len(parts) != 2:
        return False
    key, expected = parts[0].strip(), parts[1].strip()
    return activation_vars.get(key) == expected


def _evaluate_activation(rules: list[str], activation_vars: dict[str, str]) -> tuple[bool, str]:
    """Evaluate all activation rules for a clause. Returns (active, reason)."""
    if not rules:
        return True, "always-on"
    for rule in rules:
        if not _evaluate_rule(rule, activation_vars):
            return False, f"Activation rule '{rule}' niet voldaan"
    # Build descriptive reason
    reasons = []
    for rule in rules:
        parts = rule.strip().split(" == ", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            reasons.append(f"{key} == {activation_vars.get(key, '?')} → rule matched")
    return True, "; ".join(reasons) if reasons else "activation rules matched"


def _generate_risk_flags(dossier: dict, selected_clauses: list[dict]) -> list[dict]:
    """Generate risk flags based on dossier data and selected clauses. GN-001 compliant."""
    flags: list[dict] = []

    # Elektriciteit niet conform → human_review_required
    elek = _resolve_dot_path(dossier, "attesten.elektriciteit")
    if elek == "niet_conform":
        flags.append({
            "clause_id": "VERKL_ELEC_01",
            "risk_level": "high",
            "type": "human_review_required",
            "source_field": "attesten.elektriciteit",
            "source_value": elek,
            "flag": (
                "Elektrische installatie niet conform. Clausetekst verwijst naar gevolgen bij "
                "niet-conformiteit. Exacte juridische implicatie (herstelplicht, prijsvermindering, "
                "informatieverplichting) vereist beoordeling door jurist of makelaar op basis van de "
                "concrete clausetekst en dossiercontext. Engine trekt hier geen conclusie."
            ),
        })

    # Financiering lopend → opschortende voorwaarde actief
    fin = dossier.get("financiering_status")
    if fin and fin != "bevestigd":
        flags.append({
            "clause_id": "OPSCH_FIN_01",
            "risk_level": "high",
            "source_field": "financiering_status",
            "source_value": fin,
            "flag": (
                "Financiering niet bevestigd. Opschortende voorwaarde actief. "
                "Verzakingstermijn 14 kalenderdagen na dagtekening. Twee attesten "
                "Belgische financiële instellingen vereist bij weigering."
            ),
        })

    # requires_jurist → medium risk
    for clause in selected_clauses:
        if clause.get("requires_jurist"):
            flags.append({
                "clause_id": clause["id"],
                "risk_level": "medium",
                "source_field": None,
                "source_value": None,
                "flag": "Clause requires_jurist=true. Standaard review bij ondertekening.",
            })

    return flags


def select_clauses(dossier: dict, library: list[dict]) -> dict:
    """
    Select clauses from library based on activation rules and dossier data.
    Returns selection result with selected_clauses, risk_flags, skipped_clause_ids,
    activation_evaluation (per-clause log), and derived_fields (transparency).
    """
    dossier_id = dossier.get("dossier_id", "unknown")
    activation_vars, derived_fields = _derive_activation_vars(dossier)

    selected: list[dict] = []
    skipped: list[dict] = []
    activation_evaluation: list[dict] = []

    for clause in library:
        cid = clause["id"]
        rules = clause.get("activation", [])
        active, reason = _evaluate_activation(rules, activation_vars)

        activation_evaluation.append({
            "clause_id": cid,
            "rules": rules,
            "evaluated": active,
            "reason": reason,
        })

        if active:
            selected.append({**clause, "activation_reason": reason})
        else:
            skipped.append({"id": cid, "reason": reason})

    risk_flags = _generate_risk_flags(dossier, selected)

    high = sum(1 for f in risk_flags if f["risk_level"] == "high")
    medium = sum(1 for f in risk_flags if f["risk_level"] == "medium")
    low = sum(1 for f in risk_flags if f["risk_level"] == "low")

    return {
        "dossier_id": dossier_id,
        "clause_library": "clauses_v0.2.json",
        "selection_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected_clause_ids": [c["id"] for c in selected],
        "selected_clauses": selected,
        "risk_flags": risk_flags,
        "skipped_clause_ids": skipped,
        "validated_against": list(activation_vars.items()),
        "derived_fields": derived_fields,
        "activation_evaluation": activation_evaluation,
        "summary": {
            "total_in_library": len(library),
            "selected": len(selected),
            "skipped": len(skipped),
            "risk_flags_high": high,
            "risk_flags_medium": medium,
            "risk_flags_low": low,
            "requires_jurist_count": sum(1 for c in selected if c.get("requires_jurist")),
        },
    }
