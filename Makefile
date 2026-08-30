# De Agentic Code Factory. Alle doelen die de demo nodig heeft, en niets anders.
# Uitgelicht uit businessdatasolutions/plinkie, waar hij is gebouwd.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Toon alle doelen
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: werkwijze-test
werkwijze-test: ## Controles van het gereedschap voor de CAID-proef (werkwijze/, C1)
	@# Draait de steekproef uit werkwijze/config.json tegen de matcher. De niet-treffers
	@# in die tabel zijn even belangrijk als de treffers: een te breed patroon breekt een
	@# run af op werk dat gewoon mocht. Dit doel hangt bewust nog nergens onder — bij C14
	@# wordt het de eerste stap van `make werkwijze-proef`. Tot dan is het handwerk, en
	@# dat staat als bekend gat in werkwijze/caid-ontwerp.html §13.
	@fout=0; \
	 scripts/werkwijze/config.py --zelftest || fout=1; \
	 scripts/werkwijze/graaf.py --zelftest || fout=1; \
	 exit $$fout

.PHONY: volgscherm
volgscherm: ## Live volgscherm van de code factory — http://127.0.0.1:8788
	@# Draait uitsluitend op 127.0.0.1: er staat repo-inhoud op het scherm en er
	@# is geen inlog. Het scherm rekent niets zelf uit — de standen komen uit
	@# graaf.py en de verbodslijst uit config.json, want twee implementaties van
	@# dezelfde regel lopen uiteen zonder dat iemand het merkt.
	node scripts/volgscherm.mjs $(or $(RUN),werkwijze/runs/2026-08-30-01) $(or $(POORT),8788)

.PHONY: fabriek-schoon
fabriek-schoon: ## Zet de code factory terug op de beginstand (vóór een demo of opname)
	@# Eén doel in plaats van een blok om te plakken. Dat is geen luxe: in een
	@# interactieve zsh is `#` géén commentaarteken, dus een geplakt blok met
	@# uitleg erin geeft "command not found: #" (gemeten 30-08-2026).
	@# **Eerst een lopende manager stoppen.** Zonder dit wist dit doel het bord
	@# terwijl er nog een ronde draaide, en die vulde het binnen een seconde weer —
	@# wat er precies uitziet als "alles begint meteen opnieuw" (gemeten
	@# 30-08-2026). Schoonmaken terwijl er een schrijver actief is, is geen
	@# schoonmaken.
	@if pgrep -f "fabriek --run" >/dev/null 2>&1; then \
	   echo "een ronde liep nog; die wordt gestopt"; \
	   pkill -f "fabriek --run" 2>/dev/null || true; sleep 1; \
	 fi
	@for w in $$(git worktree list --porcelain | grep '^worktree' | grep worktrees | sed 's|worktree ||'); do \
	   git worktree remove --force "$$w" 2>/dev/null || true; done; \
	 git branch | grep 'proef/fase7-caid-' | xargs -r git branch -D >/dev/null 2>&1 || true; \
	 git branch -f proef/fase7-caid main; \
	 rm -f werkwijze/runs/2026-08-30-01/gebeurtenissen.jsonl werkwijze/runs/2026-08-30-01/aanwijzing.json werkwijze/runs/2026-08-30-01/scenario.json; \
	 scripts/werkwijze/graaf.py --bouw werkwijze/opzet-fase7.json werkwijze/runs/2026-08-30-01 >/dev/null
	@echo "bord teruggezet: 7.1 en 7.2 vrij, 7.3 geblokkeerd. Er draait niets."

.PHONY: fabriek-overtreding
fabriek-overtreding: fabriek-schoon ## Zet scherp dat een engineer een verboden bestand raakt; jij start de ronde
	@# Eén naam. De alias `fabriek-verbod` is op 30-08-2026 weggehaald: hij heette
	@# eerst zo, maar "verbod" leest als "zet het verbod aan" terwijl dit doel de
	@# regel juist laat overtreden. Twee namen voor één handeling is een aarzeling
	@# op het moment dat je hem intypt met de camera aan.
	@# Dit doel draait niets. Het schrijft een scenario en laat het bord op de
	@# beginstand staan, zodat jij de ronde start met dezelfde knop als anders.
	@# Een demo waarin de ene keer een commando de run start en de andere keer een
	@# knop, laat de kijker naar het verschil zoeken in plaats van naar de poort.
	@scripts/werkwijze/fabriek.py --wapen-overtreding $(or $(RUN),werkwijze/runs/2026-08-30-01) $(or $(WIE),eng-1)
	@echo ""
	@echo "De poort stond al aan en staat nog steeds aan; dit zet hem niet aan."
	@echo "Klik nu Volgende ronde starten op http://127.0.0.1:8788"

.PHONY: fabriek-jules
fabriek-jules: ## Bewijs de tweede engineer-bezetting met één echte Jules-sessie (kost tokens bij Google)
	@# Vraagt JULES_API_KEY. De sleutel haal je op jules.google.com/settings, en de
	@# Jules-GitHub-app moet op businessdatasolutions/plinkie staan — zonder dat
	@# ziet de API de repo niet. De opdracht maakt één bestandje en verandert
	@# verder niets; opruimen is de branch weggooien die Jules aanmaakt.
	@scripts/werkwijze/fabriek.py --jules-proef $(or $(RUN),werkwijze/runs/jules-proef)

.PHONY: fabriek-agent
fabriek-agent: ## Toon de definitie van de managerlaag: model, framework en gereedschappen
	@# Voor de video: het bewijs dat de manager een ADK-agent op Gemini is, zonder
	@# een derde venster te openen. Een editor erbij zou betekenen dat je tijdens
	@# een ongeknipte opname van venster wisselt, en dat is precies wat het
	@# draaiboek wil vermijden.
	@# Alleen de manager. `JulesEngineer` staat wél in engineer.py maar heeft nog
	@# nooit gedraaid, en code tonen die niet is uitgevoerd hoort niet in een demo.
	@echo "== services/fabriek/src/plinkie_fabriek/agent.py — de manager =="
	@sed -n '25,26p;32p' services/fabriek/src/plinkie_fabriek/agent.py
	@sed -n '143,155p' services/fabriek/src/plinkie_fabriek/agent.py

.PHONY: volgscherm-stoppen
volgscherm-stoppen: ## Stop een volgscherm dat nog op de achtergrond draait
	@pkill -f volgscherm.mjs 2>/dev/null && echo "volgscherm gestopt" || echo "er draaide er geen"

.PHONY: werkwijze-proef
werkwijze-proef: werkwijze-test ## Droogloop van de code factory: echte worktrees en commits, geen model
	@# De gate uit C14. Echte git, echte toets, geen modelaanroep en geen kosten.
	@# Een scherm dat de proef moet meten, mag niet zelf ongemeten zijn — dezelfde
	@# reden als bij `make speurder-proef`.
	scripts/werkwijze/fabriek.py --droogloop $(or $(RUN),werkwijze/runs/2026-08-30-01)

.PHONY: fabriek-run
fabriek-run: ## Eén ronde van de code factory met de ADK-manager (kost modeltokens)
	cd services/fabriek && uv run fabriek --run ../../$(or $(RUN),werkwijze/runs/2026-08-30-01)
