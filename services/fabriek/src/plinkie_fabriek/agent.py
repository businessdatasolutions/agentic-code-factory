"""De manager van de code factory als ADK-agent.

**Waarom de manager een agent is en niet een script.** De rol bestaat uit drie
soorten werk (ontwerp §2.1). Het machinewerk — mergen, de verbodslijst toetsen,
hertellen — is gewone code en hoort dat te blijven: dat mag niet van een model
afhangen. Het denkwerk is wél een oordeel: welke van de vrije subtaken deel je
uit, en aan wie. Het paper achter deze proef laat zien dat juist die keuze de
uitkomst domineert (8,7% tegen 34,3% op dezelfde repository, met hetzelfde
model, alleen een andere toewijzing).

De agent krijgt daarom gereedschappen die elk voor zich deterministisch zijn, en
beslist alleen wat er niet uit te rekenen valt. Hij kan de verbodslijst niet
omzeilen: die wordt in `merge_subtaak` afgedwongen, niet in de prompt gevraagd.

Model en framework zijn ook een toelatingseis van de wedstrijd: ADK 2.x als
Google Agent Framework, `gemini-3.7-flash` op het Agent Platform.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from . import config as configuratie
from . import graaf as graafmodule
from . import logboek

MODEL = "gemini-3.7-flash"

INSTRUCTIE = """Je bent de manager van een code factory. Je deelt werk uit aan engineers die
elk in een eigen, geïsoleerde werkplek zitten, en je voegt hun werk samen.

Je werkt in ronden. Elke ronde doe je dit, in deze volgorde:

1. Roep `lees_aanwijzing` aan. Staat `stop` op true, dan is de noodrem ingedrukt: deel niets uit,
   merge niets, en sluit meteen af met `klaar_voor_nu`. Anders gaat wat de mens heeft aangewezen
   vóór jouw eigen keuze.
   Een aangewezen subtaak die geblokkeerd is deel je NIET uit; je meldt waarom hij wacht.
2. Roep `lees_graaf` aan voor de stand van elke subtaak.
3. Deel vrije subtaken uit met `deel_uit`, tot het maximum aantal engineers bereikt is.
   Kies bij gelijke stand de subtaak die de meeste andere subtaken deblokkeert.
   Engineers heten `eng-1`, `eng-2`, ... — nooit anders, want het volgscherm vindt
   hun werkplek op die naam.
4. Roep `stand_engineers` aan. Elke engineer die `klaar` staat MOET je mergen met
   `merge_subtaak` vóórdat je de ronde afsluit. Werk dat klaar is en niet gemerged,
   is werk dat niemand heeft.
5. Stop pas met `klaar_voor_nu` als er niets vrij is om uit te delen én niemand klaar
   staat om te mergen. Controleer dat met `stand_engineers`, niet uit je hoofd.

Harde regels waar je niet omheen mag:
- Je verzint NOOIT een subtaak. Wat je uitdeelt staat in de graaf, woordelijk.
- Je zet NOOIT een vinkje in het build plan. Dat doet een mens.
- Je raakt zelf geen bestanden aan in de werkplek van een engineer.
- Loopt een merge stuk op de verbodslijst, dan is de run voorbij. Je repareert niets, je probeert
  het niet opnieuw, en je deelt niets meer uit. Sluit af met `klaar_voor_nu`.

