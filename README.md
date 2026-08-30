# Agentic Code Factory

**A manager agent reads a project's own build plan, delegates subtasks to engineers in isolated
workspaces, and merges their work behind a gate it cannot talk its way past.**

Every engineering team has the same messy chore: a backlog of subtasks that depend on each other.
The expensive mistake is not writing the code. It is picking the wrong thing to build next. The
research this is built on measures exactly that — two runs on the same repository, the same model,
differing only in which files got assigned, scored 8.7% and 34.3%.

So the delegation decision is the part we gave to an agent. Everything else is ordinary code.

---

## Hackathon submission — All Things Agentic

**Category: The Taskmaster.**

| Requirement | How this project meets it | Where to look |
|---|---|---|
| Gemini 3.5 or newer | `gemini-3.7-flash` drives the manager | [`agent.py`](services/fabriek/src/plinkie_fabriek/agent.py) |
| At least one Google Agent Framework | **Google ADK 2.x** — the manager is an `LlmAgent` with six `FunctionTool`s | same file |
| At least one Google Cloud service | **Gemini Enterprise Agent Platform** — every manager call lands there; 653 requests measured in three hours of test runs on 30-08-2026 | same file |

**Live:** the dashboard on Cloud Run — https://fabriek-owsxcee6ka-ez.a.run.app — showing a recorded
run. It reads no repository and steers nothing, and says so at the top.

