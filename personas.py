"""Persona slot model + validation for the public trading-floor demo.

A "slot" is one of the 4 trader seats on the floor. By default it's filled
with one of the canonical personas (Warren/George/Ray/Cathie). Visitors
can flip a slot to `is_custom=True` and supply their own name + strategy
+ model.

Phase 2 layer; Phase 3 (UI) consumes these helpers to render the Setup
screen and call `start_session()` when the visitor clicks Launch.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from accounts import Account, DEFAULT_INITIAL_BALANCE
from reset import (
    DEFAULT_STRATEGIES,
    waren_strategy,
    george_strategy,
    ray_strategy,
    cathie_strategy,
)

MIN_BALANCE = 1_000.0
MAX_BALANCE = 10_000_000.0
NAME_RE = re.compile(r"^[A-Za-z0-9 \-_]{1,30}$")
SOFT_MIN_STRATEGY_CHARS = 50


# (Display label, OpenAI-Agents model id, env var that gates availability).
# `None` env var means the model is available unconditionally (defaults to
# the parent OpenAI key, which we require everywhere).
_MODEL_CATALOG: list[tuple[str, str, str | None]] = [
    ("GPT 4o mini", "gpt-4o-mini", None),
    ("GPT 4.1 Mini", "gpt-4.1-mini", None),
    ("GPT 4o", "gpt-4o", None),
    ("DeepSeek V3", "deepseek-chat", "DEEPSEEK_API_KEY"),
    ("Gemini 2.5 Flash", "gemini-2.5-flash-preview-04-17", "GOOGLE_API_KEY"),
    ("Grok 3 Mini", "grok-3-mini-beta", "GROK_API_KEY"),
]


def available_models() -> list[tuple[str, str]]:
    """Return (label, model_id) for every model whose provider key is set."""
    out: list[tuple[str, str]] = []
    for label, model_id, env_key in _MODEL_CATALOG:
        if env_key is None or os.getenv(env_key):
            out.append((label, model_id))
    return out


def default_model() -> str:
    return "gpt-4o-mini"


@dataclass
class PersonaSlot:
    name: str
    lastname: str
    model_name: str
    strategy: str
    is_custom: bool = False

    @classmethod
    def default(cls, name: str, lastname: str, strategy: str, model_name: str | None = None) -> "PersonaSlot":
        return cls(
            name=name,
            lastname=lastname,
            model_name=model_name or default_model(),
            strategy=strategy.strip(),
            is_custom=False,
        )


# The factory roster — keep this in sync with reset.DEFAULT_STRATEGIES.
def default_slots() -> list[PersonaSlot]:
    return [
        PersonaSlot.default("Warren", "Patience", waren_strategy),
        PersonaSlot.default("George", "Bold", george_strategy),
        PersonaSlot.default("Ray", "Systematic", ray_strategy),
        PersonaSlot.default("Cathie", "Crypto", cathie_strategy),
    ]


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_slots(slots: list[PersonaSlot], initial_balance: float) -> ValidationResult:
    """Return a ValidationResult; `errors` blocks launch, `warnings` doesn't."""
    result = ValidationResult()
    allowed_model_ids = {model_id for _, model_id in available_models()}

    if len(slots) != 4:
        result.errors.append("Need exactly 4 trader slots.")

    if not (MIN_BALANCE <= initial_balance <= MAX_BALANCE):
        result.errors.append(
            f"Starting balance must be between ${MIN_BALANCE:,.0f} and ${MAX_BALANCE:,.0f}."
        )

    seen_keys: set[str] = set()
    for idx, slot in enumerate(slots, start=1):
        label = f"Slot {idx}"
        name = (slot.name or "").strip()
        lastname = (slot.lastname or "").strip()
        strategy = (slot.strategy or "").strip()
        model = (slot.model_name or "").strip()

        if not name:
            result.errors.append(f"{label}: trader name is required.")
        elif not NAME_RE.match(name):
            result.errors.append(
                f"{label}: name must be 1–30 chars, letters/digits/space/hyphen/underscore only."
            )
        else:
            key = name.lower()
            if key in seen_keys:
                result.errors.append(f"{label}: duplicate trader name '{name}'.")
            seen_keys.add(key)

        if not lastname:
            result.errors.append(f"{label}: lastname / tagline is required.")

        if not strategy:
            result.errors.append(f"{label}: strategy is required.")
        elif slot.is_custom and len(strategy) < SOFT_MIN_STRATEGY_CHARS:
            result.warnings.append(
                f"{label}: custom strategy is short ({len(strategy)} chars); "
                f"≥{SOFT_MIN_STRATEGY_CHARS} chars gives the agent more to work with."
            )

        if not model:
            result.errors.append(f"{label}: model is required.")
        elif allowed_model_ids and model not in allowed_model_ids:
            result.errors.append(
                f"{label}: model '{model}' is not available (provider key not configured)."
            )

    return result


def start_session(
    session_id: str,
    slots: list[PersonaSlot],
    initial_balance: float = DEFAULT_INITIAL_BALANCE,
) -> None:
    """Reset every per-session account row to match the configured slots."""
    for slot in slots:
        account = Account.get(slot.name, session_id, initial_balance)
        account.reset(slot.strategy, initial_balance)


__all__ = [
    "PersonaSlot",
    "ValidationResult",
    "MIN_BALANCE",
    "MAX_BALANCE",
    "SOFT_MIN_STRATEGY_CHARS",
    "available_models",
    "default_model",
    "default_slots",
    "validate_slots",
    "start_session",
]
