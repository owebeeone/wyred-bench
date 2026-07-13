# Verdict codes

The comparator's findings are **contract vocabulary**
(`dev-docs/ProposalTestplanContract.md` §6); in code they are
`model.VERDICT_CODES` plus the separate refusal `model.CODE_STALE_STAMP`
(`wyred-bench/src/wyred_bench/model.py`). This page names each and shows the
battery that provokes it — it does not define them; the proposal and `model.py`
do. A `compare` run may emit **only** these codes on a comparison.

## The comparison codes

Each row's fixture is a `.measurements.json` in
`wyred-bench/tests/fixtures/measurements/` that provokes exactly that code when
scored against the committed `watchy_v1_bench.testplan.json`.

| code | fires when | check kind | fixture |
|---|---|---|---|
| `RAIL_OUT_OF_RANGE` | a rail reading falls outside its closed `[low, high]` interval | `rail` | `rail_out_of_range` |
| `CURRENT_EXCEEDED` | a current reading exceeds the one-sided `max_ma` bound | `current` | `current_exceeded` |
| `I2C_SCAN_MISSING_ADDR` | an expected I2C address did not answer | `i2c_scan` | `i2c_missing_addr` |
| `I2C_SCAN_UNEXPECTED_ADDR` | an **unexpected** address answered — exact set; a rogue device is a disagreement | `i2c_scan` | `i2c_unexpected_addr` |
| `SIGNAL_OUT_OF_RANGE` | a signal `freq`/`duty` reading falls outside its closed interval | `signal` | `signal_out_of_range` |
| `UNIT_MISMATCH` | a result's `unit` is not the check's canonical unit (`V` for rail, `mA` for current) | `rail`, `current` | `unit_mismatch` |
| `STATE_MISMATCH` | a current result's `state` does not exactly match the testplan's | `current` | `state_mismatch` |
| `CHECK_UNMEASURED` | a declared check has no result in the record | any | `check_unmeasured` |
| `MEASUREMENT_UNKNOWN_CHECK` | a result names a check the testplan does not declare | any | `measurement_unknown_check` |

The ratified interval semantics behind these codes — closed intervals with no
epsilon (RATIFY-7), exact-set I2C (RATIFY-6), one-sided current with an exact
free-string `state` (RATIFY-4) — are in `dev-docs/ProposalTestplanContract.md`
§4. This page does not restate them.

## The refusal

| code | rule | outcome |
|---|---|---|
| `STALE_STAMP` | a record whose `testplan_stamp` differs from the testplan's `(series, locks)` stamp | **refused, not compared** — verdict `REFUSED`, exit 2 |

`STALE_STAMP` is not a per-check finding: it is the whole record being turned
away before any comparison runs. See the refusal example in
[the `compare` CLI](compare.md#stale-stamp-refusal-exit-2).

## Every code, provoked

One block scores the whole battery and asserts each fixture emits its code — the
same oracle the member's own `tests/run_tests.py` enforces. Each `compare` here
is expected to fail (a finding, exit 1), so its output is captured before the
code is grepped:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ tp=wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json
$ md=wyred-bench/tests/fixtures/measurements
$ for pair in rail_out_of_range:RAIL_OUT_OF_RANGE current_exceeded:CURRENT_EXCEEDED i2c_missing_addr:I2C_SCAN_MISSING_ADDR i2c_unexpected_addr:I2C_SCAN_UNEXPECTED_ADDR signal_out_of_range:SIGNAL_OUT_OF_RANGE unit_mismatch:UNIT_MISMATCH state_mismatch:STATE_MISMATCH check_unmeasured:CHECK_UNMEASURED measurement_unknown_check:MEASUREMENT_UNKNOWN_CHECK; do
$   fx="${pair%%:*}"; code="${pair##*:}"
$   out="$(python3 -m wyred_bench.compare --testplan "$tp" --measurements "$md/$fx.measurements.json" 2>&1 || true)"
$   printf '%s\n' "$out" | grep -q "$code" || { echo "MISSING $code from $fx"; exit 7; }
$   echo "ok $fx -> $code"
$ done
# expect: ok rail_out_of_range -> RAIL_OUT_OF_RANGE
# expect: ok measurement_unknown_check -> MEASUREMENT_UNKNOWN_CHECK
```

If any fixture ever stopped emitting its code, the loop exits non-zero and this
example goes red.
