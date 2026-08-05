# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""Unit tests for the manifest expression evaluator (no Kit/USD dependency)."""

import omni.kit.test

from omni.rtwt.controller import expr


class TestExpr(omni.kit.test.AsyncTestCase):
    def test_eval_when(self):
        W = expr.eval_when
        self.assertTrue(W("", {}))
        self.assertTrue(W("vizMode in [Slice, Volume]", {"vizMode": "Slice"}))
        self.assertTrue(W("vizMode in [Slice, Volume]", {"vizMode": "Volume"}))
        self.assertFalse(W("vizMode in [Slice, Volume]", {"vizMode": "Streamlines"}))
        self.assertTrue(W("vizMode not in [Slice, Volume]", {"vizMode": "Streamlines"}))
        self.assertFalse(W("vizMode not in [Slice, Volume]", {"vizMode": "Slice"}))
        self.assertTrue(W("vizMode == Streamlines", {"vizMode": "Streamlines"}))
        self.assertFalse(W("vizMode == Streamlines", {"vizMode": "Flow"}))
        # The composed playback condition, all four corners.
        play = "(animatedStreaks && vizMode == Streamlines) || playAnimation"
        self.assertTrue(W(play, {"animatedStreaks": True, "vizMode": "Streamlines", "playAnimation": False}))
        self.assertFalse(W(play, {"animatedStreaks": False, "vizMode": "Streamlines", "playAnimation": False}))
        self.assertTrue(W(play, {"animatedStreaks": False, "vizMode": "Flow", "playAnimation": True}))
        self.assertFalse(W(play, {"animatedStreaks": True, "vizMode": "Flow", "playAnimation": False}))
        # Bare boolean knob.
        self.assertTrue(W("animatedStreaks", {"animatedStreaks": True}))
        self.assertFalse(W("animatedStreaks", {"animatedStreaks": False}))

    def test_eval_selection(self):
        S = expr.eval_selection
        self.assertEqual(S("{vizMode}_{vizField}", {"vizMode": "Slice", "vizField": "Pressure"}), "Slice_Pressure")
        self.assertEqual(
            S("{vizMode}_{vizField}", {"vizMode": "Volume", "vizField": "VelocityMagnitude"}),
            "Volume_VelocityMagnitude",
        )
        self.assertEqual(
            S(
                "{model.axis:choice-id}",
                {"model.axis:choice-id": "Aero"},
            ),
            "Aero",
        )

    def test_malformed_expr_is_safe(self):
        # A malformed expression must not raise; it evaluates False.
        with self.assertLogs(expr.logger, level="ERROR") as captured:
            self.assertFalse(expr.eval_when("vizMode in [", {"vizMode": "Slice"}))
        self.assertIn("when_expr evaluation failed", captured.output[0])

    def test_malformed_selection_placeholder_is_rejected(self):
        for selection_expr in ("{bad id}", "{unclosed", "extra}", "{}"):
            with self.subTest(selection_expr=selection_expr):
                with self.assertRaisesRegex(ValueError, "malformed selection_expr placeholder"):
                    expr.eval_selection(selection_expr, {"bad id": "ignored"})
