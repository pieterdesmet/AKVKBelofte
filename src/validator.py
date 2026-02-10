"""
Input validator for the contract generator.
Validates required fields and flags all missing data.
NOOIT raden - altijd flaggen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Pattern matching real Belgian RRN format: XX.XX.XX-XXX.XX
_RRN_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}")

from .models import (
    Adres,
    ContractInput,
    Eigendom,
    Kadaster,
    Notaris,
    Persoon,
    VerklaardeOpties,
    validate_rijksregisternummer,
)


@dataclass
class ValidationFlag:
    field_path: str
    message: str
    severity: str  # "required", "recommended", "info"


@dataclass
class ValidationResult:
    is_valid: bool
    flags: list[ValidationFlag] = field(default_factory=list)
    total_required_missing: int = 0
    total_recommended_missing: int = 0

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "total_required_missing": self.total_required_missing,
            "total_recommended_missing": self.total_recommended_missing,
            "flags": [
                {
                    "field": f.field_path,
                    "message": f.message,
                    "severity": f.severity,
                }
                for f in self.flags
            ],
        }


def _flag(flags: list[ValidationFlag], path: str, msg: str, severity: str = "required") -> None:
    flags.append(ValidationFlag(field_path=path, message=msg, severity=severity))


def _validate_persoon(
    persoon: Persoon,
    prefix: str,
    flags: list[ValidationFlag],
    role: str,
    require_rijksregister: bool = False,
) -> None:
    """Validate a person's required fields."""
    if not persoon.titel_adres:
        _flag(flags, f"{prefix}.titel_adres", f"{role}: aanhef ontbreekt")
    if not persoon.naam:
        _flag(flags, f"{prefix}.naam", f"{role}: familienaam ontbreekt")
    if not persoon.voornaam:
        _flag(flags, f"{prefix}.voornaam", f"{role}: voornaam ontbreekt")

    if not persoon.adres:
        _flag(flags, f"{prefix}.adres", f"{role}: volledig woonadres ontbreekt")
    else:
        _validate_adres(persoon.adres, f"{prefix}.adres", flags, role)

    if not persoon.geboorteplaats:
        _flag(flags, f"{prefix}.geboorteplaats", f"{role}: geboorteplaats ontbreekt")
    if not persoon.geboortedatum:
        _flag(flags, f"{prefix}.geboortedatum", f"{role}: geboortedatum ontbreekt")
    if not persoon.burgerlijke_staat:
        _flag(flags, f"{prefix}.burgerlijke_staat", f"{role}: burgerlijke staat ontbreekt")

    if require_rijksregister:
        if not persoon.rijksregisternummer:
            _flag(flags, f"{prefix}.rijksregisternummer", f"{role}: rijksregisternummer ontbreekt")
        elif not validate_rijksregisternummer(persoon.rijksregisternummer):
            _flag(flags, f"{prefix}.rijksregisternummer",
                  f"{role}: rijksregisternummer heeft ongeldig formaat (verwacht: XX.XX.XX-XXX.XX)")


def _validate_adres(adres: Adres, prefix: str, flags: list[ValidationFlag], context: str) -> None:
    if not adres.straat:
        _flag(flags, f"{prefix}.straat", f"{context}: straat ontbreekt")
    if not adres.huisnummer:
        _flag(flags, f"{prefix}.huisnummer", f"{context}: huisnummer ontbreekt")
    if not adres.postcode:
        _flag(flags, f"{prefix}.postcode", f"{context}: postcode ontbreekt")
    if not adres.gemeente:
        _flag(flags, f"{prefix}.gemeente", f"{context}: gemeente ontbreekt")


def _validate_eigendom(eigendom: Optional[Eigendom], flags: list[ValidationFlag]) -> None:
    if not eigendom:
        _flag(flags, "eigendom", "Eigendomsgegevens ontbreken volledig")
        return

    prefix = "eigendom"
    if not eigendom.type_pand:
        _flag(flags, f"{prefix}.type_pand", "Type pand ontbreekt")
    if not eigendom.gemeente:
        _flag(flags, f"{prefix}.gemeente", "Gemeente ontbreekt")
    if not eigendom.straat:
        _flag(flags, f"{prefix}.straat", "Straat ontbreekt")
    if not eigendom.huisnummer:
        _flag(flags, f"{prefix}.huisnummer", "Huisnummer ontbreekt")

    if not eigendom.kadaster:
        _flag(flags, f"{prefix}.kadaster", "Kadastrale gegevens ontbreken volledig")
    else:
        kad = eigendom.kadaster
        if not kad.afdeling:
            _flag(flags, f"{prefix}.kadaster.afdeling", "Kadastrale afdeling ontbreekt")
        if not kad.sectie:
            _flag(flags, f"{prefix}.kadaster.sectie", "Kadastrale sectie ontbreekt")
        if not kad.nummer:
            _flag(flags, f"{prefix}.kadaster.nummer", "Perceelnummer ontbreekt")
        if not kad.oppervlakte:
            _flag(flags, f"{prefix}.kadaster.oppervlakte", "Oppervlakte ontbreekt", severity="recommended")

    if not eigendom.kadastraal_inkomen:
        _flag(flags, f"{prefix}.kadastraal_inkomen", "Kadastraal inkomen ontbreekt")


