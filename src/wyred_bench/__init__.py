"""wyred-bench — the oracle extended into physics.

wyred-bench turns a derived, committed ``.testplan.json`` into two
consumer-facing outputs, deriving both from artifacts on disk without ever
importing the engine (the star topology, depth 1 — see ``CLAUDE.md``):

- ``wyred_bench.card`` renders an ordered, human-readable bench card;
- ``wyred_bench.compare`` scores a filled-in ``.measurements.json`` against
  the testplan, gate-red on any disagreement — the oracle
  ``WyredWorkflowDesign`` §3.3 promises.

Ratified interval semantics (closed intervals, exact-set I2C, one-sided
current + exact ``state``, stale-stamp refusal) live in
``wyred-wz/dev-docs/ProposalTestplanContract.md`` §4-§6. Pure stdlib.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
