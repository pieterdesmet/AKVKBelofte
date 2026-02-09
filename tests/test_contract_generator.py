"""
Tests for the Heylen Vastgoed contract generator.
Tests validation, clause resolution, audit trail, and full generation.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    Adres,
    AsbestOptie,
    BodemAttest,
    BodemOptie,
    BodemVerklaring,
    BosdecreetOptie,
    BurgerlijkeStaat,
    ContractInput,
    Eigendom,
    Kadaster,
    Notaris,
    Persoon,
    TitelAdres,
    VerklaardeOpties,
    validate_rijksregisternummer,
)
from src.validator import validate_contract_input
from src.clause_resolver import ClauseResolver
from src.contract_generator import generate_contract, generate_contract_from_dict


# === Fixtures ===

@pytest.fixture
def complete_verkoper() -> Persoon:
    return Persoon(
        titel_adres=TitelAdres.DE_HEER,
        naam="Janssens",
        voornaam="Marc",
        adres=Adres(straat="Kerkstraat", huisnummer="15", postcode="2200", gemeente="Herentals"),
        geboorteplaats="Herentals",
        geboortedatum=date(1965, 3, 12),
        rijksregisternummer="65.03.12-123.45",
        burgerlijke_staat=BurgerlijkeStaat.GEHUWD,
    )


@pytest.fixture
def complete_koper() -> Persoon:
    return Persoon(
        titel_adres=TitelAdres.MEVROUW,
        naam="De Smedt",
        voornaam="Anja",
        adres=Adres(straat="Lierseweg", huisnummer="42", postcode="2200", gemeente="Herentals"),
        geboorteplaats="Lier",
        geboortedatum=date(1988, 7, 22),
        burgerlijke_staat=BurgerlijkeStaat.ONGEHUWD,
    )


@pytest.fixture
def complete_eigendom() -> Eigendom:
    return Eigendom(
        type_pand="woning",
        gemeente="Herentals",
        straat="Bovenrij",
        huisnummer="7",
        postcode="2200",
        kadaster=Kadaster(afdeling="1", sectie="B", nummer="234A", oppervlakte="450"),
        kadastraal_inkomen="1250",
    )


@pytest.fixture
def complete_opties() -> VerklaardeOpties:
    return VerklaardeOpties(
        bodem_optie=BodemOptie.GEEN_RISICOGROND,
        bodem_verklaring=BodemVerklaring.GEEN_RISICOGROND,
        asbest_optie=AsbestOptie.GEEN_VERMOEDEN,
        bosdecreet=BosdecreetOptie.NIET_VAN_TOEPASSING,
        onroerend_erfgoed=False,
        tienjarige_verzekering_werken=False,
        financiering_vereist=True,
        rechterlijke_machtiging_vereist=False,
    )


@pytest.fixture
def complete_input(complete_verkoper, complete_koper, complete_eigendom, complete_opties) -> ContractInput:
    return ContractInput(
        verkopers=[complete_verkoper],
        kopers=[complete_koper],
        eigendom=complete_eigendom,
        notaris_verkoper=Notaris(
            kantoor="Notariskantoor Peeters",
            adres=Adres(straat="Markt", huisnummer="5", postcode="2200", gemeente="Herentals"),
            telefoon="014 21 12 34",
            email="info@notaris-peeters.be",
        ),
        verkoopprijs=325000.00,
        voorschot=32500.00,
        bodemattest=BodemAttest(datum="2026-01-15", referentie="OVAM-2026-12345", inhoud="Geen verontreiniging"),
        verklaarde_opties=complete_opties,
        datum_ondertekening=date(2026, 2, 9),
    )


# === Model Tests ===

class TestRijksregisternummer:
    def test_valid_format(self):
        assert validate_rijksregisternummer("65.03.12-123.45") is True

    def test_invalid_format_no_dots(self):
        assert validate_rijksregisternummer("650312-12345") is False

    def test_invalid_format_empty(self):
        assert validate_rijksregisternummer("") is False

    def test_invalid_format_letters(self):
        assert validate_rijksregisternummer("AB.CD.EF-GHI.JK") is False


# === Validator Tests ===

class TestValidation:
    def test_empty_input_flags_everything(self):
        result = validate_contract_input(ContractInput())
        assert result.is_valid is False
        assert result.total_required_missing > 0
        assert any(f.field_path == "verkopers" for f in result.flags)
        assert any(f.field_path == "kopers" for f in result.flags)
        assert any(f.field_path == "eigendom" for f in result.flags)
        assert any(f.field_path == "verkoopprijs" for f in result.flags)

    def test_complete_input_is_valid(self, complete_input):
        result = validate_contract_input(complete_input)
        assert result.is_valid is True
        assert result.total_required_missing == 0

    def test_missing_verkoper_naam(self, complete_input):
        complete_input.verkopers[0].naam = None
        result = validate_contract_input(complete_input)
        assert result.is_valid is False
        assert any("familienaam" in f.message for f in result.flags)

    def test_invalid_rijksregisternummer(self, complete_input):
        complete_input.verkopers[0].rijksregisternummer = "INVALID"
        result = validate_contract_input(complete_input)
        assert result.is_valid is False
        assert any("rijksregisternummer" in f.field_path for f in result.flags)

    def test_too_many_verkopers(self, complete_verkoper):
        inp = ContractInput(verkopers=[complete_verkoper] * 5)
        result = validate_contract_input(inp)
        assert any("maximum is 4" in f.message for f in result.flags)

    def test_missing_opties_flags(self, complete_input):
        complete_input.verklaarde_opties = None
        result = validate_contract_input(complete_input)
        assert result.is_valid is False
        assert any("verklaarde_opties" in f.field_path for f in result.flags)

    def test_negative_price(self, complete_input):
        complete_input.verkoopprijs = -1
        result = validate_contract_input(complete_input)
        assert result.is_valid is False

    def test_notaris_recommended(self, complete_input):
        complete_input.notaris_koper = None
        result = validate_contract_input(complete_input)
        # Notaris koper is recommended, not required
        assert result.is_valid is True
        assert result.total_recommended_missing > 0


# === Clause Resolver Tests ===

class TestClauseResolver:
    def test_load_library(self):
        resolver = ClauseResolver()
        lib = resolver.load()
        assert lib["version"] == "0.1"
        assert lib["document_type"] == "tweezijdige_aankoopbelofte"

    def test_resolve_clause_records_audit(self):
        resolver = ClauseResolver()
        resolver.load()
        clause = resolver.resolve_clause("main_agreement_clauses", "1_verkoop_belofte_call_option")
        assert clause["id"] == "CLAUSE_A1"
        audit = resolver.get_audit_trail()
        assert any(c["clause_id"] == "CLAUSE_A1" for c in audit["clauses_used"])

    def test_resolve_standard_clause(self):
        resolver = ClauseResolver()
        resolver.load()
        text = resolver.resolve_standard_clause("property_description", "disclaimer_kadaster")
        assert "kadastrale gegevens" in text.lower()
        assert len(resolver.get_audit_trail()["clauses_used"]) == 1

    def test_resolve_declaration(self):
        resolver = ClauseResolver()
        resolver.load()
        decl = resolver.resolve_declaration("ownership")
        assert decl["id"] == "DECL_OWNERSHIP"

    def test_resolve_condition(self):
        resolver = ClauseResolver()
        resolver.load()
        cond = resolver.resolve_condition("buyer_conditions", "soil_decree", selected_option="option_1")
        assert cond["id"] == "COND_BUYER_SOIL"
        audit = resolver.get_audit_trail()
        assert audit["clauses_used"][-1]["selected_option"] == "option_1"

    def test_flag_missing(self):
        resolver = ClauseResolver()
        resolver.load()
        resolver.flag_missing("test.field", "Test ontbreekt", "required")
        audit = resolver.get_audit_trail()
        assert audit["total_missing_flags"] == 1
        assert audit["missing_data_flags"][0]["field"] == "test.field"

    def test_nonexistent_clause_returns_empty(self):
        resolver = ClauseResolver()
        resolver.load()
        result = resolver.resolve_clause("main_agreement_clauses", "nonexistent")
        assert result == {}


# === Full Generator Tests ===

class TestContractGenerator:
    def test_full_generation_structure(self, complete_input):
        result = generate_contract(complete_input)

        assert "contract" in result
        assert "validation" in result
        assert "audit_trail" in result

        contract = result["contract"]
        assert contract["document_type"] == "tweezijdige_aankoopbelofte"
        assert "partijen" in contract
        assert "eigendom" in contract
        assert "sectie_a_hoofdinhoud" in contract
        assert "sectie_b_modaliteiten" in contract
        assert "sectie_c_optieprijs" in contract
        assert "sectie_d_opschortende_voorwaarden" in contract
        assert "sectie_e_prijs" in contract
        assert "sectie_f_verklaringen" in contract
        assert "sectie_g_sancties" in contract
        assert "sectie_h_kosten" in contract
        assert "sectie_i_diversen" in contract
        assert "ondertekening" in contract

    def test_valid_input_passes_validation(self, complete_input):
        result = generate_contract(complete_input)
        assert result["validation"]["is_valid"] is True

    def test_audit_trail_has_clauses(self, complete_input):
        result = generate_contract(complete_input)
        audit = result["audit_trail"]
        assert audit["library_version"] == "0.1"
        assert audit["total_clauses_used"] > 0
        assert all("clause_id" in c for c in audit["clauses_used"])
        assert all("library_version" in c for c in audit["clauses_used"])

    def test_termijnen_calculated(self, complete_input):
        result = generate_contract(complete_input)
        termijnen = result["contract"]["sectie_a_hoofdinhoud"]["berekende_termijnen"]
        assert termijnen is not None
        assert termijnen["datum_ondertekening"] == "2026-02-09"
        assert termijnen["call_optie_einde"] == "2026-06-09"  # +120 days
        assert termijnen["put_optie_einde"] == "2026-07-09"   # +30 days after call

    def test_payment_reference_built(self, complete_input):
        result = generate_contract(complete_input)
        mededeling = result["contract"]["sectie_c_optieprijs"]["betaling"]["mededeling"]
        assert mededeling == "Bovenrij 7 - 2200 Herentals"

    def test_financing_condition_included(self, complete_input):
        result = generate_contract(complete_input)
        conditions = result["contract"]["sectie_d_opschortende_voorwaarden"]
        assert "financiering" in conditions["koper_voorwaarden"]

    def test_financing_condition_excluded_when_not_required(self, complete_input):
        complete_input.verklaarde_opties.financiering_vereist = False
        result = generate_contract(complete_input)
        conditions = result["contract"]["sectie_d_opschortende_voorwaarden"]
        assert "financiering" not in conditions["koper_voorwaarden"]

    def test_broker_data_from_library(self, complete_input):
        result = generate_contract(complete_input)
        broker = result["contract"]["partijen"]["vastgoedmakelaar"]
        assert broker["company_name"] == "Heylen Vastgoed BV"

    def test_empty_input_flags_all_missing(self):
        result = generate_contract(ContractInput())
        assert result["validation"]["is_valid"] is False
        assert result["audit_trail"]["total_missing_flags"] > 0

    def test_output_is_json_serializable(self, complete_input):
        result = generate_contract(complete_input)
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        assert isinstance(serialized, str)
        # Verify round-trip
        parsed = json.loads(serialized)
        assert parsed["contract"]["document_type"] == "tweezijdige_aankoopbelofte"

    def test_from_dict_with_example_file(self):
        example_path = Path(__file__).parent.parent / "examples" / "example_input.json"
        with open(example_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = generate_contract_from_dict(data)
        assert result["validation"]["is_valid"] is True
        assert result["contract"]["sectie_e_prijs"]["verkoopprijs"] == 325000.00

    def test_no_invented_legal_text(self, complete_input):
        """Ensure all clause text comes from library, not invented."""
        result = generate_contract(complete_input)
        audit = result["audit_trail"]
        # Every clause must reference the library version
        for clause in audit["clauses_used"]:
            assert clause["library_version"] == "0.1"

    def test_multiple_verkopers(self, complete_verkoper, complete_koper, complete_eigendom, complete_opties):
        verkoper2 = Persoon(
            titel_adres=TitelAdres.MEVROUW,
            naam="Janssens",
            voornaam="Katrien",
            adres=Adres(straat="Kerkstraat", huisnummer="15", postcode="2200", gemeente="Herentals"),
            geboorteplaats="Herentals",
            geboortedatum=date(1968, 5, 20),
            rijksregisternummer="68.05.20-234.56",
            burgerlijke_staat=BurgerlijkeStaat.GEHUWD,
        )
        inp = ContractInput(
            verkopers=[complete_verkoper, verkoper2],
            kopers=[complete_koper],
            eigendom=complete_eigendom,
            verkoopprijs=325000.00,
            voorschot=32500.00,
            verklaarde_opties=complete_opties,
            datum_ondertekening=date(2026, 2, 9),
        )
        result = generate_contract(inp)
        assert len(result["contract"]["partijen"]["verkopers"]["personen"]) == 2
