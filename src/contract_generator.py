"""
Main contract generator for Heylen Vastgoed tweezijdige aankoopbelofte.

STRIKT:
- Geen juridische tekst verzinnen - enkel clause-library gebruiken.
- Ontbrekende data flaggen, nooit raden.
- Output is machineleesbaar JSON.
- Altijd auditbaarheid: gebruikte clauses en versies.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Optional

from .clause_resolver import ClauseResolver, ClauseUsage
from .models import (
    Adres,
    AsbestOptie,
    BodemOptie,
    BodemVerklaring,
    BosdecreetOptie,
    ContractInput,
    Eigendom,
    Kadaster,
    Notaris,
    Persoon,
    VerklaardeOpties,
)
from .validator import ValidationResult, validate_contract_input


def _persoon_to_dict(persoon: Persoon) -> dict:
    """Serialize a Persoon to dict, preserving None for missing fields."""
    result: dict[str, Any] = {
        "titel_adres": persoon.titel_adres.value if persoon.titel_adres else None,
        "naam": persoon.naam,
        "voornaam": persoon.voornaam,
        "geboorteplaats": persoon.geboorteplaats,
        "geboortedatum": persoon.geboortedatum.isoformat() if persoon.geboortedatum else None,
        "rijksregisternummer": persoon.rijksregisternummer,
        "burgerlijke_staat": persoon.burgerlijke_staat.value if persoon.burgerlijke_staat else None,
    }
    if persoon.adres:
        result["adres"] = {
            "straat": persoon.adres.straat,
            "huisnummer": persoon.adres.huisnummer,
            "bus": persoon.adres.bus,
            "postcode": persoon.adres.postcode,
            "gemeente": persoon.adres.gemeente,
        }
    else:
        result["adres"] = None
    return result


def _eigendom_to_dict(eigendom: Optional[Eigendom]) -> Optional[dict]:
    if not eigendom:
        return None
    result: dict[str, Any] = {
        "type_pand": eigendom.type_pand,
        "gemeente": eigendom.gemeente,
        "straat": eigendom.straat,
        "huisnummer": eigendom.huisnummer,
        "postcode": eigendom.postcode,
        "kadastraal_inkomen": eigendom.kadastraal_inkomen,
    }
    if eigendom.kadaster:
        result["kadaster"] = {
            "afdeling": eigendom.kadaster.afdeling,
            "sectie": eigendom.kadaster.sectie,
            "nummer": eigendom.kadaster.nummer,
            "oppervlakte": eigendom.kadaster.oppervlakte,
        }
    else:
        result["kadaster"] = None
    return result


def _notaris_to_dict(notaris: Optional[Notaris]) -> Optional[dict]:
    if not notaris:
        return None
    result: dict[str, Any] = {
        "kantoor": notaris.kantoor,
        "telefoon": notaris.telefoon,
        "email": notaris.email,
    }
    if notaris.adres:
        result["adres"] = {
            "straat": notaris.adres.straat,
            "huisnummer": notaris.adres.huisnummer,
            "postcode": notaris.adres.postcode,
            "gemeente": notaris.adres.gemeente,
        }
    else:
        result["adres"] = None
    return result


def _build_payment_reference(eigendom: Optional[Eigendom]) -> Optional[str]:
    """Build the payment reference from property data per clause library format."""
    if not eigendom:
        return None
    parts = []
    if eigendom.straat:
        parts.append(eigendom.straat)
    if eigendom.huisnummer:
        parts.append(eigendom.huisnummer)
    if parts:
        street_part = " ".join(parts)
    else:
        return None

    location_parts = []
    if eigendom.postcode:
        location_parts.append(eigendom.postcode)
    if eigendom.gemeente:
        location_parts.append(eigendom.gemeente)

    if location_parts:
        return f"{street_part} - {' '.join(location_parts)}"
    return street_part


class ContractGenerator:
    """
    Generates a tweezijdige aankoopbelofte contract in JSON format.
    Uses exclusively the clause library - no legal text is invented.
    """

    def __init__(self, library_filename: str = "tweezijdige_aankoopbelofte_v0.1.json"):
        self.resolver = ClauseResolver(library_filename)
        self.resolver.load()

    def generate(self, input_data: ContractInput) -> dict:
        """
        Generate a complete contract JSON from the provided input data.

        Returns a dict with:
        - contract: the assembled contract data
        - validation: validation result with any flags
        - audit_trail: full list of clauses used and versions
        """
        # Step 1: Validate input - flag all missing data
        validation = validate_contract_input(input_data)

        # Step 2: Propagate validation flags to audit trail
        for flag in validation.flags:
            self.resolver.flag_missing(flag.field_path, flag.message, flag.severity)

        # Step 3: Assemble contract sections from clause library
        contract = self._assemble_contract(input_data)

        return {
            "contract": contract,
            "validation": validation.to_dict(),
            "audit_trail": self.resolver.get_audit_trail(),
        }

    def _assemble_contract(self, input_data: ContractInput) -> dict:
        """Assemble the full contract from clause library sections."""
        lib = self.resolver.library

        return {
            "document_type": lib["document_type"],
            "document_title": lib["document_title"],
            "document_version": lib["version"],
            "metadata": {
                "jurisdiction": lib["metadata"]["jurisdiction"],
                "effective_date": lib["metadata"]["effective_date"],
                "issuing_organization": lib["metadata"]["issuing_organization"],
                "usage_restriction": lib["metadata"]["usage_restriction"],
            },
            "partijen": self._build_parties(input_data),
            "eigendom": self._build_property(input_data),
            "sectie_a_hoofdinhoud": self._build_main_agreement(input_data),
            "sectie_b_modaliteiten": self._build_modalities(input_data),
            "sectie_c_optieprijs": self._build_option_price(input_data),
            "sectie_d_opschortende_voorwaarden": self._build_suspensive_conditions(input_data),
            "sectie_e_prijs": self._build_price(input_data),
            "sectie_f_verklaringen": self._build_declarations(input_data),
            "sectie_g_sancties": self._build_sanctions(),
            "sectie_h_kosten": self._build_costs(),
            "sectie_i_diversen": self._build_other_provisions(),
            "ondertekening": self._build_signatures(input_data),
        }

    def _build_parties(self, input_data: ContractInput) -> dict:
        """Build the parties section using library definitions."""
        broker_data = self.resolver.library["parties"]["real_estate_broker"]
        seller_def = self.resolver.library["parties"]["seller"]
        buyer_def = self.resolver.library["parties"]["buyer"]

        return {
            "vastgoedmakelaar": broker_data["template_fields"],
            "verkopers": {
                "role": seller_def["role"],
                "hoofdelijke_verbondenheid": seller_def["joint_liability"],
                "verklaring": seller_def["authority_declaration"],
                "personen": [_persoon_to_dict(v) for v in input_data.verkopers],
            },
            "kopers": {
                "role": buyer_def["role"],
                "hoofdelijke_verbondenheid": buyer_def["joint_liability"],
                "verklaring": buyer_def["authority_declaration"],
                "personen": [_persoon_to_dict(k) for k in input_data.kopers],
            },
        }

    def _build_property(self, input_data: ContractInput) -> dict:
        """Build property section with standard clauses from library."""
        prop_section = self.resolver.get_section("property_description")

        # Resolve all four standard property clauses
        standard_clauses = {}
        for key in ["disclaimer_kadaster", "ki_declaration", "inspection_declaration", "description_waiver"]:
            text = self.resolver.resolve_standard_clause("property_description", key)
            if text:
                standard_clauses[key] = text

        return {
            "gegevens": _eigendom_to_dict(input_data.eigendom),
            "standaard_clausules": standard_clauses,
        }

    def _build_main_agreement(self, input_data: ContractInput) -> dict:
        """Build Section A: main agreement clauses."""
        # Resolve all three main agreement clauses
        call_option = self.resolver.resolve_clause(
            "main_agreement_clauses", "1_verkoop_belofte_call_option"
        )
        put_option = self.resolver.resolve_clause(
            "main_agreement_clauses", "2_aankoop_belofte_put_option"
        )
        notarial = self.resolver.resolve_clause(
            "main_agreement_clauses", "3_notarial_deed_requirement"
        )

        # Calculate option deadlines from signing date
        termijnen = None
        if input_data.datum_ondertekening:
            call_einde = input_data.datum_ondertekening + timedelta(days=120)  # ~4 months
            put_einde = call_einde + timedelta(days=30)
            termijnen = {
                "datum_ondertekening": input_data.datum_ondertekening.isoformat(),
                "call_optie_einde": call_einde.isoformat(),
                "put_optie_einde": put_einde.isoformat(),
            }

        return {
            "section": call_option.get("id", "CLAUSE_A1") and "A. Hoofdinhoud van de overeenkomst",
            "verkoopbelofte_call_optie": {
                "clause_id": call_option.get("id"),
                "title": call_option.get("title"),
                "key_terms": call_option.get("key_terms"),
                "extension_clause": call_option.get("extension_clause"),
            },
            "aankoopbelofte_put_optie": {
                "clause_id": put_option.get("id"),
                "title": put_option.get("title"),
                "key_terms": put_option.get("key_terms"),
            },
            "notariele_akte": {
                "clause_id": notarial.get("id"),
                "title": notarial.get("title"),
                "key_principles": notarial.get("key_principles"),
            },
            "berekende_termijnen": termijnen,
        }

    def _build_modalities(self, input_data: ContractInput) -> dict:
        """Build Section B: modalities."""
        option_exercise = self.resolver.resolve_clause("modality_clauses", "1_option_exercise")
        timing = self.resolver.resolve_clause("modality_clauses", "2_timing_requirement")
        substitution = self.resolver.resolve_clause("modality_clauses", "3_substitution_right")
        notary_desig = self.resolver.resolve_clause("modality_clauses", "4_notary_designation")

        return {
            "section": "B. Modaliteiten van de OVEREENKOMST",
            "uitoefening_optie": {
                "clause_id": option_exercise.get("id"),
                "procedure": option_exercise.get("procedure"),
            },
            "timing_attesten": {
                "clause_id": timing.get("id"),
                "requirement": timing.get("requirement"),
                "reference": timing.get("reference"),
            },
            "recht_substitutie": {
                "clause_id": substitution.get("id"),
                "conditions": substitution.get("conditions"),
            },
            "aanduiding_notarissen": {
                "clause_id": notary_desig.get("id"),
                "principles": notary_desig.get("principles"),
                "notaris_verkoper": _notaris_to_dict(input_data.notaris_verkoper),
                "notaris_koper": _notaris_to_dict(input_data.notaris_koper),
            },
        }

    def _build_option_price(self, input_data: ContractInput) -> dict:
        """Build Section C: option price / warranty / advance."""
        option_price = self.resolver.resolve_clause("option_price_warranty", "option_price")
        triple_func = self.resolver.resolve_clause("option_price_warranty", "triple_function")
        allocation = self.resolver.resolve_clause("option_price_warranty", "allocation_rules")
        interest = self.resolver.resolve_clause("option_price_warranty", "interest_handling")
        late_payment = self.resolver.resolve_clause("option_price_warranty", "late_payment_sanction")

        payment_ref = _build_payment_reference(input_data.eigendom)

        return {
            "section": "C. Optieprijs - Waarborg - Voorschot",
            "bedrag": input_data.voorschot,
            "betaling": {
                "clause_id": option_price.get("id"),
                "method": option_price.get("payment_details", {}).get("method"),
                "recipient": option_price.get("payment_details", {}).get("recipient"),
                "deadline": option_price.get("payment_details", {}).get("deadline"),
                "mededeling": payment_ref,
                "consignment": option_price.get("payment_details", {}).get("consignment"),
            },
            "drievoudige_functie": {
                "clause_id": triple_func.get("id"),
                "functions": triple_func.get("functions"),
            },
            "toewijzingsregels": {
                "clause_id": allocation.get("id"),
                "scenarios": allocation.get("scenarios"),
            },
            "interesten": {
                "clause_id": interest.get("id"),
                "rule": interest.get("rule"),
            },
            "sanctie_laattijdige_betaling": {
                "clause_id": late_payment.get("id"),
                "consequences": late_payment.get("consequences"),
            },
        }

    def _build_suspensive_conditions(self, input_data: ContractInput) -> dict:
        """Build Section D: suspensive conditions."""
        section_data = self.resolver.get_section("suspensive_conditions")
        opties = input_data.verklaarde_opties

        # Buyer conditions
        soil_option = opties.bodem_optie.value if opties and opties.bodem_optie else None
        soil = self.resolver.resolve_condition("buyer_conditions", "soil_decree", selected_option=soil_option)
        spatial = self.resolver.resolve_condition("buyer_conditions", "spatial_planning")

        financing_included = opties.financiering_vereist if opties else None
        financing = None
        if financing_included:
            financing = self.resolver.resolve_condition("buyer_conditions", "financing")

        # Mutual conditions
        free_unenc = self.resolver.resolve_condition("mutual_conditions", "free_and_unencumbered")

        court_required = opties.rechterlijke_machtiging_vereist if opties else None
        court = None
        if court_required:
            court = self.resolver.resolve_condition("mutual_conditions", "court_authorization")

        result: dict[str, Any] = {
            "section": "D. Opschortende voorwaarden",
            "algemeen_principe": section_data.get("general_principle"),
            "koper_voorwaarden": {
                "bodemdecreet": {
                    "clause_id": soil.get("id"),
                    "gekozen_optie": soil_option,
                    "title": soil.get("title"),
                },
                "ruimtelijke_ordening": {
                    "clause_id": spatial.get("id"),
                    "requirements": spatial.get("requirements"),
                },
            },
            "wederzijdse_voorwaarden": {
                "vrij_en_onbelast": {
                    "clause_id": free_unenc.get("id"),
                    "requirements": free_unenc.get("requirements"),
                },
            },
        }

        if financing:
            result["koper_voorwaarden"]["financiering"] = {
                "clause_id": financing.get("id"),
                "key_terms": financing.get("key_terms"),
            }

        if court:
            result["wederzijdse_voorwaarden"]["rechterlijke_machtiging"] = {
                "clause_id": court.get("id"),
                "requirement": court.get("requirement"),
            }

        return result

    def _build_price(self, input_data: ContractInput) -> dict:
        """Build Section E: price and payment."""
        price_section = self.resolver.get_section("price_and_payment")
        sale_price = price_section.get("sale_price", {})

        return {
            "section": "E. Prijs en betalingsmodaliteiten",
            "verkoopprijs": input_data.verkoopprijs,
            "betaling": {
                "clause_id": sale_price.get("id"),
                "timing": sale_price.get("payment_timing"),
                "method": sale_price.get("payment_method"),
            },
            "voorschot_verrekening": price_section.get("advance_payment", {}).get("description"),
            "interesten": {
                "description": price_section.get("interest_clause", {}).get("description"),
                "exception": price_section.get("interest_clause", {}).get("exception"),
            },
        }

    def _build_declarations(self, input_data: ContractInput) -> dict:
        """Build Section F: seller declarations. Uses clause library exclusively."""
        opties = input_data.verklaarde_opties

        # Always-included mandatory declarations
        ownership = self.resolver.resolve_declaration("ownership")
        mortgage = self.resolver.resolve_declaration("mortgage_free")
        conformity = self.resolver.resolve_declaration("conformity_building")
        epc = self.resolver.resolve_declaration("epc")
        expropriation = self.resolver.resolve_declaration("expropriation")
        permits = self.resolver.resolve_declaration("building_permits")
        vacant = self.resolver.resolve_declaration("vacant_buildings")
        preemption = self.resolver.resolve_declaration("pre_emption_rights")
        repair = self.resolver.resolve_declaration("repair_claims")
        heritage = self.resolver.resolve_declaration("heritage_inventory")

        # Conditional declarations
        asbest_opt = opties.asbest_optie.value if opties and opties.asbest_optie else None
        asbestos = self.resolver.resolve_declaration("asbestos", selected_option=asbest_opt)

        bos_opt = opties.bosdecreet.value if opties and opties.bosdecreet else None
        forest = self.resolver.resolve_declaration("forest_decree", selected_option=bos_opt)

        insurance_works = opties.tienjarige_verzekering_werken if opties else None
        insurance = self.resolver.resolve_declaration("insurance_ten_year_liability",
                                                       selected_option=str(insurance_works) if insurance_works is not None else None)

        bodem_verkl = opties.bodem_verklaring.value if opties and opties.bodem_verklaring else None
        soil_decl = self.resolver.resolve_declaration("soil_declaration", selected_option=bodem_verkl)

        declarations = {
            "section": "F. Verklaringen verkoper",
            "eigendomsrecht": {"clause_id": ownership.get("id"), "content": ownership.get("content")},
            "hypotheekvrij": {"clause_id": mortgage.get("id"), "content": mortgage.get("content")},
            "conformiteit_elektriciteit": {"clause_id": conformity.get("id"), "requirements": conformity.get("requirements")},
            "epc": {"clause_id": epc.get("id"), "requirement": epc.get("requirement"), "validity": epc.get("validity")},
            "asbest": {"clause_id": asbestos.get("id"), "gekozen_optie": asbest_opt},
            "tienjarige_verzekering": {"clause_id": insurance.get("id"), "werken_uitgevoerd": insurance_works},
            "onteigening": {"clause_id": expropriation.get("id")},
            "bosdecreet": {"clause_id": forest.get("id"), "gekozen_optie": bos_opt},
            "onroerend_erfgoed": {"clause_id": heritage.get("id"), "opgenomen_in_inventaris": opties.onroerend_erfgoed if opties else None},
            "bouwvergunningen": {"clause_id": permits.get("id")},
            "leegstaande_gebouwen": {"clause_id": vacant.get("id")},
            "voorkooprechten": {"clause_id": preemption.get("id")},
            "herstelvorderingen": {"clause_id": repair.get("id")},
            "bodemattest": {
                "clause_id": soil_decl.get("id"),
                "gekozen_optie": bodem_verkl,
                "attest": {
                    "datum": input_data.bodemattest.datum if input_data.bodemattest else None,
                    "referentie": input_data.bodemattest.referentie if input_data.bodemattest else None,
                    "inhoud": input_data.bodemattest.inhoud if input_data.bodemattest else None,
                },
            },
        }

        return declarations

    def _build_sanctions(self) -> dict:
        """Build Section G: sanctions. All from clause library."""
        termination = self.resolver.resolve_clause("sanctions", "express_termination")
        compensation = self.resolver.resolve_clause("sanctions", "fixed_compensation")
        interest = self.resolver.resolve_clause("sanctions", "default_interest")
        seller_default = self.resolver.resolve_clause("sanctions", "seller_default_specifics")

        return {
            "section": "G. Sanctieregeling",
            "uitdrukkelijk_ontbindend_beding": {
                "clause_id": termination.get("id"),
                "options": termination.get("options"),
                "procedure": termination.get("procedure"),
            },
            "conventionele_schadevergoeding": {
                "clause_id": compensation.get("id"),
                "amounts": compensation.get("amounts"),
                "legal_basis": compensation.get("legal_basis"),
            },
            "nalatigheidsinteresten": {
                "clause_id": interest.get("id"),
                "rate": interest.get("rate"),
                "start_date": interest.get("start_date"),
            },
            "verkoper_in_gebreke": {
                "clause_id": seller_default.get("id"),
                "scenarios": seller_default.get("scenarios"),
            },
        }

    def _build_costs(self) -> dict:
        """Build Section H: costs. All from clause library."""
        costs = self.resolver.get_section("costs_and_charges")

        self.resolver.audit.add_clause(
            ClauseUsage(
                clause_id="COSTS_CHARGES",
                clause_title="Kosten en lasten",
                section="H. Kosten en lasten",
                library_version=self.resolver.library["version"],
            )
        )

        return {
            "section": "H. Kosten en lasten",
            "principes": costs.get("principles"),
            "kosten_verkoper": costs.get("specific_costs", {}).get("seller_costs"),
            "kosten_koper": costs.get("specific_costs", {}).get("buyer_costs"),
            "makelaarscommissie": costs.get("real_estate_commission"),
        }

    def _build_other_provisions(self) -> dict:
        """Build Section I: other provisions."""
        risk = self.resolver.resolve_clause("other_provisions", "risk_transfer")
        possession = self.resolver.resolve_clause("other_provisions", "possession")
        law = self.resolver.resolve_clause("other_provisions", "applicable_law")
        gdpr = self.resolver.resolve_clause("other_provisions", "personal_data")
        entire = self.resolver.resolve_clause("other_provisions", "entire_agreement")

        return {
            "section": "I. Diverse bepalingen",
            "overgangsrisico": {
                "clause_id": risk.get("id"),
                "principle": risk.get("principle"),
            },
            "ingebruikname": {
                "clause_id": possession.get("id"),
                "standard": possession.get("standard"),
                "condition": possession.get("condition"),
            },
            "toepasselijk_recht": {
                "clause_id": law.get("id"),
                "jurisdiction": law.get("jurisdiction"),
                "court": law.get("court"),
            },
            "persoonsgegevens": {
                "clause_id": gdpr.get("id"),
                "purpose": gdpr.get("purpose"),
                "rights": gdpr.get("rights"),
            },
            "volledigheid": {
                "clause_id": entire.get("id"),
                "principle": entire.get("principle"),
                "modifications": entire.get("modifications"),
            },
        }

    def _build_signatures(self, input_data: ContractInput) -> dict:
        """Build signature section."""
        sig_section = self.resolver.get_section("signatures")

        return {
            "section": "Ondertekening",
            "requirements": sig_section.get("requirements"),
            "legal_effect": sig_section.get("legal_effect"),
            "datum_ondertekening": input_data.datum_ondertekening.isoformat() if input_data.datum_ondertekening else None,
        }


def generate_contract(input_data: ContractInput, library_filename: str = "tweezijdige_aankoopbelofte_v0.1.json") -> dict:
    """
    Public API: generate a contract from input data.

    Returns JSON-serializable dict with contract, validation, and audit_trail.
    """
    generator = ContractGenerator(library_filename)
    return generator.generate(input_data)


def generate_contract_from_dict(data: dict, library_filename: str = "tweezijdige_aankoopbelofte_v0.1.json") -> dict:
    """
    Public API: generate a contract from a raw dict (e.g. parsed from JSON).
    Converts the dict to ContractInput, then generates.
    """
    input_data = _dict_to_contract_input(data)
    return generate_contract(input_data, library_filename)


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val)
    return None


def _parse_persoon(d: dict) -> Persoon:
    adres_data = d.get("adres")
    adres = None
    if adres_data and isinstance(adres_data, dict):
        adres = Adres(
            straat=adres_data.get("straat"),
            huisnummer=adres_data.get("huisnummer"),
            bus=adres_data.get("bus"),
            postcode=adres_data.get("postcode"),
            gemeente=adres_data.get("gemeente"),
        )

    from .models import BurgerlijkeStaat, TitelAdres

    titel = None
    if d.get("titel_adres"):
        try:
            titel = TitelAdres(d["titel_adres"])
        except ValueError:
            titel = None

    burg = None
    if d.get("burgerlijke_staat"):
        try:
            burg = BurgerlijkeStaat(d["burgerlijke_staat"])
        except ValueError:
            burg = None

    return Persoon(
        titel_adres=titel,
        naam=d.get("naam"),
        voornaam=d.get("voornaam"),
        adres=adres,
        geboorteplaats=d.get("geboorteplaats"),
        geboortedatum=_parse_date(d.get("geboortedatum")),
        rijksregisternummer=d.get("rijksregisternummer"),
        burgerlijke_staat=burg,
    )


def _dict_to_contract_input(data: dict) -> ContractInput:
    """Convert a raw dict to ContractInput."""
    from .models import BodemAttest, BodemOptie, BodemVerklaring, AsbestOptie, BosdecreetOptie

    verkopers = [_parse_persoon(v) for v in data.get("verkopers", [])]
    kopers = [_parse_persoon(k) for k in data.get("kopers", [])]

    eigendom_data = data.get("eigendom")
    eigendom = None
    if eigendom_data:
        kad_data = eigendom_data.get("kadaster")
        kadaster = None
        if kad_data:
            kadaster = Kadaster(
                afdeling=kad_data.get("afdeling"),
                sectie=kad_data.get("sectie"),
                nummer=kad_data.get("nummer"),
                oppervlakte=kad_data.get("oppervlakte"),
            )
        eigendom = Eigendom(
            type_pand=eigendom_data.get("type_pand"),
            gemeente=eigendom_data.get("gemeente"),
            straat=eigendom_data.get("straat"),
            huisnummer=eigendom_data.get("huisnummer"),
            postcode=eigendom_data.get("postcode"),
            kadaster=kadaster,
            kadastraal_inkomen=eigendom_data.get("kadastraal_inkomen"),
        )

    notaris_verkoper = None
    nv_data = data.get("notaris_verkoper")
    if nv_data:
        nv_adres = None
        if nv_data.get("adres"):
            nv_adres = Adres(**{k: v for k, v in nv_data["adres"].items() if k in ("straat", "huisnummer", "bus", "postcode", "gemeente")})
        notaris_verkoper = Notaris(
            kantoor=nv_data.get("kantoor"),
            adres=nv_adres,
            telefoon=nv_data.get("telefoon"),
            email=nv_data.get("email"),
        )

    notaris_koper = None
    nk_data = data.get("notaris_koper")
    if nk_data:
        nk_adres = None
        if nk_data.get("adres"):
            nk_adres = Adres(**{k: v for k, v in nk_data["adres"].items() if k in ("straat", "huisnummer", "bus", "postcode", "gemeente")})
        notaris_koper = Notaris(
            kantoor=nk_data.get("kantoor"),
            adres=nk_adres,
            telefoon=nk_data.get("telefoon"),
            email=nk_data.get("email"),
        )

    bodemattest = None
    ba_data = data.get("bodemattest")
    if ba_data:
        bodemattest = BodemAttest(
            datum=ba_data.get("datum"),
            referentie=ba_data.get("referentie"),
            inhoud=ba_data.get("inhoud"),
        )

    opties_data = data.get("verklaarde_opties")
    opties = None
    if opties_data:
        def _safe_enum(cls, val):
            if val is None:
                return None
            try:
                return cls(val)
            except (ValueError, KeyError):
                return None

        opties = VerklaardeOpties(
            bodem_optie=_safe_enum(BodemOptie, opties_data.get("bodem_optie")),
            bodem_verklaring=_safe_enum(BodemVerklaring, opties_data.get("bodem_verklaring")),
            asbest_optie=_safe_enum(AsbestOptie, opties_data.get("asbest_optie")),
            bosdecreet=_safe_enum(BosdecreetOptie, opties_data.get("bosdecreet")),
            onroerend_erfgoed=opties_data.get("onroerend_erfgoed"),
            tienjarige_verzekering_werken=opties_data.get("tienjarige_verzekering_werken"),
            financiering_vereist=opties_data.get("financiering_vereist"),
            rechterlijke_machtiging_vereist=opties_data.get("rechterlijke_machtiging_vereist"),
        )

    return ContractInput(
        verkopers=verkopers,
        kopers=kopers,
        eigendom=eigendom,
        notaris_verkoper=notaris_verkoper,
        notaris_koper=notaris_koper,
        verkoopprijs=data.get("verkoopprijs"),
        voorschot=data.get("voorschot"),
        bodemattest=bodemattest,
        verklaarde_opties=opties,
        datum_ondertekening=_parse_date(data.get("datum_ondertekening")),
        bijzondere_voorwaarden=data.get("bijzondere_voorwaarden"),
    )
