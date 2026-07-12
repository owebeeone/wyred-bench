#!/usr/bin/env python3
"""wyred-bench acceptance — ``python3 tests/run_tests.py`` (from the repo root).

One command, four groups, exit 0 iff every group passes:

1. **fence** — every source file under ``src/`` imports only the standard
   library (plus ``wyred_bench`` itself). The stdlib-only fence, mechanical.
2. **card** — the bench card renders byte-identically across runs and matches
   the committed snapshot; every testplan check appears exactly once and in the
   documented station order.
3. **compare** — the comparator (run as a SUBPROCESS, the way a consumer runs
   it) over the measurement battery: all-pass and both boundary fixtures exit
   0; every failing fixture exits nonzero naming EXACTLY its verdict code (and
   no other); the stale-stamp fixture is refused (exit 2, ``STALE_STAMP``);
   the verdict artifact is byte-deterministic across runs. Every contract
   verdict code is provoked by at least one fixture.
4. **grounding** — every refdes / net / i2c address / rail nominal the testplan
   fixture cites is present in the FROZEN watchy_v1 goldens (the fixture is the
   hand-verified §5 worked example; goldens carry no testplan).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
FIX = HERE / "fixtures"
MEAS = FIX / "measurements"
TESTPLAN = FIX / "watchy_v1_bench.testplan.json"
SNAPSHOT = FIX / "watchy_v1_bench.benchcard.md"
# synthetic signal fixtures (DISTINCT filenames per ProposalTestplanContract §5)
# exercising shapes the golden corpus deliberately does not declare — a duty
# band, the freq+duty both-trios shape, and a malformed partial trio.
SYN = FIX / "synthetic"
SYN_TESTPLAN = SYN / "synthetic_signals.testplan.json"
SYN_PARTIAL = SYN / "synthetic_partial_trio.testplan.json"

CONTRACT = Path(os.environ.get(
    "WYRED_CONTRACT_SRC", str(REPO.parent / "wyred-contract")))
GOLDENS = CONTRACT / "goldens" / "ga019"

sys.path.insert(0, str(SRC))
from wyred_bench import model                       # noqa: E402
from wyred_bench.jsonio import canonical_str, read_json   # noqa: E402

# tampered measurement fixture -> the single verdict code it must provoke.
EXPECT_CODE = {
    "rail_out_of_range": model.CODE_RAIL_OUT_OF_RANGE,
    "i2c_missing_addr": model.CODE_I2C_SCAN_MISSING_ADDR,
    "i2c_unexpected_addr": model.CODE_I2C_SCAN_UNEXPECTED_ADDR,
    "current_exceeded": model.CODE_CURRENT_EXCEEDED,
    "signal_out_of_range": model.CODE_SIGNAL_OUT_OF_RANGE,
    "check_unmeasured": model.CODE_CHECK_UNMEASURED,
    "measurement_unknown_check": model.CODE_MEASUREMENT_UNKNOWN_CHECK,
    "unit_mismatch": model.CODE_UNIT_MISMATCH,
    "state_mismatch": model.CODE_STATE_MISMATCH,
}
PASS_FIXTURES = ("allpass", "boundary_low", "boundary_high")
REFUSE_FIXTURE = "stale_stamp"
ALL_CODES = model.VERDICT_CODES + (model.CODE_STALE_STAMP,)

# selftest (step 3.1) — the firmware self-test stub generator.
SELFTEST_DIR = FIX / "selftest"
ARTIFACT = "watchy_v1_bench"
SNAP_C = SELFTEST_DIR / ("%s.selftest.c" % ARTIFACT)
SNAP_PY = SELFTEST_DIR / ("%s.selftest.py" % ARTIFACT)
SNAP_MANIFEST = SELFTEST_DIR / ("%s.selftest.NOT_IMPLEMENTED.json" % ARTIFACT)
PINMAP = GOLDENS / ("%s.pinmap.json" % "watchy_v1")


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(mod: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", mod, *args],
                          env=_env(), capture_output=True, text=True)


def _codes_in(text: str) -> set[str]:
    return {c for c in ALL_CODES if c in text}


# --------------------------------------------------------------------------
def test_fence() -> list[str]:
    fails = []
    allowed = set(sys.stdlib_module_names) | {"wyred_bench"}
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[0]] if node.level == 0 \
                    else []
            else:
                continue
            for mod in mods:
                if mod and mod not in allowed:
                    fails.append("%s imports non-stdlib %r"
                                 % (py.relative_to(REPO), mod))
    return fails


def test_card() -> list[str]:
    fails = []
    a = _run("wyred_bench.card", "--testplan", str(TESTPLAN))
    b = _run("wyred_bench.card", "--testplan", str(TESTPLAN))
    if a.returncode != 0:
        return ["card: exit %d\n%s" % (a.returncode, a.stderr)]
    if a.stdout != b.stdout:
        fails.append("card: not byte-identical across two runs")
    if a.stdout != SNAPSHOT.read_text(encoding="utf-8"):
        fails.append("card: output differs from committed snapshot %s"
                     % SNAPSHOT.name)

    # every check appears exactly once, in documented station order
    testplan = read_json(TESTPLAN)
    want_order = [c["id"] for c in model.sorted_checks(testplan["checks"])]
    seen, seqs = [], []
    for line in a.stdout.splitlines():
        if line.startswith("### "):
            head = line[4:]
            seq, rest = head.split(".", 1)
            cid = rest.strip().split("  (")[0]
            seqs.append(int(seq))
            seen.append(cid)
    if seen != want_order:
        fails.append("card: check order %s != documented order %s"
                     % (seen, want_order))
    if seqs != list(range(1, len(want_order) + 1)):
        fails.append("card: station sequence not 1..N contiguous: %s" % seqs)
    for cid in want_order:
        if seen.count(cid) != 1:
            fails.append("card: check %s appears %d times (want 1)"
                         % (cid, seen.count(cid)))
    return fails


def test_compare() -> list[str]:
    fails = []
    provoked: set[str] = set()

    for name in PASS_FIXTURES:
        f = MEAS / ("%s.measurements.json" % name)
        p = _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
                 "--measurements", str(f))
        if p.returncode != 0:
            fails.append("%s: exit %d (want 0)\n%s%s"
                         % (name, p.returncode, p.stdout, p.stderr))
        fired = _codes_in(p.stdout)
        if fired:
            fails.append("%s: expected clean pass, fired %s" % (name, fired))

    for name, code in sorted(EXPECT_CODE.items()):
        f = MEAS / ("%s.measurements.json" % name)
        p = _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
                 "--measurements", str(f))
        fired = _codes_in(p.stdout)
        if p.returncode != 1:
            fails.append("%s: exit %d (want 1)" % (name, p.returncode))
        if fired != {code}:
            fails.append("%s: fired %s (want exactly {%s})"
                         % (name, fired, code))
        provoked |= fired

    # stale-stamp refusal: exit 2, STALE_STAMP, and NO per-check code
    f = MEAS / ("%s.measurements.json" % REFUSE_FIXTURE)
    p = _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
             "--measurements", str(f))
    fired = _codes_in(p.stdout)
    if p.returncode != 2:
        fails.append("%s: exit %d (want 2)" % (REFUSE_FIXTURE, p.returncode))
    if fired != {model.CODE_STALE_STAMP}:
        fails.append("%s: fired %s (want exactly {STALE_STAMP})"
                     % (REFUSE_FIXTURE, fired))
    if "REFUSED" not in p.stdout:
        fails.append("%s: verdict is not REFUSED" % REFUSE_FIXTURE)
    provoked |= fired

    # every contract verdict code (+ the refusal) is provoked by a fixture
    missing = set(ALL_CODES) - provoked
    if missing:
        fails.append("verdict codes never provoked by any fixture: %s"
                     % sorted(missing))

    # verdict artifact byte-deterministic across runs
    import tempfile
    allpass = MEAS / "allpass.measurements.json"
    with tempfile.TemporaryDirectory() as td:
        o1, o2 = Path(td) / "v1.json", Path(td) / "v2.json"
        _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
             "--measurements", str(allpass), "--out", str(o1))
        _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
             "--measurements", str(allpass), "--out", str(o2))
        if o1.read_bytes() != o2.read_bytes():
            fails.append("verdict artifact not byte-deterministic across runs")
    return fails


def test_grounding() -> list[str]:
    """Every refdes/net/address/nominal the testplan cites exists in the
    frozen watchy goldens (the fixture is honest to the contract)."""
    fails = []
    if not GOLDENS.exists():
        return ["grounding: goldens dir not found at %s (set "
                "WYRED_CONTRACT_SRC)" % GOLDENS]
    pinmap = read_json(GOLDENS / "watchy_v1.pinmap.json")
    l1 = read_json(GOLDENS / "watchy_v1.l1.json")

    # index test_point components by (refdes) -> set of nets, and all nets
    tp_nets: dict[str, set[str]] = {}
    for comp in pinmap.get("components", []):
        if comp.get("kind") == "test_point":
            nets = {t.get("net") for t in comp.get("terminals", [])}
            tp_nets[comp["refdes"]] = nets
    rail_volts = {r["name"]: r.get("volts") for r in l1.get("rails", [])}
    bus_names = {b["name"] for b in l1.get("buses", [])}
    # every i2c_addr declared anywhere in l1 demands
    i2c_addrs: set[int] = set()

    def walk(o):
        if isinstance(o, dict):
            if "i2c_addr" in o:
                i2c_addrs.add(int(o["i2c_addr"]))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(l1)

    testplan = read_json(TESTPLAN)
    if testplan.get("stamp") != pinmap.get("stamp"):
        fails.append("grounding: testplan stamp != frozen pinmap stamp")
    for check in testplan["checks"]:
        probe = check.get("probe", {}) or {}
        pts = list(probe.get("points", []) or [])
        if probe.get("ground_ref"):
            pts.append(probe["ground_ref"])
        for p in pts:
            refdes, net = p.get("refdes"), p.get("net")
            if refdes not in tp_nets:
                fails.append("grounding: %s cites non-testpoint %s"
                             % (check["id"], refdes))
            elif net not in tp_nets[refdes]:
                fails.append("grounding: %s cites %s with net %s not on that "
                             "testpoint %s" % (check["id"], refdes, net,
                                               tp_nets[refdes]))
        if check["kind"] == model.KIND_RAIL:
            nominal = check["expect"]["nominal"]
            if rail_volts.get(check["subject"]) != nominal:
                fails.append("grounding: %s nominal %s != l1 rail %s volts %s"
                             % (check["id"], nominal, check["subject"],
                                rail_volts.get(check["subject"])))
        if check["kind"] == model.KIND_CURRENT:
            if check["subject"] not in rail_volts:
                fails.append("grounding: current subject %s is not an l1 rail"
                             % check["subject"])
        if check["kind"] == model.KIND_I2C_SCAN:
            if check["subject"] not in bus_names:
                fails.append("grounding: i2c subject %s is not an l1 bus"
                             % check["subject"])
            for a in check["expect"]["addrs"]:
                if int(a) not in i2c_addrs:
                    fails.append("grounding: i2c addr %s not declared in l1"
                                 % a)
    return fails


def _gen_selftest(out_dir: Path) -> subprocess.CompletedProcess:
    """Run the generator as a SUBPROCESS (the way a consumer runs it)."""
    return _run("wyred_bench.selftest", "--testplan", str(TESTPLAN),
                "--pinmap", str(PINMAP), "--out-dir", str(out_dir))


def _run_py_stub(py_src: str, readings: dict) -> dict:
    """Exec the GENERATED MicroPython stub with injected fake readings and
    return its measurement record — the firmware self-test's on-board route."""
    ns: dict = {}
    exec(compile(py_src, "<selftest>", "exec"), ns)          # noqa: S102
    hooks_base = ns["Hooks"]

    class Fake(hooks_base):                                  # type: ignore
        def enter_state(self, state):
            return None

        def read_board_serial(self):
            return "SIM-0001"

        def adc_read_mv(self, check_id, channel):
            return readings[check_id]

        def read_current_ma(self, check_id, rail, state):
            return readings[check_id]

        def i2c_scan(self, check_id, bus):
            return readings[check_id]

        def measure_signal(self, check_id, tp):
            return readings[check_id]

    return ns["run_selftest"](Fake())


