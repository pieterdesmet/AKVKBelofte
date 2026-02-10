"""
CIB clause catalog for tweezijdige aankoopbelofte.

Each clause is a literal text block from the CIB template.
Where exact CIB text is not yet available, the block is marked CIB_TEXT_REQUIRED.

NEVER paraphrase or rewrite legal text.  Only select and assemble existing blocks.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# CIB document section ordering
# ---------------------------------------------------------------------------
CIB_SECTIONS = [
    {"id": "PARTIJEN", "title": "Partijen", "order": 0},
    {"id": "EIGENDOM", "title": "Aanduiding van het onroerend goed", "order": 1},
    {"id": "A", "title": "A. Verkoopbelofte en aankoopbelofte", "order": 2},
    {"id": "B", "title": "B. Modaliteiten", "order": 3},
    {"id": "C", "title": "C. Optieprijs / voorschot", "order": 4},
    {"id": "D", "title": "D. Opschortende voorwaarden", "order": 5},
    {"id": "E", "title": "E. Prijs en betaling", "order": 6},
    {"id": "F", "title": "F. Verklaringen verkoper", "order": 7},
    {"id": "G", "title": "G. Sanctieregeling", "order": 8},
    {"id": "H", "title": "H. Diverse bepalingen", "order": 9},
]

SECTION_ORDER = {s["id"]: s["order"] for s in CIB_SECTIONS}

# ---------------------------------------------------------------------------
# Clause catalog
#
# Fields per clause:
#   id              – unique identifier
#   section         – CIB section id (matches CIB_SECTIONS)
#   title           – short label for UI / logs
#   text_block      – literal CIB text (or CIB_TEXT_REQUIRED placeholder)
#   subtype         – "fixed" | "parametric" (has {{placeholders}}) | "party"
#   triggers        – dict of conditions that must ALL be true to include clause
#                     key = field name, value = expected value or special check
#                     empty dict → always included
#   blocking_level  – "none" | "required" | "ask"
#                     "required" → jurist review mandatory
#                     "ask"      → ambiguous data, Legal must confirm
#   legal_gate_requires – list of legal gate item ids that must be confirmed
#   order_in_section    – ordering within its section
# ---------------------------------------------------------------------------

CIB_CLAUSES: list[dict] = [
    # ── PARTIJEN ──────────────────────────────────────────────────────────
    {
        "id": "CIB_PARTIJ_VERKOPER",
        "section": "PARTIJEN",
        "title": "Verkoper(s)",
        "text_block": (
            "{{titel_adres}} {{voornaam}} {{naam}}, wonende te {{woonadres_volledig}}, "
            "geboren te {{geboorteplaats}} op {{geboortedatum}}, "
            "rijksregisternummer {{rijksregisternummer}}, {{burgerlijke_staat}}.\n"
            "Hierna «de verkoper» genoemd.\n"
            "Verklaren de (enige) eigenaars te zijn en bevoegd en bekwaam om te verkopen. "
            "Hoofdelijk en ondeelbaar verbonden indien meerdere personen."
        ),
        "subtype": "party",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_PARTIJ_KOPER",
        "section": "PARTIJEN",
        "title": "Koper(s)",
        "text_block": (
            "{{titel_adres}} {{voornaam}} {{naam}}, wonende te {{woonadres_volledig}}, "
            "geboren te {{geboorteplaats}} op {{geboortedatum}}, {{burgerlijke_staat}}.\n"
            "Hierna «de koper» genoemd.\n"
            "Verklaren bevoegd en bekwaam te zijn om aan te kopen. "
            "Hoofdelijk en ondeelbaar verbonden indien meerdere personen."
        ),
        "subtype": "party",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },

    # ── EIGENDOM ──────────────────────────────────────────────────────────
    {
        "id": "CIB_EIGENDOM_01",
        "section": "EIGENDOM",
        "title": "Aanduiding onroerend goed",
        "text_block": (
            "{{pand.pandtype}} gelegen te {{pand.gemeente}}, {{pand.straat}} {{pand.huisnummer}}, "
            "kadastraal bekend {{pand.kadaster.afdeling}} afdeling, sectie {{pand.kadaster.sectie}}, "
            "nummer {{pand.kadaster.perceelnummer}}, met een oppervlakte van "
            "{{pand.kadaster.oppervlakte}} m², niet-geïndexeerd kadastraal inkomen: {{pand.ki}} EUR."
        ),
        "subtype": "parametric",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_EIGENDOM_02",
        "section": "EIGENDOM",
        "title": "Kadastrale disclaimer",
        "text_block": (
            "De kadastrale gegevens dienen slechts als eenvoudige inlichtingen en de "
            "kandidaat-koper kan zich niet beroepen op enige onjuistheid of vergetelheid "
            "in deze aanduidingen."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_EIGENDOM_03",
        "section": "EIGENDOM",
        "title": "Bezichtiging en kennis staat",
        "text_block": (
            "De kandidaat-koper verklaart deze eigendom zelf te hebben bezichtigd en de "
            "staat, ligging en bestemming ervan goed te kennen. De kandidaat-koper ontslaat "
            "de kandidaat-verkoper ervan om een verdere omschrijving van het goed te geven "
            "in deze overeenkomst."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },

    # ── A. Verkoopbelofte en aankoopbelofte ───────────────────────────────
    {
        "id": "CIB_A_VERKOOPBELOFTE",
        "section": "A",
        "title": "Verkoopbelofte (call-optie)",
        "text_block": (
            "De kandidaat-verkoper verbindt zich om gedurende een termijn van vier maanden "
            "na ondertekening het onroerend goed enkel aan de kandidaat-koper TE VERKOPEN "
            "tegen de bepaalde voorwaarden. Kandidaat-koper heeft het recht om te kopen. "
            "Termijn kan in onderling akkoord verlengd worden, enkel bewijs door geschrift "
            "ondertekend door beide partijen."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_A_AANKOOPBELOFTE",
        "section": "A",
        "title": "Aankoopbelofte (put-optie)",
        "text_block": (
            "Voor het geval de call-optie niet (tijdig) wordt gelicht, verbindt de "
            "kandidaat-koper zich om het goed AAN TE KOPEN gedurende één maand na "
            "verstrijken call-optie termijn. Kandidaat-verkoper kan verkoop afdwingen. "
            "7% per jaar op saldo koopprijs gedurende put-optie termijn."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_A_TOTSTANDKOMING",
        "section": "A",
        "title": "Totstandkoming verkoop",
        "text_block": (
            "De verkoop komt pas tot stand door het verlijden van de notariële akte "
            "(plechtig contract). In afwijking van het gemeen recht, op het ogenblik van "
            "het verlijden van de notariële akte. Notaris bevestigt onder professionele "
            "aansprakelijkheid dat er juridisch geen bezwaren bestaan. Zolang de notariële "
            "akte niet werd verleden, bestaat er nog geen verkoop maar enkel een verbintenis. "
            "Tenzij dwingende overheidsbepalingen zich verzetten (zoals voorkooprecht pachter "
            "of harmonisatiedecreet)."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "required",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },

    # ── B. Modaliteiten ───────────────────────────────────────────────────
    {
        "id": "CIB_B_UITNODIGING",
        "section": "B",
        "title": "Uitnodiging ondertekening akte",
        "text_block": (
            "Schriftelijke uitnodiging via notaris tot ondertekening notariële akte op "
            "plaats, dag en uur bepaald in samenspraak met notaris. Door deze uitnodiging "
            "licht de partij de optie. Verplichting de akte te verlijden vóór verstrijken "
            "termijn. Kandidaat-koper moet bodemattest en stedenbouwkundig "
            "uittreksel/inlichtingen hebben ontvangen vooraleer optie te lichten."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_B_INDEPLAATSSTELLING",
        "section": "B",
        "title": "Indeplaatsstelling",
        "text_block": (
            "Kandidaat-koper mag een ander persoon in zijn plaats stellen voor geheel of "
            "een deel van zijn rechten en verplichtingen. Verkoop moet steeds betrekking "
            "hebben op geheel het eigendom. Kandidaat-koper blijft steeds hoofdelijk en "
            "ondeelbaar gehouden. Identiteit nieuwe kopers uiterlijk 30 dagen vóór akte "
            "aan notaris meedelen."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_B_NOTARISSEN",
        "section": "B",
        "title": "Aanduiding notarissen",
        "text_block": (
            "Partijen hebben steeds recht een notaris aan te duiden. Optreden meerdere "
            "notarissen geeft geen aanleiding tot verhoging van de kosten. "
            "Notaris kandidaat-verkoper: {{notaris.verkoper}}. "
            "Notaris kandidaat-koper: {{notaris.koper}}."
        ),
        "subtype": "parametric",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },

    # ── C. Optieprijs / voorschot ─────────────────────────────────────────
    {
        "id": "CIB_C_OPTIEPRIJS",
        "section": "C",
        "title": "Optieprijs",
        "text_block": (
            "Kandidaat-koper is optieprijs verschuldigd ten bedrage van "
            "{{transactie.waarborg}} EUR als tegenprestatie voor verkoopbelofte (call-optie) "
            "naast de verleende aankoopbelofte (put-optie). Betaling via overschrijving op "
            "rekening Heylen Vastgoed BV KBC BE21 7330 3886 5203, binnen 5 werkdagen na "
            "ondertekening, met mededeling {{pand.straat}} {{pand.huisnummer}} - "
            "{{pand.postcode}} {{pand.gemeente}}. Ter consignatie tot verlijden notariële akte."
        ),
        "subtype": "parametric",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_C_DRIEVOUDIGE_FUNCTIE",
        "section": "C",
        "title": "Drievoudige functie optieprijs",
        "text_block": (
            "Het bedrag heeft een drievoudige functie: waarborg voor uitvoering "
            "verbintenissen kandidaat-koper, voorschot op koopprijs (aangerekend bij "
            "verlijden akte), en optieprijs (definitief verworven door verkoper onder "
            "voorwaarden). Call-optie termijn verstrijkt zonder lichting EN verkoper licht "
            "put-optie niet: bedrag komt toe aan kandidaat-verkoper als definitief verworven "
            "optieprijs, behoudens wat bepaald onder opschortende voorwaarden. Opschortende "
            "voorwaarden realiseren zich niet tijdig: bedrag wordt teruggegeven aan "
            "kandidaat-koper."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_C_ONTBINDEND_BEDING",
        "section": "C",
        "title": "Uitdrukkelijk ontbindend beding bij niet-betaling",
        "text_block": (
            "Verkoper kan zich beroepen op uitdrukkelijk ontbindend beding bij "
            "niet-tijdige betaling. Aanspraak op conventioneel voorziene schadevergoeding. "
            "Conventioneel voorziene nalatigheidsinteresten bij laattijdige betaling."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },

    # ── D. Opschortende voorwaarden ───────────────────────────────────────
    {
        "id": "CIB_D_BODEM_GEEN_RISICO",
        "section": "D",
        "title": "Bodem – geen risicogrond",
        "text_block": (
            "Opschortende voorwaarde in voordeel van de kandidaat-koper: bekomen bodemattest "
            "vóór verstrijken verkoopbelofte termijn. Bodemattest toont geen gegevens bij "
            "OVAM OF geen bodemverontreiniging die saneringsverplichting geeft. Zekerheid "
            "dat eigendom geen risicogrond is via navraag OVAM en gemeente."
        ),
        "subtype": "fixed",
        "triggers": {"bodem_variant": "geen_risicogrond"},
        "blocking_level": "none",
        "legal_gate_requires": ["bodem_variant", "bodemattest_uploaded"],
        "order_in_section": 0,
    },
    {
        "id": "CIB_D_BODEM_RISICO_GEEN_SANERING",
        "section": "D",
        "title": "Bodem – risicogrond zonder saneringsverplichting",
        "text_block": (
            "Opschortende voorwaarde in voordeel van de kandidaat-koper: bekomen bodemattest "
            "vóór verstrijken verkoopbelofte termijn. Bodemattest toont geen "
            "bodemverontreiniging die saneringsverplichting geeft. Kandidaat-verkoper geeft "
            "opdracht aan notaris om op zijn kosten oriënterend bodemonderzoek te laten "
            "uitvoeren indien nodig."
        ),
        "subtype": "fixed",
        "triggers": {"bodem_variant": "risicogrond_geen_sanering"},
        "blocking_level": "required",
        "legal_gate_requires": ["bodem_variant", "bodemattest_uploaded"],
        "order_in_section": 0,
    },
    {
        "id": "CIB_D_BODEM_SANERING",
        "section": "D",
        "title": "Bodem – saneringsverplichting",
        "text_block": "CIB_TEXT_REQUIRED",
        "subtype": "fixed",
        "triggers": {"bodem_variant": "sanering_vereist"},
        "blocking_level": "required",
        "legal_gate_requires": ["bodem_variant", "bodemattest_uploaded"],
        "order_in_section": 0,
    },
    {
        "id": "CIB_D_STEDENBOUW",
        "section": "D",
        "title": "Ruimtelijke ordening",
        "text_block": (
            "Opschortende voorwaarde in voordeel van de kandidaat-koper: eigendom niet "
            "zonevreemd, vereiste vergunningen werden afgeleverd (tenzij vermoeden van "
            "vergunning), geen bouwmisdrijf, geen stedenbouwkundige beschermingsmaatregel, "
            "niet gelegen in onteigening of ontwerp onteigeningsplan, geen ongeldige verdeling."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_D_FINANCIERING",
        "section": "D",
        "title": "Opschortende voorwaarde financiering",
        "text_block": (
            "Opschortende voorwaarde in voordeel van de kandidaat-koper: het bekomen van "
            "een hypothecair krediet voor maximaal de verkoopprijs aan normale actuele "
            "marktvoorwaarden. Verzaking via aangetekend schrijven aan vastgoedmakelaar en "
            "notaris verkoper, uiterlijk 14 kalenderdagen na dagtekening overeenkomst, met "
            "minstens twee originele attesten van verschillende Belgische financiële "
            "instellingen die bevestigen dat krediet niet kan worden toegestaan."
        ),
        "subtype": "fixed",
        "triggers": {"financiering_vereist": True},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },
    {
        "id": "CIB_D_VRIJ_ONBELAST",
        "section": "D",
        "title": "Vrij en onbelast",
        "text_block": (
            "Opschortende voorwaarde in voordeel van beide partijen: toezegging "
            "(schuld)eisers dat eigendom vrij en onbelast verkocht kan worden. Geen "
            "bezwarende in- of overschrijvingen of kantmeldingen. Geen andere bezwarende "
            "vorderingen of belemmeringen. Kosten ten laste van kandidaat-verkoper."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 3,
    },
    {
        "id": "CIB_D_VOORKOOPRECHT",
        "section": "D",
        "title": "Voorkooprecht",
        "text_block": "CIB_TEXT_REQUIRED",
        "subtype": "fixed",
        "triggers": {"voorkooprecht": "ja"},
        "blocking_level": "required",
        "legal_gate_requires": ["voorkooprecht"],
        "order_in_section": 4,
    },

    # ── E. Prijs en betaling ──────────────────────────────────────────────
    {
        "id": "CIB_E_PRIJS",
        "section": "E",
        "title": "Verkoopprijs",
        "text_block": (
            "De verkoopprijs bedraagt {{transactie.verkoopsprijs}} EUR, contant te betalen "
            "bij verlijden notariële akte via rekening van instrumenterende notaris(sen). "
            "Het voorschot/optieprijs wordt aangerekend op de koopprijs bij verlijden akte. "
            "Geen interesten verschuldigd op koopprijs tussen ondertekening en betaling, "
            "tenzij put-optie gelicht wordt (dan 7% per jaar op saldo)."
        ),
        "subtype": "parametric",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },

    # ── F. Verklaringen verkoper ──────────────────────────────────────────
    {
        "id": "CIB_F_EIGENDOM",
        "section": "F",
        "title": "Verklaring eigendomsrecht",
        "text_block": (
            "Verkoper verklaart eigenaar te zijn en bevoegd te verkopen zonder beperking. "
            "Eigendom zal vrij en onbelast worden overgedragen. Kosten afbetaling hypotheek "
            "ten laste verkoper."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_F_ELEKTRICITEIT_CONFORM",
        "section": "F",
        "title": "Elektriciteit – conform",
        "text_block": (
            "De verkoper verklaart dat de elektrische installatie conform is en beschikt "
            "over een geldig keuringsattest. Het keuringsattest wordt aan de koper "
            "overhandigd bij het verlijden van de notariële akte."
        ),
        "subtype": "fixed",
        "triggers": {"elektriciteit_variant": "conform"},
        "blocking_level": "none",
        "legal_gate_requires": ["elektriciteit_variant", "elektriciteit_keuring_uploaded"],
        "order_in_section": 1,
    },
    {
        "id": "CIB_F_ELEKTRICITEIT_NIET_CONFORM",
        "section": "F",
        "title": "Elektriciteit – niet conform",
        "text_block": (
            "Conformiteit elektrische installatie: keuringsattest vereist voor installaties "
            "ouder dan 25 jaar of niet conform. Ten laste van verkoper, ten laatste bij "
            "ondertekening notariële akte. Bij niet-conformiteit moet verkoper laten "
            "herstellen of akkoord krijgen om prijs te verminderen."
        ),
        "subtype": "fixed",
        "triggers": {"elektriciteit_variant": "niet_conform"},
        "blocking_level": "none",
        "legal_gate_requires": ["elektriciteit_variant", "elektriciteit_keuring_uploaded"],
        "order_in_section": 1,
    },
    {
        "id": "CIB_F_ELEKTRICITEIT_GEEN_KEURING",
        "section": "F",
        "title": "Elektriciteit – nog geen keuring",
        "text_block": "CIB_TEXT_REQUIRED",
        "subtype": "fixed",
        "triggers": {"elektriciteit_variant": "geen_keuring"},
        "blocking_level": "ask",
        "legal_gate_requires": ["elektriciteit_variant"],
        "order_in_section": 1,
    },
    {
        "id": "CIB_F_EPC",
        "section": "F",
        "title": "Energieprestatiecertificaat",
        "text_block": (
            "Energieprestatiecertificaat (EPC) moet ter beschikking gesteld worden aan "
            "kandidaat-koper, maximum 10 jaar geldig. Kandidaat-koper verklaart kennis "
            "genomen te hebben van het EPC."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": ["epc_uploaded"],
        "order_in_section": 2,
    },
    {
        "id": "CIB_F_EPC_RENOVATIE",
        "section": "F",
        "title": "EPC – renovatieverplichting",
        "text_block": "CIB_TEXT_REQUIRED",
        "subtype": "fixed",
        "triggers": {"epc_renovation_required": True},
        "blocking_level": "none",
        "legal_gate_requires": ["epc_uploaded"],
        "order_in_section": 3,
    },
    {
        "id": "CIB_F_ASBEST",
        "section": "F",
        "title": "Asbestinventaris",
        "text_block": (
            "Asbestinventaris of attest afwezigheid asbest vereist voor woningen met "
            "bouwvergunning vóór 2001, vóór verlijden authentieke akte."
        ),
        "subtype": "fixed",
        "triggers": {"asbest_vereist": True},
        "blocking_level": "none",
        "legal_gate_requires": ["asbest_uploaded"],
        "order_in_section": 4,
    },
    {
        "id": "CIB_F_BODEM_VERKLARING",
        "section": "F",
        "title": "Verklaring bodem",
        "text_block": (
            "De kandidaat-verkoper verklaart dat het goed "
            "{{verklaarde_opties.bodem_verklaring}}. Bodemattest dd. {{bodemattest.datum}}, "
            "referentie {{bodemattest.referentie}}: {{bodemattest.inhoud}}. De "
            "kandidaat-verkoper verklaart dat het kadastraal inkomen niet onderworpen is "
            "aan een herziening en dat er geen procedures hieromtrent lopende zijn."
        ),
        "subtype": "parametric",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": ["bodemattest_uploaded"],
        "order_in_section": 5,
    },
    {
        "id": "CIB_F_MEDE_EIGENDOM",
        "section": "F",
        "title": "Mede-eigendom – basisakte en syndicus",
        "text_block": "CIB_TEXT_REQUIRED",
        "subtype": "parametric",
        "triggers": {"mede_eigendom": "ja"},
        "blocking_level": "required",
        "legal_gate_requires": ["mede_eigendom", "syndicus_info_received"],
        "order_in_section": 6,
    },

    # ── G. Sanctieregeling ────────────────────────────────────────────────
    {
        "id": "CIB_G_SANCTIE_01",
        "section": "G",
        "title": "Sanctie – keuzerecht onschuldige partij",
        "text_block": (
            "Bij niet-naleving kan onschuldige partij naar keuze: uitvoering eisen in "
            "rechte indien mogelijk, of ontbinding vorderen van de overeenkomst. Steeds "
            "met schadevergoeding en interesten indien van toepassing. Na voorafgaande "
            "ingebrekestelling per aangetekende brief met 15 dagen termijn."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "required",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_G_SANCTIE_02",
        "section": "G",
        "title": "Sanctie – schadevergoeding",
        "text_block": (
            "Bij bewezen tekortkoming zonder tijdige regularisatie na ingebrekestelling: "
            "optieprijs/waarborg/voorschot komt toe aan onschuldige partij. Indien "
            "ontoereikend: aanvullende schadevergoeding van 10% van verkoopprijs. Bij "
            "tekortkoming verkoper: minimum 10% van verkoopprijs (naast teruggave "
            "voorschot). Nalatigheidsinteresten aan wettelijke intrestvoet, van "
            "rechtswege vanaf vervaldag zonder ingebrekestelling."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "required",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },

    # ── H. Diverse bepalingen ─────────────────────────────────────────────
    {
        "id": "CIB_H_KOSTEN",
        "section": "H",
        "title": "Kosten",
        "text_block": (
            "Registratierechten en kosten van de akte ten laste van koper. "
            "Verkoophonorarium ten laste van verkoper. Aktekosten volgens gebruikelijke "
            "verdeling notariaat."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 0,
    },
    {
        "id": "CIB_H_RISICO",
        "section": "H",
        "title": "Risico en bewaarplicht",
        "text_block": (
            "Goed reist op risico verkoper tot verlijden akte. Verkoper moet eigendom "
            "onderhouden en in goede staat bewaren. Ingebruikname bij verlijden notariële "
            "akte, leeg, vrij en ontruimd van personen en goederen."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 1,
    },
    {
        "id": "CIB_H_BEVOEGDHEID",
        "section": "H",
        "title": "Toepasselijk recht en bevoegde rechtbank",
        "text_block": (
            "Toepasselijk recht: Belgisch recht. Bevoegde rechtbanken: rechtbanken van "
            "arrondissement waar onroerend goed gelegen is. Deze overeenkomst vervangt "
            "alle eerdere afspraken. Wijzigingen enkel geldig indien schriftelijk en door "
            "beide partijen ondertekend."
        ),
        "subtype": "fixed",
        "triggers": {},
        "blocking_level": "none",
        "legal_gate_requires": [],
        "order_in_section": 2,
    },
]


def get_clause_by_id(clause_id: str) -> dict | None:
    """Look up a single clause by id."""
    for c in CIB_CLAUSES:
        if c["id"] == clause_id:
            return c
    return None


def get_clauses_for_section(section_id: str) -> list[dict]:
    """Return clauses belonging to a section, ordered by order_in_section."""
    return sorted(
        [c for c in CIB_CLAUSES if c["section"] == section_id],
        key=lambda c: c["order_in_section"],
    )
