#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Run RTDT Kit-hosted validator smoke fixtures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = SCRIPT_DIR / "prompts"
REPO_ROOT = SCRIPT_DIR.parents[1]
VALIDATE = REPO_ROOT / "tools" / "validate" / "rtdt-validate.sh"


def load_evals() -> dict[str, dict]:
    evals: dict[str, dict] = {}
    for path in sorted(PROMPTS_DIR.glob("*.toml")):
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        data["_key"] = path.stem
        evals[path.stem] = data
    return evals


def resolve_key(evals: Mapping[str, dict], key: str) -> str:
    if key in evals:
        return key
    matches = [
        candidate
        for candidate in evals
        if candidate.startswith(key) or candidate.split("_", 1)[0] == key
    ]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"eval '{key}' not found or ambiguous (use --list)")


def _absolute(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return str(candidate)


def _validate_command(spec: Mapping) -> list[str]:
    command = [
        str(VALIDATE),
        "--format",
        "json",
        "--manifest",
        _absolute(spec["manifest"]),
    ]
    if schemas := spec.get("schemas"):
        command.extend(["--schemas", *schemas])
    if plugins := spec.get("schema_plugins"):
        command.extend(["--schema-plugins", *(_absolute(path) for path in plugins)])
    if stage := spec.get("stage"):
        command.extend(["--stage", _absolute(stage)])
    if callbacks := spec.get("callbacks"):
        command.extend(["--callbacks", *callbacks])
    if app := spec.get("app"):
        command.extend(["--app", app])
    return command


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "pass": bool(passed), "detail": detail}


def _result(name: str, checks: list[dict]) -> dict:
    passed = sum(1 for check in checks if check["pass"])
    total = len(checks)
    return {
        "eval": name,
        "pass": total > 0 and passed == total,
        "score": round(passed / total * 100) if total else 0,
        "checks": checks,
    }


def run_validator(ev: Mapping, timeout: int) -> dict:
    spec = ev["validate"]
    expect = ev.get("expect", {})
    checks: list[dict] = []
    try:
        completed = subprocess.run(
            _validate_command(spec),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _result(
            ev["_key"],
            [_check("validator_completed", False, f"timed out after {timeout} seconds")],
        )
    except OSError as error:
        return _result(
            ev["_key"],
            [_check("validator_completed", False, f"could not launch: {error}")],
        )

    report = None
    try:
        report = json.loads(completed.stdout.strip())
    except (json.JSONDecodeError, TypeError):
        detail = (completed.stdout + completed.stderr).strip()[-800:]
        checks.append(_check("validator_report", False, detail or "empty output"))

    if not isinstance(report, dict) or not isinstance(report.get("ok"), bool):
        if report is not None:
            checks.append(
                _check("validator_report", False, "report must be an object with boolean 'ok'")
            )
        return _result(ev["_key"], checks)

    if fatal := report.get("error"):
        checks.append(_check("validator_report", False, f"fatal validator error: {fatal}"))
        return _result(ev["_key"], checks)

    checks.append(
        _check("validator_report", True, str(report.get("summary", "structured report")))
    )

    expected_ok = bool(expect.get("ok", True))
    checks.append(
        _check(
            f"ok=={expected_ok}",
            report["ok"] is expected_ok,
            f"reported ok={report['ok']}",
        )
    )

    expected_returncode = 0 if expected_ok else 1
    checks.append(
        _check(
            "exit_status",
            completed.returncode == expected_returncode,
            f"expected {expected_returncode}, got {completed.returncode}",
        )
    )

    if needle := expect.get("error_contains"):
        errors = report.get("errors")
        hit = isinstance(errors, list) and any(
            needle in str(error) for error in errors
        )
        checks.append(_check("error_contains", hit, needle))

    return _result(ev["_key"], checks)


def print_result(result: Mapping, *, machine: bool = True) -> None:
    label = "PASS" if result["pass"] else "FAIL"
    print(f"{label}  {result['eval']}  ({result['score']}/100)")
    for check in result["checks"]:
        check_label = "PASS" if check["pass"] else "FAIL"
        print(f"  {check_label} {check['name']}: {check['detail']}")
    if machine:
        print("RTDT_EVAL_RESULT_BEGIN")
        print(json.dumps(result, sort_keys=True))
        print("RTDT_EVAL_RESULT_END")


def print_aggregate(results: list[dict]) -> None:
    passed = sum(1 for result in results if result["pass"])
    aggregate = {
        "eval": "all",
        "pass": passed == len(results),
        "score": round(passed / len(results) * 100) if results else 0,
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    print(f"\nTOTAL: {passed}/{len(results)} passed")
    print("RTDT_EVAL_RESULT_BEGIN")
    print(json.dumps(aggregate, sort_keys=True))
    print("RTDT_EVAL_RESULT_END")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--list", action="store_true", help="list validator smoke fixtures")
    selection.add_argument("--eval", help="select one validator smoke by ID or full key")
    selection.add_argument("--all", action="store_true", help="run every validator smoke")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prompt", action="store_true", help="show the selected agent-facing prompt")
    mode.add_argument("--validate", action="store_true", help="run selected Kit-hosted validation")
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="validator timeout in seconds (default: 600)",
    )
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.eval and not (args.prompt or args.validate):
        parser.error("--eval requires --prompt or --validate")
    if (args.prompt or args.validate) and not (args.eval or args.all):
        parser.error("--prompt/--validate requires --eval, or --all --validate")
    if args.all and not args.validate:
        parser.error("--all requires --validate")
    if args.all and args.prompt:
        parser.error("--all does not support --prompt")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evals = load_evals()

    if args.list:
        for key, ev in evals.items():
            print(f"  {key:<32} {ev.get('description', '')}")
        return 0

    if args.eval:
        try:
            ev = evals[resolve_key(evals, args.eval)]
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
        if args.prompt:
            print(ev.get("prompt", "").strip())
            return 0
        result = run_validator(ev, args.timeout)
        print_result(result)
        return 0 if result["pass"] else 1

    if args.all:
        results = [run_validator(ev, args.timeout) for ev in evals.values()]
        for result in results:
            print_result(result, machine=False)
        print_aggregate(results)
        return 0 if all(result["pass"] for result in results) else 1

    print("Choose --list, --eval, or --all.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
