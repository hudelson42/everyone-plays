# Everyone Plays — how this got here

Context for anyone picking the project up, human or model. `CLAUDE.md` says
what the rules are; this says where they came from and what the data looks
like. When the two disagree, `CLAUDE.md` wins — it's kept current.

---

## Where it started

The brief was a single-file HTML substitution and shift tracker for youth
soccer: mobile-first, sideline-usable, offline, roster with photos, live clock
with a shift buzzer, and a grid of playing time by position.

Open questions were settled before any code was written:

| Question | Decision |
|---|---|
| Midfielders, or just offense/defense? | Four bands: GK / DEF / MID / FWD, with formation presets |
| Do goalie minutes count toward a player's total? | Yes. GK is shown as its own column so you can still see it |
| Headshots? | Phone camera, downscaled to 128×128 JPEG q=0.72 on capture |
| What does "equal playing time" mean? | Lowest total minutes comes on next; ties broken by longest time since last on |
| Storage | Adapter chain, because `localStorage` isn't available everywhere the app runs |

A deliberate instruction shaped a lot of what followed: **err toward getting the
functionality rather than accepting arbitrary implementation limits.** Where
there was a choice between a simpler build and the thing that would actually
work on a sideline, the app took the second.

---

## The decisions that matter, and why

### Event sourcing, not counters

The first real architectural call. Rather than incrementing four timers per
player, every change appends to an immutable log and all totals are derived by
replaying it. That is what makes mid-shift swaps, undo, manual minute
corrections and the History tab mutually consistent instead of four
independent things that drift apart.

The cost is that bugs are silent. Nothing crashes; the minutes just go wrong.
Every real defect found in this project has been of that kind, which is why
there's both a live self-check and a test suite.

### The clock is timestamp-derived

`startedAt` plus elapsed, recomputed on every render and on `visibilitychange`.
A `setInterval` that increments a counter loses minutes whenever the phone
locks or the tab backgrounds — which is most of a game.

### Auto-fill is stability-biased

The original algorithm ranked each open slot by how little time a player had
spent in that band. Mathematically it equalized beautifully. In practice it
produced **"1 on · 1 off · 5 switched"** every shift — one substitution, and
six other children told to go stand somewhere new, roughly every ninety
seconds. This showed up in a screenshot from a real game.

Rewritten to: pick the squad by minutes played, hold everyone already on the
field in the position they're standing in, then apply at most `maxSwitch`
(default 2) deliberate front-to-back swaps. Equalization did not suffer — a
simulated 50-minute game still lands every outfield player on exactly 25.0
minutes with all of them playing both ends.

**Don't "optimize" this back.** The churn was the single worst usability
failure the project had.

On 2026-09-14 the coach set the swap cap's default to no limit. Holding players
in their exact position is what keeps churn down; the cap is still on Setup.

### Specific positions

Added 2026-09-14. "Defense" wasn't specific enough: a kid could spend twenty
minutes at left D and never play right D or sweeper. Each band now splits left
to right into named positions, the code is written into ON and MOVE events, and
tapping or dragging always lands in one exact position. Auto-fill sends incoming
players to the open position they've spent least time in (`freshPositions`,
default on). Eligibility stayed by band.

Logs from before this have no `pos`. They still load: `fieldLayout()` seats
those players in the first open slot of their band.

### The keeper holds their spot

Auto-fill pins whoever is in goal. A keeper changing every rotation is its own
problem.

Changed 2026-09-14. The coach wanted the goalie switched each shift by default,
and the plan built at kickoff to bring on the whole bench. Auto-fill now plans
for the end of the current shift and rotates the keeper. Turning `rotateKeeper`
off brings back the old hold.

### Tapping confirms, dragging doesn't

Explicitly requested, and correct. Two successive taps are easy to trigger by
accident on a phone in a coat pocket; a press-and-hold drag is unambiguous.

There was a brief period where both paths confirmed, on the reasoning that
inconsistency was a flaw. That was wrong: the asymmetry *is* the design. Don't
make them symmetric.

