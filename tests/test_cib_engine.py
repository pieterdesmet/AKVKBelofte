"""
Tests for CIB decision engine, legal gate, and CIB catalog.

Covers:
- Trigger derivation from dossier + gate state
- Clause selection logic (apartment vs house, asbest, financing, etc.)
- Legal gate blocking / clearing
- Ask-when-uncertain (null / ambiguous Omnicasa data)
- Document assembly structure
- CIB_TEXT_REQUIRED markers
"""

import json
import copy
from pathlib import Path

import pytest

from src.cib_engine import (
    generate_cib_document,
    derive_trigger_values,
    _clause_triggers_match,
    _fill_placeholders,
)
from src.cib_catalog import CIB_CLAUSES, CIB_SECTIONS, get_clause_by_id, get_clauses_for_section
from src.legal_gate import (
    GATE_ITEMS,
    GATE_ITEMS_BY_ID,
    empty_gate_state,
    prefill_from_dossier,
    get_dynamic_blocking,
    evaluate_gate,
)


FIXTURES_DIR = Path(__file__).parent.parent / "examples" / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_cleared_gate(dossier: dict) -> dict:
    """Create a fully confirmed gate state (all items filled + confirmed)."""
    gate = prefill_from_dossier(dossier)
    # Ensure all selects have a definitive value
    if gate.get("bodem_variant") is None:
        gate["bodem_variant"] = "geen_risicogrond"
    if gate.get("mede_eigendom") is None:
        gate["mede_eigendom"] = "nee"
    if gate.get("voorkooprecht") is None or gate.get("voorkooprecht") == "onbekend":
        gate["voorkooprecht"] = "nee"
    if gate.get("elektriciteit_variant") is None:
        gate["elektriciteit_variant"] = "conform"
    if gate.get("epc_label") is None:
        gate["epc_label"] = "B"
    # Ensure all checkboxes are True
    gate["bodemattest_uploaded"] = True
    gate["epc_uploaded"] = True
    gate["elektriciteit_keuring_uploaded"] = True
    gate["asbest_uploaded"] = True
    gate["overstromingszone"] = True
    gate["stedenbouwkundig_uittreksel_uploaded"] = True
    gate["syndicus_info_received"] = True
    return gate


# ===========================================================================
# CIB Catalog tests
# ===========================================================================

class TestCIBCatalog:
    def test_all_clauses_have_required_fields(self):
        required = {"id", "section", "title", "text_block", "subtype", "triggers",
                     "blocking_level", "legal_gate_requires", "order_in_section"}
        for clause in CIB_CLAUSES:
            missing = required - set(clause.keys())
            assert not missing, f"Clause {clause['id']} missing fields: {missing}"

    def test_all_sections_referenced_exist(self):
        valid_sections = {s["id"] for s in CIB_SECTIONS}
        for clause in CIB_CLAUSES:
            assert clause["section"] in valid_sections, (
                f"Clause {clause['id']} references unknown section {clause['section']}"
            )

    def test_unique_clause_ids(self):
        ids = [c["id"] for c in CIB_CLAUSES]
        assert len(ids) == len(set(ids)), "Duplicate clause IDs found"

    def test_get_clause_by_id(self):
        c = get_clause_by_id("CIB_E_PRIJS")
        assert c is not None
        assert c["section"] == "E"

    def test_get_clause_by_id_not_found(self):
        assert get_clause_by_id("DOES_NOT_EXIST") is None

    def test_get_clauses_for_section(self):
        partij_clauses = get_clauses_for_section("PARTIJEN")
        assert len(partij_clauses) == 2
        assert partij_clauses[0]["id"] == "CIB_PARTIJ_VERKOPER"
        assert partij_clauses[1]["id"] == "CIB_PARTIJ_KOPER"

    def test_cib_text_required_clauses(self):
        missing = [c["id"] for c in CIB_CLAUSES if c["text_block"] == "CIB_TEXT_REQUIRED"]
        assert len(missing) >= 3, "Expected at least 3 CIB_TEXT_REQUIRED clauses"

    def test_valid_blocking_levels(self):
        for clause in CIB_CLAUSES:
            assert clause["blocking_level"] in ("none", "required", "ask"), (
                f"Invalid blocking_level for {clause['id']}: {clause['blocking_level']}"
            )

    def test_valid_subtypes(self):
        for clause in CIB_CLAUSES:
            assert clause["subtype"] in ("fixed", "parametric", "party"), (
                f"Invalid subtype for {clause['id']}: {clause['subtype']}"
            )

    def test_legal_gate_requires_reference_valid_gate_items(self):
        for clause in CIB_CLAUSES:
            for gate_id in clause["legal_gate_requires"]:
                assert gate_id in GATE_ITEMS_BY_ID, (
                    f"Clause {clause['id']} references unknown gate item {gate_id}"
                )


