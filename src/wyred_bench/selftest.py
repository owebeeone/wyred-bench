"""``python3 -m wyred_bench.selftest`` — firmware self-test STUB generator.

From a derived ``.testplan.json`` (+ the frozen ``.pinmap.json`` it was
derived against) this emits two firmware self-test **stubs** — a C module and
a MicroPython-style module — that iterate the testplan's checks and write their
readings in the **same** ``.measurements.json`` shape the ``wyred_bench.compare``
oracle scores. One oracle, two probe routes (bench DMM vs on-board firmware):
the firmware self-test's output is graded by the same comparator as a
technician's bench card.

Honesty (WyredPlanTestplan step 3.1 — *"template-driven and honest about what's
stubbed"*): hardware access is emitted as **abstract hooks** (``adc_read_mv``,
``i2c_scan``, ``read_current_ma``, ``measure_signal``, ``enter_state``,
``read_board_serial``). Anything not derivable from the contract artifacts —
the ADC channel-to-pad mapping, the MCU's I2C peripheral index, the signal
capture peripheral, the current-sense method, how to enter an operating state,
the board serial source — is left abstract and enumerated twice: as a generated
``TODO`` comment table in each module, and as a machine-readable
``<name>.selftest.NOT_IMPLEMENTED.json`` manifest. **The generator never
fabricates a register map.**

Inputs are read-only artifacts on disk; nothing here imports the engine (the
star topology, depth 1 — see ``CLAUDE.md``). Pure stdlib. Output is
byte-deterministic (snapshot-comparable across runs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from wyred_bench import model
from wyred_bench.jsonio import canonical_str, read_json

TARGET_C = "c"
TARGET_PY = "micropython"
TARGETS = (TARGET_C, TARGET_PY)

# The abstract hook names emitted into BOTH targets. Kept here (not scattered
# through the templates) so the manifest, the C externs, and the Python
# ``Hooks`` base class cannot drift apart.
HOOK_ENTER_STATE = "enter_state"
HOOK_BOARD_SERIAL = "read_board_serial"
HOOK_ADC_READ_MV = "adc_read_mv"
HOOK_READ_CURRENT = "read_current_ma"
HOOK_I2C_SCAN = "i2c_scan"
HOOK_MEASURE_SIGNAL = "measure_signal"

# Reasons a hook is left abstract — none of this is derivable from the
# testplan / pinmap, so it is a TODO, never a fabricated default (law 10).
_HOOK_REASON = {
    HOOK_ADC_READ_MV: "ADC channel-to-pad mapping is not derivable from "
                      "contract artifacts",
    HOOK_READ_CURRENT: "the current-sense method (series shunt / supply "
                       "readout) is board-specific",
    HOOK_I2C_SCAN: "mapping an L1 bus name to a hardware I2C peripheral index "
                   "is not derivable from contract artifacts",
    HOOK_MEASURE_SIGNAL: "the signal-capture peripheral (timer / input "
                         "capture) is board-specific",
    HOOK_ENTER_STATE: "driving the board into a named operating state is "
                      "firmware-specific",
    HOOK_BOARD_SERIAL: "the board serial source is board-specific",
}


class SetupError(Exception):
    """Malformed / ungroundable input (exit 2, not a generated artifact)."""


# --------------------------------------------------------------------------
# pinmap cross-check — fail-closed grounding (law 10)
# --------------------------------------------------------------------------

def _test_point_nets(pinmap: dict) -> dict[str, set[str]]:
    """``refdes -> {net, ...}`` for every realized ``test_point`` component."""
    out: dict[str, set[str]] = {}
    for comp in pinmap.get("components", []) or []:
        if comp.get("kind") == "test_point":
            nets = {t.get("net") for t in comp.get("terminals", []) or []}
            out[comp.get("refdes")] = nets
    return out


def _validate_probes(testplan: dict, pinmap: dict) -> None:
    """Every probe point a check cites must be a realized ``test_point`` on
    that net in the pinmap. A stub against a probe the board does not carry
    would be a fabricated test — refused here (``SELFTEST_UNPROBEABLE``)."""
    tp_nets = _test_point_nets(pinmap)
    for check in testplan.get("checks", []) or []:
        probe = check.get("probe", {}) or {}
        points = list(probe.get("points", []) or [])
        if probe.get("ground_ref"):
            points.append(probe["ground_ref"])
        for p in points:
            refdes, net = p.get("refdes"), p.get("net")
            if refdes not in tp_nets:
                raise SetupError(
                    "SELFTEST_UNPROBEABLE: check %s cites %s, not a realized "
                    "test_point in the pinmap" % (check.get("id"), refdes))
            if net not in tp_nets[refdes]:
                raise SetupError(
                    "SELFTEST_UNPROBEABLE: check %s cites %s with net %s, not "
                    "on that test_point (%s)"
                    % (check.get("id"), refdes, net,
                       sorted(n for n in tp_nets[refdes] if n)))


# --------------------------------------------------------------------------
# planning — testplan -> ordered per-check ops + the NOT_IMPLEMENTED manifest
# --------------------------------------------------------------------------

def _provenance_comment(check: dict) -> str:
    prov = check.get("provenance", {}) or {}
    declared = prov.get("declaration", check.get("declared_by"))
    inputs = prov.get("derivation_inputs", {}) or {}
    kv = ", ".join("%s=%s" % (k, inputs[k]) for k in sorted(inputs))
    return "declared by %s; derived from %s" % (declared, kv or "(none)")


def plan_checks(testplan: dict) -> list[dict]:
    """Return an ordered list of per-check ``op`` dicts (bench-card station
    order) the C / Python templates render straight-line. Raises SetupError
    on a check kind the generator cannot honestly stub."""
    ops: list[dict] = []
    for check in model.sorted_checks(testplan.get("checks", []) or []):
        kind = check.get("kind")
        cid = check.get("id")
        op = {
            "id": cid,
            "kind": kind,
            "subject": check.get("subject"),
            "band_label": model.band_label(model.order_band(kind)),
            "provenance": _provenance_comment(check),
        }
        probe = check.get("probe", {}) or {}
        points = list(probe.get("points", []) or [])
        if kind == model.KIND_RAIL:
            pt = points[0] if points else {}
            op["net"] = pt.get("net")
            op["refdes"] = pt.get("refdes")
        elif kind == model.KIND_CURRENT:
            op["rail"] = check.get("subject")
            op["state"] = (check.get("expect", {}) or {}).get("state")
        elif kind == model.KIND_I2C_SCAN:
            op["bus"] = check.get("subject")
            op["points"] = [{"refdes": p.get("refdes"), "net": p.get("net")}
                            for p in points]
        elif kind == model.KIND_SIGNAL:
            pt = points[0] if points else {}
            op["net"] = pt.get("net")
            op["refdes"] = pt.get("refdes")
            expect = check.get("expect", {}) or {}
            # only the quantities the check actually declared are measured.
            op["quantities"] = [q for q in ("freq", "duty")
                                if expect.get(q) is not None]
        else:
            raise SetupError(
                "cannot generate a self-test for unknown check kind %r on %s"
                % (kind, cid))
        ops.append(op)
    return ops


def build_manifest(testplan: dict, ops: list[dict]) -> dict:
    """The machine-readable ``NOT_IMPLEMENTED`` manifest: every abstract hook
    and every unresolved parameter, enumerated. Non-empty by construction —
    every self-test needs at least ``read_board_serial``."""
    hooks_used: dict[str, list[str]] = {HOOK_BOARD_SERIAL: []}
    unresolved: list[dict] = []

    def use(hook: str, cid: str | None) -> None:
        hooks_used.setdefault(hook, [])
        if cid is not None and cid not in hooks_used[hook]:
            hooks_used[hook].append(cid)

    for op in ops:
        cid, kind = op["id"], op["kind"]
        if kind == model.KIND_RAIL:
            use(HOOK_ADC_READ_MV, cid)
            unresolved.append({
                "check": cid, "kind": kind, "hook": HOOK_ADC_READ_MV,
                "parameter": "channel", "net": op.get("net"),
                "refdes": op.get("refdes"),
                "note": "ADC channel wired to net %s (test point %s) is not "
                        "derivable; fill in the integer channel."
                        % (op.get("net"), op.get("refdes")),
            })
        elif kind == model.KIND_CURRENT:
            use(HOOK_ENTER_STATE, cid)
            use(HOOK_READ_CURRENT, cid)
            unresolved.append({
                "check": cid, "kind": kind, "hook": HOOK_ENTER_STATE,
                "parameter": "state_entry", "state": op.get("state"),
                "note": "driving the board into operating state %r is "
                        "firmware-specific." % op.get("state"),
            })
            unresolved.append({
                "check": cid, "kind": kind, "hook": HOOK_READ_CURRENT,
                "parameter": "current_sense", "rail": op.get("rail"),
                "state": op.get("state"),
                "note": "the current-sense method for rail %s is "
                        "board-specific." % op.get("rail"),
            })
        elif kind == model.KIND_I2C_SCAN:
            use(HOOK_I2C_SCAN, cid)
            unresolved.append({
                "check": cid, "kind": kind, "hook": HOOK_I2C_SCAN,
                "parameter": "bus_peripheral", "bus": op.get("bus"),
                "note": "mapping L1 bus %s to a hardware I2C peripheral index "
                        "is not derivable." % op.get("bus"),
            })
        elif kind == model.KIND_SIGNAL:
            use(HOOK_MEASURE_SIGNAL, cid)
            unresolved.append({
                "check": cid, "kind": kind, "hook": HOOK_MEASURE_SIGNAL,
                "parameter": "capture", "tp": op.get("net"),
                "refdes": op.get("refdes"),
                "note": "the signal-capture method for net %s (test point %s) "
                        "is board-specific." % (op.get("net"),
                                                op.get("refdes")),
            })

    # board serial is always an abstract read.
    unresolved.append({
        "check": None, "kind": None, "hook": HOOK_BOARD_SERIAL,
        "parameter": "board_serial",
        "note": "the board serial source is board-specific.",
    })

    hooks = [{"hook": name, "reason": _HOOK_REASON[name],
              "checks": sorted(hooks_used[name])}
             for name in sorted(hooks_used)]
    unresolved.sort(key=lambda u: (str(u.get("check")), u["hook"],
                                   u["parameter"]))
    return {
        "artifact": testplan.get("artifact"),
        "generated_by": "wyred_bench.selftest",
        "targets": list(TARGETS),
        "stamp": testplan.get("stamp"),
        "hooks": hooks,
        "unresolved": unresolved,
    }


# --------------------------------------------------------------------------
# rendering helpers
# --------------------------------------------------------------------------

def _stamp_compact(stamp: Any) -> str:
    """Canonical compact JSON for the stamp (sorted keys) — embedded verbatim
    so the emitted ``testplan_stamp`` matches the testplan's own stamp and the
    comparator does not refuse the measurement as stale."""
    return json.dumps(stamp, sort_keys=True, separators=(",", ":"))


def _c_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# --------------------------------------------------------------------------
# C emitter
# --------------------------------------------------------------------------

def render_c(testplan: dict, ops: list[dict]) -> str:
    artifact = testplan.get("artifact")
    stamp_json = _stamp_compact(testplan.get("stamp"))
    L: list[str] = []
    a = L.append

    a("/* %s.selftest.c -- GENERATED firmware self-test stub"
      % artifact)
    a(" *")
    a(" * Generated by wyred_bench.selftest from the derived testplan and the")
    a(" * frozen pinmap. Iterates every testplan check, calls the abstract")
    a(" * hardware hooks below, and writes a .measurements.json-shaped record")
    a(" * that wyred_bench.compare scores. DO NOT EDIT BY HAND -- regenerate.")
    a(" *")
    a(" * NOT IMPLEMENTED (see %s.selftest.NOT_IMPLEMENTED.json): every wb_*"
      % artifact)
    a(" * hook below is abstract. Provide them for the target MCU; nothing")
    a(" * here fabricates a register map.")
    a(" */")
    a("#include <stdio.h>")
    a("#include <stddef.h>")
    a("")
    a("/* --- abstract hardware hooks (NOT IMPLEMENTED) --- */")
    a("extern void        wb_enter_state(const char *state);")
    a("extern const char *wb_read_board_serial(void);")
    a("extern double      wb_adc_read_mv(const char *check_id, int channel);")
    a("extern double      wb_read_current_ma(const char *check_id,")
    a("                                      const char *rail,")
    a("                                      const char *state);")
    a("extern size_t      wb_i2c_scan(const char *check_id, const char *bus,")
    a("                               int *out_addrs, size_t max_addrs);")
    a("extern void        wb_measure_signal(const char *check_id,")
    a("                                     const char *tp,")
    a("                                     double *out_freq,")
    a("                                     double *out_duty);")
    a("")
    a("/* Per-rail ADC channel is NOT derivable (channel-to-pad mapping). The")
    a(" * TODO table below records each rail's unresolved channel; every rail")
    a(" * read passes this sentinel until an integrator fills the channel in. */")
    a("#define WB_ADC_CHANNEL_UNSET (-1)")
    a("")
    a("/* TODO (channel-to-pad mapping, NOT IMPLEMENTED):")
    rail_ops = [op for op in ops if op["kind"] == model.KIND_RAIL]
    if rail_ops:
        for op in rail_ops:
            a(" *   check %s -> ADC channel for net %s (test point %s)"
              % (op["id"], op.get("net"), op.get("refdes")))
    else:
        a(" *   (no rail checks)")
    a(" */")
    a("")
    a("int wb_run_selftest(FILE *out)")
    a("{")
    a('    fprintf(out, "{");')
    a('    fprintf(out, "\\"artifact\\":\\"%s\\",");' % _c_escape(artifact))
    a('    fprintf(out, "\\"board_serial\\":\\"%s\\",",'
      " wb_read_board_serial());")
    a('    fprintf(out, "\\"testplan_stamp\\":%s,");' % _c_escape(stamp_json))
    a('    fprintf(out, "\\"results\\":{");')
    for idx, op in enumerate(ops):
        a("")
        a("    /* [%s] check %s (%s) subject %s"
          % (op["band_label"], op["id"], op["kind"], op.get("subject")))
        a("     * %s */" % op["provenance"])
        a("    {")
        sep = "" if idx == 0 else ','  # comma BEFORE every result but the 1st
        if sep:
            a('        fprintf(out, ",");')
        a('        const char *cid = "%s";' % _c_escape(op["id"]))
        _c_render_op(a, op)
        a("    }")
    a("")
    a('    fprintf(out, "}");   /* results */')
    a('    fprintf(out, "}\\n"); /* record */')
    a("    return 0;")
    a("}")
    a("")
    a("int main(void)")
    a("{")
    a("    return wb_run_selftest(stdout);")
    a("}")
    return "\n".join(L) + "\n"


def _c_render_op(a, op: dict) -> None:
    kind = op["kind"]
    if kind == model.KIND_RAIL:
        a("        double mv = wb_adc_read_mv(cid, WB_ADC_CHANNEL_UNSET);")
        a('        fprintf(out, "\\"%s\\":{\\"unit\\":\\"V\\",'
          '\\"value\\":%.6g}", cid, mv / 1000.0);')
    elif kind == model.KIND_CURRENT:
        # state is a compile-time literal (known from the testplan); cid and
        # ma stay C printf placeholders, so build by concatenation to avoid a
        # Python-vs-C '%' collision.
        state = _c_escape(op.get("state") or "")
        rail = _c_escape(op.get("rail") or "")
        a('        wb_enter_state("' + state + '");')
        a('        double ma = wb_read_current_ma(cid, "' + rail + '", "'
          + state + '");')
        a('        fprintf(out, "\\"%s\\":{\\"state\\":\\"' + state
          + '\\",\\"unit\\":\\"mA\\",\\"value\\":%.6g}", cid, ma);')
    elif kind == model.KIND_I2C_SCAN:
        a("        int addrs[32];")
        a('        size_t n = wb_i2c_scan(cid, "%s", addrs, 32);'
          % _c_escape(op.get("bus") or ""))
        a('        size_t i;')
        a('        fprintf(out, "\\"%s\\":{\\"addrs\\":[", cid);')
        a("        for (i = 0; i < n; i++)")
        a('            fprintf(out, "%s%d", i ? "," : "", addrs[i]);')
        a('        fprintf(out, "]}");')
    elif kind == model.KIND_SIGNAL:
        a("        double freq = 0.0, duty = 0.0;")
        a('        wb_measure_signal(cid, "%s", &freq, &duty);'
          % _c_escape(op.get("net") or ""))
        # emit only the declared quantities, keys sorted for determinism.
        a('        fprintf(out, "\\"%s\\":{\\"values\\":{", cid);')
        for i, q in enumerate(sorted(op.get("quantities", []))):
            lead = "" if i == 0 else ","
            var = "freq" if q == "freq" else "duty"
            a('        fprintf(out, "%s\\"%s\\":%%.6g", %s);'
              % (lead, q, var))
        a('        fprintf(out, "}}");')


# --------------------------------------------------------------------------
# MicroPython emitter
# --------------------------------------------------------------------------

def render_py(testplan: dict, ops: list[dict]) -> str:
    artifact = testplan.get("artifact")
    stamp_json = _stamp_compact(testplan.get("stamp"))
    L: list[str] = []
    a = L.append

    a('"""%s.selftest.py -- GENERATED firmware self-test stub (MicroPython).'
      % artifact)
    a("")
    a("Iterates every testplan check, calls the abstract hardware hooks on the")
    a("injected ``hooks`` object, and returns a .measurements.json-shaped")
    a("record that wyred_bench.compare scores. DO NOT EDIT BY HAND -- "
      "regenerate.")
    a("")
    a("NOT IMPLEMENTED (see %s.selftest.NOT_IMPLEMENTED.json): every method on"
      % artifact)
    a("``Hooks`` is abstract. Subclass it for the target board; nothing here")
    a("fabricates a register map.")
    a('"""')
    a("")
    a("try:")
    a("    import ujson as json")
    a("except ImportError:")
    a("    import json")
    a("")
    a('ARTIFACT = "%s"' % artifact)
    a("# Embedded verbatim so the record stamp matches the testplan's own")
    a("# stamp (else wyred_bench.compare refuses the measurement as stale).")
    a("STAMP = json.loads('%s')" % stamp_json)
    a("# Per-rail ADC channel is NOT derivable; sentinel until an integrator")
    a("# fills it in. TODO (channel-to-pad mapping, NOT IMPLEMENTED):")
    rail_ops = [op for op in ops if op["kind"] == model.KIND_RAIL]
    if rail_ops:
        for op in rail_ops:
            a("#   check %s -> ADC channel for net %s (test point %s)"
              % (op["id"], op.get("net"), op.get("refdes")))
    else:
        a("#   (no rail checks)")
    a("ADC_CHANNEL_UNSET = None")
    a("")
    a("")
    a("class Hooks(object):")
    a('    """Abstract hardware access. Subclass and implement each method for')
    a("    the target MCU; every method here is in the NOT_IMPLEMENTED "
      "manifest.")
    a('    """')
    a("")
    a("    def enter_state(self, state):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: enter_state")')
    a("")
    a("    def read_board_serial(self):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: read_board_serial")')
    a("")
    a("    def adc_read_mv(self, check_id, channel):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: adc_read_mv")')
    a("")
    a("    def read_current_ma(self, check_id, rail, state):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: read_current_ma")')
    a("")
    a("    def i2c_scan(self, check_id, bus):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: i2c_scan")')
    a("")
    a("    def measure_signal(self, check_id, tp):")
    a('        raise NotImplementedError("NOT_IMPLEMENTED: measure_signal")')
    a("")
    a("")
    a("def run_selftest(hooks):")
    a('    """Run every check via ``hooks`` and return the measurement record')
    a("    dict (the .measurements.json shape wyred_bench.compare scores)."
      '"""')
    a("    results = {}")
    for op in ops:
        a("")
        a("    # [%s] check %s (%s) subject %s"
          % (op["band_label"], op["id"], op["kind"], op.get("subject")))
        a("    # %s" % op["provenance"])
        a('    cid = "%s"' % op["id"])
        _py_render_op(a, op)
    a("")
    a("    return {")
    a('        "artifact": ARTIFACT,')
    a('        "board_serial": hooks.read_board_serial(),')
    a('        "results": results,')
    a('        "testplan_stamp": STAMP,')
    a("    }")
    a("")
    a("")
    a("def main(argv=None):")
    a('    """Abstract-hook default run: prints the record as JSON. A real')
    a("    integrator calls run_selftest(MyHooks()) on-device instead."
      '"""')
    a("    import sys")
    a("    record = run_selftest(Hooks())")
    a("    sys.stdout.write(json.dumps(record))")
    a("    return 0")
    a("")
    a("")
    a('if __name__ == "__main__":')
    a("    import sys")
    a("    sys.exit(main(sys.argv[1:]))")
    return "\n".join(L) + "\n"


