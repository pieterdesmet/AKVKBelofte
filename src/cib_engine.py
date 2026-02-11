"""
CIB decision engine.

Selects applicable CIB clauses based on:
  a) Omnicasa property data (dossier fields)
  b) Upload presence flags (bodemattest, keuring, etc.)
  c) Legal Gate confirmations (explicit user choices)

Assembles a CIB-structured document: Partijen → Eigendom → A … H.
Never invents or paraphrases legal text.  Only selects and fills placeholders.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

ENGINE_VERSION = "0.1.0"

from src.cib_catalog import CIB_CLAUSES, CIB_SECTIONS, SECTION_ORDER, VERSION as CATALOG_VERSION
from src.legal_gate import evaluate_gate, prefill_from_dossier, GATE_ITEMS_BY_ID
from src.audit_log import build_audit_event, log_cib_generation

# ---------------------------------------------------------------------------
# Placeholder handling (reuses pattern from assembler_strict)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([\w.]+)\}\}")


def _resolve_dot(data: dict, path: str) -> str | None:
    """Resolve a dot-notation path.  Returns string or None."""
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


def _fill_placeholders(
    text: str,
    data: dict,
    unresolved: list[dict],
    clause_id: str,
) -> str:
    """Replace {{path}} tokens with data values.  Track unresolved."""

    def replacer(match: re.Match) -> str:
        path = match.group(1)
        val = _resolve_dot(data, path)
        if val is not None:
            return val
        unresolved.append({
            "placeholder": f"{{{{{path}}}}}",
            "clause_id": clause_id,
            "reason": "missing",
        })
        return match.group(0)

    return _PLACEHOLDER_RE.sub(replacer, text)


def _expand_party_block(
    text_block: str,
    persons: list[dict],
    clause_id: str,
    unresolved: list[dict],
) -> str:
    """Expand a party template for each person in the list."""
    # Split off the collective declaration (after first period + space + capital)
    split_match = re.search(r"\.\s+((?:Verklaren|Hierna)\b)", text_block)
    if split_match:
        tpl = text_block[: split_match.start() + 1]
        tail = text_block[split_match.start() + 2:]
    else:
        tpl = text_block
        tail = ""

    parts: list[str] = []
    for p in persons:
        person_data = {
            "titel_adres": p.get("titel_adres"),
            "voornaam": p.get("voornaam"),
            "naam": p.get("naam"),
            "woonadres_volledig": p.get("adres"),
            "geboorteplaats": p.get("geboorteplaats"),
            "geboortedatum": p.get("geboortedatum"),
            "rijksregisternummer": p.get("rijksregisternummer"),
            "burgerlijke_staat": p.get("burgerlijke_staat"),
        }
        parts.append(_fill_placeholders(tpl, person_data, unresolved, clause_id))

    result = "\n".join(parts)
    if tail:
        result += "\n" + tail
    return result


# ---------------------------------------------------------------------------
# Trigger derivation
# ---------------------------------------------------------------------------

def derive_trigger_values(dossier: dict, gate_state: dict[str, Any]) -> dict[str, Any]:
    """
    Compute trigger values used to match clause triggers.
    Sources: dossier fields + legal gate state.
    Returns a flat dict of trigger_name → value.
    """
    triggers: dict[str, Any] = {}

    # From gate state (user-confirmed or pre-filled)
    triggers["bodem_variant"] = gate_state.get("bodem_variant")
    triggers["mede_eigendom"] = gate_state.get("mede_eigendom")
    triggers["voorkooprecht"] = gate_state.get("voorkooprecht")
    triggers["elektriciteit_variant"] = gate_state.get("elektriciteit_variant")

    # financiering_vereist: True unless financiering_status == "bevestigd"
    fin = dossier.get("financiering_status")
    triggers["financiering_vereist"] = fin is not None and fin != "bevestigd"

    # asbest_vereist: True when bouwjaar < 2001
    bouwjaar = _resolve_dot(dossier, "pand.bouwjaar")
    if bouwjaar is not None:
        triggers["asbest_vereist"] = int(bouwjaar) < 2001
    else:
        triggers["asbest_vereist"] = False

    # epc_renovation_required: True when EPC label >= D
    epc_label = gate_state.get("epc_label")
    if epc_label and epc_label in ("D", "E", "F"):
        triggers["epc_renovation_required"] = True
    else:
        triggers["epc_renovation_required"] = False

    return triggers


# ---------------------------------------------------------------------------
# Clause selection
# ---------------------------------------------------------------------------

def _clause_triggers_match(
    clause_triggers: dict[str, Any],
    derived: dict[str, Any],
) -> bool:
    """Return True if all clause trigger conditions are met."""
    if not clause_triggers:
        return True  # always-on clause
    for key, expected in clause_triggers.items():
        actual = derived.get(key)
        if actual != expected:
            return False
    return True


def _gate_requires_met(
    clause: dict,
    gate_state: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Check whether legal gate requirements for a clause are satisfied.
    Returns (met, list_of_unmet_gate_ids).
    """
    requires = clause.get("legal_gate_requires", [])
    if not requires:
        return True, []
    unmet: list[str] = []
    for gate_id in requires:
        gate_item = GATE_ITEMS_BY_ID.get(gate_id)
        if gate_item is None:
            continue
        value = gate_state.get(gate_id)
        if gate_item.input_type == "checkbox":
            if value is not True:
                unmet.append(gate_id)
        elif gate_item.input_type == "select":
            if value is None or value == "onbekend":
                unmet.append(gate_id)
    return len(unmet) == 0, unmet


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def generate_cib_document(
    dossier: dict,
    gate_state: dict[str, Any] | None = None,
) -> dict:
    """
    Main entry point for CIB document generation.

    Args:
        dossier: Full dossier dict (partijen, pand, transactie, etc.)
        gate_state: Legal gate state dict.  If None, pre-filled from dossier.

    Returns dict with keys:
        gate_result        – legal gate evaluation
        trigger_values     – derived trigger values for transparency
        selected_clauses   – list of selected clause dicts with metadata
        skipped_clauses    – list of {id, reason}
        sections           – ordered list of {section_id, title, clauses: [{id, title, text}]}
        document_text      – assembled full text
        unresolved_placeholders – list of {placeholder, clause_id, reason}
        cib_text_required  – list of clause ids where CIB text is still needed
        flags              – list of flag dicts
        readiness_status   – CIB-aware status
        confidence_score   – 0-100
        next_actions       – list of action strings
    """
    if gate_state is None:
        gate_state = prefill_from_dossier(dossier)

    # 1. Evaluate legal gate
    gate_result = evaluate_gate(gate_state, dossier)

    # 2. Derive trigger values
    trigger_values = derive_trigger_values(dossier, gate_state)

    # 3. Select clauses
    selected: list[dict] = []
    skipped: list[dict] = []
    cib_text_required: list[str] = []

    for clause in CIB_CLAUSES:
        cid = clause["id"]

        # Check trigger match
        if not _clause_triggers_match(clause["triggers"], trigger_values):
            skipped.append({"id": cid, "reason": "Trigger niet voldaan"})
            continue

        # Check gate requirements
        gate_met, unmet_gates = _gate_requires_met(clause, gate_state)

        selected.append({
            **clause,
            "gate_met": gate_met,
            "unmet_gates": unmet_gates,
        })

        if clause["text_block"] == "CIB_TEXT_REQUIRED":
            cib_text_required.append(cid)

    # 4. Assemble sections
    unresolved: list[dict] = []
    sections: list[dict] = []
    text_parts: list[str] = []

    for section_def in CIB_SECTIONS:
        sid = section_def["id"]
        section_clauses = [c for c in selected if c["section"] == sid]
        section_clauses.sort(key=lambda c: c["order_in_section"])

        if not section_clauses:
            continue

        section_texts: list[dict] = []
        section_header = f"{'=' * 60}\n{section_def['title'].upper()}\n{'=' * 60}"
        text_parts.append(section_header)

        for clause in section_clauses:
            cid = clause["id"]
            text_block = clause["text_block"]

            # CIB_TEXT_REQUIRED → leave marker
            if text_block == "CIB_TEXT_REQUIRED":
                rendered = f"[CIB_TEXT_REQUIRED: {clause['title']}]"
            # Party blocks: expand for each person
            elif clause["subtype"] == "party":
                if cid == "CIB_PARTIJ_VERKOPER":
                    persons = dossier.get("partijen", {}).get("verkopers", [])
                elif cid == "CIB_PARTIJ_KOPER":
                    persons = dossier.get("partijen", {}).get("kopers", [])
                else:
                    persons = []
                rendered = _expand_party_block(text_block, persons, cid, unresolved)
            # Parametric: fill placeholders
            elif clause["subtype"] == "parametric":
                rendered = _fill_placeholders(text_block, dossier, unresolved, cid)
            # Fixed: verbatim
            else:
                rendered = text_block

            section_texts.append({
                "id": cid,
                "title": clause["title"],
                "text": rendered,
                "blocking_level": clause["blocking_level"],
                "gate_met": clause["gate_met"],
                "unmet_gates": clause["unmet_gates"],
            })
            text_parts.append(f"--- {clause['title']} ---\n{rendered}")

        sections.append({
            "section_id": sid,
            "title": section_def["title"],
            "clauses": section_texts,
        })

    # 5. Risk flags
    flags: list[dict] = []

    # CIB_TEXT_REQUIRED flags (hard-blocking)
    cib_text_required_details: list[dict] = []
    for clause in selected:
        if clause["text_block"] == "CIB_TEXT_REQUIRED":
            cib_text_required_details.append({
                "id": clause["id"],
                "title": clause["title"],
            })
    for item in cib_text_required_details:
        flags.append({
            "type": "cib_text_required",
            "clause_id": item["id"],
            "risk_level": "high",
            "detail": f"Exacte CIB-tekst ontbreekt voor {item['id']} ({item['title']}) — generatie geblokkeerd",
        })

    # Unresolved placeholder flags
    for u in unresolved:
        flags.append({
            "type": "unresolved_placeholder",
            "clause_id": u["clause_id"],
            "risk_level": "high",
            "detail": f"Placeholder {u['placeholder']} niet ingevuld",
            "placeholder": u["placeholder"],
        })

    # Clauses with blocking_level == "required"
    for clause in selected:
        if clause["blocking_level"] == "required":
            flags.append({
                "type": "jurist_review_required",
                "clause_id": clause["id"],
                "risk_level": "medium",
                "detail": f"Clausule {clause['id']} vereist juridische review",
            })

    # Clauses with blocking_level == "ask"
    for clause in selected:
        if clause["blocking_level"] == "ask":
            flags.append({
                "type": "ask_confirmation",
                "clause_id": clause["id"],
                "risk_level": "medium",
                "detail": f"Clausule {clause['id']} vereist bevestiging (ambigue data)",
            })

    # Unmet gate requirements on selected clauses
    for clause in selected:
        if not clause["gate_met"]:
            flags.append({
                "type": "gate_not_met",
                "clause_id": clause["id"],
                "risk_level": "high",
                "detail": (
                    f"Legal Gate niet voldaan voor {clause['id']}: "
                    f"ontbrekend: {', '.join(clause['unmet_gates'])}"
                ),
            })

    # 6. Confidence score
    high_flags = sum(1 for f in flags if f["risk_level"] == "high")
    medium_flags = sum(1 for f in flags if f["risk_level"] == "medium")
    confidence_score = round(100 - (5 * high_flags) - (2 * medium_flags))
    confidence_score = max(0, min(100, confidence_score))

    # 7. Readiness status + next actions
    next_actions: list[str] = []

    jurist_required_ids = [
        c["id"] for c in selected if c["blocking_level"] == "required"
    ]
    jurist_recommended_ids = [
        c["id"] for c in selected if c["blocking_level"] == "ask"
    ]

    if not gate_result["cleared"]:
        readiness_status = "GATE_BLOCKED"
        next_actions.append(
            f"Legal Gate niet volledig: {gate_result['confirmed_count']}/{gate_result['total_blocking_count']} bevestigd"
        )
        for item in gate_result["blocking_items"][:5]:
            next_actions.append(f"  → {item['label']}: {item['reason']}")
        if gate_result["ask_items"]:
            next_actions.append("Omnicasa data ambigu — Legal moet volgende items bevestigen:")
            for item in gate_result["ask_items"]:
                next_actions.append(f"  → {item['label']}")
    elif cib_text_required:
        readiness_status = "DRAFT_BLOCKED"
        next_actions.append(
            "CIB-tekst ontbreekt — generatie geblokkeerd. "
            "Vul de exacte CIB-tekst aan voor:"
        )
        for item in cib_text_required_details:
            next_actions.append(f"  → {item['id']}: {item['title']}")
    elif len(unresolved) > 0:
        readiness_status = "DRAFT_BLOCKED"
        next_actions.append(
            "Vul ontbrekende velden aan: "
            + ", ".join(u["placeholder"] for u in unresolved)
        )
    elif high_flags > 0 or len(jurist_required_ids) > 0:
        readiness_status = "DRAFT_REVIEW_REQUIRED"
        next_actions.append("Juridische review verplicht")
        if jurist_required_ids:
            next_actions.append(
                "Jurist review verplicht voor: " + ", ".join(jurist_required_ids)
            )
        if cib_text_required:
            next_actions.append(
                "CIB-tekst nog aanvullen voor: " + ", ".join(cib_text_required)
            )
    elif medium_flags > 0 or len(jurist_recommended_ids) > 0:
        readiness_status = "DRAFT_REVIEW_RECOMMENDED"
        next_actions.append("Juridische review aanbevolen")
    else:
        readiness_status = "DRAFT_OK"
        next_actions.append("Klaar voor interne review en voorbereiding handtekening.")

    result = {
        "dossier_id": dossier.get("dossier_id", "unknown"),
        "generation_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_result": gate_result,
        "trigger_values": trigger_values,
        "selected_clauses": [
            {"id": c["id"], "title": c["title"], "blocking_level": c["blocking_level"]}
            for c in selected
        ],
        "skipped_clauses": skipped,
        "sections": sections,
        "document_text": "\n\n".join(text_parts),
        "unresolved_placeholders": unresolved,
        "cib_text_required": cib_text_required,
        "flags": flags,
        "readiness_status": readiness_status,
        "confidence_score": confidence_score,
        "next_actions": next_actions,
        "summary": {
            "total_clauses_in_catalog": len(CIB_CLAUSES),
            "selected_count": len(selected),
            "skipped_count": len(skipped),
            "sections_count": len(sections),
            "unresolved_count": len(unresolved),
            "cib_text_required_count": len(cib_text_required),
            "flags_high": high_flags,
            "flags_medium": medium_flags,
            "jurist_required_count": len(jurist_required_ids),
            "gate_cleared": gate_result["cleared"],
        },
    }

    # Audit log — never blocks generation
    try:
        audit_event = build_audit_event(
            result, gate_state, dossier, CATALOG_VERSION,
            engine_version=ENGINE_VERSION,
        )
        log_cib_generation(audit_event)
    except Exception:  # noqa: BLE001
        import sys
        print("[AUDIT WARNING] Audit logging failed", file=sys.stderr)

    return result