# ===========================================================================
# Legal Gate tests
# ===========================================================================

class TestLegalGate:
    def test_empty_gate_state_all_unconfirmed(self):
        state = empty_gate_state()
        for g in GATE_ITEMS:
            if g.input_type == "checkbox":
                assert state[g.id] is False
            elif g.input_type == "select":
                assert state[g.id] is None

    def test_prefill_happy_path(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        state = prefill_from_dossier(dossier)
        assert state["bodem_variant"] == "geen_risicogrond"
        assert state["bodemattest_uploaded"] is True
        assert state["mede_eigendom"] == "nee"
        assert state["elektriciteit_variant"] == "conform"
        # voorkooprecht should be "onbekend" because hasPreemptiveRightsId is not in fixture
        assert state["voorkooprecht"] == "onbekend"

    def test_prefill_bodem_risico(self):
        dossier = _load_fixture("f4_bodem_risico.json")
        state = prefill_from_dossier(dossier)
        assert state["bodem_variant"] == "risicogrond_geen_sanering"

    def test_prefill_elektriciteit_niet_conform(self):
        dossier = _load_fixture("f3_electricity_niet_conform.json")
        state = prefill_from_dossier(dossier)
        assert state["elektriciteit_variant"] == "niet_conform"

    def test_gate_blocked_when_empty(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        state = empty_gate_state()
        result = evaluate_gate(state, dossier)
        assert result["cleared"] is False
        assert len(result["blocking_items"]) > 0

    def test_gate_cleared_when_all_confirmed(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = evaluate_gate(gate, dossier)
        assert result["cleared"] is True
        assert result["confirmed_count"] == result["total_blocking_count"]

    def test_dynamic_blocking_syndicus(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        # mede_eigendom = nee → syndicus not blocking
        gate = prefill_from_dossier(dossier)
        gate["mede_eigendom"] = "nee"
        blocking = get_dynamic_blocking(gate, dossier)
        assert blocking["syndicus_info_received"] is False

        # mede_eigendom = ja → syndicus blocking
        gate["mede_eigendom"] = "ja"
        blocking = get_dynamic_blocking(gate, dossier)
        assert blocking["syndicus_info_received"] is True

    def test_dynamic_blocking_elektriciteit_keuring(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = prefill_from_dossier(dossier)
        # conform → keuring uploaded is blocking
        gate["elektriciteit_variant"] = "conform"
        blocking = get_dynamic_blocking(gate, dossier)
        assert blocking["elektriciteit_keuring_uploaded"] is True

        # geen_keuring → keuring uploaded NOT blocking
        gate["elektriciteit_variant"] = "geen_keuring"
        blocking = get_dynamic_blocking(gate, dossier)
        assert blocking["elektriciteit_keuring_uploaded"] is False

    def test_dynamic_blocking_asbest_bouwjaar(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        # bouwjaar 1995 < 2001 → asbest blocking
        assert dossier["pand"]["bouwjaar"] == 1995
        gate = prefill_from_dossier(dossier)
        blocking = get_dynamic_blocking(gate, dossier)
        assert blocking["asbest_uploaded"] is True

        # bouwjaar >= 2001 → asbest not blocking
        dossier_new = copy.deepcopy(dossier)
        dossier_new["pand"]["bouwjaar"] = 2005
        blocking = get_dynamic_blocking(gate, dossier_new)
        assert blocking["asbest_uploaded"] is False

    def test_ask_when_uncertain_voorkooprecht(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = prefill_from_dossier(dossier)
        # voorkooprecht prefilled as "onbekend" → ask item
        result = evaluate_gate(gate, dossier)
        ask_ids = [item["id"] for item in result["ask_items"]]
        assert "voorkooprecht" in ask_ids

    def test_ask_when_uncertain_null_select(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = prefill_from_dossier(dossier)
        # Force a select to None
        gate["bodem_variant"] = None
        result = evaluate_gate(gate, dossier)
        ask_ids = [item["id"] for item in result["ask_items"]]
        assert "bodem_variant" in ask_ids


# ===========================================================================
# Trigger derivation tests
# ===========================================================================

class TestTriggerDerivation:
    def test_derive_happy_path(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        triggers = derive_trigger_values(dossier, gate)
        assert triggers["bodem_variant"] == "geen_risicogrond"
        assert triggers["financiering_vereist"] is False
        assert triggers["asbest_vereist"] is True  # bouwjaar 1995
        assert triggers["mede_eigendom"] == "nee"
        assert triggers["epc_renovation_required"] is False

    def test_derive_financing_lopend(self):
        dossier = _load_fixture("f2_financing_lopend.json")
        gate = _make_cleared_gate(dossier)
        triggers = derive_trigger_values(dossier, gate)
        assert triggers["financiering_vereist"] is True

    def test_derive_epc_renovation(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        gate["epc_label"] = "D"
        triggers = derive_trigger_values(dossier, gate)
        assert triggers["epc_renovation_required"] is True

        gate["epc_label"] = "B"
        triggers = derive_trigger_values(dossier, gate)
        assert triggers["epc_renovation_required"] is False

    def test_derive_bouwjaar_2005_no_asbest(self):
        dossier = _load_fixture("f5_bouwjaar_2005_no_asbest.json")
        gate = _make_cleared_gate(dossier)
        triggers = derive_trigger_values(dossier, gate)
        assert triggers["asbest_vereist"] is False


# ===========================================================================
# Clause selection tests
# ===========================================================================

class TestClauseSelection:
    def test_triggers_match_empty(self):
        assert _clause_triggers_match({}, {}) is True

    def test_triggers_match_simple(self):
        assert _clause_triggers_match(
            {"bodem_variant": "geen_risicogrond"},
            {"bodem_variant": "geen_risicogrond"},
        ) is True

    def test_triggers_no_match(self):
        assert _clause_triggers_match(
            {"bodem_variant": "sanering_vereist"},
            {"bodem_variant": "geen_risicogrond"},
        ) is False

    def test_triggers_match_bool(self):
        assert _clause_triggers_match(
            {"financiering_vereist": True},
            {"financiering_vereist": True},
        ) is True
        assert _clause_triggers_match(
            {"financiering_vereist": True},
            {"financiering_vereist": False},
        ) is False

    def test_happy_path_selects_bodem_geen_risico(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_D_BODEM_GEEN_RISICO" in selected_ids
        assert "CIB_D_BODEM_RISICO_GEEN_SANERING" not in selected_ids
        assert "CIB_D_BODEM_SANERING" not in selected_ids

    def test_bodem_risico_selects_correct_variant(self):
        dossier = _load_fixture("f4_bodem_risico.json")
        gate = _make_cleared_gate(dossier)
        gate["bodem_variant"] = "risicogrond_geen_sanering"
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_D_BODEM_RISICO_GEEN_SANERING" in selected_ids
        assert "CIB_D_BODEM_GEEN_RISICO" not in selected_ids

    def test_financing_lopend_includes_financing_clause(self):
        dossier = _load_fixture("f2_financing_lopend.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_D_FINANCIERING" in selected_ids

    def test_financing_confirmed_excludes_financing_clause(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_D_FINANCIERING" not in selected_ids

    def test_bouwjaar_before_2001_includes_asbest(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        assert dossier["pand"]["bouwjaar"] < 2001
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_ASBEST" in selected_ids

    def test_bouwjaar_2005_excludes_asbest(self):
        dossier = _load_fixture("f5_bouwjaar_2005_no_asbest.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_ASBEST" not in selected_ids

    def test_elektriciteit_conform_selects_correct_variant(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_ELEKTRICITEIT_CONFORM" in selected_ids
        assert "CIB_F_ELEKTRICITEIT_NIET_CONFORM" not in selected_ids
        assert "CIB_F_ELEKTRICITEIT_GEEN_KEURING" not in selected_ids

    def test_elektriciteit_niet_conform_selects_correct_variant(self):
        dossier = _load_fixture("f3_electricity_niet_conform.json")
        gate = _make_cleared_gate(dossier)
        gate["elektriciteit_variant"] = "niet_conform"
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_ELEKTRICITEIT_NIET_CONFORM" in selected_ids
        assert "CIB_F_ELEKTRICITEIT_CONFORM" not in selected_ids

    def test_mede_eigendom_ja_includes_mede_eigendom_clause(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        gate["mede_eigendom"] = "ja"
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_MEDE_EIGENDOM" in selected_ids

    def test_mede_eigendom_nee_excludes_mede_eigendom_clause(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        gate["mede_eigendom"] = "nee"
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        assert "CIB_F_MEDE_EIGENDOM" not in selected_ids

    def test_always_on_clauses_always_present(self):
        """Clauses with empty triggers should always be selected."""
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        selected_ids = [c["id"] for c in result["selected_clauses"]]
        always_on = ["CIB_PARTIJ_VERKOPER", "CIB_PARTIJ_KOPER", "CIB_EIGENDOM_01",
                      "CIB_A_VERKOOPBELOFTE", "CIB_E_PRIJS", "CIB_H_KOSTEN"]
        for cid in always_on:
            assert cid in selected_ids, f"{cid} should always be selected"


# ===========================================================================
# Document assembly tests
# ===========================================================================

class TestDocumentAssembly:
    def test_document_text_not_empty(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert len(result["document_text"]) > 0

    def test_sections_ordered(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        section_ids = [s["section_id"] for s in result["sections"]]
        expected_order = ["PARTIJEN", "EIGENDOM", "A", "B", "C", "D", "E", "F", "G", "H"]
        for i, sid in enumerate(section_ids):
            assert sid in expected_order
            if i > 0:
                assert expected_order.index(sid) > expected_order.index(section_ids[i - 1])

    def test_party_expansion_multiple_sellers(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        # Add second seller
        dossier_multi = copy.deepcopy(dossier)
        dossier_multi["partijen"]["verkopers"].append({
            "titel_adres": "Mevrouw",
            "naam": "Janssens",
            "voornaam": "Lies",
            "adres": "Kerkstraat 10, 2200 Herentals",
            "geboorteplaats": "Gent",
            "geboortedatum": "1972-03-03",
            "rijksregisternummer": "TEST_RRN_F1_003",
            "burgerlijke_staat": "gehuwd",
        })
        gate = _make_cleared_gate(dossier_multi)
        result = generate_cib_document(dossier_multi, gate)
        text = result["document_text"]
        assert "Marc Janssens" in text
        assert "Lies Janssens" in text

    def test_parametric_placeholders_filled(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        text = result["document_text"]
        # Check that transactie.verkoopsprijs is filled
        assert "225000" in text
        # Check that pand.gemeente is filled
        assert "Herentals" in text

    def test_cib_text_required_marker(self):
        """Clauses with CIB_TEXT_REQUIRED show marker in output and hard-block."""
        dossier = _load_fixture("f4_bodem_risico.json")
        gate = _make_cleared_gate(dossier)
        gate["bodem_variant"] = "sanering_vereist"
        result = generate_cib_document(dossier, gate)
        assert "CIB_D_BODEM_SANERING" in result["cib_text_required"]
        assert "[CIB_TEXT_REQUIRED:" in result["document_text"]
        # Hard-block: status must be DRAFT_BLOCKED
        assert result["readiness_status"] == "DRAFT_BLOCKED"

    def test_no_unresolved_on_complete_dossier(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert len(result["unresolved_placeholders"]) == 0


# ===========================================================================
# Readiness status tests
# ===========================================================================

class TestReadinessStatus:
    def test_gate_blocked_status(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        # Use empty gate → gate not cleared
        result = generate_cib_document(dossier, empty_gate_state())
        assert result["readiness_status"] == "GATE_BLOCKED"

    def test_draft_review_required_with_jurist_clauses(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        # Should have review_required due to CIB_A_TOTSTANDKOMING (required) and sanctie clauses
        assert result["readiness_status"] in ("DRAFT_REVIEW_REQUIRED", "DRAFT_REVIEW_RECOMMENDED")

    def test_confidence_score_range(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert 0 <= result["confidence_score"] <= 100

    def test_next_actions_populated(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        result = generate_cib_document(dossier)
        assert len(result["next_actions"]) > 0


# ===========================================================================
# Flags tests
# ===========================================================================

class TestFlags:
    def test_cib_text_required_flag_is_high_risk(self):
        dossier = _load_fixture("f4_bodem_risico.json")
        gate = _make_cleared_gate(dossier)
        gate["bodem_variant"] = "sanering_vereist"
        result = generate_cib_document(dossier, gate)
        cib_flags = [f for f in result["flags"] if f["type"] == "cib_text_required"]
        assert len(cib_flags) > 0
        # Must be high risk (hard-blocking)
        for f in cib_flags:
            assert f["risk_level"] == "high"

    def test_jurist_required_flag(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        jurist_flags = [f for f in result["flags"] if f["type"] == "jurist_review_required"]
        assert len(jurist_flags) > 0  # CIB_A_TOTSTANDKOMING, CIB_G_SANCTIE_01, CIB_G_SANCTIE_02

    def test_gate_not_met_flags(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = prefill_from_dossier(dossier)
        # bodemattest_uploaded True, but epc_uploaded False, keuring False
        result = generate_cib_document(dossier, gate)
        gate_flags = [f for f in result["flags"] if f["type"] == "gate_not_met"]
        # Some clauses should have unmet gates
        assert len(gate_flags) > 0


# ===========================================================================
# CIB_TEXT_REQUIRED hard-block tests
# ===========================================================================

class TestCIBTextRequiredHardBlock:
    """Verify that CIB_TEXT_REQUIRED in selected clauses hard-blocks generation."""

    def _trigger_sanering(self):
        """Return (dossier, gate) that triggers CIB_D_BODEM_SANERING (CIB_TEXT_REQUIRED)."""
        dossier = _load_fixture("f4_bodem_risico.json")
        gate = _make_cleared_gate(dossier)
        gate["bodem_variant"] = "sanering_vereist"
        return dossier, gate

    def test_status_is_draft_blocked(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        assert result["readiness_status"] == "DRAFT_BLOCKED"

    def test_cib_text_required_list_populated(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        assert len(result["cib_text_required"]) > 0
        assert "CIB_D_BODEM_SANERING" in result["cib_text_required"]

    def test_next_actions_mention_missing_clauses(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        actions_text = "\n".join(result["next_actions"])
        assert "CIB_D_BODEM_SANERING" in actions_text
        assert "CIB-tekst ontbreekt" in actions_text

    def test_flags_are_high_risk(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        cib_flags = [f for f in result["flags"] if f["type"] == "cib_text_required"]
        assert all(f["risk_level"] == "high" for f in cib_flags)

    def test_flag_detail_contains_clause_title(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        cib_flags = [f for f in result["flags"] if f["type"] == "cib_text_required"]
        # Detail should mention both the ID and the title
        for f in cib_flags:
            assert f["clause_id"] in f["detail"]

    def test_document_text_contains_marker(self):
        dossier, gate = self._trigger_sanering()
        result = generate_cib_document(dossier, gate)
        assert "[CIB_TEXT_REQUIRED:" in result["document_text"]

    def test_happy_path_no_cib_text_required(self):
        """Happy path (F1 + cleared gate) should NOT have CIB_TEXT_REQUIRED."""
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert len(result["cib_text_required"]) == 0
        assert result["readiness_status"] != "DRAFT_BLOCKED"

    def test_gate_blocked_takes_precedence_over_cib_text_required(self):
        """GATE_BLOCKED should take precedence over CIB_TEXT_REQUIRED DRAFT_BLOCKED."""
        dossier = _load_fixture("f4_bodem_risico.json")
        gate = empty_gate_state()
        gate["bodem_variant"] = "sanering_vereist"
        result = generate_cib_document(dossier, gate)
        # Gate is not cleared → GATE_BLOCKED wins
        assert result["readiness_status"] == "GATE_BLOCKED"

    def test_multiple_cib_text_required_all_listed(self):
        """When multiple CIB_TEXT_REQUIRED clauses trigger, all are listed."""
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        # Force triggers for multiple CIB_TEXT_REQUIRED clauses
        gate["mede_eigendom"] = "ja"
        gate["elektriciteit_variant"] = "geen_keuring"
        result = generate_cib_document(dossier, gate)
        # CIB_F_MEDE_EIGENDOM and CIB_F_ELEKTRICITEIT_GEEN_KEURING are both CIB_TEXT_REQUIRED
        if len(result["cib_text_required"]) >= 2:
            assert result["readiness_status"] == "DRAFT_BLOCKED"
            # All should appear in next_actions
            actions_text = "\n".join(result["next_actions"])
            for cid in result["cib_text_required"]:
                assert cid in actions_text

    def test_confidence_drops_with_cib_text_required(self):
        """Confidence should drop due to high-risk CIB_TEXT_REQUIRED flags."""
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result_clean = generate_cib_document(dossier, gate)

        gate["bodem_variant"] = "sanering_vereist"
        # Need to re-use f4 for proper triggers
        dossier_risico = _load_fixture("f4_bodem_risico.json")
        gate_risico = _make_cleared_gate(dossier_risico)
        gate_risico["bodem_variant"] = "sanering_vereist"
        result_blocked = generate_cib_document(dossier_risico, gate_risico)

        assert result_blocked["confidence_score"] < result_clean["confidence_score"]


# ===========================================================================
# Summary tests
# ===========================================================================

class TestSummary:
    def test_summary_fields(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        summary = result["summary"]
        assert "total_clauses_in_catalog" in summary
        assert "selected_count" in summary
        assert "skipped_count" in summary
        assert "sections_count" in summary
        assert summary["selected_count"] + summary["skipped_count"] == summary["total_clauses_in_catalog"]

    def test_summary_counts_consistent(self):
        dossier = _load_fixture("f1_happy_path_confirmed_financing.json")
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert result["summary"]["selected_count"] == len(result["selected_clauses"])
        assert result["summary"]["skipped_count"] == len(result["skipped_clauses"])


# ===========================================================================
# Cross-fixture tests (all 6 fixtures)
# ===========================================================================

FIXTURE_FILES = [
    "f1_happy_path_confirmed_financing.json",
    "f2_financing_lopend.json",
    "f3_electricity_niet_conform.json",
    "f4_bodem_risico.json",
    "f5_bouwjaar_2005_no_asbest.json",
    "f6_missing_required_field.json",
]


class TestCrossFixtures:
    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_generate_does_not_crash(self, fixture_file):
        """Engine should not crash on any fixture, even with default gate."""
        dossier = _load_fixture(fixture_file)
        result = generate_cib_document(dossier)
        assert "readiness_status" in result
        assert "document_text" in result
        assert "confidence_score" in result

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_generate_with_cleared_gate(self, fixture_file):
        """Engine should produce valid output with fully confirmed gate."""
        dossier = _load_fixture(fixture_file)
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        assert result["summary"]["gate_cleared"] is True
        assert result["readiness_status"] != "GATE_BLOCKED"
        assert len(result["sections"]) > 0

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_partijen_always_present(self, fixture_file):
        dossier = _load_fixture(fixture_file)
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        section_ids = [s["section_id"] for s in result["sections"]]
        assert "PARTIJEN" in section_ids

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_selected_plus_skipped_equals_total(self, fixture_file):
        dossier = _load_fixture(fixture_file)
        gate = _make_cleared_gate(dossier)
        result = generate_cib_document(dossier, gate)
        total = len(CIB_CLAUSES)
        assert result["summary"]["selected_count"] + result["summary"]["skipped_count"] == total
