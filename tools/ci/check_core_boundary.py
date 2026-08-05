#!/usr/bin/env python3
"""CI boundary guard for the Real-Time Digital Twins core/specialization split.

Fails (non-zero exit) if the use-case-agnostic core (``source/core/**``) takes on a
dependency on the automotive-aero specialization. This enforces the boundary invariant:
*delete ``source/specializations/auto-aero/`` and the core still builds.*

Checks
------
1. No ``source/core`` ``extension.toml`` declares a dependency on a specialization
   module (``omni.rtwt.auto_aero.*``).
2. No ``source/core`` Python imports a specialization module or hardcodes the
   ``source/specializations`` path.
3. No ``source/core`` Python hardcodes a specialization AppState schema-name literal
   (``RtwtInferenceAppStateAPI`` / ``RtwtVizAppStateAPI``); these are supplied via carb
   settings. No core site hardcodes them, so the allowlist is empty and the guard FAILS
   on *any* occurrence under ``source/core``.

Usage
-----
    python3 tools/ci/check_core_boundary.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "source" / "core"

# Specialization namespace / on-disk path that core must never reference.
SPEC_MODULE_RE = re.compile(r"omni\.rtwt\.auto_aero")
SPEC_PATH_RE = re.compile(r"source/specializations")

# Specialization AppState schema-name literals that must not be hardcoded in core.
SPEC_SCHEMA_LITERALS = ("RtwtInferenceAppStateAPI", "RtwtVizAppStateAPI")

# The specialization AppState schema names are supplied via carb settings
# (exts."omni.rtwt.controller".app_state_api_schemas /
#  exts."omni.rtwt.inference".app_state_api_schemas), so this allowlist is empty:
# the guard FAILS on any occurrence of these literals anywhere under source/core.
LITERAL_ALLOWLIST: set[str] = set()


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _first_line_with(text: str, needle: str) -> int:
    for n, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return n
    return 0


def main() -> int:
    if not CORE.is_dir():
        print(f"[boundary-guard] ERROR: core dir not found: {_rel(CORE)}", file=sys.stderr)
        return 2

    violations: list[str] = []

    # Check 1: extension.toml dependencies on specialization modules.
    for toml in sorted(CORE.rglob("config/extension.toml")):
        for i, line in enumerate(toml.read_text(encoding="utf-8").splitlines(), 1):
            if SPEC_MODULE_RE.search(line):
                violations.append(
                    f"{_rel(toml)}:{i}: core extension depends on a specialization "
                    f"module -> {line.strip()}"
                )

    # Checks 2 & 3: python imports / path refs / hardcoded schema-name literals.
    for py in sorted(CORE.rglob("*.py")):
        relpath = _rel(py)
        text = py.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if ("import" in line and SPEC_MODULE_RE.search(line)) or SPEC_PATH_RE.search(line):
                violations.append(
                    f"{relpath}:{i}: core references the specialization -> {line.strip()}"
                )
        if relpath not in LITERAL_ALLOWLIST:
            for literal in SPEC_SCHEMA_LITERALS:
                if literal in text:
                    violations.append(
                        f"{relpath}:{_first_line_with(text, literal)}: core hardcodes "
                        f"specialization schema name '{literal}' -- move it to a carb "
                        f"setting"
                    )

    if violations:
        print("[boundary-guard] FAIL: core -> specialization coupling detected:\n", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(f"\n[boundary-guard] {len(violations)} violation(s).", file=sys.stderr)
        return 1

    print("[boundary-guard] OK: no core -> specialization dependency.")

    pending = []
    for relpath in sorted(LITERAL_ALLOWLIST):
        fp = REPO_ROOT / relpath
        if fp.is_file() and any(lit in fp.read_text(encoding="utf-8", errors="replace")
                                for lit in SPEC_SCHEMA_LITERALS):
            pending.append(relpath)
    if pending:
        print(f"[boundary-guard] NOTE: {len(pending)} core file(s) still hardcode a "
              f"specialization schema name (allowlisted):")
        for relpath in pending:
            print(f"    - {relpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
