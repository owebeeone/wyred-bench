# The `card` CLI — `python3 -m wyred_bench.card`

Renders a derived `.testplan.json` as an ordered, human-readable check card
(Markdown) for a technician at a probe station. It derives from the **testplan
artifact alone** — resolved probe points, expected values, and ranges are
embedded — so no engine or pinmap is needed. The output is byte-deterministic
(no timestamps, sorted provenance): snapshot-comparable across runs.

## Synopsis

```text
python3 -m wyred_bench.card --testplan T.testplan.json [--out T.benchcard.md]
```

## Flags

| flag | required | type | meaning |
|---|---|---|---|
| `--testplan` | yes | path | the `<name>.testplan.json` to render |
| `--out` | no | path | write the Markdown here; default: stdout |

Both flags are greppable in the source:
`grep -n add_argument wyred-bench/src/wyred_bench/card.py`.

## Exit codes

| exit | meaning |
|---|---|
| 0 | card rendered |
| 2 | setup error — the testplan could not be read, or its `expect` block violated the FLAT shape (see [measurement records](measurement-records.md#the-flat-shape-is-enforced)) |

## Ordering policy

Checks render in station order, then by check id within a band
(`WyredPlanTestplan` step 2.1; the bands are `_ORDER_BAND` in
`wyred-bench/src/wyred_bench/model.py`). Every check appears exactly once.

| band | heading | check kind |
|---|---|---|
| 0 | power-off / continuity | *(reserved — no continuity check kind yet)* |
| 1 | power-on rails | `rail` |
| 2 | current | `current` |
| 3 | buses | `i2c_scan` |
| 4 | signals | `signal` |

## Render a card

Render the committed worked example to stdout:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.card --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json
# expect: Bench card
# expect: power-on rails
```

Its first entries look like this (one section per band, one numbered card per
check):

```text
# Bench card — watchy_v1_bench

- Stamp: series A; locks external-interface=0, firmware-facing=0
- Ordering: power-off / continuity -> power-on rails -> current -> buses -> signals; then by check id.
- Every check appears exactly once. Record measurements in a `.measurements.json` and score them with `python3 -m wyred_bench.compare`.

## power-on rails

### 1. rail_3v3  (rail)

- Subject: rail +3V3
- Expected: 3.3 V, range [3.135, 3.465] V
- Probe: TP4 pad 1 (net +3V3); ground TP5 pad 1 (net GND)
- Instrument: DMM DC volts on TP4 referenced to TP5
- Provenance: declared by rail_3v3; derived from (none)
```

Each card carries the check's expected value + range, the resolved probe points
and ground reference, a suggested instrument, and provenance back to the
declaration.

## Write to a file

`--out` writes the same bytes to a path. Here it goes to a scratch directory, so
nothing in any repo tree is touched:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ out="$(mktemp -d)"
$ python3 -m wyred_bench.card --testplan wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json --out "$out/watchy_v1_bench.benchcard.md"
$ head -1 "$out/watchy_v1_bench.benchcard.md"
$ rm -rf "$out"
# expect: Bench card
```

Once the card is filled in on the bench, record the readings in a
`.measurements.json` and score them with the [`compare` CLI](compare.md).
