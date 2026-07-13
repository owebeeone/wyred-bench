# wyred-bench reference

`wyred-bench` is **the oracle extended into physics**: from committed contract
artifacts alone — a derived `.testplan.json` (plus a `.pinmap.json` where a tool
needs realized probe points) — it produces the outputs a bench technician and a
firmware integrator work from. It **depends on `wyred-contract` only** and never
imports the engine (`wyred`); it meets `wyred`, `wyred-harness`, and
`wyred-audit` at **artifacts on disk** (the star topology, depth 1). Pure Python
standard library, no dependencies.

These pages are reference material for the wyred-bench command surface. They are
**not normative**. The testplan / measurement / verdict *semantics* — the FLAT
`expect` shapes, the closed-interval and exact-set rules (RATIFY-1…7), and the
verdict-code vocabulary — live in `dev-docs/ProposalTestplanContract.md` §4–§6,
and their in-code embodiment is `wyred-bench/src/wyred_bench/model.py` (every
name there traces to that proposal). The pages here explain how to *run* the
tools and *point at* those sources; where a page and the contract disagree, the
page is the defect.

!!! note "The schemas have not landed yet"
    The testplan and measurement records are **contract vocabulary** that lands
    in `wyred-contract/schemas/` via the single-writer flow, after the
    proposal's ratification (`wyred-bench/README.md` → *Deferred*). Until then
    there is no `testplan.schema.json` to link, and
    `dev-docs/ProposalTestplanContract.md` §4–§6 plus `model.py` are the
    authoritative sources.

## Pages

- **[The `card` CLI](card.md)** — render a testplan as an ordered,
  human-readable bench card for a probe station.
- **[The `compare` CLI](compare.md)** — score a filled-in measurement record
  against the testplan; THE oracle, gate-red on any disagreement.
- **[Verdict codes](verdict-codes.md)** — the comparator's contract-vocabulary
  findings, plus the stale-stamp refusal.
- **[Measurement records & the FLAT `expect` shapes](measurement-records.md)** —
  how to author a `.measurements.json`, the per-kind result shapes, and the
  pinned FLAT testplan `expect` shapes it is scored against.
- **[The `selftest` CLI](selftest.md)** — generate firmware self-test stubs
  (C + MicroPython) that write the same measurement shape the comparator scores.

## Running these commands

wyred-bench is a `src/`-layout package. Every runnable example in these pages
runs from the **workspace root** with `wyred-bench/src` on `PYTHONPATH`:

```text
PYTHONPATH=wyred-bench/src python3 -m wyred_bench.card --help
```

The `[project.scripts]` console entry points — `wyred-bench-card`,
`wyred-bench-compare`, `wyred-bench-selftest` — are available instead once the
package is installed. As a smoke test, the module runs and advertises its flags:

<!-- pythonpath: wyred-bench/src -->
<!-- cwd: . -->
```console
$ python3 -m wyred_bench.card --help
# expect: --testplan
```

The one committed worked example — the engine-emitted
`watchy_v1_bench.testplan.json` — lives at
`wyred-bench/tests/fixtures/watchy_v1_bench.testplan.json` (byte-identical to
`wyred-examples/testplan_expected/`); the pages below render and score it, and
the measurement battery beside it in `tests/fixtures/measurements/`.
