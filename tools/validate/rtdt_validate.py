# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Validate a workflow manifest, run inside the app via ``--exec``.

This is launched by ``rtdt-validate.sh`` (``repo.sh launch -n <app> -- --exec``). Running inside
the app means USD, the rtwt extensions, and the AppState schemas are already loaded — so this just
calls the controller's own ``validate_workflow`` and reports the result. It uses only what the app
already ships; no extra dependencies.

Inputs come from the environment so the wrapper can pass them through ``--exec``:

* ``RTDT_VALIDATE_MANIFEST`` — manifest to check; defaults to the app's configured manifest.
* ``RTDT_VALIDATE_SCHEMAS``  — space-separated AppState API names; defaults to the configured set.
* ``RTDT_VALIDATE_STAGE``    — optional stage .usda for binding/output/variant-set checks.
* ``RTDT_VALIDATE_CALLBACKS``— optional binding-callback names; defaults to the registered set.
* ``RTDT_VALIDATE_FORMAT``   — ``text`` (default) or ``json``.

The report is printed between ``RTDT_VALIDATE_BEGIN``/``END`` markers, followed by a
``RTDT_VALIDATE_STATUS ok|errors`` line the wrapper reads for its exit code.
"""

import json
import os
import sys

import omni.kit.app

FORMAT = os.environ.get("RTDT_VALIDATE_FORMAT", "text")


def _emit(report=None, fatal=None):
    lines = ["RTDT_VALIDATE_BEGIN"]
    if fatal is not None:
        lines.append(json.dumps({"ok": False, "error": fatal}) if FORMAT == "json" else f"ERROR: {fatal}")
        status = "errors"
    elif FORMAT == "json":
        lines.append(json.dumps({"ok": report.ok, "summary": report.summary(),
                                 "errors": report.errors, "warnings": report.warnings}))
        status = "ok" if report.ok else "errors"
    else:
        lines += [f"ERROR: {e}" for e in report.errors]
        lines += [f"WARNING: {w}" for w in report.warnings]
        lines.append(report.summary())
        status = "ok" if report.ok else "errors"
    lines += ["RTDT_VALIDATE_END", f"RTDT_VALIDATE_STATUS {status}"]
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
    return status


def _run():
    from omni.rtwt.controller import schema_settings, validator
    from omni.rtwt.controller.manifest import ManifestLoader

    manifest_path = os.environ.get("RTDT_VALIDATE_MANIFEST") or ""
    manifest = ManifestLoader.load(manifest_path) if manifest_path else ManifestLoader.load_configured()

    schemas_env = os.environ.get("RTDT_VALIDATE_SCHEMAS") or ""
    schema_names = schemas_env.split() if schemas_env else schema_settings.app_state_api_schemas()

    stage = None
    stage_path = os.environ.get("RTDT_VALIDATE_STAGE") or ""
    if stage_path:
        from pxr import Usd

        stage = Usd.Stage.Open(stage_path)

    callbacks_env = os.environ.get("RTDT_VALIDATE_CALLBACKS")
    if callbacks_env is not None:
        callback_names = set(callbacks_env.split())
    else:
        try:
            from omni.rtwt.controller.callbacks import CallbackRegistry

            callback_names = CallbackRegistry.names()
        except Exception:  # noqa: BLE001 - hooks extension may not be enabled
            callback_names = None

    return validator.validate_workflow(manifest, schema_names, stage, callback_names)


try:
    report = _run()
    code = 0 if report.ok else 1
    _emit(report=report)
except Exception as exc:  # noqa: BLE001 - report any failure rather than a bare Kit traceback
    import traceback

    _emit(fatal=f"{exc!r}\n{traceback.format_exc()}")
    code = 2

try:
    omni.kit.app.get_app().post_quit()
except Exception:  # noqa: BLE001
    pass
os._exit(code)
