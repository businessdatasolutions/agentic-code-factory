/** Het volgscherm van de code factory (C5–C8).
 *
 * Eén bestand, alleen ingebouwde modules, geen build-stap — dezelfde vorm als
 * `scripts/beheer-lokaal.mjs` en om dezelfde reden: een werkscherm dat je moet
 * bouwen voordat je het kunt bekijken, bekijk je niet.
 *
 * Draait uitsluitend op 127.0.0.1. Er staat repo-inhoud op het scherm en er is
 * geen inlog.
 *
 * **Het scherm rekent niets zelf uit.** De standen komen uit
 * `graaf.py --standen` en de verbodslijst uit `config.py`. Twee implementaties
 * van dezelfde regel lopen uiteen zonder dat iemand het merkt, en dan toont het
 * scherm iets anders dan de manager afdwingt.
 *
 * **Twee lagen, en het verschil staat op het scherm.** `gemeld` komt van de
 * agent zelf (rijk, vroeg, niet te vertrouwen), `gemeten` uit git (arm, laat,
 * niet te vervalsen).
 *
 *   node scripts/volgscherm.mjs [runmap] [poort]
 */

import { execFile, spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { promisify } from "node:util";

const draai = promisify(execFile);
const WORTEL = path.resolve(import.meta.dirname, "..");
const RUNMAP = path.resolve(process.argv[2] ?? "werkwijze/runs/2026-08-30-01");
const CONFIG = JSON.parse(fs.readFileSync(path.join(WORTEL, "werkwijze/config.json"), "utf8"));
const POORT = Number(process.env.PORT ?? process.argv[3] ?? CONFIG.poort ?? 8788);

/** Opgenomen run: geen repo, geen git, geen sturing.
 *
 * Zo draait dit scherm op Cloud Run. Er is daar geen werkkopie om te meten en
 * niets aan te sturen, dus leest hij een bevroren `standen.json` in plaats van
 * `graaf.py` aan te roepen, en weigert hij elke schrijfroute. De pagina zegt dat
 * ook, want een scherm dat eruitziet als live en het niet is, is erger dan geen
 * scherm. De inhoud is een échte run, geen opgemaakte. */
const OPGENOMEN = process.env.FABRIEK_SNAPSHOT === "1";

/** Lokale tijd met offset, in dezelfde vorm als de Python-kant schrijft.
 *
 * `toISOString()` geeft UTC, en dan stonden jouw aanwijzingen twee uur eerder in
 * hetzelfde logboek dan het werk van de manager (gemeten 30-08-2026). Dat is niet
 * alleen lelijk: het hele ontwerp rust op het vergelijken van tijdstempels tussen
 * wat gemeld is en wat gemeten is, en dat kan niet met twee klokken. */
function nu() {
  const d = new Date();
  const off = -d.getTimezoneOffset();
  const teken = off >= 0 ? "+" : "-";
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19)
    + teken + pad(off / 60) + ":" + pad(off % 60);
}

/* ------------------------------------------------------------------ meten */

/** De git-toestand van één worktree. Read-only: een scherm dat schrijft in wat
 *  het meet, verandert wat het meet. */
async function meetWorktree(naam) {
  if (OPGENOMEN) return null;
  const map = path.join(WORTEL, ".claude", "worktrees", naam);
  if (!fs.existsSync(map)) return null;
  const git = async (args) => (await draai("git", args, { cwd: map })).stdout.trim();
  try {
    const [tak, commits, vuil, laatste] = await Promise.all([
      git(["rev-parse", "--abbrev-ref", "HEAD"]),
      // Tellen vanaf het splitspunt met main, niet vanaf de basisbranch: die
      // schuift op bij elke merge, waardoor een engineer ná zijn eigen merge
      // plotseling nul commits zou tonen.
      git(["merge-base", "main", "HEAD"]).then((b) => git(["rev-list", "--count", `${b}..HEAD`]))
        .catch(() => "0"),
      git(["status", "--porcelain"]),
      git(["log", "-1", "--format=%ct %h %s"]).catch(() => ""),
    ]);
    const bestanden = vuil ? vuil.split("\n").length : 0;
    const [stempel, hash, ...rest] = laatste.split(" ");
    return {
      tak,
      commits: Number(commits) || 0,
      bestanden,
      laatsteCommit: hash ? { hash, tekst: rest.join(" "), t: Number(stempel) * 1000 } : null,
      gewijzigd: nieuwsteWijziging(map),
    };
  } catch {
    return null;
  }
}

/** Wanneer er voor het laatst iets veranderde in de worktree. Dit is de meting
 *  waarop de stiltewaarschuwing rust: een agent die zwijgt maar wél schrijft,
 *  is niet stil. */
function nieuwsteWijziging(map, diepte = 0) {
  let nieuwste = 0;
  if (diepte > 4) return nieuwste;
  let inhoud;
  try { inhoud = fs.readdirSync(map, { withFileTypes: true }); } catch { return nieuwste; }
  for (const item of inhoud) {
    if (item.name === ".git" || item.name === "node_modules" || item.name === ".venv") continue;
    const vol = path.join(map, item.name);
    try {
      if (item.isDirectory()) nieuwste = Math.max(nieuwste, nieuwsteWijziging(vol, diepte + 1));
      else nieuwste = Math.max(nieuwste, fs.statSync(vol).mtimeMs);
    } catch { /* verdwenen tijdens het lezen; dat mag */ }
  }
  return nieuwste;
}

/* ---------------------------------------------------------------- lezen */