### Substitutions can't be deleted from History

Only goals, cards, saves and notes have a × button. Deleting an OFF event makes
a player accrue minutes forever and breaks time conservation with no visible
symptom. Corrections happen by substituting again, or with Undo.

Event *reassignment* exists instead, because the mistake coaches actually make
is crediting the wrong scorer — and deleting-and-re-adding loses the clock
time.

### Cards are derived, never written to the roster

An earlier version set `p.avail = "out"` on a red card. That survived New Game,
so a player sent off in one match stayed mysteriously benched the following
week with nothing on screen explaining it.

### Nothing leaves the device

No accounts, no sync, no analytics. Partly a feature, partly risk management:
the moment children's names and photos land on a server, COPPA and state
privacy law apply. Keeping everything local avoids that entirely.

### Multiple teams

Added 2026-09-14, because some coaches run more than one team. Each team is a
whole state object under its own storage key, so the tracking code never
learned about teams. Game format, formation, timing and rotation settings are
per team, since an under-8 and an under-12 side play differently. Sun mode,
sound and vibration are shared because they're about the phone. Two clocks
can't run at once, so switching pauses the open one after asking. A child on
two teams is two separate roster entries; linking them wasn't worth the
complexity.

### Past games are summaries, and a season is a filter

Added 2026-09-14. Finished games used to keep a minutes table keyed by player
name, dated when **New game** was tapped. The Roster tab's season stats read
every past game's log, but logs are trimmed after three games, so a fourth game
made the Roster tab throw. Each game is now a summary keyed by player id and
dated at kickoff, and all season numbers come from summaries.

The coach chose date filters (all, last 10, last 5) over explicit seasons, and
chose not to build a playing-time target or a parent summary for now. Share of
minutes is measured against games attended, so missing a week isn't flagged as
unfair.

### The name

Renamed from Sideline to Everyone Plays on 2026-09-14, before the project was
promoted anywhere. "Sideline" was crowded in exactly this space:
- TEAM SIDELINE is a registered mark for sports league software.
- Pinger holds SIDELINE registrations for its second-phone-number app.
- Sideline Pro is an App Store app doing nearly the same job, live since May 2025.

"Put Me In Coach" was considered and dropped. It's a line from John Fogerty's
"Centerfield", he has filed trademarks on that lyric, and several youth-sports
businesses already use the phrase. "Everyone Plays" turned up no app or brand
in a web search. That isn't a full trademark clearance.

Storage keys, the cache name and the backup marker still say `sideline`.

### No icons

Words, or standard box-score letters — G, A, SOG, YC. An emoji-based pass was
built and rejected as not obvious enough. Chevrons for collapse are fine.

### History is a lineup record, not a transcript

One card per shift showing who played where, with duration and any match
events. Mid-shift substitutions are counted ("2 mid-shift changes"), not
listed. An earlier version enumerated every on/off and was correct but unusable.

---

## Working style expressed during development

- **Review before building.** Proposals get critiqued and a final configuration
  approved before code is written.
- **Claims get tested, not asserted.** Every behavioural statement in this
  project was verified in a headless browser first. When a regression was
  suspected, the answer was a mechanical diff of every function, setting, event
  type, DOM hook and string — not reassurance.
- **Plain text output**, not rich cards.
- Direct correction is expected when a change was wrong. The drag/tap revert
  came from exactly that and the app is better for it.

---

## Data schema

The open team's state lives in one object, `S`, serialized to storage as JSON.
Each team has its own copy under its own key, listed in a small index:

```
TEAMS = {                  // stored under "sideline-teams-v1"
  v: 1,
  active: "t1",
  list:   [{ id, name, key, players, bytes }],   // first team's key is "sideline-tracker-v1"
  shared: { sun, sound, vibrate, dragBuzz }      // applied to every team on load
}

Backup = { sideline: "backup", v: 2, at, active,   // active is an index into teams
           shared, teams: [{ name, data: S }] }
```

