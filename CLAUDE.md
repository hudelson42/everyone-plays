# Everyone Plays — project notes

Formerly called Sideline. Internal names still use `sideline` on purpose: the
storage keys (`sideline-tracker-v1`, `sideline-teams-v1`, `sideline-team-*`),
the service worker cache, and the `sideline: "backup"` marker in backup files.
Renaming the storage keys would strand every existing save. Leave them alone.

A substitution and playing-time tracker for youth soccer coaches. Single-page
app, no build step, no dependencies, no server, no accounts.

`HISTORY.md` has the full decision log, the data schema in detail, and the list
of bugs found so far with how each was caught. Read it before changing anything
in the time model or the rotation algorithm.

## Layout

```
index.html      the entire app — HTML, CSS and JS inline, ~120 KB
manifest.json   PWA manifest
sw.js           service worker (offline cache)
icon-*.png      app icons, including maskable variants for Android
tests/          Playwright suite — run this before shipping anything
CLAUDE.md       this file — operating rules
HISTORY.md      how the project got here, full schema, past bugs
```

`index.html` is deliberately one file. Don't split it into modules or add a
bundler; the ability to open it as a plain file and have it work is a feature.
No CDN links, no web fonts, no external requests of any kind. The only outside
links are text links to Ko-fi, which are plain navigation and load nothing. They
appear in three places:
- the About card on Setup;
- the "Is this really free?" card at the bottom of Help;
- a dismissible note after the 3rd filed game and every 5th after that
  (`supportNoteDue()`). It shows on Field and History only until kickoff, and
  can be turned off on Setup (`supportNotes`).

Never put them on Field, Next or the clock screen during play, never in a
pop-up or toast, and never in Advanced mode.

## The one idea that matters

Everything is derived from an immutable event log. `S.game.log` holds
`{eid, g, t, gt, sh, period, type, playerId, band, pos}` records. `compute()`
replays it and returns per-player time by band and by position, stint counts,
cards, goals.
Nothing is incremented in place.

That is what makes swaps, undo, manual corrections and history all consistent
with each other. It also means bugs are **silent** — nothing crashes, the
minutes just quietly go wrong. Hence the invariants below.

- `gt` is game-elapsed seconds, which excludes paused time. Use it for anything
  that affects minutes.
- `t` is wall-clock epoch ms, for display only.
- `g` groups events pushed together (one substitution = 2 events, one group).
  Undo pops a whole group.
- `sh` is the shift number. History groups by it.
- `pos` is the specific position code (`LD`, `SW`, `ST`…) on ON and MOVE.
  Games logged before positions existed have none; `fieldLayout()` seats those
  players in the first open slot of their band. Always go through
  `fieldLayout()` / `whereOn()` for "who is where", never `onBand` alone.

## Invariants — these must hold

The Setup tab has a **Run self-check** button (`selfCheck()`) that asserts them
live. The test suite asserts them too. If you change anything in the time
model, check both.

1. **Minutes add up.** Sum of all players' time equals the integral of
   on-field headcount over elapsed game time. This is the big one.
2. Field never holds more than `teamSize`; no band exceeds `slotsFor(band)`;
   no two players share a position code.
3. No player has two open stints at once.
4. Nobody is on the field in a position they aren't eligible for (auto-fill
   must never do this; manual placement may, with a warning).
5. No event references a deleted player.

## Decisions already made — don't undo these without a reason

**Substitutions cannot be deleted from History.** Only goals, cards, saves and
notes have a × button. Deleting an OFF event makes a player accrue minutes
forever and breaks invariant 1 silently. Fix substitutions by substituting
again, or with Undo.

**Cards are derived from the log, never written onto the roster.** An earlier
version set `p.avail = "out"` on a red card, which survived New Game and left a
player mysteriously benched the following week.

**Auto-fill is stability-biased.** Naive "put each player where they've played
least" produced *1 on, 1 off, 5 switched* every shift — seven kids being told
new positions every ninety seconds. Current algorithm: pick the squad by
minutes, hold everyone already on the field in the exact position they're
standing in, put incoming players in the open positions they've spent least
time in (`freshPositions`, default on; off evens out by band only), then apply
front-to-back swaps that each even things out by more than two minutes.
`maxSwitch` caps those swaps. Its default is `null`, no limit — the coach chose
that on 2026-09-14 knowing the history above. Equalization is unaffected — a
simulated 50-minute game still lands every outfield player on exactly 25.0
minutes.

**Positions are specific; eligibility is by band.** Each band splits left to
right into named positions (`POSDEF`, `posCodes()`): Left D / Sweeper / Right D,
Left wing / Striker / Right wing, and so on. Tapping and dragging always land in
one exact slot, and swapping two players trades their exact positions. The
roster still ticks only GK / DEF / MID / FWD. Lineups save slots by index, gaps
included, so players come back in the same position.

**A period ending moves straight to the next one.** `endPeriodNow()` advances
to the next period with the clock stopped at 0:00 and `onBreak` set, so START
begins it. It doesn't switch tabs on its own; the Field and Next tabs say what's
happening. Only the last period sets `periodOver`, and START then offers a new
game. Coaches used to have to find the Clock tab to start period 2.

**A loaded lineup never leaves a spot open if someone can fill it.**
`loadLineup()` places saved players first. `fillOpenSpots()` then gives any spot
that would go on empty (nothing planned, nobody standing there) to the fairest
available player, and the toast names them. Save on the Next tab saves the plan
(`saveLineup(name, true)` uses `resolvePlan()`); Save from the field saves the
field.

