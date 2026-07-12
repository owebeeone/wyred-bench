"""Canonical JSON I/O — the byte-determinism discipline (RATIFY-7).

Every artifact wyred-bench WRITES (verdict artifacts) is serialized exactly
the way the engine writes its goldens: ``json.dumps(obj, indent=2,
sort_keys=True) + "\\n"``. That is the discipline that lets a bench card and a
verdict be byte-compared across runs, and it is verified byte-for-byte against
the frozen goldens' own formatting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonical_str(obj: Any) -> str:
    """Return the canonical JSON text for ``obj`` (sorted keys, 2-space
    indent, trailing newline) — identical to the engine's golden format."""
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def write_canonical(path: str | Path, obj: Any) -> None:
    """Write ``obj`` to ``path`` as canonical JSON, UTF-8, no BOM."""
    Path(path).write_text(canonical_str(obj), encoding="utf-8")


def read_json(path: str | Path) -> Any:
    """Read and parse a JSON artifact from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