function logboek(laatste = 60) {
  const pad = path.join(RUNMAP, "gebeurtenissen.jsonl");
  if (!fs.existsSync(pad)) return [];
  return fs.readFileSync(pad, "utf8").split("\n").filter(Boolean)
    .map((r) => { try { return JSON.parse(r); } catch { return null; } })
    .filter(Boolean).slice(-laatste).reverse();
}

async function standen() {
  if (OPGENOMEN) {
    // Bevroren bij het maken van de opname, met dezelfde `graaf.py --standen`
    // die de manager gebruikt. Eén bron, ook als hij hier uit blik komt.
    try {
      return JSON.parse(fs.readFileSync(path.join(RUNMAP, "standen.json"), "utf8"));
    } catch (fout) {
      return { naam: "opname onvolledig", subtaken: [], fout: String(fout).slice(0, 200) };
    }
  }
  try {
    const { stdout } = await draai(path.join(WORTEL, "scripts/werkwijze/graaf.py"),
      ["--standen", RUNMAP], { cwd: WORTEL });
    return JSON.parse(stdout);
  } catch (fout) {
    return { naam: "graaf niet leesbaar", subtaken: [], fout: String(fout).slice(0, 200) };
  }
}

/** Een scherpgezet scenario hoort op het scherm te staan vóórdat het afgaat.
 *  Anders lijkt de overtreding straks uit het niets te komen, en dan is het een
 *  truc in plaats van een demonstratie. */
function scenario() {
  const pad = path.join(RUNMAP, "scenario.json");
  if (!fs.existsSync(pad)) return null;
  try { return JSON.parse(fs.readFileSync(pad, "utf8")); } catch { return null; }
}

function aanwijzing() {
  const pad = path.join(RUNMAP, "aanwijzing.json");
  if (!fs.existsSync(pad)) return { volgorde: [], uitgesloten: [], stop: false };
  try { return JSON.parse(fs.readFileSync(pad, "utf8")); } catch { return { volgorde: [] }; }
}

function schrijfAanwijzing(nieuw) {
  const huidig = aanwijzing();
  const uit = { ...huidig, ...nieuw, gezet: nu() };
  fs.mkdirSync(RUNMAP, { recursive: true });
  fs.writeFileSync(path.join(RUNMAP, "aanwijzing.json"), JSON.stringify(uit, null, 2) + "\n");
  return uit;
}

/* ------------------------------------------------------------ waarschuwen */

/** De acht signalen uit het ontwerp §8. Twee niveaus: een waarschuwing kleurt
 *  het scherm, een alarm hoort de run af te breken. */
function signalen(regels, engineers, rondeStand) {
  const uit = [];
  const nu = Date.now();
  if (rondeStand && rondeStand.bezig && regels.length) {
    const stil = Math.round((nu - Date.parse(regels[0].t)) / 1000);
    if (stil > 60) uit.push({ niveau: "waarschuwing", wie: "manager",
      tekst: `de ronde staat ${stil} s stil op "${regels[0].tekst.slice(0, 40)}" — `
           + "waarschijnlijk een trage of herhaalde modelaanroep. Afbreken kan." });
  }
  const drempel = (CONFIG.stiltedrempel_min ?? 10) * 60_000;

  for (const r of regels) {
    if (r.soort === "verbod" || r.soort === "alarm")
      uit.push({ niveau: "alarm", tekst: r.tekst, wie: r.wie, t: r.t, waarom: r.waarom });
  }
  for (const [naam, e] of Object.entries(engineers)) {
    if (!e.meting) continue;
    const eigen = regels.filter((r) => r.wie === naam);
    const laatsteMelding = eigen.find((r) => r.bron === "gemeld");
    const stil = Math.max(e.meting.gewijzigd || 0,
      laatsteMelding ? Date.parse(laatsteMelding.t) : 0);
    if (e.stand === "bezig" && stil && nu - stil > drempel)
      uit.push({ niveau: "waarschuwing", wie: naam,
        tekst: `stil sinds ${Math.round((nu - stil) / 60000)} min (drempel ${CONFIG.stiltedrempel_min})` });

    const sindsWerk = [];
    for (const r of eigen) { if (r.bron === "gemeten") break; if (r.bron === "gemeld") sindsWerk.push(r); }
    if (sindsWerk.length >= (CONFIG.meldingen_zonder_werk ?? 3))
      uit.push({ niveau: "waarschuwing", wie: naam,
        tekst: `${sindsWerk.length}× gemeld zonder gemeten wijziging` });

    const rood = eigen.find((r) => r.soort === "toets" && r.uitslag === "rood");
    const commit = eigen.find((r) => r.soort === "commit");
    if (rood && commit && Date.parse(commit.t) >= Date.parse(rood.t))
      uit.push({ niveau: "alarm", wie: naam, tekst: "commit ná een rode toets" });
  }
  return uit;
}

/* ---------------------------------------------------------------- ronde */

/** De manager draait in ronden, geen proces. Hij draait niet uit zichzelf, en het
 *  scherm hoort dat te zeggen in plaats van stil te blijven: wie iets aanwijst
 *  en niets ziet gebeuren, denkt dat het kapot is. Deze knop start één ronde. */
let ronde = { bezig: false, gestart: null, uitslag: null };
let rondeProces = null;
const RONDE_TIJDSLIMIET_MS = 5 * 60_000;

