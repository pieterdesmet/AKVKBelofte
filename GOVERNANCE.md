# Governance Notes - Heylen Vastgoed Contract Generator

## GN-001: Engine mag geen juridische conclusies trekken

**Datum**: 2026-02-10
**Status**: Actief
**Impact**: Alle risk_flags en warnings in validation/selection output

### Principe

De clause selection engine en validator zijn **data-matchers**, geen juridische
interpretatoren. Wanneer een dossier-veld (bv. `attesten.elektriciteit =
niet_conform`) matcht met een clausule (bv. `VERKL_ELEC_01`), mag de engine:

- **WEL**: flaggen dat er een mismatch/aandachtspunt is
- **WEL**: het risico-niveau aangeven (high/medium/low)
- **WEL**: verwijzen naar de relevante clausule-ID
- **NIET**: een juridische conclusie trekken ("verkoper moet herstellen")
- **NIET**: de clausetekst interpreteren als verplichting of advies

### Implementatie

Risk flags met juridische implicaties krijgen:
```json
{
  "type": "human_review_required",
  "flag": "... Vereist beoordeling door jurist of makelaar ... Engine trekt hier geen conclusie."
}
```

### Rationale

De exacte juridische gevolgen hangen af van:
1. De concrete clausetekst in context
2. Het specifieke dossier (onderhandeling, afspraken, etc.)
3. De professionele beoordeling van jurist of makelaar

Automatische conclusies zijn misleidend en potentieel aansprakelijk.
