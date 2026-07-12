"""``python3 -m wyred_bench`` — usage banner pointing at the two tools.

The real entry points are the submodule mains: ``python3 -m wyred_bench.card``
and ``python3 -m wyred_bench.compare``.
"""

import sys

USAGE = (
    "wyred-bench: the oracle extended into physics\n"
    "\n"
    "  python3 -m wyred_bench.card     --testplan T.testplan.json "
    "--out T.benchcard.md\n"
    "  python3 -m wyred_bench.compare  --testplan T.testplan.json "
    "--measurements M.measurements.json [--out V.verdict.json]\n"
    "  python3 -m wyred_bench.selftest --testplan T.testplan.json "
    "--pinmap T.pinmap.json --out-dir DIR\n"
)


def main() -> int:
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
