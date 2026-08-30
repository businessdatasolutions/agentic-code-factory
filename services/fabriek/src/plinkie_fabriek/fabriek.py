#!/usr/bin/env python3
"""De lus van de code factory: uitdelen, toetsen, mergen, administreren.

Twee bezettingen van de managerrol, dezelfde lus:

    fabriek.py --droogloop RUNMAP   geen model, geen kosten; de gate uit C14
    fabriek.py --run RUNMAP         de ADK-agent op Gemini beslist wat er uitgaat

Het machinewerk hieronder is in beide gevallen identiek en deterministisch. Dat
is de grens die het ontwerp trekt: een model kiest wát er wordt uitgedeeld, en
raakt nooit de vraag óf een merge mag.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from . import config as configuratie
from . import engineer as engineermodule
from . import graaf as graafmodule
from . import logboek
from .graaf import bouw as bouw_graaf

WORTEL = Path(__file__).resolve().parents[4]


def git(args: list[str], cwd: Path = WORTEL) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def proefmap(cfg: dict) -> Path:
    """De proefbranch krijgt een eigen worktree, en dat is geen netheid.

    Zonder deze map zou de manager `git checkout` doen in de hoofdmap en
    daarmee de branch omgooien van wie daar op dat moment werkt. Een run mag
    niet ingrijpen in de werkplek van de mens die hem bekijkt.
    """
    map_ = WORTEL / ".claude" / "worktrees" / "proef"
    if not map_.exists():
        git(["worktree", "add", str(map_), cfg["basisbranch"]])
    return map_


# ----------------------------------------------------------------- de poort

def verboden_paden(basis: str, branch: str, cfg: dict) -> list[tuple[str, str, str]]:
    """De controle van G1, op de diff en niet op vertrouwen. Draait vlak vóór de
    merge, want daar is het werk af en nog niet binnen.

    Geeft per treffer het pad, het patroon dat hem ving, en **waarom dat pad op
    de lijst staat**. Die laatste komt uit `verboden-waarom` in de config en is
    geen versiering: zonder reden luidt de melding "BUILDPLAN.md valt onder
    BUILDPLAN.md", en dat verklaart niets aan wie het scherm leest.
    """
    uit = git(["diff", "--name-only", f"{basis}...{branch}"])
    treffers = []
    for pad in uit.stdout.splitlines():
        if not pad.strip():
            continue
        stand, patroon = configuratie.stand(pad, cfg)
        if stand == "verboden":
            waarom = cfg.get("verboden-waarom", {}).get(patroon, "")
            treffers.append((pad, patroon, waarom))
    return treffers


def merge(subtaak: str, engineer_naam: str, runmap: Path, cfg: dict) -> dict:
    """Verbodslijst, merge, retest. Rood betekent terugdraaien en teruggeven;
    de manager repareert niet zelf, want dan schrijft hij code die niemand toetste."""
    basis = cfg["basisbranch"]
    branch = f"{basis}-{engineer_naam}"

    # De poort meldt áltijd wat hij deed, ook als hij iets vindt. Tot 30-08-2026
    # schreef hij alleen een regel als hij níéts vond, en dan stond er bij een
    # treffer nergens dat er een diff was getoetst — terwijl dat precies de
    # bewering is die erbij hoort.
    gewijzigd = [p for p in git(["diff", "--name-only", f"{basis}...{branch}"]).stdout.splitlines()
                 if p.strip()]
    treffers = verboden_paden(basis, branch, cfg)
    meervoud = "" if len(gewijzigd) == 1 else "e"
    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="poort",
                    tekst=(f"verbodslijst getoetst op {len(gewijzigd)} gewijzigd{meervoud} "
                           f"pad{'' if len(gewijzigd) == 1 else 'en'}: "
                           + (f"{len(treffers)} treffer" if treffers else "geen treffer")),
                    subtaak=subtaak)
    if treffers:
        for pad, patroon, waarom in treffers:
            # Het pad, en pas daarna het patroon als het iets toevoegt. Bij een
            # exact pad zijn ze gelijk, en dan is "valt onder" ruis.
            via = "" if pad == patroon else f" (verboden via {patroon})"
            logboek.schrijf(runmap, bron="gemeten", wie=engineer_naam, soort="verbod",
                            tekst=f"raakte {pad}{via}", subtaak=subtaak, waarom=waarom)
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="alarm",
                        tekst=f"run afgebroken (G1): {engineer_naam} raakte {treffers[0][0]}",
                        subtaak=subtaak, waarom=treffers[0][2])
        return {"gelukt": False, "reden": "verbodslijst", "paden": [p for p, _, _ in treffers]}


    werkmap = proefmap(cfg)
    git(["checkout", basis], werkmap)
    vorige = git(["rev-parse", "HEAD"], werkmap).stdout.strip()
    uit = git(["merge", "--no-ff", "-m", f"{subtaak} van {engineer_naam}", branch], werkmap)
    if uit.returncode:
        logboek.schrijf(runmap, bron="gemeten", wie=engineer_naam, soort="conflict",
                        tekst=uit.stdout.strip().splitlines()[0][:120] if uit.stdout else "conflict",
                        subtaak=subtaak)
        git(["merge", "--abort"], werkmap)
        return {"gelukt": False, "reden": "conflict"}

    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="merge",
                    tekst=f"{subtaak} van {engineer_naam} naar {basis}", subtaak=subtaak)

    # Retest ná de merge. Twee branches die apart groen zijn kunnen samen rood
    # zijn, en die vraag stelt alleen de merge.
    paden = git(["diff", "--name-only", f"{vorige}..HEAD"], werkmap).stdout.splitlines()
    for commando in configuratie.toetsen(paden, cfg):
        toets = subprocess.run(commando, shell=True, cwd=werkmap, capture_output=True, text=True)
        groen = toets.returncode == 0
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="retest",
                        tekst=f"{commando} {'groen' if groen else 'rood'}",
                        subtaak=subtaak, uitslag="groen" if groen else "rood")
        if not groen:
            git(["reset", "--hard", vorige], werkmap)
            logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="merge-mislukt",
                            tekst=f"merge teruggedraaid: {commando} was rood na samenvoegen",
                            subtaak=subtaak)
            return {"gelukt": False, "reden": "retest rood", "commando": commando}

    pad = runmap / "graaf.json"
    g = json.loads(pad.read_text(encoding="utf-8"))
    g["knopen"][subtaak]["runstand"] = "gemerged"
    pad.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="administratie",
                    tekst=f"{subtaak} staat op {basis}; geen vinkje — dat doet een mens",
                    subtaak=subtaak)
    return {"gelukt": True}


# ------------------------------------------------------------- de droogloop

DRAAIBOEKEN = {
    "7.1": [
        {"soort": "schrijf", "pad": "services/watchdog/README.md",
         "inhoud": "# watchdog\n\nDeterministische join: contracten x marktdata x kalender.\nGeen LLM (BP §4 stap 8).\n"},
        {"soort": "toets", "commando": "test -f services/watchdog/README.md"},
        {"soort": "commit", "boodschap": "7.1 watchdog: skelet van de join"},
        {"soort": "schrijf", "pad": "services/watchdog/join.py",
         "inhoud": "def join(contracten, markt, kalender):\n    \"\"\"Deterministisch, geen model.\"\"\"\n    return []\n"},
        {"soort": "toets", "commando": "python3 -c 'import ast,sys; ast.parse(open(\"services/watchdog/join.py\").read())'"},
        {"soort": "commit", "boodschap": "7.1 watchdog: de join zelf"},
    ],
    "7.4": [
        {"soort": "schrijf", "pad": "services/watchdog/kalender.py",
         "inhoud": "VENSTERS_DAGEN = (90, 30)\n\n\ndef nadert(einddatum, vandaag):\n    \"\"\"Kalendertriggers staan los van prijstriggers (BUILDPLAN 7.4).\"\"\"\n    dagen = (einddatum - vandaag).days\n    return [v for v in VENSTERS_DAGEN if dagen == v]\n"},
        {"soort": "toets", "commando": "python3 -m compileall -q services/watchdog/kalender.py"},
        {"soort": "commit", "boodschap": "7.4 kalendertriggers op 90 en 30 dagen"},
    ],
    "7.5": [
        {"soort": "schrijf", "pad": "services/watchdog/antiruis.py",
         "inhoud": "MARGE = 2\n\n\ndef mag_melden(sinds_dagen, besparing, drempel):\n    \"\"\"Hooguit \u00e9\u00e9n melding per week, tenzij de drempel dubbel wordt gehaald.\"\"\"\n    return sinds_dagen >= 7 or besparing >= drempel * MARGE\n"},
        {"soort": "toets", "commando": "python3 -m compileall -q services/watchdog/antiruis.py"},
        {"soort": "commit", "boodschap": "7.5 anti-ruis: een week, tenzij dubbel de drempel"},
    ],
    "7.6": [
        {"soort": "schrijf", "pad": "services/watchdog/stap8.py",
         "inhoud": "STAP = 8\n\n\ndef in_runrapport(resultaat):\n    \"\"\"De watchdog is stap 8 van de nachtrun (BP \u00a74).\"\"\"\n    return {\"stap\": STAP, \"alerts\": len(resultaat)}\n"},
        {"soort": "toets", "commando": "python3 -m compileall -q services/watchdog/stap8.py"},
        {"soort": "commit", "boodschap": "7.6 watchdog als stap 8 in de nachtrun"},
    ],
    "7.2": [
        {"soort": "schrijf", "pad": "services/watchdog/drempels.py",
         "inhoud": "STANDAARD_DREMPEL_EUR = 15\n\n\ndef boven_drempel(besparing, drempel=STANDAARD_DREMPEL_EUR):\n    return besparing >= drempel\n"},
        {"soort": "toets", "commando": "python3 -c 'import ast; ast.parse(open(\"services/watchdog/drempels.py\").read())'"},
        {"soort": "commit", "boodschap": "7.2 drempels per gebruiker, standaard 15 euro"},
        {"soort": "meld", "als": "toets", "tekst": "alert-voorkeuren nagelopen", "uitslag": "groen"},
    ],
}


VERBOD_STAP = [
    {"soort": "schrijf", "pad": "BUILDPLAN.md",
     "inhoud": "# per ongeluk overschreven door een engineer\n"},
    {"soort": "commit", "boodschap": "7.1 (en per ongeluk het build plan)"},
]


# Lopende engineers, op naam. De manager start ze en wacht niet: dat is het
# hele punt van asynchrone samenwerking, en zonder dit draaide de een pas als de
# ander klaar was (gemeten 30-08-2026 — eng-1 klaar om 15:22:02, eng-2 begon om
# 15:22:03). Isolatie zonder gelijktijdigheid is branch-and-merge zonder de winst.
LOPEND: dict[str, threading.Thread] = {}


def start_engineer(werker, opdracht) -> str:
    """Zet een engineer aan het werk in een eigen draad en keer meteen terug.

    Mergen blijft wél sequentieel; dat is geen omissie maar de bouw van het
    paper: integratie is één voor één en test-gated, en juist daarom mag het
    bouwen parallel."""
    draad = threading.Thread(target=werker.loop_af, args=(opdracht,),
                             name=opdracht.engineer, daemon=True)
    LOPEND[opdracht.engineer] = draad
    draad.start()
    return "bezig"


def wacht_op(namen=None, tijdslimiet: float = 600) -> None:
    for naam, draad in list(LOPEND.items()):
        if namen is None or naam in namen:
            draad.join(timeout=tijdslimiet)


def verzeker_graaf(runmap: Path) -> None:
    """Bouw de graaf als hij ontbreekt, en zeg dat in één regel.

    Zonder dit gaf een verse runmap een `FileNotFoundError` met tien regels
    traceback eronder. Dat is midden in een opname het slechtst denkbare
    antwoord: het ziet eruit als een kapotte fabriek terwijl er alleen een
    bestand ontbreekt dat we zelf kunnen maken.
    """
    if (runmap / "graaf.json").exists():
        return
    opzet_pad = WORTEL / "werkwijze" / "opzet-fase7.json"
    if not opzet_pad.exists():
        raise SystemExit(f"geen graaf in {runmap} en geen opzet in {opzet_pad}")
    opzet = json.loads(opzet_pad.read_text(encoding="utf-8"))
    g = bouw_graaf(opzet, graafmodule.lees_buildplan())
    runmap.mkdir(parents=True, exist_ok=True)
    (runmap / "graaf.json").write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    (runmap / "opzet.json").write_text(json.dumps(opzet, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(f"graaf gebouwd in {runmap} ({len(g['bereik'])} subtaken)")


def lees_scenario(runmap: Path) -> dict:
    """Een scherpgezet scenario voor de eerstvolgende ronde.

    Staat los van de opdracht en van de graaf: het beschrijft niet wat er gebouwd
    moet worden maar wat er misgaat. Zo kun je de poort laten afgaan in een ronde
    die je zelf start, in plaats van in een run die meteen wegloopt.
    """
    pad = runmap / "scenario.json"
    if not pad.exists():
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def stappen_voor(subtaak: str, engineer_naam: str, runmap: Path, *, toon_verbod: bool) -> list[dict]:
    """Het draaiboek van deze engineer, plus de overtreding als die scherp staat."""
    stappen = list(DRAAIBOEKEN.get(subtaak, []))
    scenario = lees_scenario(runmap)
    wie = scenario.get("overtreding")
    if toon_verbod or (wie and wie == engineer_naam):
        stappen = stappen + VERBOD_STAP
    return stappen


def droogloop(runmap: Path, cfg: dict, *, toon_verbod: bool = False) -> int:
    verzeker_graaf(runmap)
    """De gate uit C14: echte worktrees, echte commits, echte toets, geen model.
    Een scherm dat de proef moet meten, mag niet zelf ongemeten zijn."""
    g = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))
    vrij = [n for n in g["bereik"] if graafmodule.stand(n, g)[0] == "vrij"]
    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestart",
                    tekst=f"droogloop — geen model, geen kosten; {len(vrij)} subtaken vrij")

    aan_het_werk = []
    for teller, subtaak in enumerate(vrij[: cfg.get("engineers", 2)], start=1):
        naam = f"eng-{teller}"
        opdracht = engineermodule.Opdracht(
            subtaak=subtaak,
            titel=g["knopen"][subtaak]["titel"],
            tekst=g["knopen"][subtaak]["titel"],
            startbranch=cfg["basisbranch"],
            branch=f"{cfg['basisbranch']}-{naam}",
            toetsen=[], verboden=cfg["verboden"], engineer=naam,
        )
        logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="uitgedeeld",
                        tekst=f"{subtaak} aan {naam}", subtaak=subtaak)
        g["knopen"][subtaak]["runstand"] = "uitgedeeld"
        g["knopen"][subtaak]["engineer"] = naam
        (runmap / "graaf.json").write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
        stappen = stappen_voor(subtaak, naam, runmap, toon_verbod=toon_verbod and teller == 1)
        werker = engineermodule.NepEngineer(WORTEL, runmap, stappen)
        start_engineer(werker, opdracht)
        aan_het_werk.append((subtaak, naam))

    # Iedereen bouwt tegelijk; samenvoegen gaat één voor één, want de proefbranch
    # is de enige plek waar werk samenkomt.
    wacht_op()
    for subtaak, naam in aan_het_werk:
        klaar = any(r["soort"] == "klaar" and r.get("subtaak") == subtaak
                    for r in logboek.lees(runmap, laatste=400))
        if klaar:
            uitslag = merge(subtaak, naam, runmap, cfg)
            if uitslag.get("reden") == "verbodslijst":
                # G1: één treffer en de run is voorbij. Niet corrigeren, niet
                # doorgaan met de rest — vanaf hier is niet meer vast te stellen
                # of de administratie klopt.
                logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestopt",
                                tekst="afgebroken op de verbodslijst; de rest is niet uitgedeeld")
                return 1
            g = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))

    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestopt",
                    tekst="droogloop afgerond")
    return 0


# ------------------------------------------------------------------- de run

async def run_met_agent(runmap: Path, cfg: dict) -> int:
    """De ADK-agent bezet de managerrol. Hij kiest; de code merget."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from .agent import bouw_agent

    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "1")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

    g = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))
    bezetting = engineermodule.kies_bezetting(runmap, WORTEL)
    logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestart",
                    tekst=f"ADK-manager op gemini-3.7-flash; engineers: {bezetting}")

    def uitdelen(subtaak: str, naam: str, graafstand: dict) -> dict:
        opdracht = engineermodule.Opdracht(
            subtaak=subtaak, titel=graafstand["knopen"][subtaak]["titel"],
            tekst=graafstand["knopen"][subtaak]["titel"],
            startbranch=cfg["basisbranch"], branch=f"{cfg['basisbranch']}-{naam}",
            toetsen=[], verboden=cfg["verboden"], engineer=naam,
        )
        graafstand["knopen"][subtaak]["runstand"] = "uitgedeeld"
        graafstand["knopen"][subtaak]["engineer"] = naam
        (runmap / "graaf.json").write_text(
            json.dumps(graafstand, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if bezetting == "jules":
            werker = engineermodule.JulesEngineer(
                runmap, os.environ["JULES_API_KEY"],
                os.environ.get("JULES_SOURCE", "sources/github/businessdatasolutions/plinkie"))
            # In een eigen draad, net als de lokale engineer: een Jules-sessie duurt
            # minuten en de manager hoort niet te blokkeren zolang hij loopt.
            draad = threading.Thread(target=werker.loop_af, args=(opdracht,),
                                     name=naam, daemon=True)
            LOPEND[naam] = draad
            draad.start()
            return {"gelukt": True, "stand": "bezig"}
        werker = engineermodule.NepEngineer(
            WORTEL, runmap, stappen_voor(subtaak, naam, runmap, toon_verbod=False))
        return {"gelukt": True, "stand": start_engineer(werker, opdracht)}

    afgebroken: dict[str, str] = {}

    def mergen(subtaak: str, naam: str) -> dict:
        # Eén engineer tegelijk mergen, en pas als zijn draad klaar is. De
        # manager mag parallel láten bouwen, niet parallel samenvoegen.
        if afgebroken:
            return {"gelukt": False, "reden": "run afgebroken",
                    "toelichting": afgebroken["reden"]}
        wacht_op({naam})
        uitslag = merge(subtaak, naam, runmap, cfg)
        if uitslag.get("reden") == "verbodslijst":
            # G1: één treffer en de run is voorbij. Zonder deze rem probeerde de
            # agent dezelfde merge drie keer, kreeg drie keer terecht nul op het
            # rekest, en vulde het logboek met hetzelfde alarm (gemeten
            # 30-08-2026). De poort deed het goed; wat ontbrak was het gevolg.
            afgebroken["reden"] = f"{naam} raakte {uitslag['paden'][0]}"
        return uitslag

    runner = InMemoryRunner(agent=bouw_agent(runmap, uitdelen=uitdelen, mergen=mergen,
                                             engineers=cfg.get("engineers", 2)))
    sessie = await runner.session_service.create_session(app_name=runner.app_name,
                                                         user_id="fabriek")
    # Een ronde is één activering van de manager, en een ronde eindigt vanzelf. De
    # lus eromheen is deterministisch: zolang er nog iets vrij is óf iets klaar
    # staat om te mergen, krijgt hij een volgende ronde. Zonder die lus stopt
    # een agent na het uitdelen, want dan lijkt er even niets te doen — gemeten
    # 30-08-2026, en dat kostte de merge van twee afgeronde subtaken.
    def valt_er_iets_te_doen() -> tuple[bool, str]:
        stand_graaf = json.loads((runmap / "graaf.json").read_text(encoding="utf-8"))
        vrij = [n for n in stand_graaf["bereik"]
                if graafmodule.stand(n, stand_graaf)[0] == "vrij"]
        klaar = set()
        for regel in logboek.lees(runmap, laatste=400):
            if regel["soort"] == "klaar" and regel.get("subtaak"):
                klaar.add(regel["subtaak"])
            if regel["soort"] == "merge" and regel.get("subtaak"):
                klaar.discard(regel["subtaak"])
        if klaar:
            return True, f"Deze subtaken staan klaar en zijn nog niet gemerged: {', '.join(sorted(klaar))}. Merge ze."
        if vrij:
            return True, f"Deze subtaken zijn vrij: {', '.join(vrij)}. Deel ze uit."
        return False, ""

    opdrachttekst = ("Start een ronde. Lees eerst de aanwijzing, dan de graaf, "
                     "en deel uit wat vrij is.")
    for ronde in range(1, 5):
        bericht = types.Content(role="user", parts=[types.Part(text=opdrachttekst)])
        async for gebeurtenis in runner.run_async(user_id="fabriek", session_id=sessie.id,
                                                  new_message=bericht):
            if gebeurtenis.content and gebeurtenis.content.parts:
                for deel in gebeurtenis.content.parts:
                    if getattr(deel, "text", None):
                        logboek.schrijf(runmap, bron="gemeld", wie="manager", soort="toets",
                                        tekst=deel.text.strip()[:160])
        if afgebroken:
            logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestopt",
                            tekst=f"run voorbij na de verbodslijst: {afgebroken['reden']}")
            return 1
        verder, opdrachttekst = valt_er_iets_te_doen()
        if not verder:
            logboek.schrijf(runmap, bron="gemeten", wie="manager", soort="run-gestopt",
                            tekst=f"niets vrij en niets te mergen na ronde {ronde}")
            break
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) < 3:
        print(__doc__.strip())
        return 1
    modus, runmap = argv[1], Path(argv[2])
    cfg = configuratie.lees()
    if modus == "--jules-proef":
        # Eén echte Jules-sessie, met een opdracht die niets kan breken. Bedoeld om
        # de bezetting te bewijzen: sleutel, GitHub-app, sessie, activiteiten, en
        # een branch die je daarna weggooit.
        sleutel = os.environ.get("JULES_API_KEY")
        if not sleutel:
            print("Geen JULES_API_KEY gezet.\n"
                  "Haal er een op jules.google.com/settings en draai:\n"
                  "  JULES_API_KEY=... make fabriek-jules")
            return 1
        bron = os.environ.get("JULES_SOURCE", "")
        werker = engineermodule.JulesEngineer(runmap, sleutel, bron)
        runmap.mkdir(parents=True, exist_ok=True)

        antwoord = werker.bronnen()
        if "fout" in antwoord:
            print(f"De API weigerde het opvragen van bronnen: {antwoord['fout']}")
            print("Meestal betekent dit: sleutel ongeldig, of de Jules-GitHub-app staat")
            print("nog niet op businessdatasolutions/plinkie.")
            return 1
        lijst = antwoord.get("sources", [])
        print(f"{len(lijst)} bron(nen) zichtbaar voor deze sleutel:")
        for b in lijst:
            print("  ", b.get("name", "?"))
        if not bron:
            passend = [b["name"] for b in lijst if "plinkie" in b.get("name", "")]
            if not passend:
                print("\nGeen bron met 'plinkie' erin. Installeer de Jules-GitHub-app op de repo,")
                print("of geef de bron mee met JULES_SOURCE=sources/github/...")
                return 1
            werker.bron = passend[0]
            print(f"\ngekozen bron: {werker.bron}")

        opdracht = engineermodule.Opdracht(
            subtaak="proef", titel="Jules-bezetting bewijzen",
            tekst=("Create a file werkwijze/jules-proef.md with exactly two lines: the first line "
                   "the heading '# Jules', the second line one sentence stating which model you are. "
                   "Change nothing else."),
            startbranch=os.environ.get("JULES_BRANCH", "main"),
            branch="", toetsen=[], verboden=cfg["verboden"], engineer="eng-jules")
        print("\nsessie starten... (een Jules-sessie duurt minuten, niet seconden)")
        stand = werker.loop_af(opdracht, tijdslimiet_s=int(os.environ.get("JULES_LIMIET", "900")))
        print(f"\nuitslag: {stand}   sessie: {werker.sessie}")
        print("Het logboek staat in", runmap / "gebeurtenissen.jsonl")
        print("Opruimen: verwijder de branch of pull request die Jules heeft gemaakt.")
        return 0 if stand == "klaar" else 1

    if modus == "--wapen-overtreding":
        # Zet het scenario scherp en draai níéts. De ronde start jij, op het
        # scherm, precies zoals een gewone ronde — anders is de demo twee
        # verschillende handelingen die hetzelfde zouden moeten heten.
        wie = argv[3] if len(argv) > 3 else "eng-1"
        runmap.mkdir(parents=True, exist_ok=True)
        (runmap / "scenario.json").write_text(
            json.dumps({"overtreding": wie,
                        "waarom": "demo van de poort; de overtreding is gescript"},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logboek.schrijf(runmap, bron="gemeten", wie="jij", soort="waarschuwing",
                        tekst=f"scenario scherp: {wie} raakt straks een verboden bestand")
        print(f"scenario scherp gezet: {wie} raakt een verboden bestand in de volgende ronde.")
        print("Start die ronde zelf op het volgscherm — er draait nu niets.")
        return 0

    if modus == "--droogloop":
        return droogloop(runmap, cfg, toon_verbod="--verbod" in argv)
    if modus == "--run":
        verzeker_graaf(runmap)
        return asyncio.run(run_met_agent(runmap, cfg))
    print(f"onbekende modus: {modus}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
