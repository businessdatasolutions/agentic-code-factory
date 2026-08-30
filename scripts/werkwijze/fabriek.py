#!/usr/bin/env python3
"""Ingang naar de lus van de code factory zonder venv.

De droogloop gebruikt alleen de standaardbibliotheek en moet draaien voordat er
een venv bestaat. De `--run`-modus laadt ADK en hoort daarom via
`make fabriek-run` te gaan, in de venv van de service.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "fabriek" / "src"))

from plinkie_fabriek.fabriek import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
