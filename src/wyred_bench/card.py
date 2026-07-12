"""``python3 -m wyred_bench.card`` — the bench-card generator.

Renders a derived ``.testplan.json`` as an ordered, human-readable check card
for a technician at a probe station. Depends on the testplan artifact alone
(it is self-contained: resolved probe points, expected values, and ranges are
embedded), so the card derives without the engine.

Ordering policy (WyredPlanTestplan step 2.1): power-off / continuity ->
power-on rails -> current -> buses -> signals; within a band, by check id.
Every check appears exactly once. The output is byte-deterministic (no
timestamps, sorted provenance) so it can be snapshot-compared across runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from wyred_bench import model
from wyred_bench.jsonio import read_json


def _num(x: Any) -> str:
    """Render a JSON number cleanly: integers without a decimal point,
    others via shortest round-tripping repr."""
    f = float(x)
    if f == int(f):
        return str(int(f))
    return repr(f)


def _probe_point(p: dict) -> str:
    return "%s pad %s (net %s)" % (p.get("refdes"), p.get("pad"),
                                   p.get("net"))


def _probe_line(check: dict) -> str:
    probe = check.get("probe", {}) or {}
    points = probe.get("points", []) or []
    ground = probe.get("ground_ref")
    if check["kind"] == model.KIND_CURRENT and not points:
        return ("no test point — probe method (series ammeter / supply "
                "readout) is a bench-card matter")
    parts = ["; ".join(_probe_point(p) for p in points) or "(none)"]
    if ground:
        parts.append("ground %s" % _probe_point(ground))
    return "; ".join(parts)


def _expected_line(check: dict) -> str:
    kind = check["kind"]
    e = check["expect"]
    if kind == model.KIND_RAIL:
        return "%s V, range [%s, %s] V" % (_num(e["nominal"]), _num(e["low"]),
                                           _num(e["high"]))
    if kind == model.KIND_CURRENT:
        return "<= %s mA (state '%s')" % (_num(e["max_ma"]), e.get("state"))
    if kind == model.KIND_I2C_SCAN:
        addrs = ", ".join("0x%02X" % int(a) for a in e["addrs"])
        return "addresses {%s} (exact set)" % addrs
    if kind == model.KIND_SIGNAL:
        segs = []
        # FLAT trio (ProposalTestplanContract §5), read via the shared model
        # helper so card + compare cannot drift on the shape again.
        freq = model.signal_band(e, "freq")
        if freq is not None:
            segs.append("freq %s Hz, range [%s, %s] Hz"
                        % (_num(freq[0]), _num(freq[1]), _num(freq[2])))
        duty = model.signal_band(e, "duty")
        if duty is not None:
            segs.append("duty %s %%, range [%s, %s] %%"
                        % (_num(duty[0]), _num(duty[1]), _num(duty[2])))
        return "; ".join(segs)
    return repr(e)


def _instrument_line(check: dict) -> str:
    kind = check["kind"]
    probe = check.get("probe", {}) or {}
    points = probe.get("points", []) or []
    ground = probe.get("ground_ref")
    if kind == model.KIND_RAIL:
        tp = points[0]["refdes"] if points else "(probe)"
        gnd = ground["refdes"] if ground else "GND"
        return "DMM DC volts on %s referenced to %s" % (tp, gnd)
    if kind == model.KIND_CURRENT:
        return ("series ammeter / shunt on the %s rail; put the board in "
                "state '%s'" % (check.get("subject"),
                                check["expect"].get("state")))
    if kind == model.KIND_I2C_SCAN:
        tp = ", ".join("%s (%s)" % (p["refdes"], p["net"]) for p in points)
        return ("I2C scan on %s [%s]; expect an ACK from each listed address"
                % (check.get("subject"), tp))
    if kind == model.KIND_SIGNAL:
        tp = points[0]["refdes"] if points else "(probe)"
        net = points[0]["net"] if points else check.get("subject")
        return ("oscilloscope on %s (net %s); measure frequency and duty"
                % (tp, net))
    return "(instrument TBD)"


def _provenance_line(check: dict) -> str:
    prov = check.get("provenance", {}) or {}
    declared = prov.get("declaration", check.get("declared_by"))
    inputs = prov.get("derivation_inputs", {}) or {}
    kv = ", ".join("%s=%s" % (k, inputs[k]) for k in sorted(inputs))
    return "declared by %s; derived from %s" % (declared, kv or "(none)")


def render(testplan: dict) -> str:
    """Return the bench-card markdown for a testplan (byte-deterministic)."""
    artifact = testplan.get("artifact")
    stamp = testplan.get("stamp")
    checks = model.sorted_checks(testplan.get("checks", []))

    out: list[str] = []
    out.append("# Bench card — %s" % artifact)
    out.append("")
    out.append("- Stamp: %s" % model.stamp_display(stamp))
    out.append("- Ordering: power-off / continuity -> power-on rails -> "
               "current -> buses -> signals; then by check id.")
    out.append("- Every check appears exactly once. Record measurements in a "
               "`.measurements.json` and score them with "
               "`python3 -m wyred_bench.compare`.")
    out.append("")

    seq = 0
    current_band: int | None = None
    for check in checks:
        band = model.order_band(check["kind"])
        if band != current_band:
            current_band = band
            out.append("## %s" % model.band_label(band))
            out.append("")
        seq += 1
        out.append("### %d. %s  (%s)" % (seq, check["id"], check["kind"]))
        out.append("")
        out.append("- Subject: %s %s"
                   % (check["kind"], check.get("subject")))
        out.append("- Expected: %s" % _expected_line(check))
        out.append("- Probe: %s" % _probe_line(check))
        out.append("- Instrument: %s" % _instrument_line(check))
        out.append("- Provenance: %s" % _provenance_line(check))
        out.append("")

    return "\n".join(out).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wyred_bench.card",
        description="Render a testplan as an ordered bench card (markdown).")
    parser.add_argument("--testplan", required=True, type=Path,
                        help="path to the <name>.testplan.json")
    parser.add_argument("--out", type=Path,
                        help="write the markdown here (default: stdout)")
    args = parser.parse_args(argv)

    try:
        testplan = read_json(args.testplan)
    except (OSError, ValueError) as exc:
        sys.stderr.write("setup error: %s\n" % exc)
        return 2

    try:
        md = render(testplan)
    except model.ExpectShapeError as exc:
        # a malformed testplan expect shape is a structured setup error
        # (exit 2), never a raw KeyError/TypeError traceback.
        sys.stderr.write("setup error: %s\n" % exc)
        return 2
    if args.out is not None:
        args.out.write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
