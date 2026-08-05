# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Static contract for declarative controller bindings.

Keep this module free of Kit runtime imports.  Both the validator and the executor use this
vocabulary, which prevents a manifest from validating a binding kind that the runtime will later
ignore.
"""

import re


SUPPORTED_BINDING_KINDS = frozenset(
    {
        "Attribute",
        "Callback",
        "ColormapDomain",
        "Material",
        "Playback",
        "Relationship",
        "Transform",
        "Variant",
        "ViewportScale",
        "Visibility",
    }
)

# Fields that each handler actually consumes, in addition to ``kind``, ``knobs`` and
# ``when_expr``.  A populated field outside this set is almost certainly an authoring mistake:
# accepting it would imply behavior that the executor does not implement.
BINDING_KIND_FIELDS = {
    "Attribute": frozenset({"targets", "attribute"}),
    "Callback": frozenset({"callback"}),
    "ColormapDomain": frozenset({"callback"}),
    "Material": frozenset({"targets", "material_on", "material_off"}),
    "Playback": frozenset(),
    "Relationship": frozenset({"targets", "attribute"}),
    "Transform": frozenset({"params"}),
    "Variant": frozenset({"targets", "variant_set", "selection_expr"}),
    "ViewportScale": frozenset({"params"}),
    "Visibility": frozenset({"targets"}),
}

TARGET_BINDING_KINDS = frozenset(
    {"Attribute", "Material", "Relationship", "Variant", "Visibility"}
)
ATTRIBUTE_BINDING_KINDS = frozenset({"Attribute", "Relationship"})
CALLBACK_BINDING_KINDS = frozenset({"Callback", "ColormapDomain"})
SINGLE_VALUE_BINDING_KINDS = frozenset(
    {"Attribute", "Material", "Relationship", "Transform", "Visibility"}
)

# Manifest control ids used in selection placeholders. Keep validation and runtime substitution on
# this one expression so a placeholder cannot validate successfully and then remain unsubstituted.
SELECTION_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.:\-]*)\}")


def has_malformed_selection_placeholder(expression: str) -> bool:
    """Return whether *expression* contains a brace outside a valid control placeholder."""
    remainder = SELECTION_PLACEHOLDER_RE.sub("", expression)
    return "{" in remainder or "}" in remainder