def _validate_notaris(notaris: Optional[Notaris], prefix: str, flags: list[ValidationFlag], label: str) -> None:
    if not notaris:
        _flag(flags, prefix, f"{label} ontbreekt", severity="recommended")
        return

    if not notaris.kantoor:
        _flag(flags, f"{prefix}.kantoor", f"{label}: kantoor ontbreekt", severity="recommended")


def _validate_opties(opties: Optional[VerklaardeOpties], flags: list[ValidationFlag]) -> None:
    if not opties:
        _flag(flags, "verklaarde_opties", "Verklaarde opties ontbreken - keuzes voor bodem, asbest, etc. vereist")
        return

    prefix = "verklaarde_opties"
    if opties.bodem_optie is None:
        _flag(flags, f"{prefix}.bodem_optie", "Bodemoptie (risicogrond ja/nee) niet gekozen")
    if opties.bodem_verklaring is None:
        _flag(flags, f"{prefix}.bodem_verklaring", "Bodemverklaring verkoper niet gekozen")
    if opties.asbest_optie is None:
        _flag(flags, f"{prefix}.asbest_optie", "Asbestoptie niet gekozen", severity="recommended")
    if opties.bosdecreet is None:
        _flag(flags, f"{prefix}.bosdecreet", "Bosdecreet toepasselijkheid niet gekozen", severity="recommended")
    if opties.financiering_vereist is None:
        _flag(flags, f"{prefix}.financiering_vereist", "Financieringsvoorwaarde niet gekozen")


def _scan_for_rrn_patterns(data: Any, path: str, flags: list[ValidationFlag]) -> None:
    """
    Recursively scan all string values in the input data for real RRN patterns.
    Flags a high-severity warning if found. Does NOT block generation.
    Advises masking with TEST_RRN_xxx values.
    """
    if isinstance(data, str):
        if _RRN_PATTERN.search(data):
            _flag(
                flags, path,
                f"GDPR-waarschuwing: waarde '{data}' lijkt een echt rijksregisternummer te bevatten. "
                f"Gebruik testwaarden (bv. TEST_RRN_001) in niet-productiedata.",
                severity="high",
            )
    elif isinstance(data, dict):
        for key, value in data.items():
            _scan_for_rrn_patterns(value, f"{path}.{key}" if path else key, flags)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _scan_for_rrn_patterns(item, f"{path}[{i}]", flags)


def validate_contract_input(input_data: ContractInput) -> ValidationResult:
    """
    Validate all required input for contract generation.
    Flags ALL missing or invalid data - never guesses.
    """
    flags: list[ValidationFlag] = []

    # Verkopers (min 1, max 4)
    if not input_data.verkopers:
        _flag(flags, "verkopers", "Geen verkopers opgegeven (minimum 1 vereist)")
    elif len(input_data.verkopers) > 4:
        _flag(flags, "verkopers", "Meer dan 4 verkopers opgegeven (maximum is 4)")
    else:
        for i, verkoper in enumerate(input_data.verkopers):
            _validate_persoon(
                verkoper, f"verkopers[{i}]", flags,
                role=f"Verkoper {i + 1}",
                require_rijksregister=True,
            )

    # Kopers (min 1, max 4)
    if not input_data.kopers:
        _flag(flags, "kopers", "Geen kopers opgegeven (minimum 1 vereist)")
    elif len(input_data.kopers) > 4:
        _flag(flags, "kopers", "Meer dan 4 kopers opgegeven (maximum is 4)")
    else:
        for i, koper in enumerate(input_data.kopers):
            _validate_persoon(
                koper, f"kopers[{i}]", flags,
                role=f"Koper {i + 1}",
                require_rijksregister=False,
            )

    # Eigendom
    _validate_eigendom(input_data.eigendom, flags)

    # Prijs
    if input_data.verkoopprijs is None:
        _flag(flags, "verkoopprijs", "Verkoopprijs ontbreekt")
    elif input_data.verkoopprijs <= 0:
        _flag(flags, "verkoopprijs", "Verkoopprijs moet groter zijn dan 0")

    if input_data.voorschot is None:
        _flag(flags, "voorschot", "Voorschot/optieprijs ontbreekt")
    elif input_data.voorschot <= 0:
        _flag(flags, "voorschot", "Voorschot moet groter zijn dan 0")

    # Notarissen
    _validate_notaris(input_data.notaris_verkoper, "notaris_verkoper", flags, "Notaris verkoper")
    _validate_notaris(input_data.notaris_koper, "notaris_koper", flags, "Notaris koper")

    # Opties/Verklaringen
    _validate_opties(input_data.verklaarde_opties, flags)

    # Bodemattest
    if input_data.bodemattest:
        if not input_data.bodemattest.datum:
            _flag(flags, "bodemattest.datum", "Datum bodemattest ontbreekt", severity="recommended")
        if not input_data.bodemattest.referentie:
            _flag(flags, "bodemattest.referentie", "Referentienummer bodemattest ontbreekt", severity="recommended")

    # Datum ondertekening
    if not input_data.datum_ondertekening:
        _flag(flags, "datum_ondertekening", "Datum van ondertekening ontbreekt")

    # GDPR: scan for real RRN patterns in all string fields
    _scan_for_rrn_patterns(input_data.__dict__, "", flags)

    required_missing = sum(1 for f in flags if f.severity == "required")
    recommended_missing = sum(1 for f in flags if f.severity == "recommended")

    return ValidationResult(
        is_valid=required_missing == 0,
        flags=flags,
        total_required_missing=required_missing,
        total_recommended_missing=recommended_missing,
    )
