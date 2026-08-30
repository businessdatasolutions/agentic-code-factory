#!/usr/bin/env python3
"""Meldhulpstuk voor engineers (C3). Eén aanroep, geen afhankelijkheden.

    meld.py RUNMAP eng-1 toets "make test groen (48 tests)" --uitslag groen

Kort genoeg om in de opdracht te passen: een engineer die drie regels moet
onthouden om te melden, meldt niet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "fabriek" / "src"))

from plinkie_fabriek.logboek import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
