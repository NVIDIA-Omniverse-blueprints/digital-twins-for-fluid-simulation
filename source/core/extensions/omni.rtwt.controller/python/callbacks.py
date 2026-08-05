# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Specialization callback registry.

A binding of kind ``Callback`` (or ``ColormapDomain``) names a specialization *adapter* the core
engine invokes to compute derived writes that core cannot express declaratively (e.g. the
automotive-aero dynamic-pressure colormap physics). The adapter contract is deliberately tiny:

    fn(control_state: dict) -> [(prim_path: str, attribute: str, value), ...]

It is a **pure function** — it performs no Kit calls and does no ``Sdf.ChangeBlock`` reasoning.
The engine applies the returned writes and decides change-block placement. This keeps any
workflow-specific derived effect entirely outside ``source/core/``: authoring one is "write a
pure function returning writes + reference it by name from the manifest."

Adapters register here from a specialization extension's ``on_startup`` (see
``omni.rtwt.auto_aero.hooks``). Core ships an empty registry.
"""

from logging import getLogger
from typing import Callable

logger = getLogger(__name__)

# (prim_path, attribute, value) write tuples.
CallbackFn = Callable[[dict], list]


class CallbackRegistry:
    """Process-global name -> adapter registry. Names are workflow-scoped (e.g.
    ``"auto_aero.dynamic_pressure"``)."""

    _fns: dict = {}

    @classmethod
    def register(cls, name: str, fn: CallbackFn) -> None:
        if name in cls._fns and cls._fns[name] is not fn:
            logger.warning("CallbackRegistry: overriding already-registered callback '%s'", name)
        cls._fns[name] = fn
        logger.info("CallbackRegistry: registered callback '%s'", name)

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._fns.pop(name, None)

    @classmethod
    def get(cls, name: str) -> "CallbackFn | None":
        return cls._fns.get(name)

    @classmethod
    def names(cls) -> set:
        return set(cls._fns)