This repository was extracted on 30-08-2026 from
[`businessdatasolutions/plinkie`](https://github.com/businessdatasolutions/plinkie), where the
factory was built and where it runs against a live backlog. Everything here was written during the
submission period.

---

## What one run looks like

`make werkwijze-proef` — under a minute, one manager, two engineers:

```
manager  run-gestart    droogloop — geen model, geen kosten
manager  uitgedeeld     7.1 aan eng-1          <- two subtasks are free, so two engineers start
eng-1    commit         f6178a6 7.1 watchdog: skelet van de join
manager  poort          verbodslijst getoetst op 2 gewijzigde paden: geen treffer
manager  merge          7.1 van eng-1 naar proef/fase7-caid
manager  retest         compileall services/watchdog groen    <- after the merge, not before
manager  administratie  7.1 staat op de branch; geen vinkje — dat doet een mens
manager  uitgedeeld     7.4 aan eng-1          <- 7.4 became free because 7.1 landed
```

The interface and the log are Dutch; the team and the product are Dutch, and this is an internal
tool. This README and the architecture diagram are English.

Subtask **7.3 stays blocked for the whole run.** It states its own dependency on four subtasks from
another phase, and the manager leaves it alone instead of building something that cannot work yet.
That dependency is the only one in the original 6,958-line build plan written in a form a machine
can read; every other edge is stated by hand in `werkwijze/opzet-fase7.json`.

---

## Three design decisions worth checking

| Decision | Why | Where |
|---|---|---|
| **The model chooses what to delegate; code decides whether a merge may happen.** The forbidden-path list is enforced on the diff before every merge, never asked of the model in a prompt. | An agent that can argue its way past its own guardrail does not have one. | [`fabriek.py`](services/fabriek/src/plinkie_fabriek/fabriek.py) |
| **The log separates *reported* from *measured*.** What the agent says about itself is rich, early and untrustworthy; what git says is thin, late and impossible to fake. | An agent that has lost track reports progress that is not there. A timestamp comparison between two measured lines is what revealed that the engineers were running one after the other, not side by side. | [`logboek.py`](services/fabriek/src/plinkie_fabriek/logboek.py) |
| **The manager retests *after* the merge**, on top of the engineer's own test before commit. | Two branches that are each green can be red together, and only the merge asks that question. | [`fabriek.py`](services/fabriek/src/plinkie_fabriek/fabriek.py) |

---

## Reproducible testing

Everything below runs without a Google Cloud account, without an API key, and without a model. It
costs nothing. Verified on the versions listed; nothing here is version-sensitive beyond git
worktree support.

**Prerequisites**

| Tool | Verified on | Needed for |
|---|---|---|
| `git` | 2.50.1 | worktrees — the isolation the whole thing rests on |
| `python3` | 3.9.6 | the guardrail, the graph, the dry run. **Standard library only, no virtualenv** |
| `node` | 24.19.0 | the dashboard. Built-in modules only, no `npm install` |
| `make` | any | the entry points |
| `uv` + a Google Cloud project | 0.12.5 | *optional* — only for the ADK manager on Gemini |

**1. Clone and check the guardrail**

```bash
git clone https://github.com/businessdatasolutions/agentic-code-factory
cd agentic-code-factory
make werkwijze-test
```

Expected, exactly:

```
config: 13/13 steekproefgevallen goed
graaf: 15/15 controles goed
```

The first line checks the forbidden-path matcher against a table of thirteen cases, five of which
are deliberate **non**-matches. The second replays fifteen graph scenarios, including the one where
subtask 7.3 must stay blocked even after every other subtask has merged.

**2. Run the whole loop**

```bash
make werkwijze-proef
```

This creates real `git worktree`s, makes real commits, runs real tests, checks the forbidden-path
list against each diff, merges to a trial branch and retests after every merge. Two engineers work
in parallel; merging is sequential. It ends by printing the board:

```
Fase 7 — bewakingsmotor
  7.1    gemerged     `services/watchdog/`: deterministische join      [eng-1]
  7.2    gemerged     Drempels per gebruiker (default € 15/mnd)        [eng-2]
  7.3    geblokkeerd  Alert-flow: watchdog → Pub/Sub → bezorgdienst
         wacht op 6.18, 6.19, 6.20, 6.21  (buiten deze run: 6.18, 6.19, 6.20, 6.21)
  7.4    gemerged     Kalender-triggers los van prijstriggers getest   [eng-1]
  7.5    gemerged     Anti-ruis: maximaal 1 alert per contract         [eng-2]
  7.6    gemerged     Watchdog als stap 8 in de nachtrun               [eng-1]
```

**Five subtasks merged, one left alone.** 7.3 is the check that matters: it states its own
dependency on four subtasks from a phase that is not in this run, and the manager never assigns it.

Inspect what actually happened:

```bash
git log --oneline --merges proef/fase7-caid     # one merge commit per subtask
cat werkwijze/runs/2026-08-30-01/gebeurtenissen.jsonl | tail -20
```

Every log line carries `"bron": "gemeten"` (observed from git) or `"bron": "gemeld"` (what the agent
said about itself). That distinction is the point of the log, and it is what revealed two of the
three bugs described in the write-up.

**3. Watch it happen**

```bash
make volgscherm     # http://127.0.0.1:8788, then reload the tab
```

Left column: the build plan with the reason beside every blocked subtask. Right: the manager, the
engineers with their measured git state, the warnings, and the log with both of its sources. The
badge at the top shows the guardrail is armed and how often it has run.

**4. See the guardrail refuse a merge**

```bash
make fabriek-overtreding    # runs nothing; resets the board and arms a scenario
```

Then press **Volgende ronde starten** on the dashboard. Expected: the badge turns red
(`poort AFGEGAAN`), two alarms appear with the reason, the run stops, and the offending work is
**not** on the trial branch:

```bash
git diff main proef/fase7-caid -- BUILDPLAN.md   # empty: nothing forbidden landed
```

**The violation is scripted** — `VERBOD_STAP` in `fabriek.py` tells one engineer to touch that file.
In a normal run nothing breaks the rule, and then the gate is not visible at all. This shows that
the gate holds; it does not show how often a real model would try.

**5. Reset**

```bash
make fabriek-schoon     # removes worktrees and branches, rebuilds the graph, stops a running round
```

**Optional: the manager as a real agent**

```bash
gcloud auth application-default login
GOOGLE_CLOUD_PROJECT=<your-project> make fabriek-run
```

The scripted loop is replaced by an ADK `LlmAgent` on `gemini-3.7-flash` that decides what to
delegate. Measured: about 90 seconds for the same five subtasks. This is the only step that costs
model tokens.

---

## What this does not show

One run, on one repository, on a backlog we chose. The paper behind it measures a spread from +30.7
to −10.5 percentage points *between repositories*, so a single result sits inside its own noise.

The headline numbers deserve care too. The abstract reports +25.6 percentage points, and that is
the weakest of the three models tested; for the strongest, the same table shows +6.1 and +6.0, at
roughly two to four times the cost, and wall-clock goes **up** in every row. Coordination buys
accuracy, not speed.

**On the second engineer implementation.** `engineer.py` also contains `JulesEngineer`, which talks
to Google's Jules API and would run each engineer in its own Google Cloud VM. It has never been
executed — no API key configured, no session ever created. It is written, not demonstrated, and
nothing here rests on it.

---

## Layout

```
services/fabriek/     the manager (ADK) and the engineer role, with its two implementations
scripts/volgscherm.mjs  the dashboard: node, no dependencies, no build step
scripts/werkwijze/    entry points that run without a virtualenv
werkwijze/            config.json (one source for the rules), the run scope, PRD and design doc
BUILDPLAN.md          the workload: Phase 7 of Plinkie, written weeks before this factory existed
docs/                 architecture diagram
```

The design documents in `werkwijze/` are Dutch and are the reasoning behind every decision above,
including the ones that turned out wrong. `caid-prd.html` states what the experiment must show and
when it fails; `caid-ontwerp.html` is the architecture and the build order.

---

Built at [Business Data Solutions](https://www.businessdatasolutions.nl). Write-up:
https://www.businessdatasolutions.nl/blog/branches-not-time/
