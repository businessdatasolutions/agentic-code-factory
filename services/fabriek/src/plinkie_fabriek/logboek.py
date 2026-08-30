#!/usr/bin/env python3
"""Het gebeurtenislogboek van een run (C2/C3).

Eén regel per gebeurtenis, append-only, nooit herschreven. Wie een regel wil
corrigeren schrijft een nieuwe.

**Twee bronnen, en het verschil is de kern van het ontwerp.** `gemeld` komt van
de agent zelf: rijk en vroeg, en niet te vertrouwen — een agent die vastloopt
houdt op met melden, en een agent die de weg kwijt is meldt vooruitgang die er
niet is. `gemeten` komt uit git en het bestandssysteem: arm en laat, en niet te
vervalsen. Een commit bestaat of bestaat niet.

Het volgscherm merkt elke regel met zijn bron, en de interessante gevallen zijn
die waarin de twee uiteenlopen. Zie het ontwerp §5.

Gebruik als hulpstuk voor een engineer:
    logboek.py RUNMAP WIE SOORT "tekst" [--subtaak 7.2] [--uitslag groen]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

BRONNEN = ("gemeld", "gemeten")
SOORTEN = (
    "run-gestart", "run-gestopt", "uitgedeeld", "begonnen", "toets", "commit",
    "klaar", "vastgelopen", "merge", "merge-mislukt", "conflict", "retest",
    "verbod", "waarschuwing", "alarm", "administratie", "opgewarmd", "aanwijzing",
)


def schrijf(runmap: Path, *, bron: str, wie: str, soort: str, tekst: str, **extra) -> dict:
    """Voegt één regel toe. Openen met 'a' en één write-aanroep: twee processen
    die tegelijk melden, leveren dan geen half doorelkaar geschoven regel op."""
    if bron not in BRONNEN:
        raise ValueError(f"onbekende bron: {bron}")
    regel = {
        "t": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bron": bron,
        "wie": wie,
        "soort": soort,
        "tekst": tekst,
    }
    regel.update({k: v for k, v in extra.items() if v is not None})
    runmap.mkdir(parents=True, exist_ok=True)
    pad = runmap / "gebeurtenissen.jsonl"
    with pad.open("a", encoding="utf-8") as bestand:
        bestand.write(json.dumps(regel, ensure_ascii=False) + "\n")
    return regel


def lees(runmap: Path, *, laatste: int | None = None) -> list[dict]:
    """Alle regels, of de laatste N. Een half geschreven staartregel wordt
    overgeslagen in plaats van dat het lezen omvalt: het logboek wordt gelezen
    terwijl er in geschreven wordt, en dat is de normale toestand."""
    pad = runmap / "gebeurtenissen.jsonl"
    if not pad.exists():
        return []
    regels = []
    for rauw in pad.read_text(encoding="utf-8").splitlines():
        if not rauw.strip():
            continue
        try:
            regels.append(json.loads(rauw))
        except json.JSONDecodeError:
            continue
    return regels[-laatste:] if laatste else regels


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) < 5:
        print(__doc__.strip())
        return 1
    runmap, wie, soort, tekst = Path(argv[1]), argv[2], argv[3], argv[4]
    extra = {}
    for vlag, sleutel in (("--subtaak", "subtaak"), ("--uitslag", "uitslag")):
        if vlag in argv:
            extra[sleutel] = argv[argv.index(vlag) + 1]
    bron = "gemeten" if "--gemeten" in argv else "gemeld"
    schrijf(runmap, bron=bron, wie=wie, soort=soort, tekst=tekst, **extra)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
