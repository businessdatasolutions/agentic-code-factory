#!/usr/bin/env python3
"""Ingang naar `plinkie_fabriek.graaf` zonder venv.

De kern woont in `services/fabriek/` omdat de ADK-manager hem daar nodig heeft.
Deze modules gebruiken alleen de standaardbibliotheek, dus ze zijn ook zonder
`uv` te importeren — en dat moet, want `make werkwijze-test` hoort te draaien
voordat er ook maar één venv bestaat.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "fabriek" / "src"))

from plinkie_fabriek.graaf import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
