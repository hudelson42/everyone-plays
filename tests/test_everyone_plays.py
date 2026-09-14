#!/usr/bin/env python3
"""
Everyone Plays test suite.

    pip install playwright && playwright install chromium
    python3 tests/test_everyone_plays.py

Drives a real headless Chromium against index.html. Most of what can go wrong
in this app goes wrong silently — the numbers drift, nothing throws — so these
tests lean on invariants rather than on the absence of exceptions.
"""

import pathlib
import signal
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = "file://" + str(ROOT / "index.html")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def section(title):
    print(f"\n{title}")


SEED = """([names, size, advanced]) => {
  S.roster = names.map((x, i) => ({
    id: 'p' + i, name: x, number: String(i + 2),
    photo: null, avail: 'available', elig: newElig()
  }));
  S.settings.advanced = advanced;
  S.settings.teamSize = size;
  S.settings.formationIdx = 0;
  S.settings.maxSwitch = null;
  S.settings.freshPositions = true;
  S.game = newGame();
  const spots = [];
  BANDS.forEach(b => { for (let i = 0; i < slotsFor(b); i++) spots.push([b, i]); });
  S.game.seq++;
  spots.forEach(([b, j], i) => S.game.log.push({
    eid: uid(), g: 1, t: Date.now(), gt: 0, sh: 1, period: 1,
    type: 'ON', playerId: 'p' + i, band: b, pos: slotPos(b, j)
  }));
  invalidate(); render();
}"""

ROSTER = ["Ava Chen", "Ben Ortiz", "Cole Park", "Dara Singh", "Eli Brooks",
          "Fia Moreau", "Gus Reyes", "Hana Lee", "Ivy Nowak", "Jack Duarte",
          "Kira Amin", "Liam Vance", "Mia Fox"]

# the app's own invariant checker, reused here
SELF_CHECK = "selfCheck().indexOf('FAIL') === -1"

# replays the log checking nobody ever shares a position, and counts how many
# different positions each outfield player has actually spent time in
POSITION_STATS = """(() => {
  const st = compute(), at = {};
  let clashes = 0;
  S.game.log.forEach((e, i) => {
    if (e.type === 'ON' || e.type === 'MOVE') at[e.playerId] = e.pos;
    else if (e.type === 'OFF') delete at[e.playerId];
    const nx = S.game.log[i + 1];
    if (!nx || nx.g !== e.g) {
      const v = Object.values(at).filter(Boolean);
      if (new Set(v).size !== v.length) clashes++;
    }
  });
  const missing = S.game.log.filter(e => (e.type === 'ON' || e.type === 'MOVE') && !e.pos).length;
  const per = S.roster.filter(p => p.id !== 'p0')
    .map(p => Object.keys(st[p.id].pos).filter(c => st[p.id].pos[c] > 0).length);
  return { clashes, missing, avg: +(per.reduce((a, b) => a + b, 0) / per.length).toFixed(2) };
})()"""


def run_shift(pg, at_seconds):
    """Advance the clock, auto-fill, and send the resulting shift on."""
    pg.evaluate(f"S.game.base = {at_seconds}; invalidate(); autoFillNext();")
    diff = pg.evaluate("""(() => { const e = planDiff(); return {
        on: e.filter(x => x.type === 'ON').length,
        off: e.filter(x => x.type === 'OFF').length,
        mv: e.filter(x => x.type === 'MOVE').length }; })()""")
    pg.evaluate("const e = planDiff(); beginNewShift(); push(e);")
    return diff