function startRonde() {
  if (ronde.bezig) return { gestart: false, reden: "er loopt al een ronde" };
  // De noodrem uit het ontwerp (W9). Zolang hij aanstaat begint er niets nieuws;
  // dat is het verschil met "Ronde afbreken", dat alleen de lopende ronde raakt.
  if (aanwijzing().stop) return { gestart: false, reden: "de noodrem staat aan" };
  ronde = { bezig: true, gestart: Date.now(), uitslag: null };
  const proces = spawn("uv", ["run", "fabriek", "--run", RUNMAP], {
    cwd: path.join(WORTEL, "services", "fabriek"),
    env: { ...process.env, GOOGLE_CLOUD_PROJECT: process.env.GOOGLE_CLOUD_PROJECT ?? "plinkie-staging" },
    stdio: "ignore",
    detached: false,
  });
  rondeProces = proces;
  // Een harde bovengrens. Een modelaanroep kan blijven hangen (429-herhalingen,
  // een trage respons), en dan stond de knop op slot terwijl er niets meer
  // gebeurde — vijf minuten lang, gemeten 30-08-2026. Een ronde die vastzit
  // hoort te eindigen, niet te blijven bestaan.
  const wekker = setTimeout(() => {
    if (rondeProces === proces) stopRonde("tijdslimiet van 5 minuten bereikt");
  }, RONDE_TIJDSLIMIET_MS);
  proces.on("exit", (code) => {
    clearTimeout(wekker); rondeProces = null;
    ronde = { bezig: false, gestart: ronde.gestart, uitslag: code };
  });
  proces.on("error", (fout) => {
    clearTimeout(wekker); rondeProces = null;
    ronde = { bezig: false, gestart: ronde.gestart, uitslag: String(fout).slice(0, 120) };
  });
  return { gestart: true };
}

/** Een lopende ronde afbreken. Alles wat al gemerged is blijft staan; de
 *  proefbranch is de enige plek waar werk samenkomt en die raken we hier niet. */
function stopRonde(reden) {
  if (!rondeProces) return { gestopt: false, reden: "er loopt geen ronde" };
  try { rondeProces.kill("SIGTERM"); } catch { /* al weg */ }
  fs.appendFileSync(path.join(RUNMAP, "gebeurtenissen.jsonl"),
    JSON.stringify({ t: nu(), bron: "gemeten", wie: "jij", soort: "run-gestopt",
      tekst: "ronde afgebroken: " + reden }) + "\n");
  rondeProces = null;
  ronde = { bezig: false, gestart: ronde.gestart, uitslag: "afgebroken" };
  return { gestopt: true };
}

/* -------------------------------------------------------------- toestand */

async function toestand() {
  const regels = logboek();
  const graaf = await standen();
  const engineers = {};
  for (const s of graaf.subtaken) {
    if (!s.engineer) continue;
    engineers[s.engineer] ??= { subtaak: s.id, titel: s.titel, stand: "bezig" };
  }
  const uitLog = new Set(regels.map((r) => r.wie).filter((w) => w && w !== "manager" && w !== "jij"));
  for (const naam of uitLog) engineers[naam] ??= { subtaak: null, titel: "", stand: "bezig" };
  for (const [naam, e] of Object.entries(engineers)) {
    const eigen = regels.filter((r) => r.wie === naam);
    // De laatste subtaak waaraan deze engineer werkte, uit het logboek. Uit de
    // graaf halen gaf de éérste toewijzing, terwijl de toetsregel van de laatste
    // was: eng-1 stond op 7.1 met de testuitvoer van 7.6 eronder.
    const laatsteSub = eigen.find((r) => r.subtaak)?.subtaak ?? e.subtaak;
    if (laatsteSub) e.subtaak = laatsteSub;
    const vanSub = eigen.filter((r) => !laatsteSub || r.subtaak === laatsteSub);
    e.meting = await meetWorktree(naam);
    if (!e.meting && OPGENOMEN) {
      // Geen werkkopie in een container, maar de commits zijn wél gemeten: ze
      // staan als `bron: "gemeten"` in het logboek. "Geen worktree gevonden"
      // laten staan zou een opname als een storing laten lezen.
      const commits = eigen.filter((r) => r.soort === "commit");
      e.meting = {
        uitLogboek: true,
        commits: commits.length,
        bestanden: null,
        laatsteCommit: commits[0]
          ? { hash: String(commits[0].tekst).split(" ")[0],
              tekst: String(commits[0].tekst).split(" ").slice(1).join(" "),
              t: Date.parse(commits[0].t) }
          : null,
        gewijzigd: commits[0] ? Date.parse(commits[0].t) : 0,
      };
    }
    if (eigen.some((r) => r.soort === "klaar")) e.stand = "klaar";
    if (eigen.some((r) => r.soort === "vastgelopen")) e.stand = "vastgelopen";
    e.laatsteToets = vanSub.find((r) => r.soort === "toets") ?? null;
    e.laatste = eigen[0] ?? null;
  }
  const manager = regels.find((r) => r.wie === "manager");
  return {
    run: path.basename(RUNMAP),
    graaf,
    engineers,
    manager: manager ? { t: manager.t, tekst: manager.tekst, soort: manager.soort } : null,
    aanwijzing: aanwijzing(),
    scenario: scenario(),
    opgenomen: OPGENOMEN,
    opnamedatum: regels.length ? regels[regels.length - 1].t.slice(0, 10).split("-").reverse().join("-") : null,
    paginaversie: "2026-08-30-logscroll",
    ronde: { ...ronde, ooitGedraaid: regels.some((r) => r.wie === "manager") },
    signalen: signalen(regels, engineers, ronde),
    logboek: regels.slice(0, 120),
    config: {
      engineers: CONFIG.engineers, plafond: CONFIG.kostenplafond,
      // De verbodslijst hoort zichtbaar te zijn vóórdat hij afgaat. Een regel die
      // je pas leert kennen op het moment dat hij je run afbreekt, is een val en
      // geen afspraak.
      verboden: (CONFIG.verboden ?? []).map((patroon) => ({
        patroon, waarom: (CONFIG["verboden-waarom"] ?? {})[patroon] ?? "",
      })),
      exclusief: CONFIG.exclusief ?? [],
    },
    // De stand van de poort. Er is geen uitschakelaar en die hoort er niet te
    // zijn; "uit" betekent hier dat er geen regels staan, en dan toetst hij op
    // niets. Dat is het enige geval waarin hij niets doet, en het hoort zichtbaar
    // te zijn in plaats van afleidbaar.
    poort: {
      actief: (CONFIG.verboden ?? []).length > 0,
      paden: (CONFIG.verboden ?? []).length,
      afgegaan: regels.find((r) => r.soort === "verbod")?.t ?? null,
      getoetst: regels.filter((r) => r.soort === "poort").length,
    },
  };
}

