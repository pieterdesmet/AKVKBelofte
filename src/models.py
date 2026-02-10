"""
Data models for the Heylen Vastgoed contract generator.
Defines the input schema and internal data structures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class TitelAdres(str, Enum):
    DE_HEER = "De heer"
    MEVROUW = "Mevrouw"
    DE_HEER_EN_MEVROUW = "De heer en Mevrouw"


class BurgerlijkeStaat(str, Enum):
    ONGEHUWD = "ongehuwd"
    GEHUWD = "gehuwd"
    WETTELIJK_SAMENWONEND = "wettelijk samenwonend"
    FEITELIJK_SAMENWONEND = "feitelijk samenwonend"
    GESCHEIDEN = "gescheiden"
    WEDUWE_WEDUWNAAR = "weduwe/weduwnaar"


class BodemOptie(str, Enum):
    GEEN_RISICOGROND = "option_1"
    WEL_RISICOGROND = "option_2"


class AsbestOptie(str, Enum):
    GEEN_VERMOEDEN = "option_1"
    KOPER_VERZAAKT = "option_2"


class BosdecreetOptie(str, Enum):
    NIET_VAN_TOEPASSING = "niet_van_toepassing"
    VAN_TOEPASSING = "van_toepassing"


class BodemVerklaring(str, Enum):
    GEEN_RISICOGROND = "option_1"
    WEL_RISICOGROND = "option_2"
    GEEN_ACTIVITEIT = "option_3"


RIJKSREGISTER_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}$")


def validate_rijksregisternummer(value: str) -> bool:
    """Validate Belgian national registry number format (XX.XX.XX-XXX.XX).
    Also accepts TEST_RRN_* patterns for sanitized test data (GDPR compliance)."""
    if value.startswith("TEST_RRN_"):
        return True
    return bool(RIJKSREGISTER_PATTERN.match(value))


@dataclass
class Adres:
    straat: Optional[str] = None
    huisnummer: Optional[str] = None
    bus: Optional[str] = None
    postcode: Optional[str] = None
    gemeente: Optional[str] = None


@dataclass
class Persoon:
    titel_adres: Optional[TitelAdres] = None
    naam: Optional[str] = None
    voornaam: Optional[str] = None
    adres: Optional[Adres] = None
    geboorteplaats: Optional[str] = None
    geboortedatum: Optional[date] = None
    rijksregisternummer: Optional[str] = None
    burgerlijke_staat: Optional[BurgerlijkeStaat] = None


@dataclass
class Kadaster:
    afdeling: Optional[str] = None
    sectie: Optional[str] = None
    nummer: Optional[str] = None
    oppervlakte: Optional[str] = None


@dataclass
class Eigendom:
    type_pand: Optional[str] = None
    gemeente: Optional[str] = None
    straat: Optional[str] = None
    huisnummer: Optional[str] = None
    postcode: Optional[str] = None
    kadaster: Optional[Kadaster] = None
    kadastraal_inkomen: Optional[str] = None


@dataclass
class Notaris:
    kantoor: Optional[str] = None
    adres: Optional[Adres] = None
    telefoon: Optional[str] = None
    email: Optional[str] = None


@dataclass
class BodemAttest:
    datum: Optional[str] = None
    referentie: Optional[str] = None
    inhoud: Optional[str] = None


@dataclass
class VerklaardeOpties:
    """Seller declaration choices - which options are selected."""
    bodem_optie: Optional[BodemOptie] = None
    bodem_verklaring: Optional[BodemVerklaring] = None
    asbest_optie: Optional[AsbestOptie] = None
    bosdecreet: Optional[BosdecreetOptie] = None
    onroerend_erfgoed: Optional[bool] = None
    tienjarige_verzekering_werken: Optional[bool] = None
    financiering_vereist: Optional[bool] = None
    rechterlijke_machtiging_vereist: Optional[bool] = None


@dataclass
class ContractInput:
    """Complete input for generating a tweezijdige aankoopbelofte."""
    verkopers: list[Persoon] = field(default_factory=list)
    kopers: list[Persoon] = field(default_factory=list)
    eigendom: Optional[Eigendom] = None
    notaris_verkoper: Optional[Notaris] = None
    notaris_koper: Optional[Notaris] = None
    verkoopprijs: Optional[float] = None
    voorschot: Optional[float] = None
    bodemattest: Optional[BodemAttest] = None
    verklaarde_opties: Optional[VerklaardeOpties] = None
    datum_ondertekening: Optional[date] = None
    bijzondere_voorwaarden: Optional[str] = None
