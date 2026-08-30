#!/usr/bin/env python3
"""Leest `werkwijze/config.json` en beantwoordt de enige vraag die tijdens een run telt:
mag deze engineer dit pad aanraken?

**Waarom een eigen matcher en niet `fnmatch`.** `fnmatch` laat `*` over `/` heen lopen.
Dan matcht `plinkie-*.html` ook `ideeen/plinkie-manifesto.html`, en `BUILDPLAN.md` zou
je moeten schrijven als iets wat niet ook `services/watchdog/BUILDPLAN.md` vangt. Beide
fouten breken een run af op werk dat gewoon mocht, en dat is even schadelijk als een
verbod dat niet pakt. Hier geldt daarom: `*` en `?` blijven binnen één padsegment,
alleen `**` kruist mappen, en elk patroon is verankerd in de wortel van de repo.

**Waarom de steekproef in de config staat en niet hier.** Het volgscherm (C5) leest
dezelfde lijst in node. Twee implementaties van dezelfde regel lopen uiteen zonder dat
iemand het merkt; de tabel in `steekproef` is wat ze allebei moeten reproduceren. Zie
`design/taalregels.json`, waar dezelfde truc staat en om dezelfde reden.

Gebruik:
    config.py --stand PAD...        # per pad: verboden | exclusief | vrij
    config.py --stand -             # paden van stdin, één per regel
    config.py --toets PAD...        # welke toetscommando's bij deze paden horen
    config.py --zelftest            # draait de steekproef uit de config

Afloopcode van `--stand`: 2 zodra één pad verboden is, anders 0. Daarmee is dit
rechtstreeks de poort van C10:

    git diff --name-only basis...branch | scripts/werkwijze/config.py --stand -
"""

# De systeem-python op macOS is 3.9 en kent `str | None` in annotaties nog niet;
# deze regel maakt ze tekst in plaats van uitvoering. Dit script draait bewust
# zónder venv, net als de andere controles in `scripts/`.
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORTEL = Path(__file__).resolve().parents[4]
CONFIG = WORTEL / "werkwijze" / "config.json"


def lees(pad: Path = CONFIG) -> dict:
    return json.loads(pad.read_text(encoding="utf-8"))


def _naar_regex(patroon: str) -> re.Pattern:
    """Vertaal één glob naar een regex die op het hele pad past.

    `**` kruist mappen, `*` en `?` blijven binnen één segment. Alles daarbuiten
    wordt letterlijk genomen, punten incluis — `plinkie-*.html` mag niet ook
    `plinkie-xhtml` vangen.
    """
    stuk = []
    i = 0
    while i < len(patroon):
        teken = patroon[i]
        if teken == "*":
            if patroon[i : i + 2] == "**":
                stuk.append(".*")
                i += 2
                continue
            stuk.append("[^/]*")
        elif teken == "?":
            stuk.append("[^/]")
        else:
            stuk.append(re.escape(teken))
        i += 1
    return re.compile("".join(stuk) + r"\Z")


def _raakt(pad: str, patronen) -> str | None:
    """Geeft het patroon terug dat dit pad vangt, of None."""
    pad = pad.strip().lstrip("./")
    for patroon in patronen:
        if _naar_regex(patroon).match(pad):
            return patroon
    return None


def stand(pad: str, config: dict) -> tuple[str, str | None]:
    """`verboden`, `exclusief` of `vrij`, met het patroon dat de uitslag gaf.

    Verboden wint van exclusief: een pad dat op beide lijsten staat is verboden,
    want een roosterregel kan een verbod niet verzachten.
    """
    treffer = _raakt(pad, config.get("verboden", []))
    if treffer:
        return "verboden", treffer
    treffer = _raakt(pad, config.get("exclusief", []))
    if treffer:
        return "exclusief", treffer
    return "vrij", None


def toetsen(paden, config: dict) -> list[str]:
    """De toetscommando's van elk werkgebied dat door deze paden geraakt wordt.

    Volgorde blijft die van de config, zodat twee runs dezelfde regels opleveren
    en een meetblad te vergelijken is.
    """
    gevonden = []
    geraakt = set()
    for gebied, commandos in config.get("toetsen", {}).items():
        regex = _naar_regex(gebied)
        for pad in paden:
            schoon = pad.strip().lstrip("./")
            if schoon in geraakt or not regex.match(schoon):
                continue
            geraakt.add(schoon)  # eerste treffer wint: specifiek vóór algemeen
            for commando in commandos:
                if commando not in gevonden:
                    gevonden.append(commando)
    return gevonden


def zelftest(config: dict) -> int:
    steekproef = config.get("steekproef", [])
    if not steekproef:
        print("config: geen steekproef — dan bewaakt niemand of de matcher nog klopt")
        return 1
    fouten = 0
    for geval in steekproef:
        gekregen, patroon = stand(geval["pad"], config)
        if gekregen != geval["verwacht"]:
            fouten += 1
            print(
                f"FOUT  {geval['pad']}\n"
                f"      verwacht: {geval['verwacht']} ({geval['waarom']})\n"
                f"      gekregen: {gekregen}" + (f" via {patroon}" if patroon else "")
            )
    print(f"config: {len(steekproef) - fouten}/{len(steekproef)} steekproefgevallen goed")
    return 1 if fouten else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) < 2:
        print(__doc__.strip())
        return 1
    modus, rest = argv[1], argv[2:]
    config = lees()

    if modus == "--zelftest":
        return zelftest(config)

    if rest == ["-"]:
        rest = [r for r in sys.stdin.read().splitlines() if r.strip()]
    if not rest:
        print("geef minstens één pad, of `-` om ze van stdin te lezen")
        return 1

    if modus == "--stand":
        verboden = 0
        for pad in rest:
            uitslag, patroon = stand(pad, config)
            waarom = config.get("verboden-waarom", {}).get(patroon or "", "")
            regel = f"{uitslag:10} {pad}"
            if patroon:
                regel += f"   ← {patroon}"
            print(regel)
            if uitslag == "verboden":
                verboden += 1
                if waarom:
                    print(f"           {waarom}")
        if verboden:
            print(f"\n{verboden} verboden pad(en). De run hoort hier af te breken (G1).")
            return 2
        return 0

    if modus == "--toets":
        for commando in toetsen(rest, config):
            print(commando)
        return 0

    print(f"onbekende modus: {modus}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
