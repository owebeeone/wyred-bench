# Measurement records & the FLAT `expect` shapes

A `.measurements.json` is the record a technician (or a firmware self-test)
fills in with what the board actually did; the [`compare` CLI](compare.md)
scores it against the testplan. One oracle, two probe routes: a bench DMM and an
on-board firmware self-test write the **same** shape, graded by the same
comparator.

This page shows the record shape and the pinned FLAT testplan `expect` shapes it
is scored against. It is **not normative** — the shapes are
`dev-docs/ProposalTestplanContract.md` §5–§6, read in code through
`wyred-bench/src/wyred_bench/model.py` (`signal_band`) and the per-kind readers
in `compare.py` (`_compare_rail` / `_compare_current` / `_compare_i2c_scan` /
`_compare_signal`).

## The record shape (§6)

```json
{
  "artifact": "watchy_v1_bench",
  "board_serial": "SN-0001",
  "testplan_stamp": { "series": "A", "locks": { "external-interface": 0, "firmware-facing": 0 } },
  "state": "active",
  "results": { "<check_id>": { "...": "per-kind reading, below" } }
}
```

- `testplan_stamp` **must equal** the testplan's own `(series, locks)` stamp, or
  the record is refused (`STALE_STAMP`; see [verdict codes](verdict-codes.md)).
- `state` is the record-level operating state; a `current` result may override
  it per-result. `board_serial` and `state` are free strings.
- `results` maps each check id to a per-kind reading. A declared check with no
  entry FAILS (`CHECK_UNMEASURED`); an entry naming no declared check is
  `MEASUREMENT_UNKNOWN_CHECK`.

## Per-kind result shapes

| check kind | result shape | notes |
|---|---|---|
| `rail` | `{"unit": "V", "value": <number>}` | `unit` must be `V`, else `UNIT_MISMATCH` |
| `current` | `{"unit": "mA", "value": <number>, "state": "<str>"}` | `unit` must be `mA`; `state` matched exactly and may override the record `state` |
| `i2c_scan` | `{"addrs": [<int>, ...]}` | the exact set of addresses that answered |
| `signal` | `{"values": {"freq": <number>, "duty": <number>}}` | include **only** the quantities the check declared |

The all-pass record for the committed watchy testplan (only `freq` is declared
for its one signal, so only `freq` is measured):

```json
{
  "artifact": "watchy_v1_bench",
  "board_serial": "SN-0001",
  "results": {
    "batt_current": { "state": "active", "unit": "mA", "value": 120.0 },
    "i2c_accel":    { "addrs": [24] },
    "prog_signal":  { "values": { "freq": 115200.0 } },
    "rail_3v3":     { "unit": "V", "value": 3.3 }
  },
  "state": "active",
  "testplan_stamp": { "locks": { "external-interface": 0, "firmware-facing": 0 }, "series": "A" }
}
```

## The FLAT `expect` shapes (§5)

The testplan side each result is scored against. `expect` is **FLAT, pinned per
kind** (`dev-docs/ProposalTestplanContract.md` §5 — pinned 2026-07-13, closing
finding F1; nested forms are illegal):

| kind | `expect` shape |
|---|---|
| `rail` | `{"nominal": n, "low": l, "high": h}` — closed interval |
| `current` | `{"max_ma": m, "state": "<str>"}` — one-sided `≤` |
| `i2c_scan` | `{"addrs": [<int>, ...]}` — exact set |
| `signal` | `{"freq": n, "freq_low": l, "freq_high": h}` and/or `{"duty": d, "duty_low": l, "duty_high": h}` |

For `signal`, each trio is present **iff** its quantity was declared (RATIFY-5),
and your record measures exactly the declared quantities. The watchy example
declares only `freq`; a synthetic fixture declares `duty` (and one check
declares both `freq` and `duty`) — its all-pass record scores clean:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.compare --testplan wyred-bench/tests/fixtures/synthetic/synthetic_signals.testplan.json --measurements wyred-bench/tests/fixtures/synthetic/synthetic_allpass.measurements.json
# expect: VERDICT: PASS
```

### The FLAT shape is enforced

The `signal` `expect` is read in one place (`model.signal_band`) so the card
generator and the comparator can never drift on it. A **partial** trio (some but
not all of `{q, q_low, q_high}`) or a **nested** trio is a structured setup
error (`ExpectShapeError`, exit 2) — never a silent crash or a guessed bound.
The committed `synthetic_partial_trio` testplan declares `freq` without its
`freq_low`/`freq_high`, so the card generator refuses it:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ rc=0
$ python3 -m wyred_bench.card --testplan wyred-bench/tests/fixtures/synthetic/synthetic_partial_trio.testplan.json || rc=$?
$ echo "card-exit=$rc"
# expect: partial freq trio
# expect: card-exit=2
```

## Authoring checklist

- Copy `testplan_stamp` verbatim from the testplan's `stamp` (else `STALE_STAMP`).
- One `results` entry per declared check — no more (`MEASUREMENT_UNKNOWN_CHECK`),
  no fewer (`CHECK_UNMEASURED`).
- Use the canonical `unit` per kind (`V`, `mA`); give a `current` result the
  `state` the check expects.
- For a `signal`, put a reading under `values` for **each** declared quantity,
  and only those.

The comparator then scores the record — see [the `compare` CLI](compare.md) and
[verdict codes](verdict-codes.md).
