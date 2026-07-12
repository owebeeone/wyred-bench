# wyred-bench — boundary rules

- **Depends on wyred-contract only** (testplan / pinmap / measurement
  schemas, goldens, fixtures). Never imports `wyred`, `wyred-harness`, or
  `wyred-audit`; it meets them at **artifacts on disk** (the star topology,
  depth 1). Python, **stdlib-only** — no new dependencies.
- Cross-repo composition is **subprocess-only**: wyred-bench reads a
  committed `.testplan.json` (+ pinmap where needed) and a filled-in
  `.measurements.json`; it never calls the engine to derive them. A bench
  card and a measurement verdict must be derivable from the artifacts alone.
- **The comparator is the oracle §3.3 promises** — a measured board vs the
  testplan, mechanical, gate-red on disagreement. Its verdict codes are
  contract vocabulary (`ProposalTestplanContract.md` §6); keep them in
  lockstep with that proposal. An unmeasured check is a FAILURE
  (`CHECK_UNMEASURED`), never a silent omission — no silent defaults extends
  into physics (law 10).
- **Ratified interval semantics** live in `ProposalTestplanContract.md`
  §4–§6 (RATIFY-1…7). Closed intervals (a value exactly at a bound PASSES,
  RATIFY-7); I2C scan is exact-set (RATIFY-6); current is one-sided ≤ with a
  free-string `state` matched exactly (RATIFY-4). The comparator compares
  parsed floats against the testplan's stored bounds exactly — **no epsilon**
  (RATIFY-7): the bounds already encode the acceptable band.
- **Stale-stamp refusal:** a measurement record whose `testplan_stamp`
  differs from the testplan's own `(series, lock versions)` stamp is
  **refused, not compared**.
- Canonical JSON everywhere the tool WRITES (`json.dumps(obj, indent=2,
  sort_keys=True) + "\n"`) so byte-determinism survives ranges and physical
  measurements. Bench cards and verdict artifacts are byte-deterministic
  across runs.
- Test fixtures live under `tests/fixtures/`; the testplan fixture is the
  hand-verified `ProposalTestplanContract.md` §5 worked example (goldens
  carry no testplan, so it is verified against the frozen watchy goldens by
  hand, never emitted here). Acceptance: `python3 tests/run_tests.py` —
  card snapshot byte-identical + every verdict code provoked + boundary /
  stale-stamp cases. Never hand-edit a committed snapshot; regenerate it
  from the tool.
- README.md lists what IS implemented and what is explicitly deferred; keep
  both honest when changing scope.
