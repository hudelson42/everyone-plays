# Sideline

A substitution and shift tracker for youth soccer coaches. One HTML file, no
account, no signal required.

**Use it here:** https://YOURNAME.github.io/sideline/

Add it to your home screen and it opens like an app.

## What it does

Sideline keeps track of who is on the field and how long each player has been
out there, so playing time comes out even without you keeping a tally in your
head while nine kids ask you when they're going on.

- **Even minutes.** Every player's clock runs while they're on. The app builds
  the next shift around whoever has played least.
- **Positions, not just bodies.** Goalie, defense, midfield and forward are
  tracked separately, so you can see that a player got twenty minutes but never
  left the back line.
- **A next shift, always ready.** It prepares the rotation in the background.
  When the buzzer goes, you tap once.
- **No seven-kid reshuffles.** Players already on the field hold their position
  unless moving them genuinely evens things out, capped at a couple of changes
  per shift.
- **Built for a sideline.** Big targets, high-contrast sun mode, a buzzer and a
  vibration at shift end, and the screen stays awake.
- **Injuries and late arrivals.** Pull a player in one tap and the app offers
  the fairest replacement. Mark someone as arriving late or leaving early and
  they drop out of the rotation.
- **A record afterwards.** Minutes per position per player, exportable as CSV
  for the parent emails.

Optional Advanced mode adds formations, goals, assists, shots, cards, opponent
scoring and season totals. Leave it off and the app stays simple.

## Your data stays on your phone

There is no server, no account and no analytics. Everything lives in your
browser's storage on your own device. Nothing about any child leaves the phone
it was typed into.

The flip side is that clearing your browser data will erase your roster. Use
**Setup → Save backup file** before a big day. That file is the only copy that
survives.

## Getting started

1. **Roster** — add players. A name and a number is enough.
2. **Setup** — pick your format. It ships set to 7 v 7.
3. **Field** — tap an open spot, then tap the player who goes there.
4. **START** — top left, runs the clock.
5. When the buzzer goes, tap **Send them on**.

The **Help** tab covers the rest.

## Running it yourself

It's a single file with no build step and no dependencies. Download
`index.html` and open it in a browser. That said, opening it straight from your
downloads folder makes browser storage unreliable on some phones — if you want
it to remember your roster, host it or use the link above.

## Development

Everything lives in `index.html` — no build step, no dependencies. Open it in a
browser and edit. `CLAUDE.md` has the architecture notes and the
decisions worth not relitigating; `HISTORY.md` has the full data schema, why
each decision was made, and the bugs found so far.

Before shipping a change:

```bash
pip install playwright && playwright install chromium
python3 tests/test_sideline.py
```

When you change `index.html`, bump `CACHE` in `sw.js` in the same commit, or
phones that already installed the app will keep running the old version.

## Contributing

Bug reports and feature requests are welcome via GitHub Issues. If you coach
and something about this gets in your way during a real game, that's the most
useful thing you can tell me.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, run it for your club. If it
helps your team, that's the whole point.
