# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Workflow validation.

Checks a workflow manifest against the USD AppState schema(s) — and, when a stage is supplied,
against the live scene — and emits **actionable** errors, so customization is "edit -> validate ->
precise error" rather than edit-and-hope. Unknown axes surface as errors instead of being silently
dropped.

Two entry points:

* :func:`validate_workflow` — a plain function (no Kit command context required), so CI/tests and
  the controller can both call it.
* :class:`RtwtValidateWorkflowCommand` — a thin ``omni.kit.commands`` wrapper for interactive use
  that defaults to the configured manifest + current stage.

Static checks (always): every control has a unique web/runtime short key; schema_attr exists;
values/cache_values match the USD type/allowedTokens; ``cache_values`` only on
``role="inference"`` controls; binding kinds, populated fields, and knob cardinality have
implemented semantics; binding ``knobs``/``selection_expr`` refer to declared control ids; a named
``callback`` resolves (when the registry is provided). Stage checks (when a stage is given):
manifest and stage-authored binding target prims exist; ``Variant`` variant-sets exist (with a
geometry-recipe hint when absent); colormap readouts resolve to a well-formed colormap prim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from logging import getLogger

from pxr import OmniSci, OmniSciVtk, Usd

from .binding_contract import (
    ATTRIBUTE_BINDING_KINDS,
    BINDING_KIND_FIELDS,
    CALLBACK_BINDING_KINDS,
    SELECTION_PLACEHOLDER_RE,
    SINGLE_VALUE_BINDING_KINDS,
    SUPPORTED_BINDING_KINDS,
    TARGET_BINDING_KINDS,
    has_malformed_selection_placeholder,
)
from .control_registry import _gather_attr_facts
from .manifest import BindingSpec, WorkflowManifest

logger = getLogger(__name__)

_TOKEN_TYPES = ("token", "string")
_BINDING_DATA_FIELDS = (
    "targets",
    "variant_set",
    "selection_expr",
    "attribute",
    "material_on",
    "material_off",
    "callback",
    "params",
)
# Multiple-apply schema whose instances on the inference prim are the outputs the runtime requests.
_RESULT_FIELD_API = "RtwtResultFieldSelectionAPI"


@dataclass
class ValidationReport:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "workflow valid"
        parts = [f"{len(self.errors)} error(s)", f"{len(self.warnings)} warning(s)"]
        return "; ".join(parts)


def _check_value_against_tokens(report, cid, label, values, allowed):
    if not allowed:
        return
    for v in values:
        if str(v) not in allowed:
            report.error(
                f"control '{cid}': {label} value '{v}' is not in the schema allowedTokens "
                f"[{', '.join(allowed)}]"
            )


def _control_short_key(cid, ctrl) -> str:
    return ctrl.schema_attr.rsplit(":", 1)[-1] if ctrl.schema_attr else cid


def _check_control_key_mapping(report, manifest) -> None:
    """Ensure schema-derived web keys form a lossless map back to manifest control ids."""
    by_short: dict[str, list[tuple[str, str]]] = {}
    for cid, ctrl in manifest.controls.items():
        if not ctrl.schema_attr:
            report.error(
                f"control '{cid}': schema_attr is required — controls are stateful and must map "
                "to a typed attribute on the workflow app-state prim; use a readout or view for "
                "non-state UI data"
            )
        short = _control_short_key(cid, ctrl)
        by_short.setdefault(short, []).append((cid, ctrl.schema_attr))

    for short, controls in by_short.items():
        if len(controls) < 2:
            continue
        details = ", ".join(
            f"'{cid}' ({schema_attr or 'no schema_attr'})" for cid, schema_attr in controls
        )
        report.error(
            f"control short key '{short}' is ambiguous: {details} — schema_attr final namespace "
            "components are the web-API keys and must be unique"
        )


def _binding_label(owner: str, binding: BindingSpec) -> str:
    return f"{owner}: binding kind '{binding.kind or '<empty>'}'"


