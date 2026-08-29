"""Who decides the next action.

A Protocol rather than a concrete class, because the agent's whole test suite
depends on being able to script decisions. ``VisionPolicy`` is the production
implementation; tests pass a policy that returns a fixed list, so no test needs
ollama, a monkeypatch, or a model on disk.

Verified live on 2026-08-29 against ``qwen2.5vl:7b``: constrained decoding holds
(3.6 s per decision with a screenshot attached), and the model declines elements
marked OFF LIMITS. It also showed the failure this module has to absorb — asked
without an image it returned ``{"action": "click"}`` with no index at all. A
policy that raised there would end the run; instead the action comes back
malformed, the guard refuses it, and the refusal is fed back as context.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

from app.discovery.browse.guard import is_credential_field, is_login_control
from app.discovery.browse.observe import render_observation
from app.discovery.browse.prompts import SYSTEM_PROMPT
from app.discovery.browse.types import ActionKind, BrowseAction, Observation
from app.services.llm_json import generate_json
from app.utils.logger import logger

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thought": {"type": "string", "maxLength": 300},
        "action": {
            "type": "string",
            "enum": [kind.value for kind in ActionKind],
        },
        "index": {"type": ["integer", "null"]},
        "x": {"type": ["integer", "null"]},
        "y": {"type": ["integer", "null"]},
        "text": {"type": ["string", "null"], "maxLength": 200},
        "url": {"type": ["string", "null"], "maxLength": 400},
        "direction": {"type": ["string", "null"]},
    },
    "required": ["thought", "action"],
}


class BrowsePolicy(Protocol):
    """Decides one action from one observation."""

    async def decide(self, observation: Observation, image: bytes) -> BrowseAction | None:
        """Return the next action, or ``None`` when no usable answer came back."""
        ...


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):  # bool is an int; never a coordinate
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def parse_action(payload: dict[str, Any] | None) -> BrowseAction | None:
    """Turn a model reply into an action, or ``None`` if it is not one.

    Deliberately permissive about *fields* and strict about the *verb*: a
    missing index is a refusable action the agent can learn from, while an
    unknown verb is not an action at all.
    """
    if not isinstance(payload, dict):
        return None
    raw_kind = str(payload.get("action") or "").strip().lower()
    try:
        kind = ActionKind(raw_kind)
    except ValueError:
        return None

    direction = str(payload.get("direction") or "down").strip().lower()
    return BrowseAction(
        kind=kind,
        index=_as_int(payload.get("index")),
        x=_as_int(payload.get("x")),
        y=_as_int(payload.get("y")),
        text=str(payload.get("text") or ""),
        url=str(payload.get("url") or "").strip(),
        direction="up" if direction.startswith("up") else "down",
        thought=str(payload.get("thought") or "").strip()[:300],
        by="model",
    )


class VisionPolicy:
    """Asks the local multimodal model, under a constrained JSON grammar."""

    def __init__(
        self,
        *,
        model: str,
        timeout_s: float = 45.0,
        keep_alive: str = "30s",
        temperature: float = 0.1,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._keep_alive = keep_alive
        """Short on purpose: this model and the narrative model cannot both be
        resident in 8 GB, so it must let go promptly once the phase is over."""

        self._temperature = temperature
        self.calls = 0

    async def decide(self, observation: Observation, image: bytes) -> BrowseAction | None:
        self.calls += 1
        prompt = render_observation(observation, off_limits=_off_limits(observation))
        images = [base64.b64encode(image).decode("utf-8")] if image else None

        payload = await generate_json(
            prompt,
            ACTION_SCHEMA,
            model=self._model,
            timeout_s=self._timeout_s,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            max_output_tokens=400,
            images=images,
            keep_alive=self._keep_alive,
        )
        action = parse_action(payload)
        if action is None:
            logger.log_warning(
                f"Browse policy returned nothing usable from '{self._model}'",
                broadcast=False,
            )
        return action


def _off_limits(observation: Observation) -> list[int]:
    """Indices the guard would refuse, so the observation can say so first.

    Asking the guard rather than restating its patterns: two copies of "what
    counts as a login control" would drift, and the copy that drifted would be
    the one the model reads.
    """
    return [
        element.index for element in observation.elements if is_login_control(element) or is_credential_field(element)
    ]