```
S = {
  v: 1,
  roster:    [Player],
  settings:  Settings,
  game:      Game,        // the match in progress
  archive:   [Archived],  // finished games, newest first, capped at 12
  lineups:   [Lineup]     // saved starting elevens, capped at 12
}
```

### Player

```
{ id: "p<base36>",        // uid(), stable for the life of the roster entry
  name: "Ava Chen",
  number: "7",            // string, may be empty
  photo: "data:image/jpeg;base64,…" | null,   // 128×128, ~5 KB
  avail: "available" | "late" | "early" | "out",
  elig:  { GK: bool, DEF: bool, MID: bool, FWD: bool } }
```

Only `available` counts as playable. Red cards and the sin bin are derived from
the log, not stored here.

### Settings

| Key | Default | Meaning |
|---|---|---|
| `advanced` | `false` | Reveals formations, match events, opponent scoring, season stats |
| `teamSize` | `7` | Players on the field **including** the keeper |
| `formationIdx` | `0` | Index into `FORMATIONS[teamSize]`; 7v7 default is 3-0-3-1 |
| `periods` / `periodLen` | `2` / `25` | Count and minutes |
| `shiftLen` | `5` | Minutes between rotations |
| `minStint` | `90` | Seconds a player must be on before auto-fill will pull them |
| `maxSwitch` | `null` | Most players swapped front to back in one shift; `null` is no limit |
| `rotate` | `true` | Prefer moving players between defense and attack |
| `rotateKeeper` | `true` | Switch the goalie each shift; off holds the keeper in goal |
| `extraTime` | `true` | At full time the buzzer goes and the clock keeps running until the coach ends the period (added 2026-09-15); off stops the clock at full time, the old behaviour |
| `freshPositions` | `true` | Put incoming players in the open positions they've played least |
| `autoPlan` | `false` | Keep the next shift prepared in the background (default changed to off 2026-09-14) |
| `confirmChanges` | `true` | Confirm tap-initiated changes (drag is never confirmed) |
| `ycSinBin` | `false` | Whether a yellow card removes the player temporarily |
| `sinBinMins` | `5` | Sin bin duration |
| `staleWarn` | `10` | Minutes on the bench before a player is flagged |
| `warnLead` | `30` | Seconds before shift end for the warning beep |
| `sound` / `vibrate` / `sun` | `false` / `false` / `false` | Shift-end buzzer, shift-end vibration, high-contrast theme |
| `dragBuzz` | `true` | Short buzz when you press and hold a player to drag |
| `seasonBalance` | `false` | Move kids who are behind over past games up the auto-fill order |
| `goalieRotation` | `false` | Advanced: suggest who goes in goal next |
| `pauseReminder` | `true` | Nudge when the clock stays paused mid-period |
| `supportNotes` | `true` | Occasional Ko-fi note after a filed game (3rd, then every 5th); shared by every team |

Formations are written **defense-midfield-forward-keeper**, so `3-0-3-1` is
three at the back, no midfield, three up top, one in goal.

### Game

```
{ log: [Event], seq: 0,      // seq increments per push, becomes the group id
  shift: 1, period: 1,
  running: false, startedAt: null,   // epoch ms while the clock runs
  base: 0,                   // seconds banked in the current period
  priorTotal: 0,             // seconds from completed periods
  periodOver: false,
  shiftStart: 0,             // game-elapsed seconds the current shift began
  warned: false, alerted: false,
  adj: { playerId: { BAND: secondsDelta } },   // manual minute corrections
  id, date, opponent,        // date is set at the first kickoff
  present: [playerId] | null,  // who was available at kickoff
  pausedAt, nagged,          // paused-clock reminder
  onBreak,                   // between periods: advanced, clock not yet started
  next: { GK: [id|null], DEF: […], MID: […], FWD: […] } | null }
```

Slot `i` in a band is position `posCodes(band, slotsFor(band))[i]`, so
`next.DEF[0]` is Left D in a three-back formation.

`base + (now - startedAt)` is time in the current period, clamped to
`periodLen`. `priorTotal + that` is game-elapsed. Everything that affects
minutes uses game-elapsed seconds, so paused time never counts.

