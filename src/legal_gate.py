"""
Legal Gate: blocking confirmations that must be cleared before contract generation.

Each gate item represents a legal confirmation or upload verification.
If any blocking item is unconfirmed, generation is disabled.

Ask-when-uncertain: when Omnicasa data is null/ambiguous, the item status
becomes "ask" rather than assuming a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Gate item definitions
# ---------------------------------------------------------------------------

@dataclass
class GateItem:
    """A single legal gate confirmation."""
    id: str
    label: str
    category: str  # UI grouping
    input_type: str  # "select" | "checkbox"
    options: list[str] = field(default_factory=list)  # for select type
    blocking: bool = True  # if True, must be confirmed to allow generation
    help_text: str = ""
    default: Any = None


# All gate items in presentation order
GATE_ITEMS: list[GateItem] = [
    # ── Bodem ─────────────────────────────────────────────────────────────
    GateItem(
        id="bodem_variant",
        label="Bodemvariant",
        category="Bodem",
        input_type="select",
        options=["geen_risicogrond", "risicogrond_geen_sanering", "sanering_vereist"],
        blocking=True,
        help_text="Kies de variant op basis van het bodemattest (OVAM).",
    ),
    GateItem(
        id="bodemattest_uploaded",
        label="Bodemattest geüpload",
        category="Bodem",
        input_type="checkbox",
        blocking=True,
        help_text="Bevestig dat het bodemattest beschikbaar is.",
    ),

    # ── Mede-eigendom ─────────────────────────────────────────────────────
    GateItem(
        id="mede_eigendom",
        label="Mede-eigendom (appartement / VME)",
        category="Mede-eigendom",
        input_type="select",
        options=["nee", "ja"],
        blocking=True,
        help_text="Is het goed onderdeel van een mede-eigendom?",
    ),
    GateItem(
        id="syndicus_info_received",
        label="Syndicus-informatie ontvangen",
        category="Mede-eigendom",
        input_type="checkbox",
        blocking=False,  # only blocking when mede_eigendom == ja
        help_text="Enkel vereist bij mede-eigendom. Basisakte, RVM, werkkapitaal, ...",
    ),

    # ── Voorkooprechten ───────────────────────────────────────────────────
    GateItem(
        id="voorkooprecht",
        label="Voorkooprecht",
        category="Voorkooprechten",
        input_type="select",
        options=["nee", "ja", "onbekend"],
        blocking=True,
        help_text=(
            "Rust er een voorkooprecht op het goed? "
            "Kies 'onbekend' als Omnicasa geen data bevat — Legal moet bevestigen."
        ),
    ),

    # ── Elektriciteit ─────────────────────────────────────────────────────
    GateItem(
        id="elektriciteit_variant",
        label="Elektriciteitskeuring",
        category="Elektriciteit",
        input_type="select",
        options=["conform", "niet_conform", "geen_keuring"],
        blocking=True,
        help_text="Selecteer de status van het keuringsattest elektrische installatie.",
    ),
    GateItem(
        id="elektriciteit_keuring_uploaded",
        label="Keuringsattest geüpload",
        category="Elektriciteit",
        input_type="checkbox",
        blocking=False,  # dynamic: blocking when variant != geen_keuring
        help_text="Bevestig dat het keuringsattest beschikbaar is.",
    ),

    # ── EPC ───────────────────────────────────────────────────────────────
    GateItem(
        id="epc_uploaded",
        label="EPC geüpload",
        category="EPC",
        input_type="checkbox",
        blocking=True,
        help_text="Bevestig dat het energieprestatiecertificaat beschikbaar is.",
    ),
    GateItem(
        id="epc_label",
        label="EPC label",
        category="EPC",
        input_type="select",
        options=["A", "B", "C", "D", "E", "F"],
        blocking=False,
        help_text="Optioneel: het EPC label. Label D of slechter activeert renovatieverplichting.",
    ),

    # ── Asbest ────────────────────────────────────────────────────────────
    GateItem(
        id="asbest_uploaded",
        label="Asbestattest geüpload",
        category="Asbest",
        input_type="checkbox",
        blocking=False,  # dynamic: blocking when constructionYear < 2001
        help_text="Enkel verplicht voor woningen met bouwvergunning vóór 2001.",
    ),

    # ── Overstromingsgevoeligheid ─────────────────────────────────────────
    GateItem(
        id="overstromingszone",
        label="Overstromingsgevoeligheid geverifieerd",
        category="Overig",
        input_type="checkbox",
        blocking=False,
        help_text="Bevestig dat de overstromingskaart geraadpleegd is.",
    ),

    # ── Stedenbouw ────────────────────────────────────────────────────────
    GateItem(
        id="stedenbouwkundig_uittreksel_uploaded",
        label="Stedenbouwkundig uittreksel geüpload",
        category="Overig",
        input_type="checkbox",
        blocking=False,
        help_text="Bevestig dat het stedenbouwkundig uittreksel beschikbaar is.",
    ),
]

GATE_ITEMS_BY_ID: dict[str, GateItem] = {g.id: g for g in GATE_ITEMS}


# ---------------------------------------------------------------------------
# Gate state and evaluation
# ---------------------------------------------------------------------------

def empty_gate_state() -> dict[str, Any]:
    """Return a fresh gate state with all items unconfirmed."""
    state: dict[str, Any] = {}
    for g in GATE_ITEMS:
        if g.input_type == "checkbox":
            state[g.id] = False
        elif g.input_type == "select":
            state[g.id] = None  # unselected
    return state


def prefill_from_dossier(dossier: dict) -> dict[str, Any]:
    """
    Pre-fill gate state from dossier data where unambiguous.
    Ambiguous/missing values are left as None → triggers "ask" in UI.
    """
    state = empty_gate_state()

    # Bodem
    bodem = _dot(dossier, "attesten.bodem")
    if bodem == "ok":
        state["bodem_variant"] = "geen_risicogrond"
    elif bodem == "risico":
        state["bodem_variant"] = "risicogrond_geen_sanering"
    # else: None → ask

    if _dot(dossier, "bodemattest.datum"):
        state["bodemattest_uploaded"] = True

    # Mede-eigendom
    me = dossier.get("mede_eigendom")
    if me is True:
        state["mede_eigendom"] = "ja"
    elif me is False:
        state["mede_eigendom"] = "nee"
    # else: None → ask

    # Voorkooprecht — Omnicasa field hasPreemptiveRightsId
    preemptive = dossier.get("hasPreemptiveRightsId")
    if preemptive is None or preemptive == 0:
        state["voorkooprecht"] = "onbekend"  # ask Legal to confirm
    elif preemptive == 1:
        state["voorkooprecht"] = "ja"
    else:
        state["voorkooprecht"] = "nee"

    # Elektriciteit
    elek = _dot(dossier, "attesten.elektriciteit")
    if elek == "ok":
        state["elektriciteit_variant"] = "conform"
    elif elek == "niet_conform":
        state["elektriciteit_variant"] = "niet_conform"
    # else: None → ask

    # EPC
    epc_label = _dot(dossier, "attesten.epc_label")
    if epc_label:
        state["epc_label"] = epc_label

    # Asbest
    asbest = _dot(dossier, "attesten.asbest")
    if asbest and "ok" in str(asbest):
        state["asbest_uploaded"] = True

    return state


def get_dynamic_blocking(gate_state: dict[str, Any], dossier: dict) -> dict[str, bool]:
    """
    Compute which items are effectively blocking given current state/dossier.
    Some items are only blocking conditionally.
    """
    blocking: dict[str, bool] = {}
    for g in GATE_ITEMS:
        if g.blocking:
            blocking[g.id] = True
        else:
            blocking[g.id] = False

    # syndicus_info_received: blocking only when mede_eigendom == ja
    if gate_state.get("mede_eigendom") == "ja":
        blocking["syndicus_info_received"] = True

    # elektriciteit_keuring_uploaded: blocking when variant is set (not geen_keuring)
    ev = gate_state.get("elektriciteit_variant")
    if ev in ("conform", "niet_conform"):
        blocking["elektriciteit_keuring_uploaded"] = True

    # asbest_uploaded: blocking when constructionYear < 2001
    bouwjaar = _dot(dossier, "pand.bouwjaar")
    if bouwjaar is not None and int(bouwjaar) < 2001:
        blocking["asbest_uploaded"] = True

    return blocking


def evaluate_gate(gate_state: dict[str, Any], dossier: dict) -> dict:
    """
    Evaluate the legal gate.

    Returns:
        {
            "cleared": bool,                 # True if generation allowed
            "blocking_items": [...],         # list of {id, label, reason}
            "ask_items": [...],              # items where Legal must confirm
            "confirmed_count": int,
            "total_blocking_count": int,
        }
    """
    dynamic_blocking = get_dynamic_blocking(gate_state, dossier)

    blocking_items: list[dict] = []
    ask_items: list[dict] = []
    confirmed = 0
    total_blocking = 0

    for g in GATE_ITEMS:
        is_blocking = dynamic_blocking.get(g.id, False)
        if not is_blocking:
            continue

        total_blocking += 1
        value = gate_state.get(g.id)

        if g.input_type == "checkbox":
            if value is True:
                confirmed += 1
            else:
                blocking_items.append({
                    "id": g.id,
                    "label": g.label,
                    "category": g.category,
                    "reason": "Niet bevestigd",
                })
        elif g.input_type == "select":
            if value is None:
                blocking_items.append({
                    "id": g.id,
                    "label": g.label,
                    "category": g.category,
                    "reason": "Geen selectie gemaakt",
                })
                ask_items.append({
                    "id": g.id,
                    "label": g.label,
                    "category": g.category,
                    "reason": "Omnicasa data ontbreekt of is ambigu — Legal moet bevestigen",
                })
            elif value == "onbekend":
                blocking_items.append({
                    "id": g.id,
                    "label": g.label,
                    "category": g.category,
                    "reason": "Waarde is 'onbekend' — Legal moet bevestigen",
                })
                ask_items.append({
                    "id": g.id,
                    "label": g.label,
                    "category": g.category,
                    "reason": "Kies een definitieve waarde",
                })
            else:
                confirmed += 1

    return {
        "cleared": len(blocking_items) == 0,
        "blocking_items": blocking_items,
        "ask_items": ask_items,
        "confirmed_count": confirmed,
        "total_blocking_count": total_blocking,
    }


def _dot(data: dict, path: str) -> Any:
    """Resolve dot-notation path."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current
