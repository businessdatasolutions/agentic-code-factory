# BUILDPLAN — de werkvoorraad

Dit is het stuk build plan waarop de factory wordt getoond: **Fase 7 van Plinkie**, de
bewakingsmotor. Het is woordelijk overgenomen uit `businessdatasolutions/plinkie`, waar het weken
vóór de factory is geschreven — dat is precies wat het bruikbaar maakt als proef: de subtaken zijn
niet bedacht om een demo te laten slagen.

Twee dingen om te weten voordat je de graaf leest:

- **7.3 blijft de hele run geblokkeerd.** Hij schrijft zelf uit dat hij 6.18 tot en met 6.21 nodig
  heeft, en die horen bij een andere fase die hier niet staat. De manager laat hem daarom met rust.
- **Alleen 7.3 schrijft zijn afhankelijkheid uit.** In het volledige plan van 6.958 regels is dat de
  enige die dat doet, in een vorm die een machine kan lezen. De rest van de volgorde staat met de
  hand in `werkwijze/opzet-fase7.json`.

---

## Fase 7 — Bewakingsmotor & alerts

**Doel.** F4: elke nacht elk bewaakt contract tegen de verse markt + kalenderlogica;
signaal alleen bij relevantie.
**Wat de tester doet.** Zet op een eigen bewaakt contract een drempel ("meld vanaf
€15/mnd"), verlaagt in staging kunstmatig een marktprijs, draait de nachtrun en
ontvangt precies één alert-mail met het juiste bedrag en het boetevrije venster.
**Spec.** F4; PRD §9 stap 8; BP §4 stap 8 (géén LLM, geen PII in de job; mail-merge
pas in de e-mailservice).

### Subtaken
- [ ] 7.1 `services/watchdog/`: deterministische join `user_contracts` × marktdata ×
      kalenderlogica (einddatum, opzegtermijn, boetevrij venster, actie-einddata).
- [ ] 7.2 Drempels per gebruiker (default €15/mnd) + alert-voorkeuren-tabel.
- [ ] 7.3 Alert-flow: watchdog → Pub/Sub → **bezorgdienst** die de versleutelde
      `bezorg_verwijzing` ontsleutelt en het adres in kluis B opzoekt (BP v1.28 §2d, §4 stap 8).
      *(**Herschreven 23-08-2026, vóórdat deze subtaak gebouwd is.** Hier stond "e-mailservice die
      het adres pas bij Identity Platform ophaalt", en dát is precies de join die BP v1.28 uit de
      opslag haalt — alleen dan als vaste nachtelijke handeling, met de gedeelde sleutel over een
      Pub/Sub-topic en langs de logregels van twee diensten. De watchdog publiceert
      `{bezorg_verwijzing, onderwerp, tekst}` en géén `account_sleutel`. Was 7.3 eerst gebouwd zoals
      hij hier stond, dan hadden we de koppeling er eerst in en daarna weer uit gehaald.)*
      *(**Vereist 6.18 t/m 6.21.** Deze subtaak kan niet vóór de kluizen bestaan, en dat is de
      volgorde-afhankelijkheid die het makkelijkst over het hoofd wordt gezien.)*
- [ ] 7.4 Kalender-triggers los van prijstriggers getest: einddatum −90d/−30d, einde
      opzegtermijn.
- [ ] 7.5 Anti-ruis: maximaal 1 alert per contract per week tenzij drempel opnieuw
      overschreden met ≥2× marge (PRD §2.4-gain "geen alert-ruis").
- [ ] 7.6 Watchdog als stap 8 in de nachtrun-orchestratie + in het run-rapport.

### Testgate
- [ ] Scenario-tests: prijsdaling boven/onder drempel, naderend exit-venster,
      geen-verandering → resp. alert / geen alert / kalender-alert / stilte
- [ ] Job-logs bevatten account-UUID's maar aantoonbaar geen e-mailadressen
- [ ] Tester-scenario (kunstmatige prijsdaling) levert exact één correcte mail
### Afsluiting
- [ ] commit — [ ] push — [ ] vink Fase 7 af in het overzicht

---
