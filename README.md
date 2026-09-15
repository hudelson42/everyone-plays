# Everyone Plays

A substitution and shift tracker for youth sports coaches: soccer (and futsal),
field hockey, lacrosse, ice hockey and basketball. One HTML file, no account, no
signal required.

**Use it here:** https://hudelson42.github.io/everyone-plays/

Add it to your home screen and it opens like an app.

## What it does

Everyone Plays keeps track of who is on the field and how long each player has been
out there, so playing time comes out even without you keeping a tally in your
head while nine kids ask you when they're going on.

- **Even minutes.** Every player's clock runs while they're on. The app builds
  the next shift around whoever has played least.
- **Positions, not just bodies.** Every spot is a real position — left D,
  sweeper, striker, right wing — so you can see that a player got twenty minutes
  but never left the back line, or never played the right side.
- **Everyone tries new spots.** Subs go into the positions they've played least,
  so over a game kids rotate around the field. Turn it off if you'd rather keep
  kids where they're comfortable.
- **A next shift in one tap.** Tap Plan next shift and it builds the rotation;
  check it and send them on. Or have it keep one ready in the background.
- **Extra time counts.** At full time the buzzer goes but the clock keeps
  running until you end the period, so stoppage time still counts toward
  minutes.
- **No needless reshuffles.** Players already on the field hold their position
  unless moving them genuinely evens things out. You can cap how many switch
  per shift on Setup.
- **Built for a sideline.** Big targets, high-contrast sun mode, an optional
  buzzer and vibration at shift end, and the screen stays awake.
- **Injuries and late arrivals.** Pull a player in one tap and the app offers
  the fairest replacement. Mark someone as arriving late or leaving early and
  they drop out of the rotation.
- **A record afterwards.** Minutes per position per player, exportable as CSV
  for the parent emails.
- **More than one team.** Each team keeps its own roster, settings, minutes and
  history. Tap the team name on the Roster tab to switch.
- **The whole season.** Past games are listed by date. The Season view adds them
  up: games played and missed, minutes, each kid's share of an even split, and
  positions played, plus the team's record in Advanced mode. It can also even
  out playing time across games, suggest who goes in goal next, and remind you
  when the clock has been left paused.

- **Your sport.** Each team has its own sport, with that sport's positions and
  words: left D and sweeper in soccer, point guard and center in basketball, the
  Ice tab in hockey. Hockey rotates whole lines and defense pairs; lacrosse and
  hockey penalties sit a player out for their length; basketball can foul
  players out.

Optional Advanced mode adds formations, the score, each sport's stats (goals,
assists, shots, saves, cards and penalties; or points, rebounds, steals and
fouls) and season totals. Leave it off and the app stays simple.

## Your data stays on your phone

There is no server, no account and no analytics. Everything lives in your
browser's storage on your own device. Nothing about any child leaves the phone
it was typed into.

The flip side is that clearing your browser data will erase your roster. Use
**Setup → Save backup file** before a big day. It includes every team, and it's
the only copy that survives.

## Getting started

1. **Roster** — add players. A name and a number is enough.
2. **Setup** — pick your sport and format. A new install starts as 7 v 7 soccer.
3. **Field** — tap an open position, then tap the player who goes there.
4. **START** — top left, runs the clock.
5. When the buzzer goes, tap **Plan next shift**, check it, then **Send them on**.
   The green **Field** tab is what's live; the amber **Next** tab is the plan.
6. Not sure what a setting does? Tap the **?** next to it.

**How it works**, at the top of Setup, covers the rest. Tap the clock at the top
for period controls, notes and New game.

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
python3 tests/test_everyone_plays.py
```

When you change `index.html`, bump `CACHE` in `sw.js` in the same commit, or
phones that already installed the app will keep running the old version.

## Contributing

Bug reports and feature requests are welcome via GitHub Issues. If you coach
and something about this gets in your way during a real game, that's the most
useful thing you can tell me.

## Support

Everyone Plays is free, with no ads and no accounts. If it helps your team, you
can [buy me a coffee on Ko-fi](https://ko-fi.com/hudelson).

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, run it for your club. If it
helps your team, that's the whole point.