def _check_binding_semantics(
    report,
    owner: str,
    binding: BindingSpec,
    declared: set[str],
    callback_names: "set | None",
) -> None:
    """Reject declarations whose fields the executor would otherwise ignore."""
    label = _binding_label(owner, binding)
    if binding.kind not in SUPPORTED_BINDING_KINDS:
        supported = ", ".join(sorted(SUPPORTED_BINDING_KINDS))
        report.error(
            f"{label} is unsupported — choose one of [{supported}]; unknown kinds are not "
            "executed"
        )
        return

    consumes_one_knob = binding.kind in SINGLE_VALUE_BINDING_KINDS or (
        binding.kind == "Variant" and not binding.selection_expr
    )
    if consumes_one_knob and len(binding.knobs) != 1:
        selection_detail = (
            " when selection_expr is empty" if binding.kind == "Variant" else ""
        )
        report.error(
            f"{label} requires exactly one control id in knobs{selection_detail} — its runtime "
            "handler consumes that one value"
        )
    elif not binding.knobs:
        report.error(
            f"{label} requires at least one control id in knobs — bindings evaluate manifest "
            "control ids, not schema attribute names"
        )
    for knob in binding.knobs:
        if knob not in declared:
            report.error(f"{label} references undeclared control id '{knob}' in knobs")

    allowed_fields = BINDING_KIND_FIELDS[binding.kind]
    for field_name in _BINDING_DATA_FIELDS:
        value = getattr(binding, field_name)
        if value and field_name not in allowed_fields:
            report.error(
                f"{label} does not support '{field_name}' — the runtime handler ignores that "
                f"field; remove it or choose the binding kind that implements it"
            )

    if binding.kind in TARGET_BINDING_KINDS and not binding.targets:
        report.error(f"{label} requires at least one target prim path in targets")
    if binding.kind in ATTRIBUTE_BINDING_KINDS and not binding.attribute:
        report.error(f"{label} requires an attribute name")
    if binding.kind in CALLBACK_BINDING_KINDS and not binding.callback:
        report.error(f"{label} requires a registered callback name")
    if binding.kind == "Variant" and not binding.variant_set:
        report.error(f"{label} requires variant_set")
    if binding.kind == "Material" and not (binding.material_on or binding.material_off):
        report.error(f"{label} requires material_on, material_off, or both")
    if binding.kind in {"Playback", "ViewportScale"} and not binding.when_expr:
        report.error(
            f"{label} requires when_expr — without a condition it cannot derive an on/off state"
        )

    if has_malformed_selection_placeholder(binding.selection_expr):
        report.error(
            f"{label} selection_expr contains a malformed placeholder — use "
            "'{control-id}' with no whitespace and balanced braces"
        )

    for placeholder in SELECTION_PLACEHOLDER_RE.findall(binding.selection_expr):
        if placeholder not in declared:
            report.error(
                f"{label} selection_expr references undeclared control id '{placeholder}'"
            )
        elif placeholder not in binding.knobs:
            report.error(
                f"{label} selection_expr uses control id '{placeholder}' but knobs does not list "
                "it — list every state dependency explicitly"
            )

    if binding.callback and callback_names is not None and binding.callback not in callback_names:
        report.error(
            f"{label} callback '{binding.callback}' is not registered — ensure the "
            "specialization hooks extension is enabled"
        )


def validate_workflow(
    manifest: WorkflowManifest | None,
    schema_names: list[str],
    stage: "Usd.Stage | None" = None,
    callback_names: "set | None" = None,
) -> ValidationReport:
    """Validate *manifest* against the named AppState schemas (and *stage*, if provided)."""
    report = ValidationReport()
    if manifest is None:
        report.error("no workflow manifest loaded (missing/unset/invalid workflow_manifest)")
        return report

    facts = _gather_attr_facts(schema_names)
    valid_attrs = set(facts)
    declared = set(manifest.controls)
    _check_control_key_mapping(report, manifest)

    for cid, ctrl in manifest.controls.items():
        # schema_attr must exist on an applied AppState schema.
        if ctrl.schema_attr and ctrl.schema_attr not in valid_attrs:
            report.error(
                f"control '{cid}': schema_attr '{ctrl.schema_attr}' not found on the applied "
                f"AppState schema(s) {schema_names} — add the attribute to the specialization "
                f"schema.usda and regenerate"
            )

        # cache_values only make sense for inference-role controls.
        if ctrl.cache_values and ctrl.role != "inference":
            report.error(
                f"control '{cid}': cache_values requires role='inference' (got role='{ctrl.role}') "
                f"— only inference controls enter the cache key / pre-cache product"
            )

        # values / cache_values must match the schema allowedTokens for token-typed attrs.
        af = facts.get(ctrl.schema_attr)
        if af and af.type_name in _TOKEN_TYPES and af.allowed_tokens:
            _check_value_against_tokens(report, cid, "values", ctrl.values, af.allowed_tokens)
            _check_value_against_tokens(report, cid, "cache_values", ctrl.cache_values, af.allowed_tokens)

        # binding integrity.
        for b in ctrl.bindings:
            owner = f"control '{cid}'"
            _check_binding_semantics(report, owner, b, declared, callback_names)
            if stage is not None:
                _check_binding_targets(report, owner, b, stage)

    if stage is not None:
        _check_stage_bindings(report, declared, callback_names, stage)
        _check_outputs(report, manifest, stage)
        _check_colormap_readouts(report, manifest, stage)

    return report


