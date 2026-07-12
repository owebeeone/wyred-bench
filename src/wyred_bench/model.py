"""Shared vocabulary for the bench-card generator and the comparator.

The check kinds, the ordering policy, the contract verdict codes, and the
``(series, lock versions)`` stamp helpers live here so ``card.py`` and
``compare.py`` cannot drift from each other. Every name here traces to
``wyred-wz/dev-docs/ProposalTestplanContract.md``.
"""

from __future__ import annotations

from typing import Any

# Check kinds (ProposalTestplanContract.md §1/§5).
KIND_RAIL = "rail"
KIND_CURRENT = "current"
KIND_I2C_SCAN = "i2c_scan"
KIND_SIGNAL = "signal"
KINDS = (KIND_RAIL, KIND_CURRENT, KIND_I2C_SCAN, KIND_SIGNAL)

# Bench-card ordering policy (WyredPlanTestplan step 2.1): power-off /
# continuity -> power-on rails -> current -> buses -> signals. Lower band
# sorts first; within a band, checks sort by id. Continuity has no check kind
# yet (band 0 reserved) — the policy documents the slot regardless.
_ORDER_BAND = {
    KIND_RAIL: 1,
    KIND_CURRENT: 2,
    KIND_I2C_SCAN: 3,
    KIND_SIGNAL: 4,
}
_ORDER_BAND_LABEL = {
    0: "power-off / continuity",
    1: "power-on rails",
    2: "current",
    3: "buses",
    4: "signals",
}

# Contract verdict codes (ProposalTestplanContract.md §6). The comparator may
# emit only these on a comparison; STALE_STAMP is the separate refusal.
CODE_RAIL_OUT_OF_RANGE = "RAIL_OUT_OF_RANGE"
CODE_I2C_SCAN_MISSING_ADDR = "I2C_SCAN_MISSING_ADDR"
CODE_I2C_SCAN_UNEXPECTED_ADDR = "I2C_SCAN_UNEXPECTED_ADDR"
CODE_CURRENT_EXCEEDED = "CURRENT_EXCEEDED"
CODE_SIGNAL_OUT_OF_RANGE = "SIGNAL_OUT_OF_RANGE"
CODE_CHECK_UNMEASURED = "CHECK_UNMEASURED"
CODE_MEASUREMENT_UNKNOWN_CHECK = "MEASUREMENT_UNKNOWN_CHECK"
CODE_UNIT_MISMATCH = "UNIT_MISMATCH"
CODE_STATE_MISMATCH = "STATE_MISMATCH"
VERDICT_CODES = (
    CODE_RAIL_OUT_OF_RANGE,
    CODE_I2C_SCAN_MISSING_ADDR,
    CODE_I2C_SCAN_UNEXPECTED_ADDR,
    CODE_CURRENT_EXCEEDED,
    CODE_SIGNAL_OUT_OF_RANGE,
    CODE_CHECK_UNMEASURED,
    CODE_MEASUREMENT_UNKNOWN_CHECK,
    CODE_UNIT_MISMATCH,
    CODE_STATE_MISMATCH,
)
# The refusal (ProposalTestplanContract.md §6): a measurement whose stamp
# differs from the testplan's is refused, not compared. Not a per-check code.
CODE_STALE_STAMP = "STALE_STAMP"

# Expected canonical units per scalar quantity.
UNIT_RAIL = "V"
UNIT_CURRENT = "mA"
UNIT_FREQ = "Hz"
UNIT_DUTY = "%"


def order_band(kind: str) -> int:
    """Ordering band for a check kind (unknown kinds sort last)."""
    return _ORDER_BAND.get(kind, 99)


def band_label(band: int) -> str:
    return _ORDER_BAND_LABEL.get(band, "other")


def sorted_checks(checks: list[dict]) -> list[dict]:
    """Checks in bench-card station order: by band, then by id."""
    return sorted(checks, key=lambda c: (order_band(c.get("kind", "")),
                                         c.get("id", "")))


class ExpectShapeError(ValueError):
    """A testplan ``expect`` block violates the FLAT per-kind shape
    (ProposalTestplanContract §5) — e.g. a partial or nested signal trio. A
    *structured* error the card generator and the comparator both surface as a
    setup error, never a bare ``KeyError``/``TypeError``."""


def signal_band(expect: dict, qty: str) -> tuple[float, float, float] | None:
    """Read a signal quantity's FLAT trio from a check ``expect`` block.

    The signal ``expect`` shape is pinned FLAT (ProposalTestplanContract §5 —
    the shape the engine emits, ``wyred/src/wyred/paths.py``): the nominal is
    ``expect[qty]`` and its closed interval is ``expect[qty + "_low"]`` /
    ``expect[qty + "_high"]``. Both quantities (``freq``, ``duty``) are
    optional; a trio is present **iff** its quantity was declared (RATIFY-5).

    Returns ``(nominal, low, high)`` as floats, or ``None`` if the quantity was
    not declared. Reading it in ONE place keeps the card generator and the
    comparator from ever drifting on the shape again (the F1 defect). Illegal
    shapes are ``ExpectShapeError``, never a silent crash:

    - a **nested** trio (``expect[qty]`` is an object — the retired hand-authored
      form) is illegal; the flat form is normative;
    - a **partial** trio (some but not all of the three keys present) is illegal
      — never a partial trio.
    """
    nominal = expect.get(qty)
    low = expect.get("%s_low" % qty)
    high = expect.get("%s_high" % qty)
    if any(isinstance(v, dict) for v in (nominal, low, high)):
        raise ExpectShapeError(
            "signal expect for %r is nested (%r); the FLAT form "
            "{%s, %s_low, %s_high} is normative (ProposalTestplanContract §5)"
            % (qty, nominal, qty, qty, qty))
    present = [v is not None for v in (nominal, low, high)]
    if not any(present):
        return None
    if not all(present):
        raise ExpectShapeError(
            "signal expect has a partial %s trio (%s=%r, %s_low=%r, "
            "%s_high=%r): each trio is present in full or not at all "
            "(ProposalTestplanContract §5)"
            % (qty, qty, nominal, qty, low, qty, high))
    return float(nominal), float(low), float(high)


def stamp_key(stamp: dict[str, Any] | None) -> tuple:
    """A hashable, order-independent key for a ``(series, locks)`` stamp, so
    two stamps compare equal iff series and every lock version match."""
    stamp = stamp or {}
    locks = stamp.get("locks", {}) or {}
    return (stamp.get("series"),
            tuple(sorted((str(k), v) for k, v in locks.items())))


def stamp_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return stamp_key(a) == stamp_key(b)


def stamp_display(stamp: dict[str, Any] | None) -> str:
    """One-line ``series A; locks external-interface=0, firmware-facing=0``
    rendering for card headers and refusal messages."""
    stamp = stamp or {}
    locks = stamp.get("locks", {}) or {}
    lock_str = ", ".join("%s=%s" % (k, locks[k]) for k in sorted(locks))
    return "series %s; locks %s" % (stamp.get("series"), lock_str or "(none)")
