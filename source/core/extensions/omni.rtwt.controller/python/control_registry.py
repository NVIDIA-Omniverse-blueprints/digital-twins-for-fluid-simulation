# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""ControlRegistry — merge USD AppState schema facts with manifest control metadata.

The USD AppState schema is the typed-knob substrate (attribute types, ``allowedTokens``, and the
runtime default authored on the manifest's ``app_state_prim``). The manifest layers
role/widget/bounds/bindings on top. ``ControlRegistry`` resolves the two into one immutable
control set that ``get_state`` / ``set_state`` / ``get_control_manifest`` and the pre-cache walk
all read — the single place schema introspection happens.

A control has two deliberately distinct keys:

* its manifest ``id``, used by bindings and expressions; and
* its short key (the web-API wire key), derived from the last namespace component of
  ``schema_attr`` (e.g. ``omni:rtwt:app_state:spoiler`` -> ``spoiler``).

The registry owns the lossless mapping between those namespaces and rejects short-key collisions
instead of allowing a dictionary comprehension to silently discard a control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from logging import getLogger

from pxr import Usd

from .manifest import ControlSpec, WorkflowManifest

logger = getLogger(__name__)


@dataclass(frozen=True)
class _AttrFacts:
    type_name: str = ""
    allowed_tokens: tuple = ()
    display_name: str = ""


@dataclass(frozen=True)
class ResolvedControl:
    """A manifest ``ControlSpec`` resolved against its USD schema attribute facts."""

    spec: ControlSpec
    facts: _AttrFacts = field(default_factory=_AttrFacts)

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def role(self) -> str:
        return self.spec.role

    @property
    def schema_attr(self) -> str:
        return self.spec.schema_attr

    @property
    def short_key(self) -> str:
        """Web-API wire key: last namespace component of the schema attr, else the control id."""
        if self.spec.schema_attr:
            return self.spec.schema_attr.rsplit(":", 1)[-1]
        return self.spec.id

    @property
    def usd_type(self) -> str:
        return self.facts.type_name

    @property
    def allowed_tokens(self) -> tuple:
        return self.facts.allowed_tokens


def _gather_attr_facts(schema_names: list[str]) -> dict:
    """Return ``full_attr_name -> _AttrFacts`` for every attribute on the named applied schemas.

    Uses ``Usd.PrimDefinition.GetPropertyMetadata`` (stable across USD versions) and skips
    relationships. Defensive: any introspection failure degrades to empty facts rather than
    raising, so a control still resolves (the validator reports type gaps separately).
    """
    facts: dict = {}
    registry = Usd.SchemaRegistry()
    for api in schema_names:
        defn = registry.FindAppliedAPIPrimDefinition(api)
        if not defn:
            logger.warning("ControlRegistry: applied API schema not found: %s", api)
            continue
        for prop in defn.GetPropertyNames():
            # Skip properties that aren't attributes (e.g. the ROI relationship).
            if not defn.GetAttributeDefinition(prop):
                continue
            type_name = allowed = display = None
            try:
                type_name = defn.GetPropertyMetadata(prop, "typeName")
                allowed = defn.GetPropertyMetadata(prop, "allowedTokens")
                display = defn.GetPropertyMetadata(prop, "displayName")
            except Exception as exc:  # noqa: BLE001 - introspection is best-effort
                logger.debug("ControlRegistry: metadata read failed for %s: %s", prop, exc)
            facts[prop] = _AttrFacts(
                type_name=str(type_name) if type_name else "",
                allowed_tokens=tuple(str(t) for t in allowed) if allowed else (),
                display_name=str(display) if display else "",
            )
    return facts


class ControlRegistry:
    """Immutable, ordered set of resolved controls for a workflow."""

    def __init__(self, controls: list[ResolvedControl], manifest: WorkflowManifest):
        self._controls = list(controls)
        self._manifest = manifest
        self._by_id = {c.id: c for c in self._controls}
        self._by_short: dict[str, ResolvedControl] = {}
        for control in self._controls:
            previous = self._by_short.get(control.short_key)
            if previous is not None:
                raise ValueError(
                    f"ambiguous control short key '{control.short_key}': controls "
                    f"'{previous.id}' ({previous.schema_attr or 'no schema_attr'}) and "
                    f"'{control.id}' ({control.schema_attr or 'no schema_attr'}) map to the same "
                    "web/runtime key; give each schema_attr a unique final namespace component"
                )
            self._by_short[control.short_key] = control

    @classmethod
    def build(cls, manifest: WorkflowManifest, schema_names: list[str]) -> "ControlRegistry":
        facts = _gather_attr_facts(schema_names)
        resolved = [
            ResolvedControl(spec=spec, facts=facts.get(spec.schema_attr, _AttrFacts()))
            for spec in manifest.controls.values()
        ]
        return cls(resolved, manifest)

    @property
    def manifest(self) -> WorkflowManifest:
        return self._manifest

    def controls(self) -> list[ResolvedControl]:
        return list(self._controls)

    def get(self, control_id: str) -> ResolvedControl | None:
        return self._by_id.get(control_id)

    def get_by_short_key(self, short_key: str) -> ResolvedControl | None:
        return self._by_short.get(short_key)

    def inference_controls(self) -> list[ResolvedControl]:
        """Controls whose values key the cache / drive the pre-cache product (``role == 'inference'``)."""
        return [c for c in self._controls if c.role == "inference"]

    def short_to_full(self) -> dict:
        """Web-API short key -> full schema attribute name (only controls that bind a schema attr)."""
        return {c.short_key: c.schema_attr for c in self._controls if c.schema_attr}

    def full_to_short(self) -> dict:
        return {c.schema_attr: c.short_key for c in self._controls if c.schema_attr}

    def id_to_full(self) -> dict:
        """Manifest control id -> full schema attribute name for binding-state construction."""
        return {c.id: c.schema_attr for c in self._controls if c.schema_attr}

    def id_to_short(self) -> dict:
        return {c.id: c.short_key for c in self._controls}

    def short_to_id(self) -> dict:
        return {c.short_key: c.id for c in self._controls}


# Cached singleton registry for the configured workflow (manifest + schema facts). The
# workflow_manifest / app_state_api_schemas settings are fixed at app-config time, so it is built
# once and reused by both the AppState operator and the web API. Returns None when no manifest is
# configured (core-only / no workflow).
_WORKFLOW_REGISTRY = None


def get_workflow_registry() -> "ControlRegistry | None":
    global _WORKFLOW_REGISTRY
    if _WORKFLOW_REGISTRY is None:
        from . import schema_settings
        from .manifest import ManifestLoader

        manifest = ManifestLoader.load_configured()
        if manifest is None:
            return None
        _WORKFLOW_REGISTRY = ControlRegistry.build(manifest, schema_settings.app_state_api_schemas())
    return _WORKFLOW_REGISTRY