def _check_binding_targets(report, owner, binding, stage) -> None:
    for target in binding.targets:
        prim = stage.GetPrimAtPath(target)
        if not prim or not prim.IsValid():
            report.error(f"{owner}: binding target prim '{target}' does not exist on the stage")
            continue
        if binding.kind == "Variant" and binding.variant_set:
            if not prim.GetVariantSets().HasVariantSet(binding.variant_set):
                report.error(
                    f"{owner}: variant set '{binding.variant_set}' not found on '{target}' "
                    f"— author the variant set on the geometry prim(s) (and any sibling CFD/visual "
                    f"prim), set the model tag, and re-align the CAE viz; see the geometry recipe"
                )


def _check_stage_bindings(report, declared, callback_names, stage) -> None:
    """Apply the same semantics checks to advanced USD-authored bindings."""
    try:
        from .binding_graph import _BINDING_API, _binding_from_instance

        binding_records = []
        prefix = f"{_BINDING_API}:"
        for prim in stage.Traverse():
            for schema in prim.GetAppliedSchemas():
                if schema.startswith(prefix):
                    instance = schema[len(prefix):]
                    binding_records.append(
                        (str(prim.GetPath()), instance, _binding_from_instance(prim, instance))
                    )
    except Exception as exc:  # noqa: BLE001 - validation should report, not crash, on stage access
        report.error(f"failed to inspect stage-authored control bindings: {exc}")
        return

    for prim_path, instance, binding in binding_records:
        owner = f"stage-authored binding '{instance}' on '{prim_path}'"
        _check_binding_semantics(report, owner, binding, declared, callback_names)
        _check_binding_targets(report, owner, binding, stage)


def _check_outputs(report, manifest, stage) -> None:
    # Declared outputs must resolve to fields on active OmniSci result datasets.
    for oid, out in manifest.outputs.items():
        target_prim = stage.GetPrimAtPath(out.target) if out.target else Usd.Prim()
        if not target_prim or not target_prim.IsValid():
            report.error(f"output '{oid}': target prim '{out.target}' does not exist on the stage")
            continue
        if not target_prim.IsA(OmniSci.Dataset):
            report.error(
                f"output '{oid}': target '{out.target}' must be an OmniSciDataset, "
                f"not '{target_prim.GetTypeName()}'"
            )
            continue
        if "RtwtInferenceResultsAPI" not in target_prim.GetAppliedSchemas():
            report.error(
                f"output '{oid}': target '{out.target}' must apply RtwtInferenceResultsAPI"
            )
        if not target_prim.HasAPI(OmniSciVtk.ImageDataAPI):
            report.error(
                f"output '{oid}': target '{out.target}' must provide a composed "
                "OmniSciVtkImageDataAPI grid contract (typically by referencing the "
                "inference domain)"
            )
        if not out.field_name:
            report.error(f"output '{oid}': field_name is required")
            continue
        if not target_prim.HasAPI(OmniSci.FieldAPI, out.field_name):
            report.error(
                f"output '{oid}': target '{out.target}' has no "
                f"OmniSciFieldAPI:{out.field_name}"
            )
        if not target_prim.HasAPI(OmniSci.ArrayAPI, out.field_name):
            report.error(
                f"output '{oid}': target '{out.target}' has no "
                f"OmniSciArrayAPI:{out.field_name}"
            )

    # Output drift guard. The inference prim's ``RtwtResultFieldSelectionAPI:<id>`` instances are
    # the outputs the runtime actually requests; the manifest ``[outputs]`` is the canonical
    # declaration. They must agree, or output customization silently drifts. Turn divergence into
    # an actionable error.
    inf_prim = stage.GetPrimAtPath(manifest.inference_prim)
    if not inf_prim or not inf_prim.IsValid():
        if manifest.outputs:
            report.warn(
                f"cannot cross-check outputs: inference prim '{manifest.inference_prim}' not found "
                f"on the stage"
            )
        return

    prefix = f"{_RESULT_FIELD_API}:"
    stage_ids = {s[len(prefix):] for s in inf_prim.GetAppliedSchemas() if s.startswith(prefix)}
    declared = set(manifest.outputs)
    for sid in sorted(stage_ids - declared):
        report.error(
            f"output '{sid}': requested on the stage via {prefix}{sid} but not declared in the "
            f"manifest [outputs] — add an [outputs.{sid}] entry (the manifest is the canonical "
            f"output registry)"
        )
    for did in sorted(declared - stage_ids):
        report.warn(
            f"output '{did}': declared in the manifest [outputs] but has no {prefix}{did} on "
            f"'{manifest.inference_prim}' — it will not be inference-requested"
        )

    # Cross-check each stage-authored wire-output mapping against its canonical
    # manifest dataset + field declaration.
    for oid in sorted(declared & stage_ids):
        out = manifest.outputs[oid]
        target_rel = inf_prim.GetRelationship(
            f"omni:rtwt:result_field_selection:{oid}:target"
        )
        stage_targets = [str(path) for path in target_rel.GetForwardedTargets()] if target_rel else []
        if stage_targets != [out.target]:
            report.error(
                f"output '{oid}': stage target {stage_targets} does not match manifest "
                f"target '{out.target}'"
            )
        field_attr = inf_prim.GetAttribute(
            f"omni:rtwt:result_field_selection:{oid}:fieldName"
        )
        stage_field_name = str(field_attr.Get() or "") if field_attr else ""
        if stage_field_name != out.field_name:
            report.error(
                f"output '{oid}': stage fieldName '{stage_field_name}' does not match "
                f"manifest field_name '{out.field_name}'"
            )


