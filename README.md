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

## Running it

No Google Cloud account is needed for the dry run; it uses no model and costs nothing.

```bash
make werkwijze-test      # the guardrail's own tests: 13 path cases, 15 graph scenarios
make werkwijze-proef     # a full run with scripted engineers — real worktrees, real commits
make volgscherm          # the dashboard on http://127.0.0.1:8788
make fabriek-schoon      # back to the starting position
```

With a Google Cloud project (`gcloud auth application-default login`), the manager becomes an ADK
agent on Gemini instead of a scripted loop:

```bash
GOOGLE_CLOUD_PROJECT=<your-project> make fabriek-run
```

To see the guardrail refuse a merge, arm a scenario and then start a round from the dashboard:

```bash
make fabriek-overtreding
```

That command runs nothing. It resets the board and arms one engineer to touch a forbidden file, so
you can watch the gate refuse the merge and end the run. **The violation is scripted** — in a normal
run nothing breaks the rule, and then the gate is not visible at all.

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