def _py_render_op(a, op: dict) -> None:
    kind = op["kind"]
    if kind == model.KIND_RAIL:
        a("    mv = hooks.adc_read_mv(cid, ADC_CHANNEL_UNSET)")
        a('    results[cid] = {"unit": "V", "value": mv / 1000.0}')
    elif kind == model.KIND_CURRENT:
        state = op.get("state")
        a("    hooks.enter_state(%r)" % state)
        a("    ma = hooks.read_current_ma(cid, %r, %r)"
          % (op.get("rail"), state))
        a('    results[cid] = {"state": %r, "unit": "mA", "value": ma}'
          % state)
    elif kind == model.KIND_I2C_SCAN:
        a("    addrs = hooks.i2c_scan(cid, %r)" % op.get("bus"))
        a('    results[cid] = {"addrs": [int(_a) for _a in addrs]}')
    elif kind == model.KIND_SIGNAL:
        a("    sig = hooks.measure_signal(cid, %r)" % op.get("net"))
        quantities = sorted(op.get("quantities", []))
        items = ", ".join('"%s": sig[%r]' % (q, q) for q in quantities)
        a('    results[cid] = {"values": {%s}}' % items)


# --------------------------------------------------------------------------
# top-level generate + CLI
# --------------------------------------------------------------------------