Antwoord kort. Je uitvoer is geen verslag voor een mens; het logboek is dat."""


def bouw_agent(runmap: Path, *, uitdelen, mergen, engineers: int) -> LlmAgent:
    """`uitdelen` en `mergen` worden ingespoten zodat de agent testbaar is
    zonder engineers en zonder git."""
    cfg = configuratie.lees()

    def _stap(tekst: str) -> None:
        """Elke handeling van de manager in het logboek.

        Tussen zijn start en zijn eerste toewijzing zitten meerdere
        modelaanroepen, en dat duurde in een gemeten run 40 seconden waarin het
        scherm niets toonde. Een manager die nadenkt hoort er niet uit te zien
        als een manager die vastzit."""
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="stap", tekst=tekst)

    def lees_graaf() -> str:
        """De stand van elke subtaak in deze run: vrij, uitgedeeld, gemerged,
        geblokkeerd of uitgesloten, met de nummers die hem tegenhouden."""
        _stap("leest de graaf")
        g = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))
        uit = []
        for nummer in g["bereik"]:
            naam, tegen = graafmodule.stand(nummer, g)
            uit.append({"id": nummer, "titel": g["knopen"][nummer]["titel"][:80],
                        "stand": naam, "wacht_op": tegen,
                        "engineer": g["knopen"][nummer]["engineer"]})
        return json.dumps({"subtaken": uit, "max_engineers": engineers}, ensure_ascii=False)

    def lees_aanwijzing() -> str:
        """Wat de mens op het volgscherm heeft aangewezen voor de voorrang.
        Dit is een voorrangsregel, geen bevel: een geblokkeerde subtaak blijft
        geblokkeerd."""
        _stap("leest wat jij hebt aangewezen")
        pad = runmap / "aanwijzing.json"
        if not pad.exists():
            return json.dumps({"volgorde": [], "stop": False})
        return pad.read_text(encoding="utf-8")

    def deel_uit(subtaak: str, engineer: str) -> str:
        """Geef één vrije subtaak aan één engineer. Weigert als de subtaak niet
        vrij is; dan is er iets mis met je lezing van de graaf, niet met de graaf."""
        g = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))
        naam, tegen = graafmodule.stand(subtaak, g)
        if naam != "vrij":
            logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="waarschuwing",
                            tekst=f"{subtaak} niet uitgedeeld: {naam}"
                                 + (f", wacht op {', '.join(tegen)}" if tegen else ""),
                            subtaak=subtaak)
            return json.dumps({"gelukt": False, "reden": naam, "wacht_op": tegen})
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="uitgedeeld",
                        tekst=f"{subtaak} aan {engineer}", subtaak=subtaak)
        return json.dumps(uitdelen(subtaak, engineer, g))

    def stand_engineers() -> str:
        """Wat elke engineer op dit moment doet, uit het logboek en uit git."""
        _stap("kijkt hoe de engineers ervoor staan")
        regels = logboek.lees(runmap, laatste=200)
        per = {}
        for r in regels:
            if r.get("wie") in ("manager", "jij", None):
                continue
            e = per.setdefault(r["wie"], {"stand": "bezig", "subtaak": r.get("subtaak")})
            if r["soort"] == "klaar":
                e["stand"] = "klaar"
            elif r["soort"] == "vastgelopen":
                e["stand"] = "vastgelopen"
        return json.dumps(per, ensure_ascii=False)

    def merge_subtaak(subtaak: str, engineer: str) -> str:
        """Voeg het werk van een engineer samen met de proefbranch. De
        verbodslijst wordt hier afgedwongen en niet aan jou gevraagd: raakt de
        diff een verboden pad, dan is de run voorbij. Probeer zo'n merge NIET
        opnieuw en deel niets meer uit; roep `klaar_voor_nu` aan met de reden."""
        return json.dumps(mergen(subtaak, engineer), ensure_ascii=False)

    def klaar_voor_nu(reden: str) -> str:
        """Er valt niets meer uit te delen of te mergen. Sluit de ronde af."""
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestopt", tekst=reden)
        return json.dumps({"gestopt": True, "reden": reden})

    return LlmAgent(
        name="fabriek_manager",
        model=MODEL,
        instruction=INSTRUCTIE,
        tools=[
            FunctionTool(lees_aanwijzing),
            FunctionTool(lees_graaf),
            FunctionTool(deel_uit),
            FunctionTool(stand_engineers),
            FunctionTool(merge_subtaak),
            FunctionTool(klaar_voor_nu),
        ],
    )
