"""
Clause resolver: loads clauses from the library and tracks which clauses
are used in a generated contract for full auditability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CLAUSE_LIBRARY_DIR = Path(__file__).parent.parent / "clause_library"


@dataclass
class ClauseUsage:
    """Record of a single clause being used in a contract."""
    clause_id: str
    clause_title: str
    section: str
    library_version: str
    selected_option: Optional[str] = None


@dataclass
class AuditTrail:
    """Full audit trail for a generated contract."""
    generated_at: str = ""
    library_file: str = ""
    library_version: str = ""
    clauses_used: list[ClauseUsage] = field(default_factory=list)
    missing_data_flags: list[dict[str, str]] = field(default_factory=list)

    def add_clause(self, clause: ClauseUsage) -> None:
        self.clauses_used.append(clause)

    def add_missing_flag(self, field_path: str, description: str, severity: str = "required") -> None:
        self.missing_data_flags.append({
            "field": field_path,
            "description": description,
            "severity": severity,
        })

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "library_file": self.library_file,
            "library_version": self.library_version,
            "clauses_used": [
                {
                    "clause_id": c.clause_id,
                    "clause_title": c.clause_title,
                    "section": c.section,
                    "library_version": c.library_version,
                    **({"selected_option": c.selected_option} if c.selected_option else {}),
                }
                for c in self.clauses_used
            ],
            "total_clauses_used": len(self.clauses_used),
            "missing_data_flags": self.missing_data_flags,
            "total_missing_flags": len(self.missing_data_flags),
        }


class ClauseResolver:
    """Loads and resolves clauses from the versioned clause library."""

    def __init__(self, library_filename: str = "tweezijdige_aankoopbelofte_v0.1.json"):
        self.library_path = CLAUSE_LIBRARY_DIR / library_filename
        self._library: Optional[dict] = None
        self.audit = AuditTrail()

    def load(self) -> dict:
        """Load the clause library from disk."""
        with open(self.library_path, "r", encoding="utf-8") as f:
            self._library = json.load(f)
        self.audit.library_file = self.library_path.name
        self.audit.library_version = self._library["version"]
        self.audit.generated_at = datetime.now(timezone.utc).isoformat()
        return self._library

    @property
    def library(self) -> dict:
        if self._library is None:
            self.load()
        return self._library  # type: ignore[return-value]

    def get_section(self, section_key: str) -> dict:
        """Get a top-level section from the library."""
        return self.library.get(section_key, {})

    def resolve_clause(self, section_key: str, clause_key: str, selected_option: Optional[str] = None) -> dict:
        """
        Resolve a specific clause from a section and record it in the audit trail.
        Returns the full clause data from the library.
        """
        section = self.get_section(section_key)
        clauses = section.get("clauses", section.get("mandatory_declarations", section.get("conditions", {})))

        clause_data = clauses.get(clause_key, {})
        if not clause_data:
            return {}

        clause_id = clause_data.get("id", f"{section_key}.{clause_key}")
        clause_title = clause_data.get("title", clause_key)
        section_name = section.get("section", section_key)

        self.audit.add_clause(ClauseUsage(
            clause_id=clause_id,
            clause_title=clause_title,
            section=section_name,
            library_version=self.library["version"],
            selected_option=selected_option,
        ))

        return clause_data

    def resolve_standard_clause(self, section_key: str, clause_key: str) -> str:
        """Resolve a standard text clause (e.g. property disclaimers)."""
        section = self.get_section(section_key)
        standard = section.get("standard_clauses", {})
        text = standard.get(clause_key, "")

        if text:
            self.audit.add_clause(ClauseUsage(
                clause_id=f"{section_key}.standard.{clause_key}",
                clause_title=clause_key,
                section=section.get("section", section_key),
                library_version=self.library["version"],
            ))

        return text

    def resolve_declaration(self, declaration_key: str, selected_option: Optional[str] = None) -> dict:
        """Resolve a seller declaration clause."""
        section = self.get_section("seller_declarations")
        declarations = section.get("mandatory_declarations", {})
        decl_data = declarations.get(declaration_key, {})

        if decl_data:
            self.audit.add_clause(ClauseUsage(
                clause_id=decl_data.get("id", f"DECL_{declaration_key}"),
                clause_title=decl_data.get("title", declaration_key),
                section=section.get("section", "F. Verklaringen verkoper"),
                library_version=self.library["version"],
                selected_option=selected_option,
            ))

        return decl_data

    def resolve_condition(self, condition_group: str, condition_key: str, selected_option: Optional[str] = None) -> dict:
        """Resolve a suspensive condition clause."""
        section = self.get_section("suspensive_conditions")
        group = section.get(condition_group, {}).get("conditions", {})
        cond_data = group.get(condition_key, {})

        if cond_data:
            self.audit.add_clause(ClauseUsage(
                clause_id=cond_data.get("id", f"COND_{condition_key}"),
                clause_title=cond_data.get("title", condition_key),
                section=section.get("section", "D. Opschortende voorwaarden"),
                library_version=self.library["version"],
                selected_option=selected_option,
            ))

        return cond_data

    def flag_missing(self, field_path: str, description: str, severity: str = "required") -> None:
        """Flag missing data - never guess values."""
        self.audit.add_missing_flag(field_path, description, severity)

    def get_audit_trail(self) -> dict:
        """Return the complete audit trail as a dict."""
        return self.audit.to_dict()
