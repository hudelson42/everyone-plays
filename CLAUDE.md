# Sideline — project notes

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
No CDN links, no web fonts, no external requests of any kind.

## The one idea that matters

Everything is derived from an immutable event log. `S.game.log` holds
`{eid, g, t, gt, sh, period, type, playerId, band}` records. `compute()`
replays it and returns per-player time, per-band stint counts, cards, goals.
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

## Invariants — these must hold

The Setup tab has a **Run self-check** button (`selfCheck()`) that asserts them
live. The test suite asserts them too. If you change anything in the time
model, check both.

1. **Minutes add up.** Sum of all players' time equals the integral of
   on-field headcount over elapsed game time. This is the big one.
2. Field never holds more than `teamSize`; no band exceeds `slotsFor(band)`.
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
minutes, hold everyone already on the field in the position they're standing
in, then apply at most `maxSwitch` (default 6; was 2) deliberate front-to-back swaps.
Equalization is unaffected — a simulated 50-minute game still lands every
outfield player on exactly 25.0 minutes.

**The keeper holds their spot** unless moved manually.

**Tapping confirms, dragging doesn't.** Successive taps are easy to trigger by
accident; a press-and-hold drag is deliberate. Don't make these symmetric.

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

Photos are 128×128 JPEG at q=0.72, roughly 5 KB each. The archive keeps full
event logs for the 3 most recent games only, capped at 12 games, because logs
plus base64 photos will otherwise approach the ~5 MB localStorage ceiling.

## Service worker

Network-first for the page so coaches with signal get updates, cache-first for
icons. **When you change `index.html`, bump `CACHE` in `sw.js`** or installed
phones keep running the old version. A new version prompts the user rather than
swapping out mid-game.

## Testing

```bash
pip install playwright && playwright install chromium
python3 tests/test_sideline.py
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