/* ---------------------------------------------------------------- server */

const server = http.createServer(async (verzoek, antwoord) => {
  const url = new URL(verzoek.url, "http://127.0.0.1");

  if (url.pathname === "/toestand.json") {
    antwoord.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    antwoord.end(JSON.stringify(await toestand()));
    return;
  }

  if (OPGENOMEN && verzoek.method === "POST") {
    antwoord.writeHead(405, { "content-type": "application/json" });
    antwoord.end(JSON.stringify({ fout: "opgenomen run — deze pagina stuurt niets aan" }));
    return;
  }

  if (url.pathname === "/aanwijzing" && verzoek.method === "POST") {
    let lijf = "";
    for await (const brok of verzoek) lijf += brok;
    const wens = JSON.parse(lijf || "{}");
    const uit = schrijfAanwijzing(wens);
    // De manager leest dit bij zijn volgende ronde. Zichtbaar in het logboek,
    // want anders is achteraf niet te zien of de stuurknop iets deed.
    fs.appendFileSync(path.join(RUNMAP, "gebeurtenissen.jsonl"),
      JSON.stringify({ t: nu(), bron: "gemeten", wie: "jij",
        soort: "aanwijzing", tekst: `voorrang: ${(uit.volgorde || []).join(", ") || "leeg"}` }) + "\n");
    antwoord.writeHead(200, { "content-type": "application/json" });
    antwoord.end(JSON.stringify(uit));
    return;
  }

  if (url.pathname === "/noodrem" && verzoek.method === "POST") {
    let lijf = ""; for await (const brok of verzoek) lijf += brok;
    const aan = JSON.parse(lijf || "{}").aan !== false;
    if (aan) stopRonde("noodrem");
    schrijfAanwijzing({ stop: aan });
    fs.appendFileSync(path.join(RUNMAP, "gebeurtenissen.jsonl"),
      JSON.stringify({ t: nu(), bron: "gemeten", wie: "jij", soort: "waarschuwing",
        tekst: aan ? "noodrem aan: er start geen ronde meer" : "noodrem vrijgegeven" }) + "\n");
    antwoord.writeHead(200, { "content-type": "application/json" });
    antwoord.end(JSON.stringify({ noodrem: aan }));
    return;
  }

  if (url.pathname === "/ronde-stop" && verzoek.method === "POST") {
    antwoord.writeHead(200, { "content-type": "application/json" });
    antwoord.end(JSON.stringify(stopRonde("met de hand")));
    return;
  }

  if (url.pathname === "/ronde" && verzoek.method === "POST") {
    const uit = startRonde();
    antwoord.writeHead(200, { "content-type": "application/json" });
    antwoord.end(JSON.stringify(uit));
    return;
  }

  if (url.pathname === "/stroom") {
    antwoord.writeHead(200, {
      "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive",
    });
    let leeft = true;
    verzoek.on("close", () => { leeft = false; });
    while (leeft) {
      antwoord.write(`data: ${JSON.stringify(await toestand())}\n\n`);
      await new Promise((r) => setTimeout(r, 2000));
    }
    return;
  }

  antwoord.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  antwoord.end(PAGINA);
});

server.on("error", (fout) => {
  // Een bezette poort is geen stacktrace waard. Dit gebeurt zodra er nog een
  // volgscherm draait, en tijdens een opname wil je dán één regel zien die
  // zegt wat je moet doen — niet twintig regels node-interne frames.
  if (fout.code === "EADDRINUSE") {
    console.error(`Er draait al een volgscherm op 127.0.0.1:${POORT}.`);
    console.error(`Open http://127.0.0.1:${POORT}, of stop de oude met:`);
    console.error(`  make volgscherm-stoppen        (of: POORT=8789 make volgscherm)`);
    process.exit(1);
  }
  throw fout;
});

const HOST = OPGENOMEN ? "0.0.0.0" : "127.0.0.1";

server.listen(POORT, HOST, () => {
  console.log(`volgscherm: http://${HOST}:${POORT}   runmap: ${path.relative(WORTEL, RUNMAP)}`
    + (OPGENOMEN ? "   (opgenomen run, leest geen repo)" : ""));
});

/* ---------------------------------------------------------------- pagina */