def play_full_game(pg, fresh):
    """Two 25-minute periods of 5-minute shifts, 13 players, 7 v 7."""
    pg.evaluate(SEED, [ROSTER, 7, True])
    pg.evaluate("S.settings.periods = 2; S.settings.periodLen = 25; "
                f"S.settings.freshPositions = {str(fresh).lower()};")
    for half in range(2):
        for k in range(1, 6):
            run_shift(pg, k * 300)
        if half == 0:
            pg.evaluate("S.game.base = 1500; endPeriodNow();")


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 390, "height": 844})
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        pg.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
        pg.goto(APP)
        pg.wait_for_timeout(500)

        # ---------------------------------------------------------------
        section("Formations")
        bad = pg.evaluate("""(() => { const out = [];
          for (const k in FORMATIONS) FORMATIONS[k].forEach(f => {
            const total = (f.gk ? 1 : 0) + f.d + f.m + f.f;
            if (total != k) out.push(k + ' ' + formName(f) + ' = ' + total);
          }); return out; })()""")
        check("every formation sums to its team size", not bad, ", ".join(bad))

        # ---------------------------------------------------------------
        section("Time model")
        pg.evaluate(SEED, [ROSTER, 7, True])
        for k in range(1, 4):
            run_shift(pg, k * 300)
        cons = pg.evaluate("""(() => {
          const st = compute();
          let adj = 0; const A = S.game.adj || {};
          for (const k in A) for (const b in A[k]) adj += A[k][b];
          const counted = S.roster.reduce((a, p) => a + st[p.id].total, 0) - adj;
          let expect = 0, cursor = 0, live = {};
          S.game.log.forEach(e => {
            expect += Object.keys(live).length * Math.max(0, e.gt - cursor);
            cursor = e.gt;
            if (e.type === 'ON' || e.type === 'MOVE') live[e.playerId] = 1;
            else if (e.type === 'OFF') delete live[e.playerId];
          });
          expect += Object.keys(live).length * Math.max(0, gameElapsed() - cursor);
          return { counted: Math.round(counted), expect: Math.round(expect) };
        })()""")
        check("minutes add up", abs(cons["counted"] - cons["expect"]) < 2,
              f"{cons['counted']}s counted vs {cons['expect']}s on field")

        dup = pg.evaluate("""(() => S.roster.filter(p => {
          let n = 0; S.game.log.forEach(e => { if (e.playerId === p.id) {
            if (e.type === 'ON') n++; else if (e.type === 'OFF') n--; } });
          return n > 1; }).map(p => p.name))()""")
        check("nobody is on the field twice", not dup, ", ".join(dup))

        counts = pg.evaluate("""(() => { const st = compute(); const c = {};
          BANDS.forEach(b => c[b] = S.roster.filter(p => st[p.id].onBand === b).length);
          return c; })()""")
        want = pg.evaluate("(() => { const c = {}; BANDS.forEach(b => c[b] = slotsFor(b)); return c; })()")
        check("field matches the formation", counts == want, f"{counts} vs {want}")
        check("self-check passes", pg.evaluate(SELF_CHECK))

        # ---------------------------------------------------------------
        section("Rotation quality")
        pg.evaluate(SEED, [ROSTER[:8], 7, False])   # thin bench, the hard case
        pg.evaluate("S.settings.maxSwitch = 2")
        churn = [run_shift(pg, k * 300)["mv"] for k in range(1, 6)]
        check("position switches stay under a cap when one is set", max(churn) <= 2,
              f"per shift: {churn}, cap 2")

        keeper_changes = pg.evaluate("""(() => {
          let n = 0; S.game.log.forEach(e => {
            if (e.band === 'GK' && (e.type === 'ON' || e.type === 'MOVE')) n++; });
          return n - 1; })()""")
        check("keeper is not rotated automatically", keeper_changes == 0,
              f"{keeper_changes} keeper changes")

        pg.evaluate(SEED, [ROSTER[:8], 7, False])   # SEED resets to no limit
        unlimited = [run_shift(pg, k * 300)["mv"] for k in range(1, 6)]
        check("with no limit, auto-fill still settles", pg.evaluate(SELF_CHECK),
              f"per shift: {unlimited}")

        # full game, two periods, default settings
        play_full_game(pg, True)
        spread = pg.evaluate("""(() => { const st = compute();
          const out = S.roster.filter(p => p.id !== 'p0').map(p => st[p.id].total / 60);
          const both = S.roster.filter(p => p.id !== 'p0')
            .filter(p => st[p.id].n.DEF > 0 && st[p.id].n.FWD > 0).length;
          return { lo: +Math.min(...out).toFixed(1), hi: +Math.max(...out).toFixed(1),
                   both, n: out.length }; })()""")
        check("minutes come out even over a full game",
              spread["hi"] - spread["lo"] <= 1.0,
              f"{spread['lo']}–{spread['hi']} min across {spread['n']} outfield players")
        check("everyone plays both ends", spread["both"] == spread["n"],
              f"{spread['both']}/{spread['n']}")

        # ---------------------------------------------------------------
        section("Periods")
        pg.evaluate(SEED, [ROSTER, 7, False])
        brk = pg.evaluate("""(() => {
          S.settings.periods = 2; S.settings.periodLen = 25; activeTab = 'field'; render();
          S.game.running = true; S.game.startedAt = Date.now() - 1000; S.game.base = 1500;
          tick();
          const at = { period: S.game.period, over: S.game.periodOver, onBreak: S.game.onBreak, tab: activeTab,
                       card: document.querySelector('#v-field .card b') && document.querySelector('#v-field .card b').textContent,
                       label: document.getElementById('tb-period').textContent };
          startClock();
          const after = { running: S.game.running, onBreak: S.game.onBreak, period: S.game.period };
          stopClock();
          return { at, after }; })()""")
        check("a period ending moves straight to the next one",
              brk["at"]["period"] == 2 and not brk["at"]["over"] and brk["at"]["onBreak"], str(brk["at"]))
        check("the break says so on the Field tab without switching tabs",
              brk["at"]["tab"] == "field" and "Period 1 is over" in (brk["at"]["card"] or "")
              and brk["at"]["label"] == "Period 2 ready", str(brk["at"]))
        check("START begins the next period", brk["after"]["running"] and not brk["after"]["onBreak"]
              and brk["after"]["period"] == 2, str(brk["after"]))

        last = pg.evaluate("""(() => {
          S.game.running = true; S.game.startedAt = Date.now() - 1000; S.game.base = 1500;
          tick();
          const over = S.game.periodOver, card = !!document.getElementById('f-newgame');
          startClock();
          const asked = document.getElementById('modalwrap').classList.contains('show')
            && document.getElementById('modaltitle').textContent === 'Game over';
          closeModal();
          return { over, card, asked, running: S.game.running }; })()""")
        check("the last period ends the game with a New game button", last["over"] and last["card"], str(last))
        check("START after the game offers a new game instead of running the clock",
              last["asked"] and not last["running"], str(last))

        legacy_break = pg.evaluate("""(() => {
          S.game = newGame(); S.game.period = 1; S.game.base = 1500; S.game.periodOver = true;
          startClock(); const r = { period: S.game.period, running: S.game.running }; stopClock();
          S.game = newGame(); invalidate(); render(); return r; })()""")
        check("a game saved mid-break by an older version starts its next period",
              legacy_break["period"] == 2 and legacy_break["running"], str(legacy_break))

        # ---------------------------------------------------------------
        section("Undo and shift numbers")
        pg.evaluate(SEED, [ROSTER, 7, False])
        und = pg.evaluate("""(() => {
          const st = compute(), lay = fieldLayout(st), bench = S.roster.find(p => !st[p.id].onBand), out = lay.slots.DEF[0];
          doPair(out, bench.id); render(); undoLast();
          return { msg: document.querySelector('.toast').textContent, back: compute()[out].onBand === 'DEF' }; })()""")
        check("undo says what it undid", "on for" in und["msg"] and und["back"], str(und))

        pe = pg.evaluate("""(() => {
          S.settings.periods = 2; S.game.running = true; S.game.startedAt = Date.now() - 1000; S.game.base = 1500; tick();
          const moved = S.game.period; undoLast();
          const r = { moved, period: S.game.period, base: Math.round(S.game.base), onBreak: S.game.onBreak,
                      msg: document.querySelector('.toast').textContent, ok: selfCheck().indexOf('FAIL') === -1 };
          S.game.running = true; S.game.startedAt = Date.now() - 1000; tick();
          startClock(); stopClock();
          const n = S.game.log.length; undoLast(); r.refused = S.game.log.length === n && S.game.period === 2;
          return r; })()""")
        check("undoing the end of a period puts the game back in that period",
              pe["moved"] == 2 and pe["period"] == 1 and pe["base"] == 1500 and not pe["onBreak"] and pe["ok"]
              and "end of period 1" in pe["msg"], str(pe))
        check("but not once the next period has started", pe["refused"], str(pe))

        pg.evaluate(SEED, [ROSTER, 7, False])
        num = pg.evaluate("""(() => {
          S.settings.periods = 2; S.game.running = true; S.game.startedAt = Date.now() - 1000; S.game.base = 1500; tick();
          S.game.next = null; autoFillNext(); activeTab = 'next'; render();
          const label = document.querySelector('#v-next .card b').textContent;
          const e = planDiff(); beginNewShift(); push(e);
          const sent = S.game.log[S.game.log.length - 1].sh; activeTab = 'field'; render();
          return { label, sent }; })()""")
        check("the Next tab's shift number matches the shift that gets sent",
              num["label"] == f"Shift {num['sent']}", str(num))

        # ---------------------------------------------------------------
        section("Positions")
        bad = pg.evaluate("""(() => { const out = [], was = [S.settings.teamSize, S.settings.formationIdx];
          for (const k in FORMATIONS) FORMATIONS[k].forEach((f, idx) => {
            S.settings.teamSize = +k; S.settings.formationIdx = idx;
            const codes = BANDS.flatMap(b => posCodes(b, slotsFor(b)));
            if (codes.length != k || new Set(codes).size != codes.length || codes.some(c => !POSNAME[c]))
              out.push(k + ' ' + formName(f) + ': ' + codes.join(' '));
          });
          [S.settings.teamSize, S.settings.formationIdx] = was; return out; })()""")
        check("every formation has distinct, named positions", not bad, "; ".join(bad))

        play_full_game(pg, True)
        fresh = pg.evaluate(POSITION_STATS)
        check("every substitution records a specific position", fresh["missing"] == 0,
              f"{fresh['missing']} without one")
        check("no two players ever share a position", fresh["clashes"] == 0,
              f"{fresh['clashes']} clashes")
        play_full_game(pg, False)
        plain = pg.evaluate(POSITION_STATS)
        check("subs rotate into positions they haven't played", fresh["avg"] > plain["avg"],
              f"{fresh['avg']} positions per player with it on, {plain['avg']} with it off")

        pg.evaluate(SEED, [ROSTER, 7, True])
        placed = pg.evaluate("""(() => {
          const st = compute(), lay = fieldLayout(st);
          const bench = S.roster.find(p => !st[p.id].onBand);
          push([{type: 'OFF', playerId: lay.slots.DEF[1]}]);
          doPlace(bench.id, 'DEF', 1);
          const into = compute()[bench.id].onPos;
          const ld = fieldLayout().slots.DEF[0], rd = fieldLayout().slots.DEF[2];
          doPair(ld, rd);
          const s2 = compute();
          return { into, ld: s2[ld].onPos, rd: s2[rd].onPos }; })()""")
        check("placing a player puts them in that exact position", placed["into"] == "SW",
              str(placed["into"]))
        check("swapping two defenders swaps their positions",
              placed["ld"] == "RD" and placed["rd"] == "LD", f"{placed['ld']}, {placed['rd']}")
        check("self-check passes after position moves", pg.evaluate(SELF_CHECK))

        hold = pg.evaluate("""(() => {
          const st = compute(); S.game.next = null; const n = ensureNext();
          n.FWD[2] = S.roster.find(p => !st[p.id].onBand).id;
          return planDiff().map(e => e.type + ':' + (e.pos || '')).sort(); })()""")
        check("planning one position leaves everyone else where they stand",
              hold == ["OFF:", "ON:RW"], str(hold))

        pg.evaluate(SEED, [ROSTER, 7, True])
        legacy = pg.evaluate("""(() => {
          S.game.log.forEach(e => { delete e.pos; });
          invalidate(); render();
          const placed = BANDS.reduce((a, b) => a + fieldLayout().slots[b].filter(Boolean).length, 0);
          S.game.base = 300; invalidate(); autoFillNext();
          const e = planDiff(); beginNewShift(); push(e); render();
          return { placed, ok: selfCheck().indexOf('FAIL') === -1 }; })()""")
        check("games logged before positions existed still work",
              legacy["placed"] == 7 and legacy["ok"], f"{legacy['placed']} placed")

        # ---------------------------------------------------------------
        section("Eligibility and availability")
        pg.evaluate(SEED, [ROSTER, 7, True])
        pg.evaluate("""() => { ['p8','p9','p10','p11','p12'].forEach(id => {
          const p = byId(id); if (p) p.elig = {GK:false, DEF:false, MID:false, FWD:true}; });
          invalidate(); S.game.next = null; autoFillNext(); }""")
        ok = pg.evaluate("""(() => BANDS.every(b => S.game.next[b].every(id =>
          !id || eligible(byId(id), b))))()""")
        check("auto-fill respects position eligibility", ok)

        pg.evaluate(SEED, [ROSTER, 7, True])
        pg.evaluate("""() => { byId('p9').avail = 'out'; byId('p10').avail = 'late';
          invalidate(); S.game.next = null; autoFillNext(); }""")
        ok = pg.evaluate("""(() => { const planned = Object.values(S.game.next).flat();
          return !planned.includes('p9') && !planned.includes('p10'); })()""")
        check("unavailable players are left out", ok)

        # ---------------------------------------------------------------
        section("Shifts and history")
        pg.evaluate(SEED, [ROSTER, 7, True])
        for k in range(1, 4):
            run_shift(pg, k * 300)
        pg.evaluate("beginNewShift(); beginNewShift(); beginNewShift(); render();")
        shifts = pg.evaluate("[...new Set(S.game.log.map(e => e.sh))].sort((a,b)=>a-b)")
        check("shift numbers have no gaps", shifts == list(range(1, len(shifts) + 1)), str(shifts))

        pg.click('#tabs button[data-tab="log"]')
        pg.wait_for_timeout(300)
        cards = pg.evaluate("document.querySelectorAll('#v-log .hgroup').length")
        bodies = pg.evaluate("document.querySelectorAll('#v-log .hbody').length")
        check("one history card per shift", cards == len(shifts), f"{cards} cards, {len(shifts)} shifts")
        check("only the current shift starts open", bodies == 1, f"{bodies} open")

        pg.evaluate("""() => { const st = compute();
          push([{type:'GOAL', playerId: S.roster.find(p => st[p.id].onBand === 'FWD').id}]);
          push([], 'Ref warning'); render(); }""")
        pg.wait_for_timeout(250)
        dels = pg.evaluate("document.querySelectorAll('#v-log [data-del-ev]').length")
        check("stat events are deletable", dels >= 2, f"{dels} delete buttons")
        structural = pg.evaluate("""(() => [...document.querySelectorAll('#v-log [data-del-ev]')]
          .map(b => S.game.log.find(e => e.eid === b.dataset.delEv))
          .filter(e => e && ['ON','OFF','MOVE'].includes(e.type)).length)()""")
        check("substitutions are NOT deletable", structural == 0, f"{structural} exposed")

        # ---------------------------------------------------------------
        section("Event reassignment")
        before = pg.evaluate("(() => { const e = S.game.log.find(x => x.type === 'GOAL'); return {p: e.playerId, gt: e.gt}; })()")
        pg.evaluate("""() => { const e = S.game.log.find(x => x.type === 'GOAL');
          const other = S.roster.find(p => p.id !== e.playerId);
          e.playerId = other.id; invalidate(); }""")
        after = pg.evaluate("(() => { const e = S.game.log.find(x => x.type === 'GOAL'); return {p: e.playerId, gt: e.gt}; })()")
        check("reassigning keeps the clock time", after["gt"] == before["gt"])
        check("reassigning changes who gets credit", after["p"] != before["p"])
        check("score is unaffected", pg.evaluate("computeMatchScore().us") == 1)

        # ---------------------------------------------------------------
        section("Lineups and check-in")
        pg.evaluate(SEED, [ROSTER, 7, True])
        pg.evaluate("S.lineups = []; saveLineup('Starting XI');")
        saved = pg.evaluate("S.lineups.length ? Object.values(S.lineups[0].slots).flat().filter(Boolean).length : 0")
        check("a lineup saves the whole field", saved == 7, f"{saved} players")

        pg.evaluate("S.game = newGame(); invalidate(); loadLineup(S.lineups[0].id);")
        check("loading fills the plan, not the field", pg.evaluate("nextCount()") == 7,
              f"{pg.evaluate('nextCount()')} placed")
        check("loading does not touch the field", pg.evaluate("S.game.log.length") == 0)

        pg.evaluate("""() => { S.game.next = null; byId('p2').avail = 'out';
          invalidate(); loadLineup(S.lineups[0].id); }""")
        placed = pg.evaluate("nextCount()")
        absent = pg.evaluate("!Object.values(S.game.next).flat().includes('p2')")
        msg = pg.evaluate("document.querySelector('.toast').textContent")
        check("an absent player's spot is filled, not left open",
              placed == 7 and absent and "in at" in msg and "isn't available" in msg, f"{placed} placed; {msg}")

        more = pg.evaluate("""(() => {
          const full = S.roster.slice(), L = S.lineups[0], r = {};
          byId('p2').avail = 'available';
          S.roster = full.filter(p => p.id !== 'p4'); invalidate(); S.game.next = null; loadLineup(L.id);
          r.removed = nextCount();
          S.roster = full; invalidate();
          const gapSlots = {}; Object.keys(L.slots).forEach(b => { gapSlots[b] = L.slots[b].map((x, i) => (b === 'DEF' && i === 1) ? null : x); });
          S.lineups.unshift({ id: 'gap', name: 'gap', at: Date.now(), size: L.size, form: L.form, slots: gapSlots });
          S.game.next = null; loadLineup('gap'); r.gap = nextCount(); S.lineups.shift();
          S.roster = full.slice(0, 7); byId('p0').avail = 'out'; invalidate(); S.game.next = null; loadLineup(L.id);
          r.noOne = { count: nextCount(), msg: document.querySelector('.toast').textContent };
          byId('p0').avail = 'available'; S.roster = full; invalidate(); S.game.next = null;
          return r; })()""")
        check("a player removed from the roster is replaced on load", more["removed"] == 7, str(more))
        check("a lineup saved with a gap loads full", more["gap"] == 7, str(more))
        check("when nobody is left to fill a spot, it says so",
              more["noOne"]["count"] == 6 and "still open" in more["noOne"]["msg"], str(more["noOne"]))

        nextsave = pg.evaluate("""(() => {
          S.game = newGame(); invalidate();
          const spots = []; BANDS.forEach(b => { for (let i = 0; i < slotsFor(b); i++) spots.push([b, i]); });
          S.game.seq++;
          spots.forEach(([b, j], i) => S.game.log.push({ eid: uid(), g: 1, t: Date.now(), gt: 0, sh: 1, period: 1,
            type: 'ON', playerId: 'p' + i, band: b, pos: slotPos(b, j) }));
          invalidate(); S.game.base = 300; S.game.next = null; ensureNext(); planInto('p9', 'FWD', 0);
          saveLineup('from next', true);
          const slots = Object.values(S.lineups[0].slots).flat();
          const r = { planned: slots.includes('p9'), replaced: slots.includes('p4'), count: slots.filter(Boolean).length };
          S.lineups.shift(); S.game = newGame(); invalidate(); return r; })()""")
        check("Save on the Next tab saves the plan, not the field",
              nextsave["planned"] and not nextsave["replaced"] and nextsave["count"] == 7, str(nextsave))

        pg.evaluate("""() => { S.roster.forEach(p => p.avail = 'available');
          openCheckIn(); }""")
        pg.wait_for_timeout(250)
        rows = pg.evaluate("document.querySelectorAll('#modalbody [data-ci]').length")
        check("check-in lists the whole roster", rows == len(ROSTER), f"{rows} rows")
        pg.evaluate("document.querySelectorAll('#modalbody [data-ci]')[2].click()")
        pg.wait_for_timeout(200)
        pg.click("#modalok")
        pg.wait_for_timeout(300)
        out = pg.evaluate("S.roster.filter(p => p.avail !== 'available').length")
        check("check-in marks absentees", out == 1, f"{out} out")

        # ---------------------------------------------------------------
        section("Games and season")
        pg.evaluate(SEED, [ROSTER, 7, True])
        dated = pg.evaluate("""(() => { byId('p12').avail = 'out';
          startClock(); stopClock(); const d = S.game.date, present = S.game.present.length;
          byId('p12').avail = 'available'; return { d: !!d, present }; })()""")
        check("a game's date and attendance are set at kickoff", dated["d"] and dated["present"] == 12, str(dated))

        pg.evaluate("S.archive = []")
        for i in range(5):
            pg.evaluate(SEED, [ROSTER, 7, True])
            pg.evaluate(f"S.game.date = Date.now() - {5 - i} * 7 * 864e5; S.game.opponent = 'Rivals {i}'; "
                        "S.game.present = S.roster.map(p => p.id);")
            if i == 2:
                pg.evaluate("S.game.present = S.roster.filter(p => p.id !== 'p12').map(p => p.id); byId('p12').avail = 'out';")
            for k in range(1, 6):
                run_shift(pg, k * 300)
            if i == 1:
                pg.evaluate("push([{ type: 'GOAL', playerId: 'p4' }]);")
            pg.evaluate("S.game.base = 1500; invalidate(); archiveGame();")
        pg.evaluate("S.game = newGame(); S.roster.forEach(p => p.avail = 'available'); invalidate(); render();")

        season = pg.evaluate("""(() => { const { by, team } = aggregate(seasonGames());
          const sumGames = S.archive.reduce((a, g) => a + g.players.reduce((x, p) => x + p.total, 0), 0);
          const sumSeason = Object.values(by).reduce((a, r) => a + r.total, 0);
          return { games: team.games, logs: S.archive.filter(g => g.log).length, sumGames, sumSeason,
                   p12: { gp: by.p12.gp, missed: by.p12.missed }, goals: by.p4.goals }; })()""")
        check("every finished game is filed", season["games"] == 5, f"{season['games']} games")
        check("full logs are kept for the 3 most recent games only", season["logs"] == 3, f"{season['logs']} logs")
        check("season minutes add up to the games", abs(season["sumGames"] - season["sumSeason"]) < 1,
              f"{season['sumSeason']}s vs {season['sumGames']}s")
        check("a missed game counts as missed, not as zero minutes", season["p12"] == {"gp": 4, "missed": 1}, str(season["p12"]))
        check("stats count from games whose log was trimmed", season["goals"] == 1, f"{season['goals']} goals")

        opened = pg.evaluate("""(() => { try { S.settings.advanced = true; openPlayer = 'p4'; activeTab = 'roster'; render();
          return !!document.querySelector('#v-roster .pedit'); } catch (e) { return String(e); } })()""")
        check("a player opens on Roster with more than 3 past games (used to crash)", opened is True, str(opened))
        pg.evaluate("openPlayer = null; render();")

        renamed = pg.evaluate("""(() => { byId('p4').name = 'Eli Renamed'; const r = aggregate(seasonGames()).by.p4;
          byId('p4').name = 'Eli Brooks'; return r ? r.gp : 0; })()""")
        check("renaming a player keeps their history", renamed == 5, f"{renamed} games")

        pg.click('#tabs button[data-tab="log"]')
        pg.wait_for_timeout(250)
        hist = pg.evaluate("""(() => ({ rows: document.querySelectorAll('#v-log [data-game]').length,
          months: document.querySelectorAll('#v-log .monthlab').length,
          newest: document.querySelector('#v-log [data-game] .s').textContent }))()""")
        check("History lists past games by date, newest first",
              hist["rows"] == 5 and hist["months"] >= 1 and "Rivals 4" in hist["newest"], str(hist))
        pg.click("#v-log [data-game]")
        pg.wait_for_timeout(200)
        detail = pg.evaluate("""(() => ({ players: document.querySelectorAll('#modalbody > .stage').length,
          shifts: document.querySelectorAll('#modalbody .hgroup').length }))()""")
        check("a past game opens with its players and shifts", detail["players"] >= 13 and detail["shifts"] >= 5, str(detail))
        pg.click("#g-del")
        pg.wait_for_timeout(150)
        pg.click("#modalok")
        pg.wait_for_timeout(200)
        check("a past game can be deleted", pg.evaluate("S.archive.length") == 4)

        old = pg.evaluate("""(() => { const g = upgradeGame({ at: Date.now() - 864e5, periods: 2,
            score: { us: 2, them: 1, usShots: 5, usSOG: 3, themShots: 2, themSOG: 1 },
            totals: [{ name: 'Ava Chen', number: '2', GK: 0, DEF: 600, MID: 0, FWD: 900, total: 1500, pos: 'LD 10.0, ST 15.0' },
                     { name: 'Nobody Here', number: '99', GK: 0, DEF: 0, MID: 0, FWD: 0, total: 0 }] }, S.roster);
          return { id: g.players[0].id, ld: g.players[0].pos.LD, unmatched: g.players[1].id, result: hasResult(g) }; })()""")
        check("games filed before this update are converted",
              old["id"] == "p0" and old["ld"] == 600 and old["unmatched"] is None and old["result"], str(old))

        pg.click('#tabs button[data-tab="times"]')
        pg.wait_for_timeout(150)
        pg.click('#v-times [data-tv="season"]')
        pg.wait_for_timeout(200)
        srows = pg.evaluate("document.querySelectorAll('#v-times [data-season]').length")
        check("the Season view lists every player", srows == 13, f"{srows} rows")
        pg.set_viewport_size({"width": 360, "height": 800})
        pg.wait_for_timeout(120)
        check("the Season view fits at 360 px",
              not pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"))
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.click('#v-times [data-tv="game"]')

        def plans_p6(on):
            pg.evaluate(SEED, [ROSTER[:10], 7, False])
            return pg.evaluate("""(on) => {
              const saved = S.archive; S.settings.seasonBalance = on;
              S.archive = [{ id: 'g1', v: 2, date: Date.now() - 864e5, players: S.roster.map(p => ({ id: p.id, name: p.name,
                number: p.number, attended: true, total: p.id === 'p6' ? 0 : 900, GK: 0, DEF: 0, MID: 0, FWD: 0, pos: {} })) }];
              S.archive[0].playerSeconds = S.archive[0].players.reduce((a, p) => a + p.total, 0);
              S.game.base = 300; invalidate(); S.game.next = null; autoFillNext();
              const planned = Object.values(S.game.next).flat().includes('p6');
              S.settings.seasonBalance = false; S.archive = saved; S.game.next = null;
              return planned; }""", on)
        with_on, with_off = plans_p6(True), plans_p6(False)
        check("season balance keeps on a kid who is behind over past games", with_on and not with_off,
              f"on: {with_on}, off: {with_off}")

        pg.evaluate(SEED, [ROSTER, 7, True])
        gk = pg.evaluate("""(() => {
          const saved = S.archive; S.settings.goalieRotation = true;
          S.archive = [{ id: 'g1', v: 2, date: Date.now() - 864e5, players: S.roster.map(p => ({ id: p.id, name: p.name,
            number: p.number, attended: true, total: 600, GK: p.id === 'p1' ? 600 : 0, DEF: 0, MID: 0, FWD: 0, pos: {},
            gkPeriods: p.id === 'p1' ? 2 : 0 })) }];
          activeTab = 'next'; render();
          const order = goalieOrder().map(x => x.p.id), card = !!document.getElementById('n-gk');
          if (card) document.getElementById('n-gk').click();
          const planned = ensureNext().GK[0];
          S.settings.goalieRotation = false; S.archive = saved; S.game.next = null; activeTab = 'field'; render();
          return { first: order[0], p1last: order.indexOf('p1') === order.length - 1,
                   keeperListed: order.includes('p0'), card, planned }; })()""")
        check("goalie suggestion skips the keeper and favors who hasn't been in goal",
              gk["first"] != "p0" and not gk["keeperListed"] and gk["p1last"], str(gk))
        check("the Next tab offers to put them in goal", gk["card"] and gk["planned"] == gk["first"], str(gk))

        pg.evaluate(SEED, [ROSTER, 7, False])
        nag = pg.evaluate("""(() => {
          S.game.running = false; S.game.periodOver = false; S.game.pausedAt = Date.now() - 130000; S.game.nagged = false;
          tick(); const on = document.getElementById('topbar').classList.contains('paused'), nagged = S.game.nagged;
          S.settings.pauseReminder = false; tick(); const off = document.getElementById('topbar').classList.contains('paused');
          S.settings.pauseReminder = true; S.game.pausedAt = null; tick();
          return { on, nagged, off }; })()""")
        check("a clock left paused mid-game gets a reminder", nag["on"] and nag["nagged"], str(nag))
        check("the reminder can be turned off", not nag["off"])
        pg.evaluate("S.archive = []; render();")

        # ---------------------------------------------------------------
        section("Support note")
        pg.evaluate(SEED, [ROSTER, 7, False])
        sn = pg.evaluate("""(() => {
          const dummy = () => ({ id: uid(), v: 2, date: Date.now() - 864e5, players: [], playerSeconds: 0 });
          S.settings.supportNotes = true; S.archive = [dummy(), dummy()];
          activeTab = 'field'; render(); promptNewGame(); document.getElementById('modalok').click();
          activeTab = 'field'; render();
          const r = { filed: S.archive.length, field: !!document.querySelector('#v-field [data-sn="link"]') };
          activeTab = 'log'; render(); r.history = !!document.querySelector('#v-log [data-sn="link"]');
          /* the buttons on History have to work, not the hidden copy left on Field */
          document.querySelector('#v-log [data-sn="close"]').click();
          r.closed = !document.querySelector('#v-log [data-sn]');
          activeTab = 'help'; render(); r.help = !!document.querySelector('#v-help a.tiplink[href="https://ko-fi.com/hudelson"]');
          activeTab = 'field'; render(); r.fieldGone = !document.querySelector('#v-field [data-sn]');
          return r; })()""")
        check("a support note appears after the 3rd filed game, on Field and History",
              sn["filed"] == 3 and sn["field"] and sn["history"], str(sn))
        check("Not now dismisses it, from History too", sn["closed"] and sn["fieldGone"], str(sn))
        check("Help has a Ko-fi link", sn["help"], str(sn))
        sn2 = pg.evaluate("""(() => {
          const file = () => { push([{ type: 'ON', playerId: 'p0', band: 'GK', pos: 'GK' }]); promptNewGame(); document.getElementById('modalok').click(); };
          file(); const fourth = !!S.game.supportNote;
          const dummy = () => ({ id: uid(), v: 2, date: 0, players: [], playerSeconds: 0 });
          S.archive = S.archive.concat([dummy(), dummy(), dummy()]);
          S.settings.supportNotes = false; file(); const offAtEighth = !!S.game.supportNote;
          S.settings.supportNotes = true; S.game.supportNote = true; activeTab = 'field'; render();
          const before = !!document.querySelector('#v-field [data-sn="link"]'); startClock();
          const after = !!document.querySelector('#v-field [data-sn="link"]'); stopClock();
          activeTab = 'setup'; render(); const toggle = !!document.querySelector('[data-tog="s-support"]');
          S.archive = []; S.game = newGame(); activeTab = 'field'; render();
          return { fourth, offAtEighth, before, after, toggle }; })()""")
        check("no note on the 4th game, and none when turned off",
              not sn2["fourth"] and not sn2["offAtEighth"], str(sn2))
        check("the note disappears once the game starts", sn2["before"] and not sn2["after"], str(sn2))
        check("Setup has a switch for the note", sn2["toggle"], str(sn2))

        # ---------------------------------------------------------------
        section("Haptics")
        pg.evaluate(SEED, [ROSTER, 7, False])
        pg.click('#tabs button[data-tab="field"]')
        pg.wait_for_timeout(150)
        buzz = pg.evaluate("""(() => {
          const calls = [];
          Object.defineProperty(navigator, 'vibrate', { value: p => { calls.push(p); return true; }, configurable: true });
          const hold = () => { beginDrag(document.querySelector('#v-field [data-chip]'), 10, 10); dragEnd(); };
          S.settings.vibrate = false; S.settings.dragBuzz = true; hold();
          const on = calls.length;
          S.settings.vibrate = true; S.settings.dragBuzz = false; hold();
          const off = calls.length - on;
          S.settings.vibrate = false; S.settings.dragBuzz = true;
          return { on, off }; })()""")
        check("press-and-hold buzz works with Vibrate off", buzz["on"] == 1, f"{buzz['on']} buzz")
        check("press-and-hold buzz turns off on its own", buzz["off"] == 0, f"{buzz['off']} buzz")
        pg.wait_for_timeout(300)
        novib = pg.evaluate("""(() => { const had = navigator.vibrate;
          Object.defineProperty(navigator, 'vibrate', { value: undefined, configurable: true });
          activeTab = 'setup'; render();
          const hidden = !document.querySelector('[data-tog="s-vib"]') && !document.querySelector('[data-tog="s-dragbuzz"]');
          Object.defineProperty(navigator, 'vibrate', { value: had, configurable: true });
          render(); const shown = !!document.querySelector('[data-tog="s-vib"]');
          activeTab = 'field'; render(); return { hidden, shown }; })()""")
        check("vibration settings are hidden where the phone can't vibrate (iPhone)",
              novib["hidden"] and novib["shown"], str(novib))

        # ---------------------------------------------------------------
        section("Layout")
        pg.evaluate("S.roster.forEach(p => p.avail = 'available'); invalidate();")
        overflow = []
        for width in (360, 430):
            pg.set_viewport_size({"width": width, "height": 800})
            for advanced in (False, True):
                pg.evaluate(f"S.settings.advanced = {str(advanced).lower()}; render();")
                for tab in ("field", "next", "clock", "times", "log", "roster", "help", "setup"):
                    pg.evaluate(f"activeTab = '{tab}'; render();")
                    pg.wait_for_timeout(120)
                    if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                        overflow.append(f"{tab}@{width}")
                    if pg.evaluate("(() => { const n = document.getElementById('tabs'); return n.scrollWidth > n.clientWidth; })()"):
                        overflow.append(f"tabbar@{width}")
        check("no horizontal overflow on any tab", not overflow, ", ".join(sorted(set(overflow))))
        tip = pg.evaluate("""(() => { const a = document.querySelector('#v-setup a.tiplink');
          return a ? { href: a.getAttribute('href'), rel: a.rel } : null; })()""")
        check("the Ko-fi link is on Setup and opens safely",
              tip is not None and tip["href"] == "https://ko-fi.com/hudelson" and "noopener" in tip["rel"], str(tip))
        pg.set_viewport_size({"width": 390, "height": 844})

        # a real Android phone is about 412 px wide — this is the width the overlap was seen at
        pg.set_viewport_size({"width": 412, "height": 780})
        fit = pg.evaluate("""(() => {
          activeTab = 'field'; selected = null; render();
          const r0 = document.querySelector('#v-field .band .chip').getBoundingClientRect();
          selected = { t: 'p', id: fieldLayout().slots.DEF[1], kind: 'field' }; render();
          document.querySelector('main').scrollTop = 0;
          const covered = [...document.querySelectorAll('#v-field .selbar button')].filter(b => {
            const r = b.getBoundingClientRect();
            if (r.bottom <= 0 || r.top >= innerHeight) return false;
            const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return !el || !el.closest('.selbar'); }).map(b => b.textContent);
          selected = null; render();
          return { h: Math.round(r0.height), w: Math.round(r0.width), covered }; })()""")
        check("player cards stay compact on a 412 px phone", fit["h"] <= 115 and fit["w"] <= 92, str(fit))
        check("nothing on the field covers the selected-player buttons", not fit["covered"], str(fit))
        pg.set_viewport_size({"width": 390, "height": 844})

        nav = pg.evaluate("""(() => { activeTab = lastTab = 'field'; render();
          const tabs = [...document.querySelectorAll('#tabs button')].map(b => b.dataset.tab);
          document.getElementById('tb-clockbtn').click();
          const clock = activeTab === 'clock' && document.getElementById('v-clock').classList.contains('active');
          document.getElementById('c-back').click();
          const back = activeTab;
          document.querySelector('#tabs button[data-tab="setup"]').click();
          document.getElementById('s-help-top').click();
          const help = activeTab === 'help';
          document.getElementById('h-back').click();
          return { tabs, clock, back, help, helpBack: activeTab }; })()""")
        check("six tabs, with the clock screen and Help off the tab bar",
              nav["tabs"] == ["field", "next", "times", "log", "roster", "setup"], str(nav["tabs"]))
        check("tapping the clock opens game controls, and Back returns", nav["clock"] and nav["back"] == "field", str(nav))
        check("Help opens from Setup and Back returns there", nav["help"] and nav["helpBack"] == "setup", str(nav))
        order = pg.evaluate("""(() => { activeTab = 'field'; render();
          const bench = [...document.querySelectorAll('#v-field h3')].find(h => h.textContent === 'Bench');
          const reset = document.getElementById('reset-shift');
          return !!(bench && reset && (bench.compareDocumentPosition(reset) & Node.DOCUMENT_POSITION_FOLLOWING)); })()""")
        check("the bench comes right after the field, before the shift buttons", order)
        head = pg.evaluate("""(() => { activeTab = 'next'; render();
          const row = document.getElementById('n-auto').parentElement; const r = row.contains(document.getElementById('n-send'));
          activeTab = 'field'; render(); return r; })()""")
        check("Auto-fill and Send them on sit together at the top of Next", head)

        # ---------------------------------------------------------------
        section("Persistence")
        pg.evaluate("Store.save(S)")
        pg.wait_for_timeout(300)
        before_n = pg.evaluate("S.roster.length")
        pg.reload()
        pg.wait_for_timeout(700)
        check("roster survives a reload", pg.evaluate("S.roster.length") == before_n)
        check("a running clock is paused on load", pg.evaluate("S.game.running") is False)
        check("self-check passes after reload", pg.evaluate(SELF_CHECK))

        # ---------------------------------------------------------------
        section("Teams")
        pg.evaluate("""() => { localStorage.clear();
          localStorage.setItem(KEY, JSON.stringify({ roster: [{ id: 'x1', name: 'Old Timer', number: '9',
            photo: null, avail: 'available' }], settings: { teamSize: 9, sound: true },
            game: newGame(), archive: [], lineups: [] })); }""")
        pg.reload()
        pg.wait_for_timeout(700)
        mig = pg.evaluate("""(() => ({ teams: TEAMS.list.length, name: activeTeam().name,
          player: S.roster.length ? S.roster[0].name : null, size: S.settings.teamSize,
          sound: S.settings.sound }))()""")
        check("a save from before teams becomes the first team",
              mig["teams"] == 1 and mig["name"] == "My team" and mig["player"] == "Old Timer"
              and mig["size"] == 9, str(mig))
        check("its sound setting carries over", mig["sound"] is True)

        sep = pg.evaluate("""async () => {
          const first = TEAMS.active;
          await addTeam('U10 Blue');
          const fresh = S.roster.length;
          S.roster.push({ id: 'b1', name: 'Bea', number: '4', photo: null, avail: 'available', elig: newElig() });
          S.settings.teamSize = 5; S.settings.sound = false;
          await Store.save(S);
          const second = TEAMS.active;
          await switchTeam(first);
          const a = { name: S.roster[0].name, size: S.settings.teamSize, sound: S.settings.sound };
          await switchTeam(second);
          const b = { name: S.roster[0].name, size: S.settings.teamSize };
          return { fresh, a, b }; }""")
        check("a new team starts empty", sep["fresh"] == 0)
        check("each team keeps its own roster and settings",
              sep["a"]["name"] == "Old Timer" and sep["a"]["size"] == 9
              and sep["b"]["name"] == "Bea" and sep["b"]["size"] == 5, f"{sep['a']} / {sep['b']}")
        check("sound is shared by every team", sep["a"]["sound"] is False)

        pg.evaluate("""() => { S.game.running = true; S.game.startedAt = Date.now() - 60000; S.game.base = 0;
          switchTeam(TEAMS.list[0].id); }""")
        pg.wait_for_timeout(200)
        asked = pg.evaluate("document.getElementById('modalwrap').classList.contains('show')")
        pg.click("#modalok")
        pg.wait_for_timeout(400)
        paused = pg.evaluate("""async () => { const now = activeTeam().name;
          await switchTeam(TEAMS.list[1].id);
          return { now, running: S.game.running, base: Math.round(S.game.base) }; }""")
        check("switching mid-game asks first", asked)
        check("switching pauses the clock and keeps its time",
              paused["now"] == "My team" and paused["running"] is False and paused["base"] >= 59, str(paused))

        pg.reload()
        pg.wait_for_timeout(700)
        kept = pg.evaluate("({ teams: TEAMS.list.length, name: activeTeam().name, player: S.roster[0] && S.roster[0].name })")
        check("teams survive a reload",
              kept["teams"] == 2 and kept["name"] == "U10 Blue" and kept["player"] == "Bea", str(kept))

        pg.click('#tabs button[data-tab="roster"]')
        pg.wait_for_timeout(150)
        pg.click("#r-team")
        pg.wait_for_timeout(150)
        listed = pg.evaluate("document.querySelectorAll('#modalbody [data-team]').length")
        check("the team list shows every team", listed == 2, f"{listed} listed")
        pg.click("#modalcancel")
        pg.set_viewport_size({"width": 360, "height": 800})
        wide = []
        for tab in ("field", "roster", "setup"):
            pg.click(f'#tabs button[data-tab="{tab}"]')
            pg.wait_for_timeout(120)
            if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                wide.append(tab)
        check("team controls fit at 360 px", not wide, ", ".join(wide))
        pg.set_viewport_size({"width": 390, "height": 844})

        rt = pg.evaluate("""async () => {
          const text = await buildBackup();
          await eraseAllTeams();
          const wiped = TEAMS.list.length + ':' + S.roster.length;
          loadBackup(text);
          await new Promise(r => setTimeout(r, 300));
          const names = TEAMS.list.map(t => t.name);
          const active = activeTeam().name, player = S.roster[0] && S.roster[0].name;
          await switchTeam(TEAMS.list[0].id);
          return { wiped, names, active, player, other: S.roster[0] && S.roster[0].name }; }""")
        check("erasing all teams leaves one empty team", rt["wiped"] == "1:0", rt["wiped"])
        check("a backup restores every team",
              rt["names"] == ["My team", "U10 Blue"] and rt["active"] == "U10 Blue"
              and rt["player"] == "Bea" and rt["other"] == "Old Timer", str(rt))

        old = pg.evaluate("""async () => {
          loadBackup(JSON.stringify({ roster: [{ id: 'z1', name: 'Zed', number: '1', photo: null, avail: 'available' }],
            settings: { teamSize: 6 }, game: newGame() }));
          await new Promise(r => setTimeout(r, 300));
          return { teams: TEAMS.list.length, name: activeTeam().name, player: S.roster[0].name,
                   size: S.settings.teamSize }; }""")
        check("a backup from before teams is added, not swapped in",
              old["teams"] == 3 and old["player"] == "Zed" and old["size"] == 6, str(old))

        gone = pg.evaluate("""async () => {
          const t = activeTeam(); await deleteTeam(t.id);
          return { teams: TEAMS.list.length, cleared: localStorage.getItem(t.key) === null,
                   now: activeTeam().name, ok: selfCheck().indexOf('FAIL') === -1 }; }""")
        check("deleting a team removes its data and opens another",
              gone["teams"] == 2 and gone["cleared"] and gone["now"] != "Imported team", str(gone))
        check("self-check passes with several teams", gone["ok"])

        browser.close()

    # -------------------------------------------------------------------
    section("PWA (served over HTTP)")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8099", "--directory", str(ROOT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page(viewport={"width": 390, "height": 844})
            pg.goto("http://localhost:8099/")
            pg.wait_for_timeout(1800)
            reg = pg.evaluate("""async () => { const r = await navigator.serviceWorker.getRegistration();
              return r ? !!r.active : false; }""")
            check("service worker registers and activates", reg)
            entries = pg.evaluate("""async () => { const ks = await caches.keys();
              if (!ks.length) return 0;
              const c = await caches.open(ks[0]); return (await c.keys()).length; }""")
            check("app shell is cached", entries >= 5, f"{entries} entries")

            server.send_signal(signal.SIGTERM)
            time.sleep(0.8)
            pg.goto("http://localhost:8099/")
            pg.wait_for_timeout(1200)
            check("app loads with the server down",
                  pg.evaluate("typeof compute === 'function'"))
            check("icons are served from cache offline",
                  pg.evaluate("async () => { try { return (await fetch('icon-192.png')).ok; } catch (e) { return false; } }"))
            browser.close()
    finally:
        try:
            server.kill()
        except Exception:
            pass

    # -------------------------------------------------------------------
    section("Console")
    real = [e for e in errors if "Failed to load resource" not in e]
    check("no console or page errors", not real, "; ".join(real[:3]))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  FAILED: " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