def test_selftest() -> list[str]:
    """WyredPlanTestplan step 3.1 — the firmware self-test stub generator.

    Generated C passes ``cc -fsyntax-only``; generated Python passes
    ``py_compile``; every testplan check appears exactly once in each target;
    snapshot-stable and byte-deterministic; a simulated Python-stub run is
    scored GREEN by the 2.2 comparator and RED (right code) on one bad
    reading; the NOT_IMPLEMENTED manifest is non-empty and its hooks are
    genuinely abstract in both targets.
    """
    import shutil
    import tempfile

    fails: list[str] = []
    if not PINMAP.exists():
        return ["selftest: pinmap golden not found at %s (set "
                "WYRED_CONTRACT_SRC)" % PINMAP]

    with tempfile.TemporaryDirectory() as td:
        d1, d2 = Path(td) / "a", Path(td) / "b"
        g1 = _gen_selftest(d1)
        if g1.returncode != 0:
            return ["selftest: generator exit %d\n%s%s"
                    % (g1.returncode, g1.stdout, g1.stderr)]
        g2 = _gen_selftest(d2)

        c_src = (d1 / SNAP_C.name).read_text(encoding="utf-8")
        py_src = (d1 / SNAP_PY.name).read_text(encoding="utf-8")
        man_txt = (d1 / SNAP_MANIFEST.name).read_text(encoding="utf-8")

        # byte-deterministic across two runs
        for fname in (SNAP_C.name, SNAP_PY.name, SNAP_MANIFEST.name):
            if (d1 / fname).read_bytes() != (d2 / fname).read_bytes():
                fails.append("selftest: %s not byte-identical across runs"
                             % fname)

        # snapshot-stable (regenerate == committed)
        for gen_path, snap in ((d1 / SNAP_C.name, SNAP_C),
                               (d1 / SNAP_PY.name, SNAP_PY),
                               (d1 / SNAP_MANIFEST.name, SNAP_MANIFEST)):
            if not snap.exists():
                fails.append("selftest: committed snapshot missing: %s"
                             % snap.relative_to(REPO))
            elif gen_path.read_bytes() != snap.read_bytes():
                fails.append("selftest: %s differs from committed snapshot "
                             "(regenerate)" % snap.name)

        # generated Python compiles
        pc = subprocess.run([sys.executable, "-m", "py_compile",
                             str(d1 / SNAP_PY.name)],
                            capture_output=True, text=True)
        if pc.returncode != 0:
            fails.append("selftest: generated Python fails py_compile\n%s"
                         % pc.stderr)

        # generated C passes syntax-only (loud SKIP if no C compiler)
        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if cc is None:
            print("   ~ selftest: no C compiler on PATH; cc -fsyntax-only "
                  "SKIPPED (C stub not syntax-checked)")
        else:
            cp = subprocess.run([cc, "-fsyntax-only", str(d1 / SNAP_C.name)],
                                capture_output=True, text=True)
            if cp.returncode != 0:
                fails.append("selftest: generated C fails %s -fsyntax-only\n%s"
                             % (cc, cp.stderr))

        # every testplan check appears exactly once in EACH target
        testplan = read_json(TESTPLAN)
        for cid in [c["id"] for c in testplan["checks"]]:
            lit = '"%s"' % cid
            if c_src.count(lit) != 1:
                fails.append("selftest: check %s appears %d time(s) in C "
                             "(want 1)" % (cid, c_src.count(lit)))
            if py_src.count(lit) != 1:
                fails.append("selftest: check %s appears %d time(s) in Python "
                             "(want 1)" % (cid, py_src.count(lit)))

        # NOT_IMPLEMENTED manifest: non-empty, and every listed hook is
        # genuinely abstract in BOTH targets (the honesty, asserted).
        manifest = read_json(d1 / SNAP_MANIFEST.name)
        hook_names = [h["hook"] for h in manifest.get("hooks", [])]
        if not hook_names:
            fails.append("selftest: NOT_IMPLEMENTED manifest lists no hooks")
        if not manifest.get("unresolved"):
            fails.append("selftest: NOT_IMPLEMENTED manifest has no unresolved "
                         "parameters")
        for hook in hook_names:
            if ("wb_%s" % hook) not in c_src:
                fails.append("selftest: manifest hook %s has no wb_ extern in "
                             "the C stub" % hook)
            if ("def %s(" % hook) not in py_src:
                fails.append("selftest: manifest hook %s is not abstract in "
                             "the Python stub" % hook)

        # simulated run -> GREEN, then one bad reading -> RED (right code)
        green = {
            "rail_3v3": 3300.0,                  # mV -> 3.3 V (in range)
            "batt_current": 120.0,               # mA (<= 150, state active)
            "i2c_accel": [24],                   # exact set
            "prog_signal": {"freq": 115200.0},   # freq only (duty not declared)
        }
        try:
            rec_green = _run_py_stub(py_src, green)
            red = dict(green)
            red["rail_3v3"] = 3600.0             # 3.6 V (out of range)
            rec_red = _run_py_stub(py_src, red)
        except Exception as exc:                 # noqa: BLE001
            return fails + ["selftest: Python stub raised on simulated run: %r"
                            % exc]

        m_green = Path(td) / "green.measurements.json"
        m_red = Path(td) / "red.measurements.json"
        m_green.write_text(canonical_str(rec_green), encoding="utf-8")
        m_red.write_text(canonical_str(rec_red), encoding="utf-8")

        pg = _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
                  "--measurements", str(m_green))
        if pg.returncode != 0:
            fails.append("selftest: simulated stub run scored NONZERO (want "
                         "green)\n%s%s" % (pg.stdout, pg.stderr))
        if _codes_in(pg.stdout):
            fails.append("selftest: simulated green run fired %s"
                         % _codes_in(pg.stdout))

        pr = _run("wyred_bench.compare", "--testplan", str(TESTPLAN),
                  "--measurements", str(m_red))
        if pr.returncode != 1:
            fails.append("selftest: one-bad-reading run exit %d (want 1)"
                         % pr.returncode)
        if _codes_in(pr.stdout) != {model.CODE_RAIL_OUT_OF_RANGE}:
            fails.append("selftest: one-bad-reading run fired %s (want exactly "
                         "{RAIL_OUT_OF_RANGE})" % _codes_in(pr.stdout))

    return fails


