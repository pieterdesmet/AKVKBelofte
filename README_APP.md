# Heylen Vastgoed — Contract Generator UI

Minimale Streamlit interface voor de contract generation pipeline.

## Installatie

```bash
pip install streamlit
```

## Starten

```bash
streamlit run app.py
```

## Gebruik

1. Kies een dossier uit de dropdown (7 opties: dossier_001 + 6 fixtures)
2. Klik **Load** om de JSON in de editor te laden
3. Pas de JSON eventueel aan in de editor
4. Klik **Generate** om de pipeline te runnen
5. Bekijk resultaten rechts: status badge, metrics, flags, contract tekst
6. Download assembled.json, selection.json of review_pack.zip

## Readiness statussen

| Status | Betekenis |
|--------|-----------|
| DRAFT_OK | Klaar voor interne review en handtekening |
| DRAFT_REVIEW_RECOMMENDED | Standaardclausules met aanbevolen jurist review |
| DRAFT_REVIEW_REQUIRED | Verplichte juridische review (hoog risico of bodem) |
| DRAFT_BLOCKED | Ontbrekende velden, kan niet worden afgerond |

## GDPR

De app scant automatisch op rijksregisternummers in de dossier JSON.
Bij detectie verschijnt een waarschuwing bovenaan.
Test dossiers gebruiken `TEST_RRN_` prefixen die niet als echte RRN worden gemarkeerd.
