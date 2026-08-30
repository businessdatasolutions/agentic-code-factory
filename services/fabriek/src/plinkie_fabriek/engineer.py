#!/usr/bin/env python3
"""De engineer als rol, met twee bezettingen (ontwerp §10.1).

Wat de manager van een engineer nodig heeft is klein: hij geeft een opdracht,
een startbranch, de verbodslijst en het toetscommando, en krijgt terug een
branch met commits, een stroom voortgangsmeldingen en een eindsignaal. Zolang
een bezetting dat levert, mag de manager niet weten wie er werkt.

**Bezetting 1 — `NepEngineer`.** Draait de droogloop: echte worktree, echte
commits, echte toets, geen model en geen kosten. Hij bestaat niet om te doen
alsof, maar omdat een scherm dat de proef moet meten niet zelf ongemeten mag
zijn. Elk gedrag dat het scherm moet kunnen tonen zit erin, inclusief de
gevallen die fout horen te gaan.

**Bezetting 2 — `JulesEngineer`.** Praat met de Jules-API van Google: een
GitHub-repository als `source`, een `session` met de opdracht en een
`startingBranch`, en een activiteitenstroom met shell-uitvoer en changesets
erin. De sessie draait in een eigen VM bij Google; de isolatie is daarmee niet
onze zorg maar die van de dienst.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import logboek

JULES_BASIS = "https://jules.googleapis.com/v1alpha"


@dataclass
class Opdracht:
    """Wat er uitgedeeld wordt. Woordelijk uit het build plan, niet hertekend."""

    subtaak: str
    titel: str
    tekst: str
    startbranch: str
    branch: str
    toetsen: list[str]
    verboden: list[str]
    engineer: str


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# ------------------------------------------------------------------ bezetting 1

@dataclass
class NepEngineer:
    """Echte git, echte toets, geen model. Het gedrag komt uit `draaiboek`."""

    wortel: Path
    runmap: Path
    draaiboek: list[dict] = field(default_factory=list)
    worktree: Path | None = None

    def start(self, opdracht: Opdracht) -> str:
        self.worktree = self.wortel / ".claude" / "worktrees" / opdracht.engineer
        if self.worktree.exists():
            _git(["worktree", "remove", "--force", str(self.worktree)], self.wortel)
        uit = _git(
            ["worktree", "add", "-B", opdracht.branch, str(self.worktree), opdracht.startbranch],
            self.wortel,
        )
        if uit.returncode:
            logboek.schrijf(self.runmap, bron="gemeten", wie=opdracht.engineer,
                            soort="vastgelopen", tekst=f"worktree mislukt: {uit.stderr.strip()[:200]}",
                            subtaak=opdracht.subtaak)
            return "vastgelopen"
        logboek.schrijf(self.runmap, bron="gemeten", wie=opdracht.engineer, soort="opgewarmd",
                        tekst=f"worktree op {opdracht.branch}", subtaak=opdracht.subtaak)
        logboek.schrijf(self.runmap, bron="gemeld", wie=opdracht.engineer, soort="begonnen",
                        tekst=f"aan {opdracht.subtaak} — {opdracht.titel[:60]}", subtaak=opdracht.subtaak)
        return "bezig"

    def stap(self, opdracht: Opdracht, stap: dict) -> str:
        """Eén stap uit het draaiboek. Soorten: `schrijf`, `toets`, `commit`, `meld`."""
        wie, soort = opdracht.engineer, stap["soort"]
        if soort == "schrijf":
            doel = self.worktree / stap["pad"]
            doel.parent.mkdir(parents=True, exist_ok=True)
            doel.write_text(stap["inhoud"], encoding="utf-8")
            return "bezig"
        if soort == "meld":
            logboek.schrijf(self.runmap, bron="gemeld", wie=wie, soort=stap.get("als", "toets"),
                            tekst=stap["tekst"], subtaak=opdracht.subtaak,
                            uitslag=stap.get("uitslag"))
            return "bezig"
        if soort == "toets":
            commando = stap.get("commando") or (opdracht.toetsen[0] if opdracht.toetsen else "true")
            uit = subprocess.run(commando, shell=True, cwd=self.worktree,
                                 capture_output=True, text=True)
            groen = uit.returncode == 0
            logboek.schrijf(self.runmap, bron="gemeld", wie=wie, soort="toets",
                            tekst=f"{commando} {'groen' if groen else 'rood'}",
                            subtaak=opdracht.subtaak, uitslag="groen" if groen else "rood")
            return "bezig" if groen or stap.get("negeer_rood") else "vastgelopen"
        if soort == "commit":
            _git(["add", "-A"], self.worktree)
            uit = _git(["commit", "-m", stap["boodschap"]], self.worktree)
            if uit.returncode:
                return "bezig"
            hash_ = _git(["rev-parse", "--short", "HEAD"], self.worktree).stdout.strip()
            logboek.schrijf(self.runmap, bron="gemeten", wie=wie, soort="commit",
                            tekst=f"{hash_} {stap['boodschap'][:60]}", subtaak=opdracht.subtaak)
            return "bezig"
        raise ValueError(f"onbekende stap: {soort}")

    def loop_af(self, opdracht: Opdracht) -> str:
        if not self.draaiboek:
            # Geen draaiboek betekent geen werk, en dan is "klaar" een leugen die
            # er op het scherm uitziet als voortgang. Gemeten 30-08-2026: drie
            # subtaken meldden zich klaar zonder één regel code.
            logboek.schrijf(self.runmap, bron="gemeld", wie=opdracht.engineer,
                            soort="vastgelopen", tekst="geen draaiboek voor deze subtaak",
                            subtaak=opdracht.subtaak)
            return "vastgelopen"
        stand = self.start(opdracht)
        if stand != "bezig":
            return stand
        for stap in self.draaiboek:
            stand = self.stap(opdracht, stap)
            if stand != "bezig":
                logboek.schrijf(self.runmap, bron="gemeld", wie=opdracht.engineer,
                                soort="vastgelopen", tekst="gestopt op een rode toets",
                                subtaak=opdracht.subtaak)
                return stand
        logboek.schrijf(self.runmap, bron="gemeld", wie=opdracht.engineer, soort="klaar",
                        tekst=f"{opdracht.subtaak} klaar op {opdracht.branch}",
                        subtaak=opdracht.subtaak)
        return "klaar"


# ------------------------------------------------------------------ bezetting 2

@dataclass
class JulesEngineer:
    """De Jules-API. Alpha: de specificatie kan wijzigen (ontwerp §11b.3)."""

    runmap: Path
    sleutel: str
    bron: str  # bijv. "sources/github/businessdatasolutions/plinkie"
    sessie: str | None = None

    def _roep(self, pad: str, *, gegevens: dict | None = None) -> dict:
        verzoek = urllib.request.Request(
            f"{JULES_BASIS}/{pad}",
            data=json.dumps(gegevens).encode() if gegevens is not None else None,
            headers={"X-Goog-Api-Key": self.sleutel, "Content-Type": "application/json"},
            method="POST" if gegevens is not None else "GET",
        )
        try:
            with urllib.request.urlopen(verzoek, timeout=60) as antwoord:
                return json.loads(antwoord.read().decode())
        except urllib.error.HTTPError as fout:
            return {"fout": f"{fout.code} {fout.read().decode()[:300]}"}
        except Exception as fout:  # netwerk, tijdslimiet
            return {"fout": str(fout)[:300]}

    def start(self, opdracht: Opdracht) -> str:
        antwoord = self._roep("sessions", gegevens={
            "prompt": opdracht.tekst,
            "sourceContext": {
                "source": self.bron,
                "githubRepoContext": {"startingBranch": opdracht.startbranch},
            },
            "title": f"{opdracht.subtaak} — {opdracht.titel[:60]}",
            "requirePlanApproval": False,
        })
        if "fout" in antwoord:
            logboek.schrijf(self.runmap, bron="gemeten", wie=opdracht.engineer,
                            soort="vastgelopen", tekst=f"Jules weigerde: {antwoord['fout']}",
                            subtaak=opdracht.subtaak)
            return "vastgelopen"
        self.sessie = antwoord.get("id") or antwoord.get("name", "").split("/")[-1]
        logboek.schrijf(self.runmap, bron="gemeten", wie=opdracht.engineer, soort="uitgedeeld",
                        tekst=f"Jules-sessie {self.sessie} op {opdracht.startbranch}",
                        subtaak=opdracht.subtaak)
        return "bezig"

    def haal_op(self, opdracht: Opdracht, gezien: set[str]) -> str:
        """Nieuwe activiteiten naar het logboek. Activiteiten zijn *gemeld*: ze
        komen van de agent, niet uit git."""
        antwoord = self._roep(f"sessions/{self.sessie}/activities")
        if "fout" in antwoord:
            return "bezig"
        stand = "bezig"
        for bezigheid in antwoord.get("activities", []):
            sleutel = bezigheid.get("id") or bezigheid.get("name", "")
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            soort = next((s for s in ("planGenerated", "planApproved", "progressUpdated",
                                      "sessionCompleted") if s in bezigheid), "activiteit")
            tekst = json.dumps(bezigheid.get(soort, ""), ensure_ascii=False)[:200]
            logboek.schrijf(self.runmap, bron="gemeld", wie=opdracht.engineer,
                            soort="klaar" if soort == "sessionCompleted" else "toets",
                            tekst=f"{soort}: {tekst}", subtaak=opdracht.subtaak)
            if soort == "sessionCompleted":
                stand = "klaar"
        return stand

    def bronnen(self) -> dict:
        """De repositories die deze sleutel mag zien. Eerste aanroep om te toetsen
        of sleutel én GitHub-app werken, vóór er een sessie wordt aangemaakt."""
        return self._roep("sources")

    def loop_af(self, opdracht: Opdracht, *, tijdslimiet_s: int = 900) -> str:
        """Start een sessie en volg hem tot hij klaar is.

        Zonder deze lus deed de manager wél `start()` maar nooit `haal_op()`, en
        dan bleef een Jules-engineer eeuwig 'bezig' (gemeten 30-08-2026 — het gat
        viel pas op toen de bezetting echt gebruikt zou worden).
        """
        if self.start(opdracht) != "bezig":
            return "vastgelopen"
        gezien: set[str] = set()
        begin = time.monotonic()
        while time.monotonic() - begin < tijdslimiet_s:
            if self.haal_op(opdracht, gezien) == "klaar":
                return "klaar"
            time.sleep(10)
        logboek.schrijf(self.runmap, bron="gemeten", wie=opdracht.engineer, soort="vastgelopen",
                        tekst=f"Jules-sessie {self.sessie} niet klaar binnen {tijdslimiet_s} s",
                        subtaak=opdracht.subtaak)
        return "vastgelopen"

    def bericht(self, tekst: str) -> dict:
        """Een lopende sessie bijsturen. Dit is wat een lokale agent niet kan."""
        return self._roep(f"sessions/{self.sessie}:sendMessage", gegevens={"prompt": tekst})


def kies_bezetting(runmap: Path, wortel: Path) -> str:
    """Jules zodra er een sleutel is, anders de droogloop. Geen stille keuze:
    de manager meldt in het logboek welke bezetting draait."""
    return "jules" if os.environ.get("JULES_API_KEY") else "nep"
