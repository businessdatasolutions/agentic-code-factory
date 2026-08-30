#!/usr/bin/env python3
"""Bouwt en onderhoudt de afhankelijkheidsgraaf van een proefrun (C1b).

**Waarom de graaf een bestand is en geen gedachte.** Zolang deze sessie de
managerrol bezet, zou hij de volgorde in zijn context kunnen houden. Een koude
start heeft geen context — niet na een weggevallen gesprek, en niet als de rol
later door een gewekte agent wordt bezet. Zie het ontwerp §2.3.

**Waarom de randen uit `opzet.json` komen en niet uit het build plan.** In heel
`BUILDPLAN.md` staat precies één expliciete afhankelijkheid: 7.3 vereist 6.18 t/m
6.21. Al het andere zit in het hoofd van wie het plan schreef. Een parser die
volgorde uit proza raadt, raadt meestal verkeerd en zegt er niets over; daarom
staan de randen met de hand in de opzet, en leest dit script uit het plan alleen
wat er letterlijk staat. Wat het plan zegt komt er altijd bij, ook als de opzet
het weglaat — een opzet kan een gestelde eis niet wegnemen.

**Stilte is geen onafhankelijkheid.** De opzet moet élke subtaak noemen. Een lege
lijst betekent "nagelopen en onafhankelijk"; ontbreken betekent "niemand heeft
gekeken". Dit script weigert het tweede.

Gebruik:
    graaf.py --bouw OPZET.json RUNMAP        # schrijft RUNMAP/graaf.json
    graaf.py --toon RUNMAP                   # de stand per subtaak
    graaf.py --zet ID STAND [--engineer NAAM] --run RUNMAP
    graaf.py --zelftest                      # scenario's, zonder schijf
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORTEL = Path(__file__).resolve().parents[4]
BUILDPLAN = WORTEL / "BUILDPLAN.md"

RUNSTANDEN = ("open", "uitgedeeld", "gemerged", "teruggedraaid")

# `- [ ] 7.1 tekst` of `- [x] 7.1 tekst`, met willekeurige inspringing.
SUBTAAK = re.compile(r"^\s*-\s*\[([ xX])\]\s+((?:\d+[a-z]?\.)+\d+[a-z]?)\s+(.*)$")
# De enige vorm die in dit plan echt voorkomt, plus de enkelvoudige variant.
VEREIST = re.compile(r"[Vv]ereist\s+((?:\d+[a-z]?\.)+\d+[a-z]?)(?:\s+t/m\s+((?:\d+[a-z]?\.)+\d+[a-z]?))?")


def _reeks(van: str, tot: str | None) -> list[str]:
    """`6.18 t/m 6.21` wordt vier nummers. Een reeks met letters wordt niet
    uitgevouwen: `4.2 t/m 4.2b` heeft geen telbare tussenstappen, en gokken is
    hier erger dan de twee eindpunten noemen."""
    if not tot:
        return [van]
    a, b = van.rsplit(".", 1), tot.rsplit(".", 1)
    if a[0] != b[0] or not a[1].isdigit() or not b[1].isdigit():
        return [van, tot]
    return [f"{a[0]}.{n}" for n in range(int(a[1]), int(b[1]) + 1)]


def lees_buildplan(pad: Path = BUILDPLAN) -> dict:
    """Alle genummerde subtaken met hun titel, vinkje en gestelde eisen."""
    knopen: dict[str, dict] = {}
    huidige = None
    for regel in pad.read_text(encoding="utf-8").splitlines():
        gevonden = SUBTAAK.match(regel)
        if gevonden:
            vinkje, nummer, titel = gevonden.groups()
            huidige = nummer
            knopen[nummer] = {
                "titel": re.sub(r"\s+", " ", titel).strip(),
                "afgevinkt": vinkje.lower() == "x",
                "eist": [],
            }
            staart = titel
        elif huidige and regel.strip() and not regel.lstrip().startswith("- ["):
            staart = regel
        else:
            if not regel.strip():
                huidige = None
            continue
        for van, tot in VEREIST.findall(staart):
            for nummer in _reeks(van, tot or None):
                if nummer not in knopen[huidige]["eist"] and nummer != huidige:
                    knopen[huidige]["eist"].append(nummer)
    return knopen


def bouw(opzet: dict, plan: dict) -> dict:
    """Voegt de opzet en het build plan samen tot één graaf."""
    bereik = list(opzet["subtaken"])
    randen = opzet.get("randen", {})
    ontbreekt = [n for n in bereik if n not in randen]
    if ontbreekt:
        raise SystemExit(
            "opzet: geen randen opgegeven voor " + ", ".join(ontbreekt) + ".\n"
            "Een lege lijst betekent 'nagelopen en onafhankelijk'; ontbreken betekent\n"
            "'niemand heeft gekeken'. Schrijf op welke van de twee het is."
        )

    knopen: dict[str, dict] = {}
    for nummer in bereik:
        uit_plan = plan.get(nummer, {})
        wacht = []
        for ander in randen[nummer]:
            wacht.append({"op": ander, "bron": "opzet"})
        for ander in uit_plan.get("eist", []):
            if not any(w["op"] == ander for w in wacht):
                wacht.append({"op": ander, "bron": "buildplan"})
        knopen[nummer] = {
            "titel": uit_plan.get("titel", "(niet in BUILDPLAN.md gevonden)"),
            "afgevinkt": uit_plan.get("afgevinkt", False),
            "wacht_op": wacht,
            "runstand": "open",
            "engineer": None,
        }

    # Alles waarop gewacht wordt maar wat buiten het bereik valt, komt erbij als
    # knoop die nooit vervuld raakt. Dat is geen fout maar de kern van de val:
    # 7.3 wacht op 6.21, en 6.21 hoort niet bij deze run.
    for nummer, knoop in list(knopen.items()):
        for wacht in knoop["wacht_op"]:
            if wacht["op"] not in knopen:
                uit_plan = plan.get(wacht["op"], {})
                knopen[wacht["op"]] = {
                    "titel": uit_plan.get("titel", "(onbekend)"),
                    "afgevinkt": uit_plan.get("afgevinkt", False),
                    "wacht_op": [],
                    "runstand": "open",
                    "engineer": None,
                    "buiten_bereik": True,
                }
    return {"naam": opzet.get("naam", ""), "bereik": bereik, "knopen": knopen}


def stand(nummer: str, graaf: dict) -> tuple[str, list[str]]:
    """De stand van één subtaak, met de nummers die hem tegenhouden."""
    knoop = graaf["knopen"][nummer]
    if knoop.get("buiten_bereik"):
        return "uitgesloten", []
    if knoop["afgevinkt"]:
        return "afgevinkt", []
    if knoop["runstand"] == "gemerged":
        return "gemerged", []
    if knoop["runstand"] == "uitgedeeld":
        return "uitgedeeld", []
    tegenhouders = []
    for wacht in knoop["wacht_op"]:
        ander = graaf["knopen"].get(wacht["op"])
        if ander is None:
            tegenhouders.append(wacht["op"])
        elif not (ander["afgevinkt"] or ander["runstand"] == "gemerged"):
            tegenhouders.append(wacht["op"])
    return ("geblokkeerd", tegenhouders) if tegenhouders else ("vrij", [])


def standen(graaf: dict) -> dict[str, tuple[str, list[str]]]:
    return {n: stand(n, graaf) for n in graaf["bereik"]}


def toon(graaf: dict) -> None:
    print(graaf.get("naam", ""))
    for nummer in graaf["bereik"]:
        naam, tegen = stand(nummer, graaf)
        knoop = graaf["knopen"][nummer]
        regel = f"  {nummer:6} {naam:12} {knoop['titel'][:60]}"
        if knoop["engineer"]:
            regel += f"  [{knoop['engineer']}]"
        print(regel)
        if tegen:
            uit = [t for t in tegen if graaf["knopen"].get(t, {}).get("buiten_bereik")]
            reden = "wacht op " + ", ".join(tegen)
            if uit:
                reden += f"  (buiten deze run: {', '.join(uit)})"
            print(f"         {reden}")


# ---------------------------------------------------------------- zelftest

def _proefgraaf() -> dict:
    plan = {
        "7.1": {"titel": "join", "afgevinkt": False, "eist": []},
        "7.2": {"titel": "drempels", "afgevinkt": False, "eist": []},
        "7.3": {"titel": "alert-flow", "afgevinkt": False, "eist": ["6.18", "6.19", "6.20", "6.21"]},
        "7.4": {"titel": "kalender", "afgevinkt": False, "eist": []},
        "7.5": {"titel": "anti-ruis", "afgevinkt": False, "eist": []},
        "7.6": {"titel": "stap 8", "afgevinkt": False, "eist": []},
        "6.21": {"titel": "bezorgdienst", "afgevinkt": False, "eist": []},
    }
    opzet = json.loads((WORTEL / "werkwijze" / "opzet-fase7.json").read_text(encoding="utf-8"))
    return bouw(opzet, plan)


def zelftest() -> int:
    fouten = []
    gedaan = [0]

    def eis(voorwaarde, wat):
        gedaan[0] += 1
        if not voorwaarde:
            fouten.append(wat)

    def kaart(g):
        return {n: s for n, (s, _) in standen(g).items()}

    # 1 · De val uit PRD §8.1 zit in de graaf, met een reden en met de juiste bron.
    g = _proefgraaf()
    naam, tegen = stand("7.3", g)
    eis(naam == "geblokkeerd", f"7.3 hoort geblokkeerd te zijn, is {naam}")
    eis("6.21" in tegen, f"7.3 hoort op 6.21 te wachten, wacht op {tegen}")
    eis(g["knopen"]["6.21"].get("buiten_bereik"), "6.21 hoort buiten bereik te staan")
    eis(any(w["bron"] == "buildplan" for w in g["knopen"]["7.3"]["wacht_op"]),
        "de eis van 7.3 hoort uit het build plan te komen, niet uit de opzet")

    # 2 · Bij aanvang staan er precies twee klaar — één per engineer bij de standaard van 2.
    vrij = [n for n, s in kaart(g).items() if s == "vrij"]
    eis(vrij == ["7.1", "7.2"], f"bij aanvang horen 7.1 en 7.2 vrij te zijn, gevonden {vrij}")

    # 3 · Een merge verandert de gemergede subtaak plus precies die subtaken waarvan hij
    #     de laatste tegenhouder was. Niet één, zoals het ontwerp eerst zei: een merge die
    #     niets deblokkeert verandert er één, en dat is het onbelangrijke geval.
    voor = kaart(g)
    g["knopen"]["7.1"]["runstand"] = "gemerged"
    na = kaart(g)
    veranderd = {n: (voor[n], na[n]) for n in voor if voor[n] != na[n]}
    eis(veranderd == {"7.1": ("vrij", "gemerged"), "7.4": ("geblokkeerd", "vrij")},
        f"merge van 7.1 hoort 7.1 en 7.4 te raken, gevonden {veranderd}")

    # 4 · Uitdelen deblokkeert per definitie niets en raakt er dus precies één.
    voor = na
    g["knopen"]["7.2"]["runstand"] = "uitgedeeld"
    g["knopen"]["7.2"]["engineer"] = "eng-1"
    na = kaart(g)
    eis([n for n in voor if voor[n] != na[n]] == ["7.2"],
        "uitdelen hoort precies één stand te raken")

    # 5 · 7.6 blijft wachten zolang er één tegenhouder over is.
    g["knopen"]["7.2"]["runstand"] = "gemerged"
    g["knopen"]["7.4"]["runstand"] = "gemerged"
    naam, tegen = stand("7.6", g)
    eis(naam == "geblokkeerd" and tegen == ["7.5"],
        f"7.6 hoort alleen nog op 7.5 te wachten, gevonden {naam} {tegen}")

    # 6 · En komt vrij zodra die er ook is.
    g["knopen"]["7.5"]["runstand"] = "gemerged"
    eis(stand("7.6", g)[0] == "vrij", "7.6 hoort vrij te zijn als 7.1, 7.2, 7.4 en 7.5 gemerged zijn")

    # 7 · De val sluit niet vanzelf: alles van fase 7 gemerged laat 7.3 geblokkeerd.
    eis(stand("7.3", g)[0] == "geblokkeerd",
        "7.3 hoort geblokkeerd te blijven, ook als de hele fase gemerged is")

    # 8 · De reeks uit het build plan wordt goed uitgevouwen.
    eis(_reeks("6.18", "6.21") == ["6.18", "6.19", "6.20", "6.21"], "reeks 6.18 t/m 6.21")
    eis(_reeks("4.2", None) == ["4.2"], "enkelvoudige eis")
    eis(_reeks("4.2", "4.2b") == ["4.2", "4.2b"], "reeks met letter blijft bij de eindpunten")

    # 9 · De echte tekst van BUILDPLAN.md levert de enige gestelde eis op. Verdwijnt die
    #     zin, dan is deze zelftest rood — en dat is de bedoeling, want dan is de val weg.
    echt = lees_buildplan()
    eis("6.21" in echt.get("7.3", {}).get("eist", []),
        "de eis van 7.3 hoort uit het echte BUILDPLAN.md gelezen te worden")
    eis(echt.get("7.1", {}).get("afgevinkt") is False, "7.1 hoort nog open te staan in het plan")

    for fout in fouten:
        print("FOUT  " + fout)
    print(f"graaf: {gedaan[0] - len(fouten)}/{gedaan[0]} controles goed")
    return 1 if fouten else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) < 2:
        print(__doc__.strip())
        return 1
    modus = argv[1]

    if modus == "--zelftest":
        return zelftest()

    if modus == "--bouw":
        opzet_pad, runmap = Path(argv[2]), Path(argv[3])
        opzet = json.loads(opzet_pad.read_text(encoding="utf-8"))
        graaf = bouw(opzet, lees_buildplan())
        runmap.mkdir(parents=True, exist_ok=True)
        (runmap / "graaf.json").write_text(
            json.dumps(graaf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (runmap / "opzet.json").write_text(
            json.dumps(opzet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"graaf geschreven: {runmap / 'graaf.json'} ({len(graaf['bereik'])} subtaken)")
        toon(graaf)
        return 0

    if modus == "--standen":
        # Eén bron voor de standlogica. Het volgscherm rekent niets zelf uit:
        # twee implementaties van dezelfde regel lopen uiteen zonder dat iemand
        # het merkt, en dan toont het scherm iets anders dan de manager doet.
        graaf = json.loads((Path(argv[2]) / "graaf.json").read_text(encoding="utf-8"))
        uit = []
        for nummer in graaf["bereik"]:
            naam, tegen = stand(nummer, graaf)
            knoop = graaf["knopen"][nummer]
            uit.append({
                "id": nummer,
                "titel": knoop["titel"],
                "stand": naam,
                "wacht_op": tegen,
                "buiten_bereik": [t for t in tegen if graaf["knopen"].get(t, {}).get("buiten_bereik")],
                "engineer": knoop["engineer"],
            })
        print(json.dumps({"naam": graaf.get("naam", ""), "subtaken": uit}, ensure_ascii=False))
        return 0

    if modus == "--toon":
        graaf = json.loads((Path(argv[2]) / "graaf.json").read_text(encoding="utf-8"))
        toon(graaf)
        return 0

    if modus == "--zet":
        nummer, nieuw = argv[2], argv[3]
        if nieuw not in RUNSTANDEN:
            print(f"onbekende stand: {nieuw} (kies uit {', '.join(RUNSTANDEN)})")
            return 1
        runmap = Path(argv[argv.index("--run") + 1])
        pad = runmap / "graaf.json"
        graaf = json.loads(pad.read_text(encoding="utf-8"))
        if nummer not in graaf["knopen"]:
            print(f"{nummer} staat niet in deze graaf")
            return 1
        graaf["knopen"][nummer]["runstand"] = nieuw
        if "--engineer" in argv:
            graaf["knopen"][nummer]["engineer"] = argv[argv.index("--engineer") + 1]
        pad.write_text(json.dumps(graaf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        toon(graaf)
        return 0

    print(f"onbekende modus: {modus}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
