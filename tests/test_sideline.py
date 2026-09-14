#!/usr/bin/env python3
"""
Sideline test suite.

    pip install playwright && playwright install chromium
    python3 tests/test_sideline.py

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
  S.game = newGame();
  const bands = [];
  BANDS.forEach(b => { for (let i = 0; i < slotsFor(b); i++) bands.push(b); });
  S.game.seq++;
  bands.forEach((b, i) => S.game.log.push({
    eid: uid(), g: 1, t: Date.now(), gt: 0, sh: 1, period: 1,
    type: 'ON', playerId: 'p' + i, band: b
  }));
  invalidate(); render();
}"""

ROSTER = ["Ava Chen", "Ben Ortiz", "Cole Park", "Dara Singh", "Eli Brooks",
          "Fia Moreau", "Gus Reyes", "Hana Lee", "Ivy Nowak", "Jack Duarte",
          "Kira Amin", "Liam Vance", "Mia Fox"]

# the app's own invariant checker, reused here
SELF_CHECK = "selfCheck().indexOf('FAIL') === -1"


def run_shift(pg, at_seconds):
    """Advance the clock, auto-fill, and send the resulting shift on."""
    pg.evaluate(f"S.game.base = {at_seconds}; invalidate(); autoFillNext();")
    diff = pg.evaluate("""(() => { const e = planDiff(); return {
        on: e.filter(x => x.type === 'ON').length,
        off: e.filter(x => x.type === 'OFF').length,
        mv: e.filter(x => x.type === 'MOVE').length }; })()""")
    pg.evaluate("const e = planDiff(); beginNewShift(); push(e);")
    return diff


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
        churn = [run_shift(pg, k * 300)["mv"] for k in range(1, 6)]
        cap = pg.evaluate("S.settings.maxSwitch == null ? 2 : S.settings.maxSwitch")
        check("position switches stay under the cap", max(churn) <= cap,
              f"per shift: {churn}, cap {cap}")

        keeper_changes = pg.evaluate("""(() => {
          let n = 0; S.game.log.forEach(e => {
            if (e.band === 'GK' && (e.type === 'ON' || e.type === 'MOVE')) n++; });
          return n - 1; })()""")
        check("keeper is not rotated automatically", keeper_changes == 0,
              f"{keeper_changes} keeper changes")

        # full game, two periods
        pg.evaluate(SEED, [ROSTER, 7, True])
        pg.evaluate("S.settings.periods = 2; S.settings.periodLen = 25;")
        for half in range(2):
            for k in range(1, 6):
                run_shift(pg, k * 300)
            if half == 0:
                pg.evaluate("S.game.base = 1500; endPeriodNow(); nextPeriod();")
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
        saved = pg.evaluate("S.lineups.length ? Object.values(S.lineups[0].slots).flat().length : 0")
        check("a lineup saves the whole field", saved == 7, f"{saved} players")

        pg.evaluate("S.game = newGame(); invalidate(); loadLineup(S.lineups[0].id);")
        check("loading fills the plan, not the field", pg.evaluate("nextCount()") == 7,
              f"{pg.evaluate('nextCount()')} placed")
        check("loading does not touch the field", pg.evaluate("S.game.log.length") == 0)

        pg.evaluate("""() => { S.game.next = null; byId('p2').avail = 'out';
          invalidate(); loadLineup(S.lineups[0].id); }""")
        placed = pg.evaluate("nextCount()")
        absent = pg.evaluate("!Object.values(S.game.next).flat().includes('p2')")
        check("an absent player is skipped on load", placed == 6 and absent, f"{placed} placed")

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
        section("Layout")
        pg.evaluate("S.roster.forEach(p => p.avail = 'available'); invalidate();")
        overflow = []
        for width in (360, 430):
            pg.set_viewport_size({"width": width, "height": 800})
            for advanced in (False, True):
                pg.evaluate(f"S.settings.advanced = {str(advanced).lower()}; render();")
                for tab in ("field", "next", "clock", "times", "log", "roster", "help", "setup"):
                    pg.click(f'#tabs button[data-tab="{tab}"]')
                    pg.wait_for_timeout(120)
                    if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                        overflow.append(f"{tab}@{width}")
                    if pg.evaluate("(() => { const n = document.getElementById('tabs'); return n.scrollWidth > n.clientWidth; })()"):
                        overflow.append(f"tabbar@{width}")
        check("no horizontal overflow on any tab", not overflow, ", ".join(sorted(set(overflow))))
        pg.set_viewport_size({"width": 390, "height": 844})

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
