"""
Heylen Vastgoed Contract Generator
Interne, licentie-gebonden contractgenerator voor tweezijdige aankoopbeloften.

RESTRICTIES:
- Geen juridische tekst wordt gegenereerd buiten de clause-library.
- Ontbrekende data wordt geflagd, nooit geraden.
- Alle output is machineleesbaar JSON (tenzij document_text expliciet gevraagd).
- Volledige auditbaarheid: gebruikte clauses en versies worden altijd gelogd.
"""

__version__ = "0.1.0"
