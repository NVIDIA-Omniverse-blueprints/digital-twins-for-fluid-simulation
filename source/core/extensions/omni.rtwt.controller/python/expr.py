# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
#  its affiliates is strictly prohibited.

"""A tiny, safe expression evaluator for manifest ``when_expr`` / ``selection_expr``.

Deliberately minimal — **no ``eval``** — over trusted manifest config. Grammar::

    or_expr  := and_expr ('||' and_expr)*
    and_expr := cmp ('&&' cmp)*
    cmp      := primary ( '==' primary | 'in' list | 'not' 'in' list )?
    primary  := '(' or_expr ')' | list | WORD
    list     := '[' WORD (',' WORD)* ']'

A ``WORD`` resolves to its control-state value when it names a control, else to the bare token
string (so ``vizMode == Streamlines`` compares the *value* of ``vizMode`` against the literal
token ``Streamlines``). Comparisons are string-wise; a bare ``WORD`` / parenthesized result is
truthy-tested (so a boolean knob like ``animatedStreaks`` is usable alone).

``eval_selection`` substitutes ``{knob}`` placeholders with their control-state values (used to
compose variant names such as ``"Slice_Pressure"`` from ``vizMode`` + ``vizField``).
"""

from __future__ import annotations

import re
from logging import getLogger

from .binding_contract import (
    SELECTION_PLACEHOLDER_RE,
    has_malformed_selection_placeholder,
)

logger = getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:\-]+")
_OPS = ("&&", "||", "==")
_PUNCT = set("()[],")


def eval_selection(expr: str, state: dict) -> str:
    """Substitute ``{knob}`` placeholders in *expr* with their (stringified) control values."""
    if has_malformed_selection_placeholder(expr):
        raise ValueError(f"malformed selection_expr placeholder in {expr!r}")
    return SELECTION_PLACEHOLDER_RE.sub(lambda m: str(state.get(m.group(1), "")), expr)


def eval_when(expr: str, state: dict) -> bool:
    """Evaluate a boolean ``when_expr`` against *state*. Returns True for an empty expression."""
    if not expr or not expr.strip():
        return True
    try:
        tokens = _tokenize(expr)
        parser = _Parser(tokens, state)
        result = parser.parse_or()
        if parser.peek() is not None:
            raise ValueError(f"unexpected trailing token '{parser.peek()}'")
        return bool(result)
    except Exception as exc:  # noqa: BLE001 - a malformed expr must not crash the engine
        logger.error("when_expr evaluation failed for %r: %s", expr, exc)
        return False


def _tokenize(s: str) -> list:
    tokens: list = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if s[i : i + 2] in _OPS:
            tokens.append(s[i : i + 2])
            i += 2
            continue
        if c in _PUNCT:
            tokens.append(c)
            i += 1
            continue
        m = _TOKEN_RE.match(s, i)
        if not m:
            raise ValueError(f"unexpected character {c!r}")
        tokens.append(m.group(0))
        i = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list, state: dict):
        self._t = tokens
        self._i = 0
        self._state = state

    def peek(self):
        return self._t[self._i] if self._i < len(self._t) else None

    def _next(self):
        tok = self._t[self._i]
        self._i += 1
        return tok

    def _expect(self, tok):
        if self.peek() != tok:
            raise ValueError(f"expected '{tok}', got '{self.peek()}'")
        return self._next()

    def parse_or(self):
        val = self.parse_and()
        while self.peek() == "||":
            self._next()
            rhs = self.parse_and()
            val = bool(val) or bool(rhs)
        return val

    def parse_and(self):
        val = self.parse_cmp()
        while self.peek() == "&&":
            self._next()
            rhs = self.parse_cmp()
            val = bool(val) and bool(rhs)
        return val

    def parse_cmp(self):
        left = self.parse_primary()
        op = self.peek()
        if op == "==":
            self._next()
            right = self.parse_primary()
            return str(left) == str(right)
        if op == "in":
            self._next()
            return str(left) in [str(x) for x in self._parse_list()]
        if op == "not":
            self._next()
            self._expect("in")
            return str(left) not in [str(x) for x in self._parse_list()]
        return bool(left)

    def parse_primary(self):
        tok = self.peek()
        if tok == "(":
            self._next()
            val = self.parse_or()
            self._expect(")")
            return val
        if tok == "[":
            return self._parse_list()
        if tok is None or tok in _PUNCT or tok in _OPS or tok == "in" or tok == "not":
            raise ValueError(f"unexpected token '{tok}'")
        return self._resolve(self._next())

    def _parse_list(self):
        self._expect("[")
        items = []
        if self.peek() != "]":
            items.append(self._resolve(self._next()))
            while self.peek() == ",":
                self._next()
                items.append(self._resolve(self._next()))
        self._expect("]")
        return items

    def _resolve(self, word):
        # A word that names a control resolves to its value; otherwise it is a bare token literal.
        return self._state[word] if word in self._state else word