**The whole field fits on one screen.** Pitch cards are capped at 92 px wide
with 40 px photos (`pitchSize()`). After each render, `fitPitch()` shrinks the
photos (down to 24 px), then goes tight, until the pitch fits below whatever is
above it and above the selected-player bar. While a player is selected, the
cards above the field hide. Rotating the phone re-renders. The selected-player bar is sticky with `z-index:20`,
and `#pitch` uses `isolation:isolate` so the bands' `z-index` can't paint over
it. A real Android test showed oversized cards covering its buttons.

**Six tabs.** Field, Next, Minutes, History, Roster, Setup. The clock screen
opens from the clock in the top bar, and Help from Setup; both are views with a
Back link, not tabs. Eight tabs made the labels too small to hit outdoors.

**Undo names what it undid** (`describeGroup()`). Undoing a `PERIOD_END` restores
the period from the `base`, `shift` and `shiftStart` stored on the event, and is
refused once the next period has started.

**Vibration settings are hidden where `navigator.vibrate` doesn't exist** (iOS
Safari), rather than showing switches that do nothing.

**Auto-fill plans for the end of the shift.** Players on the field are counted
as if they finish the current shift (`left` in `autoFillNext()`), including for
the minimum stint, so the plan built at kickoff already brings on the bench.
Before this, everyone tied at 0 minutes and the starters stayed on.

**The goalie switches each shift by default** (`rotateKeeper`). Auto-fill
doesn't hold the keeper in goal, and puts in goal whoever has spent least time
there. With it off, the keeper holds their spot unless moved manually, and goal
is a last resort for incoming players.

**Tapping confirms, dragging doesn't.** Successive taps are easy to trigger by
accident; a press-and-hold drag is deliberate. Don't make these symmetric.

**The press-and-hold buzz has its own setting** (`dragBuzz`). `vibrate` is only
the shift-end alert; a coach can want one without the other.

**Goalie minutes count toward a player's total.** Deliberate. The Minutes grid
shows GK separately so you can still see it.

**`compute()` is memoized** against log length, roster size, adjustments and a
bucketed clock. The render path used to call it 100+ times per render via
`available()` → `isSinBin()` → `compute()`. Call `invalidate()` after any
mutation; `render()` and `tick()` do it at entry.

**No icons in the UI.** Words or standard box-score letters (G, A, SOG, YC).
Chevrons for collapse are fine.

**Nothing leaves the device.** No analytics, no sync, no accounts. Storing
children's names and photos on a server means COPPA and state privacy law.
Keep this property.

## Storage

`Store` tries `window.storage` (Claude artifact API) → `localStorage` →
in-memory, in that order. Opened from `file://` or a `content://` download,
browser storage is often unavailable — that's why hosting matters, and why
Setup shows a warning banner when `storageMode === "memory"`.

**Teams.** A coach can have several teams. Each team is a complete `S` under
its own storage key; the first team keeps the original key
(`sideline-tracker-v1`), so saves from before teams load unchanged. The index
(`sideline-teams-v1`, the `TEAMS` object) lists the teams, which one is open,
and the settings in `SHARED` (sun, sound, vibrate, dragBuzz), which belong to
the phone rather than a team. Nothing outside the teams section should know
teams exist — keep it that way. Switching pauses a running clock first, since
only the open team's clock can move. Always load state through `hydrate()`.
Backups hold every team; an old single-team backup is added as a new team,
never swapped in. The ~5 MB quota is shared by all teams.

Photos are 128×128 JPEG at q=0.72, roughly 5 KB each. The archive holds up to
100 game summaries (a few KB each) and keeps full event logs for the 3 most
recent games only, because logs plus base64 photos will otherwise approach the
~5 MB localStorage ceiling.

## Past games and season

**New game** files the game in `S.archive` as a summary from `summarizeGame()`:
date (set at first kickoff), opponent, score, and for each player id whether
they attended and started, shifts, seconds by band and by position, stats, and
periods in goal. Everything season-related reads summaries through
`aggregate()`, never logs. Logs are trimmed after `LOGS_KEPT` games, and reading
them is what used to crash the Roster tab. `upgradeGame()` converts games filed
before summaries existed. The W–L–D record only counts games played with
Advanced mode on, so a basic game's 0–0 isn't a draw.

Share is a player's minutes divided by an even split of the games they came to.
Attendance is the `present` snapshot taken at kickoff, plus anyone who played.

- `seasonBalance` (off by default) moves kids who are behind over past games up
  the auto-fill order, capped at one shift's worth per game.
- `goalieRotation` (Advanced) suggests the next keeper on the Next tab.
- `pauseReminder` (on by default) nudges once after two minutes paused
  mid-period with players on the field. `nextPeriod()` clears `pausedAt`, so
  halftime doesn't count.

## Service worker

Network-first for the page so coaches with signal get updates, cache-first for
icons. **When you change `index.html`, bump `CACHE` in `sw.js`** or installed
phones keep running the old version. A new version prompts the user rather than
swapping out mid-game.

## Testing

```bash
pip install playwright && playwright install chromium
python3 tests/test_everyone_plays.py
```

The suite drives a real headless Chromium at 390×844. It covers time
conservation, the churn bound, full-game equalization, eligibility,
availability, shift numbering, history structure, saved lineups, check-in,
event reassignment, PWA offline behaviour, and console errors plus horizontal
overflow at 360 and 430 px in both basic and advanced modes.

Add a case whenever you fix a bug. Every real bug in this project so far was
silent — wrong numbers, not a stack trace.

## Style

Mobile-first, one-handed, outdoors, cold hands. 44 px minimum targets.
`touch-action: manipulation`, `user-select: none`, safe-area insets, never any
horizontal scroll. Sun mode is a hard-contrast theme, not a dark-mode inverse.
Copy is plain spoken — "Who is here?", not "Attendance Management".