const PAGINA = `<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code factory — volgscherm</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--tx:#e8eaed;--tx2:#a2a9b6;
--tx3:#6f7784;--acc:#4da3ff;--good:#3ecf8e;--warn:#f5b544;--bad:#f2666b;--chip:#232833}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--panel:#fff;--panel2:#f0f2f5;--line:#e0e4ea;
--tx:#161a20;--tx2:#5b6472;--tx3:#8b94a3;--acc:#0b6bcb;--good:#0e8a57;--warn:#9a6a06;--bad:#c02b32;--chip:#eef1f5}}
*{box-sizing:border-box}
/* Het hidden-attribuut is display:none uit de browserstijl, en elke eigen regel
   met display wint daarvan. Zonder deze regel stond de opnamebalk ook op het
   live scherm, met de tekst dat de knoppen niets doen terwijl ze het wel deden
   (gemeten 30-08-2026). Een scherm dat over zichzelf liegt is erger dan een
   scherm dat niets zegt. Let op: dit staat in een template-string, dus geen
   backticks in dit commentaar. */
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:14px}
.balk{display:flex;align-items:center;gap:18px;background:var(--panel2);border:1px solid var(--line);
border-radius:10px;padding:10px 16px;margin-bottom:12px;flex-wrap:wrap}
.stip{width:10px;height:10px;border-radius:50%;background:var(--good);flex:none}
.stip.stil{background:var(--tx3)}
.poort{border:1px solid;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}
.poort.aan{color:var(--good);border-color:color-mix(in srgb,var(--good) 45%,transparent)}
.poort.af{color:var(--bad);border-color:var(--bad);background:color-mix(in srgb,var(--bad) 12%,transparent)}
.poort.uit{color:var(--bad);border-color:var(--bad)}
.poort.scenario{color:var(--warn);border-color:var(--warn);
  background:color-mix(in srgb,var(--warn) 12%,transparent)}
.balk b{font-size:14px}.balk span{color:var(--tx2);font-size:13px}
.raster{display:grid;grid-template-columns:340px 1fr;gap:12px;align-items:start}
.kaart{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
h2{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--tx3);margin:0 0 10px;font-weight:600}
.taak{display:flex;align-items:baseline;gap:8px;padding:5px 0;border-bottom:1px solid var(--line)}
.taak:last-child{border-bottom:0}
.taak .nr{font-variant-numeric:tabular-nums;font-weight:600;min-width:34px}
.taak .tt{color:var(--tx2);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.taak .st{font-size:11px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);background:var(--chip);color:var(--tx2);flex:none}
.st.vrij{color:var(--tx);border-color:var(--tx3)}
.st.uitgedeeld{color:var(--acc);border-color:var(--acc)}
.st.gemerged,.st.afgevinkt{color:var(--good);border-color:var(--good)}
.st.geblokkeerd{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 45%,transparent)}
.reden{font-size:11.5px;color:var(--bad);padding:0 0 6px 42px;margin-top:-4px}
.knop{font:inherit;font-size:11px;padding:2px 10px;border-radius:999px;border:1px solid var(--acc);
background:none;color:var(--acc);cursor:pointer}
.knop:hover{background:color-mix(in srgb,var(--acc) 14%,transparent)}
.knop.uit{opacity:.35;cursor:not-allowed;border-color:var(--line);color:var(--tx3)}
.knop.aan{background:color-mix(in srgb,var(--acc) 16%,transparent);font-weight:600}
.wis{float:right;font-size:11px;border:0;background:none;color:var(--tx3);cursor:pointer;
  text-decoration:underline}
.wis:hover{color:var(--bad)}
.job{margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}
.job b{color:var(--acc);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.lanes{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:12px}
.eng{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.eng.warn{border-color:var(--warn)}.eng.klaar{border-color:var(--good)}.eng.fout{border-color:var(--bad)}
.eng .sub{font-weight:700;margin:2px 0 2px}
.eng .r{font-size:12.5px;color:var(--tx2);margin:3px 0}
.mgr{border-color:var(--acc)}
.onder{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
.sig{padding:5px 0;font-size:13px;border-bottom:1px solid var(--line)}
.sig:last-child{border-bottom:0}
.sig.alarm{color:var(--bad);font-weight:600}.sig.waarschuwing{color:var(--warn)}
.log{font-size:12.5px;font-variant-numeric:tabular-nums;max-height:300px;overflow-y:auto;
  scrollbar-width:thin}
.logkop{display:flex;align-items:baseline;gap:10px}
.logkop .f{margin-left:auto;font-size:11px}
.logkop button{font:inherit;font-size:11px;border:1px solid var(--line);background:none;
  color:var(--tx2);border-radius:999px;padding:1px 9px;cursor:pointer}
.logkop button.aan{color:var(--acc);border-color:var(--acc)}
.vast{color:var(--warn);font-size:11px}
.log div{padding:3px 0;border-bottom:1px solid var(--line);display:flex;gap:8px}
.log div:last-child{border-bottom:0}
.log .t{color:var(--tx3);flex:none}
.log .b{flex:none;width:14px;text-align:center}
.log .b.gemeten{color:var(--good)}.log .b.gemeld{color:var(--acc)}
.log .w{color:var(--tx2);flex:none;min-width:56px}
.leeg{color:var(--tx3);font-size:13px;padding:6px 0}
.legenda{color:var(--tx3);font-size:11.5px;margin-top:8px}
.verbod{margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}
.verbod summary{cursor:pointer;font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--bad);font-weight:600}
.verbod .p{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--tx);
  margin-top:7px}
.verbod .w{font-size:11.5px;color:var(--tx2);margin:1px 0 0 0}
.verbod .ex{margin-top:10px;font-size:11.5px;color:var(--tx2)}
</style></head><body><div class="wrap">
<div class="balk" id="opnamebalk" hidden style="background:color-mix(in srgb,var(--warn) 16%,var(--panel2));border-color:var(--warn)">
  <b>Opgenomen run.</b><span>Dit is een echte run van de code factory, bevroren. De pagina leest geen repository en stuurt niets aan; de knoppen doen hier niets.</span>
</div>
<div class="balk">
  <span class="stip" id="stip"></span>
  <b id="run">—</b>
  <span id="fase"></span>
  <span id="engteller"></span>
  <span id="klok"></span>
  <span id="poort" title="De verbodslijst wordt getoetst op de diff vlak vóór elke merge"></span>
  <span id="scenario" class="poort" hidden></span>
  <span style="margin-left:auto"><button class="knop" id="stop" style="border-color:var(--bad);color:var(--bad)">STOP</button></span>
</div>
<div class="raster">
  <div>
    <div class="kaart">
      <h2>Build plan — uit main</h2>
      <div id="plan"></div>
      <div class="job"><b>Voorrang</b><button class="wis" id="wis" hidden>alles wissen</button>
        <div id="job" class="leeg">niets aangewezen</div></div>
      <details class="verbod">
        <summary>Verbodslijst — <span id="verbodteller"></span></summary>
        <p class="legenda" style="margin-top:6px">Dit zijn de <b>regels</b>, niet de stand van deze
        run. Ze komen uit <code>werkwijze/config.json</code>, gelden voor elke run, en blijven dus
        staan als je het bord schoonmaakt.</p>
        <div id="verbodlijst"></div>
        <p class="legenda">Getoetst op de diff, vlak vóór elke merge. Eén treffer en de run stopt;
        er wordt niets gerepareerd en niets overgeslagen.</p>
      </details>
      <div class="legenda"><b>Aanwijzen is optioneel.</b> Wijs je niets aan, dan kiest de manager
      zelf uit wat vrij is. Wijs je wél iets aan, dan gaat jouw volgorde vóór de zijne. Een
      geblokkeerde subtaak kan niet: die zet hij vooraan zodra het kan, en hij meldt waarom hij
      wacht.</div>
    </div>
  </div>
  <div>
    <div class="kaart mgr">
      <h2>Manager — ADK-agent op Gemini</h2>
      <div id="mgr" class="leeg">nog geen handeling</div>
      <div style="margin-top:10px;display:flex;align-items:center;gap:12px">
        <button class="knop" id="ronde" style="padding:5px 14px">Volgende ronde starten</button>
        <span id="rondestand" style="color:var(--tx3);font-size:12px"></span>
      </div>
    </div>
    <div class="lanes" id="lanes"></div>
    <div class="onder">
      <div class="kaart"><h2>Waarschuwingen en alarmen</h2><div id="sig" class="leeg">niets</div></div>
      <div class="kaart">
        <div class="logkop"><h2 style="margin:0">Logboek — ▪ gemeld · ▫ gemeten</h2>
          <span class="f"><button id="filter">alleen mijlpalen</button></span></div>
        <div id="vastmelding" class="vast" hidden>je bent omhooggescrold; nieuwe regels wachten</div>
        <div class="log" id="log"></div>
      </div>
    </div>
  </div>
</div></div>
<script>
const el = (id) => document.getElementById(id);
let laatste = 0;
let alleenMijlpalen = false;

function tijd(s){ return s ? String(s).slice(11,19) : ""; }
function geleden(ms){ if(!ms) return ""; const s=Math.round((Date.now()-ms)/1000);
  return s<60 ? s+" s geleden" : Math.round(s/60)+" min geleden"; }

function teken(t){
  laatste = Date.now();
  if (t.paginaversie && t.paginaversie !== PAGINAVERSIE){
    // De server draait een nieuwere pagina dan dit tabblad. Zwijgen zou betekenen
    // dat je naar een scherm kijkt dat niet meer klopt met wat er draait.
    document.title = "herladen — " + document.title;
    const b = el("opnamebalk");
    if (b){ b.hidden = false; b.style.borderColor = "var(--acc)";
      b.innerHTML = "<b>Dit tabblad is verouderd.</b><span>De server draait een nieuwere versie "
        + "van dit scherm. Herlaad de pagina.</span>"; }
    return;
  }
  if (t.opgenomen){
    el("opnamebalk").hidden = false;
    for (const id of ["ronde","stop"]) { const k=el(id); if(k) k.hidden = true; }
    const bs2 = el("beurtstand") || el("rondestand"); if (bs2) bs2.textContent = "";
  }
  el("run").textContent = t.opgenomen ? "opgenomen run · " + (t.opnamedatum ?? t.run) : "run " + t.run;
  el("fase").textContent = t.graaf.naam;
  el("engteller").textContent = Object.keys(t.engineers).length + " van " + t.config.engineers + " engineers";
  el("klok").textContent = t.config.plafond ? "plafond " + t.config.plafond : "kostenplafond nog niet gezet";

  const plan = el("plan"); plan.innerHTML = "";
  for (const s of t.graaf.subtaken){
    const r = document.createElement("div"); r.className = "taak";
    const kanAanwijzen = s.stand === "vrij";
    r.innerHTML = '<span class="nr">'+s.id+'</span>'+
      '<span class="tt" title="'+s.titel.replace(/"/g,"&quot;")+'">'+s.titel+'</span>'+
      (s.engineer ? '<span class="st uitgedeeld">'+s.engineer+'</span>' :
        '<span class="st '+s.stand+'">'+s.stand+'</span>');
    if (kanAanwijzen){
      const plek = (t.aanwijzing.volgorde||[]).indexOf(s.id);
      const k = document.createElement("button");
      // De knop toont de stand in plaats van alleen de handeling. Een knop die
      // altijd "aanwijzen" zegt, verzwijgt dat hij ook weghaalt.
      k.className = plek >= 0 ? "knop aan" : "knop";
      k.textContent = plek >= 0 ? (plek + 1) + "e · haal weg" : "aanwijzen";
      k.title = plek >= 0 ? "staat op plek " + (plek+1) + " in de voorrang; klik om hem eruit te halen"
                          : "zet deze subtaak vooraan voor de volgende ronde";
      k.onclick = () => wijsAan(s.id); r.appendChild(k);
    }
    plan.appendChild(r);
    if (s.wacht_op.length){
      const w = document.createElement("div"); w.className="reden";
      w.textContent = "wacht op " + s.wacht_op.join(", ") +
        (s.buiten_bereik.length ? "  (buiten deze run: " + s.buiten_bereik.join(", ") + ")" : "");
      plan.appendChild(w);
    }
  }

  const pt = el("poort"); const p = t.poort;
  if (!p.actief){ pt.className="poort uit"; pt.textContent = "poort UIT — geen regels"; }
  else if (p.afgegaan){ pt.className="poort af";
    pt.textContent = "poort AFGEGAAN om " + tijd(p.afgegaan); }
  else { pt.className="poort aan";
    pt.textContent = "poort scherp · " + p.paden + " paden"
      + (p.getoetst ? " · " + p.getoetst + "× getoetst" : ""); }

  // Guard: in een tabblad dat nog de vorige pagina draait bestaat dit element
  // niet, en zonder deze regel gooit teken() daar een fout — waarna álles
  // eronder stil bevriest en het scherm er gewoon uitziet (30-08-2026).
  const sc = el("scenario");
  if (sc && t.scenario && t.scenario.overtreding && !p.afgegaan){
    sc.hidden = false; sc.className = "poort scenario";
    sc.textContent = "scenario scherp · " + t.scenario.overtreding + " raakt straks een verboden bestand";
  } else if (sc) { sc.hidden = true; }

  const vb = t.config.verboden || [];
  el("verbodteller").textContent = vb.length + " paden · vast";
  el("verbodlijst").innerHTML = vb.map(r =>
    '<div class="p">'+r.patroon+'</div>' + (r.waarom ? '<div class="w">'+r.waarom+'</div>' : '')
  ).join("") + ((t.config.exclusief||[]).length
    ? '<div class="ex"><b>Exclusief</b> (geen verbod, een roosterregel: hooguit één engineer tegelijk): '
      + t.config.exclusief.join(", ") + '</div>' : "");

  const job = el("job"); const v = (t.aanwijzing.volgorde||[]);
  job.className = v.length ? "" : "leeg";
  el("wis").hidden = !v.length;
  job.innerHTML = v.length
    ? "→ " + v.join(", daarna ") +
      '<div style="color:var(--tx3);font-size:11.5px;margin-top:3px">' +
      (t.ronde.bezig ? "de manager leest dit nu" : "wordt gelezen zodra er een ronde start") + '</div>'
    : "niets aangewezen";

  const m = el("mgr");
  if (t.manager){ m.className=""; m.innerHTML =
      '<div class="sub">'+t.manager.soort+' — '+t.manager.tekst+'</div>'+
      '<div class="r">laatste handeling '+tijd(t.manager.t)+' · '+
      (t.ronde.bezig ? 'ronde loopt' : 'wacht op de volgende ronde')+'</div>'+
      (t.ronde.bezig ? '<div class="r" style="color:var(--tx3)">Hij doet meerdere modelaanroepen '
        + 'voordat hij uitdeelt; de eerste toewijzing duurt doorgaans 10 tot 40 seconden.</div>' : ''); }
  else { m.className="leeg"; m.textContent = t.ronde.bezig
      ? "ronde gestart, nog geen handeling gemeld"
      : "de manager draait niet uit zichzelf — hij werkt in ronden. Start er een."; }

  const st = el("stop");
  if (t.aanwijzing.stop){
    st.dataset.aan = "1"; st.textContent = "NOODREM AAN — vrijgeven";
    st.style.background = "color-mix(in srgb,var(--bad) 18%,transparent)";
  } else {
    delete st.dataset.aan; st.textContent = "STOP"; st.style.background = "";
  }

  const bs = el("rondestand"); const rk = el("ronde");
  if (t.ronde.bezig){
    rk.className = "knop"; rk.disabled = false; rk.dataset.stop = "1";
    rk.style.borderColor = "var(--bad)"; rk.style.color = "var(--bad)";
    rk.textContent = "Ronde afbreken";
    bs.textContent = "ronde loopt sinds " + geleden(t.ronde.gestart); }
  else if (t.aanwijzing.stop){ rk.className="knop uit"; rk.disabled=true; delete rk.dataset.stop;
    rk.textContent = "Volgende ronde starten"; rk.style.borderColor=""; rk.style.color="";
    bs.textContent = "de noodrem staat aan"; }
  else { rk.className="knop"; rk.disabled=false; delete rk.dataset.stop;
    rk.style.borderColor = ""; rk.style.color = ""; rk.textContent = "Volgende ronde starten";
    bs.textContent = (t.aanwijzing.volgorde||[]).length
      ? "aangewezen werk wordt bij de volgende ronde opgepakt"
      : (t.ronde.uitslag===null ? "" : "vorige ronde afgerond"); }

  const lanes = el("lanes"); lanes.innerHTML = "";
  for (const [naam, e] of Object.entries(t.engineers)){
    const waarschuwt = t.signalen.some(s => s.wie===naam && s.niveau==="waarschuwing");
    const alarm = t.signalen.some(s => s.wie===naam && s.niveau==="alarm");
    const d = document.createElement("div");
    d.className = "eng" + (alarm||e.stand==="vastgelopen" ? " fout" : e.stand==="klaar" ? " klaar" : waarschuwt ? " warn" : "");
    const mt = e.meting;
    d.innerHTML = '<h2>'+naam+(e.subtaak?' — '+e.subtaak:'')+'</h2>'+
      '<div class="sub">'+(e.titel||"—").slice(0,58)+'</div>'+
      (mt ? '<div class="r">▫ '+mt.commits+' commits'+(mt.bestanden!==null?' · '+mt.bestanden+' gewijzigde bestanden':' (uit het logboek)')+'</div>'+
            '<div class="r">▫ '+(mt.laatsteCommit? mt.laatsteCommit.hash+" "+mt.laatsteCommit.tekst.slice(0,34) : "nog geen commit")+'</div>'+
            '<div class="r">▫ laatste wijziging '+geleden(mt.gewijzigd)+'</div>'
          : '<div class="r" style="color:var(--tx3)">▫ nog geen gemeten werk</div>')+
      (e.laatsteToets ? '<div class="r" style="color:'+(e.laatsteToets.uitslag==="groen"?"var(--good)":"var(--bad)")+'">▪ '+e.laatsteToets.tekst+'</div>' : '')+
      '<div class="r" style="color:var(--tx3)">stand: '+e.stand+'</div>';
    lanes.appendChild(d);
  }
  if (!Object.keys(t.engineers).length) lanes.innerHTML = '<div class="kaart leeg">nog geen engineer aan het werk</div>';

  const sig = el("sig");
  if (!t.signalen.length){ sig.className="leeg"; sig.textContent="niets"; }
  else { sig.className=""; sig.innerHTML = t.signalen.map(s =>
      '<div class="sig '+s.niveau+'">'+(s.niveau==="alarm"?"⛔ ":"⚠ ")+(s.wie?s.wie+" ":"")+s.tekst+
      (s.waarom ? '<div style="font-weight:400;color:var(--tx2);font-size:12px;margin:2px 0 4px 18px">'+s.waarom+'</div>' : '')+
      '</div>').join(""); }

  // Zonder dit springt het logboek bij elke verversing terug naar boven, en dan
  // kun je een merge van drie regels geleden niet aanwijzen — precies wat je in
  // een demo wilt doen (gemeten 30-08-2026).
  const lg = el("log");
  const bewaard = lg.scrollTop;
  const stondBoven = bewaard < 8;
  const MIJLPAAL = new Set(["merge","retest","verbod","alarm","poort","uitgedeeld",
                            "run-gestart","run-gestopt","administratie","merge-mislukt","conflict"]);
  const zichtbaar = alleenMijlpalen ? t.logboek.filter(r => MIJLPAAL.has(r.soort)) : t.logboek;
  el("filter").className = alleenMijlpalen ? "aan" : "";
  el("filter").textContent = alleenMijlpalen ? "toon alles" : "alleen mijlpalen";
  lg.innerHTML = zichtbaar.map(r =>
    '<div><span class="t">'+tijd(r.t)+'</span>'+
    '<span class="b '+r.bron+'">'+(r.bron==="gemeten"?"▫":"▪")+'</span>'+
    '<span class="w">'+r.wie+'</span><span>'+r.soort+' — '+String(r.tekst).slice(0,70)+'</span></div>').join("");
  lg.scrollTop = stondBoven ? 0 : bewaard;
  el("vastmelding").hidden = stondBoven;
}

async function wijsAan(id){
  const nu = (await (await fetch("/toestand.json")).json()).aanwijzing.volgorde || [];
  const volgorde = nu.includes(id) ? nu.filter(x=>x!==id) : [...nu, id];
  await fetch("/aanwijzing", {method:"POST", body: JSON.stringify({volgorde})});
}
el("wis").onclick = () => fetch("/aanwijzing", {method:"POST", body: JSON.stringify({volgorde:[]})});
el("filter").onclick = () => { alleenMijlpalen = !alleenMijlpalen; };
el("stop").onclick = () => fetch("/noodrem", {method:"POST",
  body: JSON.stringify({aan: !el("stop").dataset.aan})});
el("ronde").onclick = async () => {
  const k = el("ronde");
  if (k.dataset.stop){
    el("rondestand").textContent = "afbreken...";
    await fetch("/ronde-stop", {method:"POST"});
    return;
  }
  el("rondestand").textContent = "ronde starten...";
  const uit = await (await fetch("/ronde", {method:"POST"})).json();
  if (!uit.gestart) el("rondestand").textContent = uit.reden;
};

const PAGINAVERSIE = "2026-08-30-logscroll";

function verbind(){
  const bron = new EventSource("/stroom");
  bron.onmessage = (b) => teken(JSON.parse(b.data));
  bron.onerror = () => { bron.close(); el("stip").className="stip stil"; setTimeout(verbind, 2000); };
  bron.onopen = () => { el("stip").className="stip"; };
}
verbind();
setInterval(() => { if (Date.now()-laatste > 6000) el("stip").className="stip stil"; }, 2000);
</script></body></html>`;
