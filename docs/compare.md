# The `compare` CLI — `python3 -m wyred_bench.compare`

**THE oracle** (`dev-docs/WyredWorkflowDesign.md` §3.3). Scores a filled-in
`.measurements.json` against a derived `.testplan.json` and emits a structured
verdict plus a non-zero exit on any disagreement — the measured board vs the
testplan, mechanical, gate-red on disagreement. It reads two artifacts on disk
and never calls the engine.

## Synopsis

```text
python3 -m wyred_bench.compare --testplan T.testplan.json --measurements M.measurements.json [--out V.verdict.json]
```

## Flags

| flag | required | type | meaning |
|---|---|---|---|
| `--testplan` | yes | path | the `<name>.testplan.json` |
| `--measurements` | yes | path | the filled-in `<name>.measurements.json` |
| `--out` | no | path | write the canonical-JSON verdict artifact here |

All three flags are greppable in the source:
`grep -n add_argument wyred-bench/src/wyred_bench/compare.py`.

## Exit codes

| exit | status | meaning |
|---|---|---|
| 0 | `PASS` | every declared check was measured and agreed |
| 1 | `FAIL` | one or more comparison findings (see [verdict codes](verdict-codes.md)) |
| 2 | `REFUSED` / setup error | a stale-stamp refusal, or an unreadable / malformed input |

An **unmeasured check is a FAILURE** (`CHECK_UNMEASURED`), never a silent
omission — no silent defaults extends into physics.

## Output

`compare` always prints a human report to stdout — a `PASS`/`FAIL` line per
check, then the findings, then a `VERDICT:` line. With `--out` it additionally
writes the **canonical-JSON verdict artifact** (sorted keys, two-space indent) —
byte-identical across runs; without `--out` that same JSON is appended to stdout
for piping.

## A passing board

Score the all-pass record in the fixture battery; exit 0:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.compare --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --measurements wyred-bench/tests/fixtures/measurements/allpass.measurements.json
# expect: VERDICT: PASS
```

Report:

```text
artifact: watchy_v1_bench   board: SN-0001   stamp: [series A; locks external-interface=0, firmware-facing=0]
PASS batt_current                 current
PASS i2c_accel                    i2c_scan
PASS prog_signal                  signal
PASS rail_3v3                     rail
VERDICT: PASS (0 finding(s))
```

## A disagreement (non-zero exit)

A rail reading outside its closed interval fails with `RAIL_OUT_OF_RANGE` and
exit **1**. Because a failing verdict exits non-zero, a `set -e` script (or this
doc-test) must capture the code rather than let it abort:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ rc=0
$ python3 -m wyred_bench.compare --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --measurements wyred-bench/tests/fixtures/measurements/rail_out_of_range.measurements.json || rc=$?
$ echo "verdict-exit=$rc"
# expect: RAIL_OUT_OF_RANGE
# expect: verdict-exit=1
```

The report names the failing check and its code:

```text
FAIL rail_3v3                     rail  <RAIL_OUT_OF_RANGE>
  rail_3v3                   RAIL_OUT_OF_RANGE: measured 3.6 V outside [3.135, 3.465] (nominal 3.3)
VERDICT: FAIL (1 finding(s))
```

## Closed intervals (RATIFY-7)

A value **exactly at a stored bound passes** — the comparator compares parsed
floats against the testplan's bounds with no epsilon
(`dev-docs/ProposalTestplanContract.md` §4, RATIFY-7). The `boundary_high`
record sits every reading on its upper bound and still passes:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.compare --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --measurements wyred-bench/tests/fixtures/measurements/boundary_high.measurements.json
# expect: VERDICT: PASS
```

## Stale-stamp refusal (exit 2)

A measurement whose `testplan_stamp` differs from the testplan's own
`(series, locks)` stamp is **refused, not compared** — a distinct outcome from a
comparison `FAIL`, exit **2**:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ rc=0
$ python3 -m wyred_bench.compare --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --measurements wyred-bench/tests/fixtures/measurements/stale_stamp.measurements.json || rc=$?
$ echo "refusal-exit=$rc"
# expect: VERDICT: REFUSED
# expect: STALE_STAMP
# expect: refusal-exit=2
```

See [verdict codes](verdict-codes.md) for the full finding vocabulary and
[measurement records](measurement-records.md) for the record shape the
comparator scores.
