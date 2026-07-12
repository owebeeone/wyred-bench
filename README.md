# wyred-bench — the oracle extended into physics

Generated physical test harnesses derived from committed contract artifacts.
Given only a `.testplan.json` (and, where needed, a `.pinmap.json`),
wyred-bench turns the engine's derived test intent into three consumer-facing
outputs:

- **a bench card** — an ordered, human-readable check card for a technician
  at a probe station (`python3 -m wyred_bench.card`);
- **a measurement verdict** — the mechanical oracle that scores a filled-in
  `.measurements.json` against the testplan, gate-red on any disagreement
  (`python3 -m wyred_bench.compare`);
- **firmware self-test stubs** — a C module and a MicroPython module,
  generated from the testplan + pinmap, that iterate the checks and emit the
  same `.measurements.json` shape the comparator scores (one oracle, two probe
  routes — bench DMM and on-board firmware) (`python3 -m wyred_bench.selftest`).

It **depends on wyred-contract only** and never imports the engine: it meets
`wyred`, `wyred-harness`, and `wyred-audit` at artifacts on disk (the star
topology). Pure stdlib, no dependencies. Ratified semantics:
`wyred-wz/dev-docs/ProposalTestplanContract.md` §4–§6.

## Usage

```sh
# render a bench card from a testplan
python3 -m wyred_bench.card \
    --testplan watchy_v1_bench.testplan.json \
    --out watchy_v1_bench.benchcard.md

# score a filled-in measurement record against the testplan
python3 -m wyred_bench.compare \
    --testplan watchy_v1_bench.testplan.json \
    --measurements watchy_v1_bench.measurements.json \
    --out watchy_v1_bench.verdict.json

# generate firmware self-test stubs (C + MicroPython) + a NOT_IMPLEMENTED
# manifest; the stubs write a .measurements.json this same comparator scores
python3 -m wyred_bench.selftest \
    --testplan watchy_v1_bench.testplan.json \
    --pinmap  watchy_v1.pinmap.json \
    --out-dir ./out
```

`compare` exits **0** iff every declared check was measured and agreed; **1**
on any comparison finding; **2** on a stale-stamp refusal or a setup error.
Every finding names its contract verdict code on stdout.

## Verdict codes (contract vocabulary — `ProposalTestplanContract.md` §6)

`RAIL_OUT_OF_RANGE`, `I2C_SCAN_MISSING_ADDR`, `I2C_SCAN_UNEXPECTED_ADDR`,
`CURRENT_EXCEEDED`, `SIGNAL_OUT_OF_RANGE`, `CHECK_UNMEASURED`,
`MEASUREMENT_UNKNOWN_CHECK`, `UNIT_MISMATCH`, `STATE_MISMATCH`, plus the
refusal `STALE_STAMP` (a measurement whose stamp differs from the testplan's
is refused, not compared).

## Bench-card ordering policy

Checks are rendered in station order, then by check id within a band:

1. **power-off / continuity** (deferred — no continuity check kind yet);
2. **power-on rails** (`rail`);
3. **current** (`current`);
4. **buses** (`i2c_scan`);
5. **signals** (`signal`).

## What is implemented

- `wyred_bench.card` — bench-card renderer (ordered, byte-deterministic).
- `wyred_bench.compare` — the measurement comparator / oracle, with the full
  verdict-code set, closed-interval semantics (RATIFY-7), exact-set I2C
  (RATIFY-6), one-sided current + exact `state` (RATIFY-4), and stale-stamp
  refusal.
- `wyred_bench.selftest` — the firmware self-test **stub** generator
  (WyredPlanTestplan step 3.1). From `testplan + pinmap` it emits a C module
  and a MicroPython module that iterate the checks (rail → ADC read, bus →
  I2C scan, current → sensed read, signal → capture) and write a
  `.measurements.json` scored by `wyred_bench.compare`. Hardware access is
  **abstract hooks** (`adc_read_mv`, `i2c_scan`, `read_current_ma`,
  `measure_signal`, `enter_state`, `read_board_serial`); everything not
  derivable from the artifacts (ADC channel-to-pad mapping, I2C peripheral
  index, capture method, …) is left abstract and enumerated in a
  `<name>.selftest.NOT_IMPLEMENTED.json` manifest — the generator never
  fabricates a register map. Probe points are cross-checked against the
  pinmap's realized `test_point` components (fail-closed:
  `SELFTEST_UNPROBEABLE`).
- `tests/` — the testplan fixture (hand-verified `ProposalTestplanContract.md`
  §5 worked example over the frozen watchy goldens), a committed bench-card
  snapshot, the measurement fixture battery (all-pass, one per verdict code,
  min/max boundary cases, stale-stamp), and the committed self-test stub
  snapshots under `tests/fixtures/selftest/`.

## Deferred (explicitly)

- **The physical loop** (WyredPlanTestplan Phase 4) — a fabbed board serial's
  measurements gate-wired like the board-agreement probes; awaits a board.
- **Contract landing** — the testplan / measurement schemas are contract
  vocabulary; they land in `wyred-contract` via the single-writer flow
  (`ProposalTestplanContract.md`), not from this member's feature work.