def test_synthetic() -> list[str]:
    """Signal shapes the golden corpus deliberately does NOT declare
    (ProposalTestplanContract §5), kept under DISTINCT filenames so the
    comparator/card duty paths stay covered without a divergent
    watchy_v1_bench twin (the F1 defect). The canonical fixture is signal
    freq-only; here a duty-only band and a freq+duty both-trios signal are
    rendered and scored, and a partial trio is proven a STRUCTURED error
    (exit 2), never a KeyError."""
    fails: list[str] = []

    # card renders both a duty-only band and a freq+duty (both-trios) signal
    c = _run("wyred_bench.card", "--testplan", str(SYN_TESTPLAN))
    if c.returncode != 0:
        fails.append("synthetic card: exit %d\n%s" % (c.returncode, c.stderr))
    else:
        if "duty" not in c.stdout:
            fails.append("synthetic card: no duty band rendered")
        if ("range [45, 55] %" not in c.stdout
                or "range [20, 40] %" not in c.stdout):
            fails.append("synthetic card: duty ranges not rendered as expected")

    # all-pass measurement scores clean (exit 0, no codes)
    ap = _run("wyred_bench.compare", "--testplan", str(SYN_TESTPLAN),
              "--measurements",
              str(SYN / "synthetic_allpass.measurements.json"))
    if ap.returncode != 0:
        fails.append("synthetic allpass: exit %d (want 0)\n%s%s"
                     % (ap.returncode, ap.stdout, ap.stderr))
    if _codes_in(ap.stdout):
        fails.append("synthetic allpass fired %s" % _codes_in(ap.stdout))

    # an out-of-band DUTY reading fails with SIGNAL_OUT_OF_RANGE (the duty path
    # the corpus never exercises)
    doo = _run("wyred_bench.compare", "--testplan", str(SYN_TESTPLAN),
               "--measurements",
               str(SYN / "synthetic_duty_out_of_range.measurements.json"))
    if doo.returncode != 1:
        fails.append("synthetic duty_out_of_range: exit %d (want 1)"
                     % doo.returncode)
    if _codes_in(doo.stdout) != {model.CODE_SIGNAL_OUT_OF_RANGE}:
        fails.append("synthetic duty_out_of_range fired %s (want exactly "
                     "{SIGNAL_OUT_OF_RANGE})" % _codes_in(doo.stdout))

    # a PARTIAL trio is a structured setup error (exit 2), not a KeyError — in
    # BOTH the card generator and the comparator.
    for mod, extra in (("wyred_bench.card", ()),
                       ("wyred_bench.compare",
                        ("--measurements",
                         str(SYN / "synthetic_partial_trio.measurements.json")))):
        p = _run(mod, "--testplan", str(SYN_PARTIAL), *extra)
        if p.returncode != 2:
            fails.append("%s partial-trio: exit %d (want 2, structured)"
                         % (mod, p.returncode))
        if "partial" not in p.stderr:
            fails.append("%s partial-trio: not a structured shape error: %s"
                         % (mod, p.stderr.strip() or p.stdout.strip()))
    return fails


GROUPS = (
    ("fence", test_fence),
    ("card", test_card),
    ("compare", test_compare),
    ("grounding", test_grounding),
    ("selftest", test_selftest),
    ("synthetic", test_synthetic),
)


def main() -> int:
    total = 0
    for name, fn in GROUPS:
        fails = fn()
        total += len(fails)
        if fails:
            print("FAIL %s (%d):" % (name, len(fails)))
            for f in fails:
                print("   - %s" % f)
        else:
            print("PASS %s" % name)
    print("\nWYRED-BENCH TESTS: %s (%d failure(s))"
          % ("PASS" if total == 0 else "FAIL", total))
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