def generate(testplan: dict, pinmap: dict) -> dict:
    """Return ``{"c": str, "micropython": str, "manifest": dict}`` for a
    testplan validated against its pinmap. Raises SetupError on a testplan the
    generator cannot honestly stub (unprobeable / unknown kind)."""
    _validate_probes(testplan, pinmap)
    ops = plan_checks(testplan)
    return {
        TARGET_C: render_c(testplan, ops),
        TARGET_PY: render_py(testplan, ops),
        "manifest": build_manifest(testplan, ops),
    }


def _write_outputs(out_dir: Path, artifact: str, gen: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    c_path = out_dir / ("%s.selftest.c" % artifact)
    py_path = out_dir / ("%s.selftest.py" % artifact)
    man_path = out_dir / ("%s.selftest.NOT_IMPLEMENTED.json" % artifact)
    c_path.write_text(gen[TARGET_C], encoding="utf-8")
    py_path.write_text(gen[TARGET_PY], encoding="utf-8")
    man_path.write_text(canonical_str(gen["manifest"]), encoding="utf-8")
    return [c_path, py_path, man_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wyred_bench.selftest",
        description="Generate firmware self-test stubs (C + MicroPython) plus "
                    "a NOT_IMPLEMENTED manifest from a testplan + pinmap. The "
                    "stubs write a .measurements.json that wyred_bench.compare "
                    "scores.")
    parser.add_argument("--testplan", required=True, type=Path,
                        help="path to the <name>.testplan.json")
    parser.add_argument("--pinmap", required=True, type=Path,
                        help="path to the <name>.pinmap.json the testplan was "
                             "derived against (probe grounding, fail-closed)")
    parser.add_argument("--out-dir", type=Path,
                        help="write <name>.selftest.{c,py,NOT_IMPLEMENTED.json}"
                             " here")
    parser.add_argument("--target", choices=(*TARGETS, "manifest"),
                        help="print one artifact to stdout instead of writing "
                             "the set (c | micropython | manifest)")
    args = parser.parse_args(argv)

    try:
        testplan = read_json(args.testplan)
        pinmap = read_json(args.pinmap)
    except (OSError, ValueError) as exc:
        sys.stderr.write("setup error: %s\n" % exc)
        return 2

    try:
        gen = generate(testplan, pinmap)
    except SetupError as exc:
        sys.stderr.write("setup error: %s\n" % exc)
        return 2

    if args.target is not None:
        if args.target == "manifest":
            sys.stdout.write(canonical_str(gen["manifest"]))
        else:
            sys.stdout.write(gen[args.target])
        return 0

    if args.out_dir is None:
        sys.stderr.write("nothing to do: pass --out-dir or --target\n")
        return 2

    written = _write_outputs(args.out_dir, testplan.get("artifact"), gen)
    for p in written:
        sys.stdout.write("%s\n" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