def _check_colormap_readouts(report, manifest, stage) -> None:
    for r in manifest.readouts:
        if r.type != "colormap" or not r.domain_source:
            continue
        # domain_source names a colormap prim under /World/Colormaps by convention.
        candidates = [r.domain_source, f"/World/Colormaps/{r.domain_source}"]
        prim = next((stage.GetPrimAtPath(p) for p in candidates if stage.GetPrimAtPath(p).IsValid()), None)
        if prim is None:
            report.error(
                f"readout '{r.key}': colormap domainSource '{r.domain_source}' resolves to no prim "
                f"(looked for {candidates})"
            )
            continue
        if "CaeVizColormapTextureAPI" not in prim.GetAppliedSchemas():
            report.warn(
                f"readout '{r.key}': colormap prim '{prim.GetPath()}' lacks CaeVizColormapTextureAPI"
            )


# ---------------------------------------------------------------------------
# Kit command wrapper (interactive / agentic use).
# ---------------------------------------------------------------------------
try:
    import omni.kit.commands

    class RtwtValidateWorkflowCommand(omni.kit.commands.Command):
        """Validate the configured workflow against the current stage; logs the report."""

        def __init__(self, manifest=None, schema_names=None, stage=None, callback_names=None):
            self._manifest = manifest
            self._schema_names = schema_names
            self._stage = stage
            self._callback_names = callback_names
            self._report = None

        def do(self) -> ValidationReport:
            from . import schema_settings
            from .manifest import ManifestLoader

            manifest = self._manifest or ManifestLoader.load_configured()
            schema_names = self._schema_names or schema_settings.app_state_api_schemas()
            stage = self._stage
            if stage is None:
                from omni.usd import get_context

                ctx = get_context()
                stage = ctx.get_stage() if ctx else None

            callback_names = self._callback_names
            if callback_names is None:
                try:
                    from .callbacks import CallbackRegistry

                    callback_names = CallbackRegistry.names()
                except Exception:  # noqa: BLE001 - callbacks module may not be loaded yet
                    callback_names = None

            report = validate_workflow(manifest, schema_names, stage, callback_names)
            self._report = report
            for e in report.errors:
                logger.error("workflow validation: %s", e)
            for w in report.warnings:
                logger.warning("workflow validation: %s", w)
            if report.ok:
                logger.info("workflow validation passed (%s)", report.summary())
            return report

        def undo(self) -> None:
            pass

except ImportError:  # omni.kit.commands unavailable (e.g. pure-CI import) — function API still works.
    RtwtValidateWorkflowCommand = None  # type: ignore