### Event

```
{ eid: "p<base36>",   // unique, used for delete and reassign
  g:   3,             // group id — events pushed together share one; undo pops a group
  t:   1736…,         // wall clock, display only
  gt:  412.5,         // game-elapsed seconds — this is what drives minutes
  sh:  2,             // shift number, History groups by this
  period: 1,
  type, playerId, band, note,
  pos: "LD" }         // ON and MOVE only: the exact position; absent in older logs
```

Types: `ON`, `OFF`, `MOVE` (structural — these determine all minutes);
`GOAL`, `SOG`, `SHOT`, `ASSIST`, `SAVE`, `YELLOW`, `RED`, `GA`,
`OPP_GOAL`, `OPP_SOG`, `OPP_SHOT`, `NOTE`, `PERIOD_END`.

A `GOAL` implies a shot on goal and a shot; `SOG` implies a shot. They are not
logged separately — `compute()` derives the rollup, so nothing is double
counted.

### Derived — `compute()`

Returns, per player id:

```
{ GK, DEF, MID, FWD, total,      // seconds
  n: { GK, DEF, MID, FWD }, nTotal,   // times entering each band
  pos: { LD: seconds, … },       // time in each specific position
  np:  { LD: count, … },         // times moved into each position
  onBand, onPos, onSince, lastOff,    // current stint
  goals, assists, saves, ga, shots, sog, yellows, reds, sinBinEnd }
```

Memoized against log length, roster size, adjustments and a bucketed clock.
Call `invalidate()` after any mutation.

### Lineup and Archived

```
Lineup   = { id, name, at, size, form, slots: { BAND: [playerId|null] } }   // index = position slot
Archived = { id, v: 2, date, at, opponent, periods, endGt, advanced, score, playerSeconds,
             players: [{ id, name, number, attended, started, shifts,
                         GK, DEF, MID, FWD, total, pos: { LD: seconds, … },
                         goals, assists, shots, sog, saves, ga, yellows, reds, gkPeriods }],
             log }   // full log kept for the 3 most recent games only; up to 100 games
```

---

## Bugs that were found, and how

Worth reading, because they show the failure modes this codebase actually has.

| Bug | Found by | Symptom |
|---|---|---|
| Auto-fill churn — 5 position switches per shift | A screenshot from a real game | Unusable, but nothing wrong in the data |
| Deleting an OFF event broke time conservation | Code review | Player accrues minutes forever, silently |
| Red card persisted onto the roster | Code review | Player benched the following week, no explanation |
| `compute()` called 100+ times per render | Code review | Slow, worsening with log length |
| Shift numbers skipping (11, 7, 6, 4…) | Screenshot | Looks like lost data |
| `suppressClick` swallowed real taps for 400 ms | Test suite | App appears to ignore you after a drag |
| Events at the same second as a shift start were invisible | Test suite | Goal logged, never displayed |
| A goal opening a shift was treated as the shift's opening group | Test suite | Same, different cause |
| New component CSS never written (script aborted mid-edit) | Screenshot | Unstyled layout |
| Season stats read trimmed logs | Code review, 2026-09-14 | Roster tab throws once a team has four past games |

Note the pattern: **none of these threw an exception.** Screenshots and
invariant checks caught them; reading the code did not, mostly.

---

## Considered and deliberately not done

- **Native app store release.** Apple's guideline 4.2 targets wrapped websites,
  costs $99/year, and adds a release pipeline for something that works as a URL.
- **Accounts and sync.** Would put children's names and photos on a server.
- **Live multi-coach sharing.** Same reason, plus it needs a backend.
- **A playing-time target with an on-track indicator.** Genuinely good idea,
  from a competitor. Not built yet.
- **A "clock is paused" nag.** The most common way this class of app produces
  wrong numbers is a coach forgetting to restart the clock. Built 2026-09-14 as
  `pauseReminder`.
- **Selling it.** The market has a scaled incumbent and a free browser-based
  competitor with the same architecture. Decision was to give it away under MIT
  and see whether it spreads.
