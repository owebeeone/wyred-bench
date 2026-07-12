"""``python3 -m wyred_bench.compare`` — THE oracle (WyredWorkflowDesign §3.3).

Scores a filled-in ``.measurements.json`` against a derived ``.testplan.json``
and produces a structured verdict artifact plus a nonzero exit on any
disagreement. This is the measured board vs the testplan, mechanical, gate-red
on disagreement — the oracle stack's first step into physics.

Ratified semantics (ProposalTestplanContract.md §4-§6), all enforced here:

- **Stale-stamp refusal.** A measurement whose ``testplan_stamp`` differs from
  the testplan's own ``(series, lock versions)`` stamp is REFUSED, not
  compared (``STALE_STAMP``, exit 2).
- **Closed intervals, no epsilon (RATIFY-7).** A measured value exactly at a
  stored bound PASSES; the comparator compares parsed floats against the
  testplan's stored bounds directly — instrument precision is the instrument's
  problem, the bounds already encode the acceptable band.
- **I2C scan is exact-set (RATIFY-6).** A missing expected address is
  ``I2C_SCAN_MISSING_ADDR``; an unexpected extra address is
  ``I2C_SCAN_UNEXPECTED_ADDR`` and FAILS — a rogue device is a disagreement.
- **Current is one-sided ≤ with an exact free-string state (RATIFY-4).**
- **An unmeasured check FAILS (``CHECK_UNMEASURED``).** No silent defaults
  extends into physics (law 10).

Exit 0 iff every declared check was measured and agreed; 1 on any comparison
finding; 2 on a stale-stamp refusal or a setup error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from wyred_bench import model
from wyred_bench.jsonio import canonical_str, read_json, write_canonical


class SetupError(Exception):
    """A malformed testplan/measurement input (exit 2, not a verdict)."""


# --------------------------------------------------------------------------
# per-kind comparison — each returns a list of (code, detail) findings for one
# check. A check with no findings PASSED. Decision order inside each kind is
# chosen so a single deviation provokes exactly one code.
# --------------------------------------------------------------------------

def _as_float(x: Any, what: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        raise SetupError("%s is not numeric: %r" % (what, x))


def _compare_rail(check: dict, result: dict) -> list[tuple[str, str]]:
    expect = check["expect"]
    unit = result.get("unit")
    if unit != model.UNIT_RAIL:
        return [(model.CODE_UNIT_MISMATCH,
                 "expected unit %s, measured %r" % (model.UNIT_RAIL, unit))]
    value = _as_float(result.get("value"), "rail value")
    low, high = float(expect["low"]), float(expect["high"])
    if not (low <= value <= high):        # closed interval (RATIFY-7)
        return [(model.CODE_RAIL_OUT_OF_RANGE,
                 "measured %g V outside [%g, %g] (nominal %g)"
                 % (value, low, high, float(expect["nominal"])))]
    return []


def _compare_current(check: dict, result: dict,
                     record_state: Any) -> list[tuple[str, str]]:
    expect = check["expect"]
    unit = result.get("unit")
    if unit != model.UNIT_CURRENT:
        return [(model.CODE_UNIT_MISMATCH,
                 "expected unit %s, measured %r" % (model.UNIT_CURRENT, unit))]
    # state: per-result overrides the record-level state; matched EXACTLY.
    measured_state = result.get("state", record_state)
    if measured_state != expect.get("state"):
        return [(model.CODE_STATE_MISMATCH,
                 "expected state %r, measured %r"
                 % (expect.get("state"), measured_state))]
    value = _as_float(result.get("value"), "current value")
    max_ma = float(expect["max_ma"])
    if value > max_ma:                    # one-sided ≤ (RATIFY-4), closed
        return [(model.CODE_CURRENT_EXCEEDED,
                 "measured %g mA exceeds max %g mA (state %s)"
                 % (value, max_ma, expect.get("state")))]
    return []


def _compare_i2c_scan(check: dict, result: dict) -> list[tuple[str, str]]:
    expected = {int(a) for a in check["expect"]["addrs"]}
    if "addrs" not in result:
        raise SetupError("i2c_scan result for %s has no 'addrs'" % check["id"])
    measured = {int(a) for a in result["addrs"]}
    findings: list[tuple[str, str]] = []
    missing = sorted(expected - measured)
    extra = sorted(measured - expected)   # exact-set (RATIFY-6)
    if missing:
        findings.append((model.CODE_I2C_SCAN_MISSING_ADDR,
                         "expected address(es) not found: %s"
                         % ", ".join("0x%02X" % a for a in missing)))
    if extra:
        findings.append((model.CODE_I2C_SCAN_UNEXPECTED_ADDR,
                         "unexpected address(es) on bus: %s"
                         % ", ".join("0x%02X" % a for a in extra)))
    return findings


def _compare_signal(check: dict, result: dict) -> list[tuple[str, str]]:
    expect = check["expect"]
    values = result.get("values", {})
    findings: list[tuple[str, str]] = []
    for qty in ("freq", "duty"):
        try:
            # FLAT trio (ProposalTestplanContract §5), read via the shared
            # model helper so card + compare cannot drift on the shape again.
            band = model.signal_band(expect, qty)
        except model.ExpectShapeError as exc:
            # a malformed testplan is a setup error (exit 2), not a verdict.
            raise SetupError(str(exc))
        if band is None:
            continue                      # not declared -> not checked
        if qty not in values:
            # a declared quantity with no measurement is an unmeasured check.
            return [(model.CODE_CHECK_UNMEASURED,
                     "signal quantity %r declared but not measured" % qty)]
        nominal, low, high = band
        v = _as_float(values[qty], "signal %s" % qty)
        if not (low <= v <= high):        # closed interval (RATIFY-7)
            findings.append((model.CODE_SIGNAL_OUT_OF_RANGE,
                             "%s measured %g outside [%g, %g] (nominal %g)"
                             % (qty, v, low, high, nominal)))
    return findings


def _compare_check(check: dict, result: dict,
                   record_state: Any) -> list[tuple[str, str]]:
    kind = check["kind"]
    if kind == model.KIND_RAIL:
        return _compare_rail(check, result)
    if kind == model.KIND_CURRENT:
        return _compare_current(check, result, record_state)
    if kind == model.KIND_I2C_SCAN:
        return _compare_i2c_scan(check, result)
    if kind == model.KIND_SIGNAL:
        return _compare_signal(check, result)
    raise SetupError("unknown check kind %r on %s" % (kind, check["id"]))


# --------------------------------------------------------------------------
# whole-record comparison
# --------------------------------------------------------------------------

def compare(testplan: dict, measurements: dict) -> dict:
    """Return a structured verdict dict. Never raises for a comparison
    disagreement — only for malformed input (SetupError)."""
    tp_stamp = testplan.get("stamp")
    m_stamp = measurements.get("testplan_stamp")

    header = {
        "artifact": testplan.get("artifact"),
        "board_serial": measurements.get("board_serial"),
        "testplan_stamp": tp_stamp,
    }

    # 1. stale-stamp refusal — refused, not compared (ProposalTestplanContract §6)
    if not model.stamp_equal(tp_stamp, m_stamp):
        return dict(header, status="REFUSED",
                    refusal=model.CODE_STALE_STAMP,
                    findings=[{
                        "check": None,
                        "code": model.CODE_STALE_STAMP,
                        "detail": "measurement stamp [%s] != testplan stamp "
                                  "[%s] -- refused, not compared"
                                  % (model.stamp_display(m_stamp),
                                     model.stamp_display(tp_stamp)),
                    }],
                    checks=[])

    checks = testplan.get("checks", [])
    results = measurements.get("results", {})
    record_state = measurements.get("state")
    by_id = {c["id"]: c for c in checks}

    findings: list[dict] = []
    check_reports: list[dict] = []

    # 2. per declared check (sorted by id for a deterministic artifact)
    for check in sorted(checks, key=lambda c: c["id"]):
        cid = check["id"]
        if cid not in results:
            # an unmeasured check FAILS — no silent defaults (law 10)
            f = (model.CODE_CHECK_UNMEASURED, "check not present in "
                 "measurement record")
            findings.append({"check": cid, "code": f[0], "detail": f[1]})
            check_reports.append({"check": cid, "kind": check["kind"],
                                  "status": "FAIL", "codes": [f[0]]})
            continue
        cfindings = _compare_check(check, results[cid], record_state)
        if cfindings:
            for code, detail in cfindings:
                findings.append({"check": cid, "code": code, "detail": detail})
            check_reports.append({"check": cid, "kind": check["kind"],
                                  "status": "FAIL",
                                  "codes": sorted({c for c, _ in cfindings})})
        else:
            check_reports.append({"check": cid, "kind": check["kind"],
                                  "status": "PASS", "codes": []})

    # 3. measurement results that name no declared check
    for cid in sorted(results):
        if cid not in by_id:
            findings.append({"check": cid,
                             "code": model.CODE_MEASUREMENT_UNKNOWN_CHECK,
                             "detail": "measurement names no check in the "
                                       "testplan"})

    findings.sort(key=lambda f: (str(f["check"]), f["code"]))
    status = "PASS" if not findings else "FAIL"
    return dict(header, status=status, findings=findings,
                checks=check_reports)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _format_report(verdict: dict) -> str:
    lines: list[str] = []
    lines.append("artifact: %s   board: %s   stamp: [%s]"
                 % (verdict.get("artifact"), verdict.get("board_serial"),
                    model.stamp_display(verdict.get("testplan_stamp"))))
    if verdict["status"] == "REFUSED":
        for f in verdict["findings"]:
            lines.append("REFUSED %s: %s" % (f["code"], f["detail"]))
        lines.append("VERDICT: REFUSED")
        return "\n".join(lines) + "\n"
    for rep in verdict.get("checks", []):
        if rep["status"] == "PASS":
            lines.append("PASS %-28s %s" % (rep["check"], rep["kind"]))
        else:
            lines.append("FAIL %-28s %s  <%s>"
                         % (rep["check"], rep["kind"],
                            ", ".join(rep["codes"])))
    for f in verdict["findings"]:
        lines.append("  %-26s %s: %s"
                     % (f["check"], f["code"], f["detail"]))
    lines.append("VERDICT: %s (%d finding(s))"
                 % (verdict["status"], len(verdict["findings"])))
    return "\n".join(lines) + "\n"


def _exit_code(verdict: dict) -> int:
    if verdict["status"] == "PASS":
        return 0
    if verdict["status"] == "REFUSED":
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wyred_bench.compare",
        description="Score a measurement record against a testplan (the "
                    "oracle). Exit 0 iff every check was measured and agreed.")
    parser.add_argument("--testplan", required=True, type=Path,
                        help="path to the <name>.testplan.json")
    parser.add_argument("--measurements", required=True, type=Path,
                        help="path to the <name>.measurements.json")
    parser.add_argument("--out", type=Path,
                        help="write the canonical JSON verdict artifact here")
    args = parser.parse_args(argv)

    try:
        testplan = read_json(args.testplan)
        measurements = read_json(args.measurements)
    except (OSError, ValueError) as exc:
        sys.stderr.write("setup error: %s\n" % exc)
        return 2

    try:
        verdict = compare(testplan, measurements)
    except SetupError as exc:
        sys.stderr.write("setup error: %s\n" % exc)
        return 2

    sys.stdout.write(_format_report(verdict))
    if args.out is not None:
        write_canonical(args.out, verdict)
    else:
        # still expose the canonical artifact on stdout for piping
        sys.stdout.write(canonical_str(verdict))
    return _exit_code(verdict)


if __name__ == "__main__":
    sys.exit(main())
